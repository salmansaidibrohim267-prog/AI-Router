"""Tests for the deployment pipeline subsystem (Stage 10.10)."""

import pytest

from app.deploy import (
    DeployConfig,
    DeploymentPipeline,
    DeploymentVerifier,
    GateResult,
    GitOpsError,
    GitOpsManifest,
    GitOpsValidator,
    QualityGate,
    QualityGateError,
    QualityGateRunner,
    RollbackTestError,
    RollbackTester,
    SmokeResult,
    SmokeStep,
    SmokeTestError,
    SmokeTester,
    VerificationError,
    create_deployment_pipeline,
)


def healthy_probe(version="1.0.0-rc.1", latency_ms=10.0):
    def probe():
        return {"ok": True, "latency_ms": latency_ms, "version": version, "detail": "healthy"}

    return probe


class TestDeployConfig:
    def test_defaults(self):
        config = DeployConfig()
        assert config.target_version == "1.0.0-rc.1"
        assert config.environment == "staging"
        assert config.min_coverage == 95.0
        assert config.max_latency_ms == 500.0
        assert config.require_signatures is True
        assert config.auto_rollback is True

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("DEP_ENVIRONMENT", "production")
        monkeypatch.setenv("DEP_MIN_COVERAGE", "90")
        config = DeployConfig.from_env()
        assert config.environment == "production"
        assert config.min_coverage == 90.0

    def test_unknown_kwarg_raises(self):
        with pytest.raises(TypeError):
            DeployConfig(bogus=1)

    def test_as_dict(self):
        assert DeployConfig().as_dict()["target_version"] == "1.0.0-rc.1"


class TestQualityGate:
    def test_evaluate_operators(self):
        gate = QualityGate("x", threshold=5, operator=">=")
        assert gate.evaluate(5.0) is True
        assert gate.evaluate(4.9) is False
        assert QualityGate("x", threshold=5, operator="<=").evaluate(5.0) is True
        assert QualityGate("x", threshold=5, operator=">").evaluate(6.0) is True
        assert QualityGate("x", threshold=5, operator="<").evaluate(4.0) is True
        assert QualityGate("x", threshold=5, operator="==").evaluate(5.0) is True

    def test_unknown_operator_raises(self):
        with pytest.raises(QualityGateError):
            QualityGate("x", operator="<>").evaluate(1.0)

    def test_to_dict(self):
        data = QualityGate("x").to_dict()
        assert data["name"] == "x"
        assert data["operator"] == ">="


class TestQualityGateRunner:
    def setup_method(self):
        self.runner = QualityGateRunner()

    def test_run_all_passing(self):
        self.runner.register("coverage", lambda: {"passed": True, "value": 96.0})
        self.runner.register("p95_latency_ms", lambda: {"passed": True, "value": 100.0})
        self.runner.register("error_rate", lambda: {"passed": True, "value": 0.5})
        self.runner.register("tests_passed", lambda: {"passed": True, "value": 1})
        results = self.runner.run_and_raise()
        assert len(results) == 4
        assert all(r.passed for r in results)

    def test_run_failure_raises(self):
        self.runner.register("coverage", lambda: {"passed": True, "value": 96.0})
        self.runner.register("p95_latency_ms", lambda: {"passed": False, "value": 700.0})
        self.runner.register("error_rate", lambda: {"passed": True, "value": 0.5})
        self.runner.register("tests_passed", lambda: {"passed": True, "value": 1})
        with pytest.raises(QualityGateError) as exc:
            self.runner.run_and_raise()
        assert "p95_latency_ms" in str(exc.value)

    def test_missing_check_fails_gate(self):
        results = self.runner.run([QualityGate("coverage")])
        assert results[0].passed is False
        assert results[0].detail == "no check registered"

    def test_run_uses_configured_thresholds(self):
        config = DeployConfig(min_coverage=90.0)
        runner = QualityGateRunner(config)
        runner.register("coverage", lambda: {"value": 91.0})
        results = runner.run()
        coverage = [r for r in results if r.gate.name == "coverage"][0]
        assert coverage.passed is True

    def test_summary(self):
        self.runner.register("coverage", lambda: {"passed": True, "value": 96.0})
        results = self.runner.run([QualityGate("coverage")])
        summary = self.runner.summary(results)
        assert summary["total"] == 1
        assert summary["passed"] == 1


class TestSmokeTester:
    def test_run_all_steps(self):
        tester = SmokeTester()
        tester.register_probe("health", healthy_probe())
        tester.register_probe("readiness", healthy_probe())
        tester.register_probe("chat", healthy_probe())
        results = tester.run()
        assert len(results) == 3
        assert all(r.passed for r in results)

    def test_missing_probe_fails_step(self):
        tester = SmokeTester()
        results = tester.run()
        assert all(not r.passed for r in results)
        assert results[0].detail == "no probe registered"

    def test_failure_raises(self):
        tester = SmokeTester()
        tester.register_probe("health", lambda: {"ok": False, "detail": "down", "latency_ms": 0})
        with pytest.raises(SmokeTestError):
            tester.run_and_raise()

    def test_custom_steps(self):
        tester = SmokeTester()
        tester.set_steps([SmokeStep("health", "health")])
        tester.register_probe("health", healthy_probe())
        assert len(tester.run()) == 1

    def test_timeout_expires(self):
        tester = SmokeTester()
        tester.set_steps([SmokeStep("a"), SmokeStep("b")])
        tester.register_probe("a", healthy_probe())
        results = tester.run(timeout_seconds=0)
        assert results[1].passed is False

    def test_summary(self):
        tester = SmokeTester()
        tester.register_probe("health", healthy_probe())
        results = tester.run()
        summary = tester.summary(results)
        assert summary["total"] == 3
        assert summary["failed"] == 2

    def test_result_fields(self):
        tester = SmokeTester()
        tester.set_steps([SmokeStep("health")])
        tester.register_probe("health", healthy_probe(latency_ms=5.0))
        results = tester.run()
        assert results[0].latency_ms == 5.0
        assert results[0].to_dict()["passed"] is True


class TestRollbackTester:
    def test_successful_rollback(self):
        current = {"version": "1.0.0-rc.1"}

        def deployer(version):
            current["version"] = version
            return True

        tester = RollbackTester()
        tester.register_deployer(deployer)
        tester.register_probe(lambda: {"ok": True, "latency_ms": 1.0, "version": current["version"], "detail": ""})
        result = tester.run("1.0.1-rc.1", "1.0.0")
        assert result["recovered"] is True
        assert result["rolled_back_to"] == "1.0.0"

    def test_requires_deployer_and_probe(self):
        with pytest.raises(RollbackTestError):
            RollbackTester().run("2.0.0", "1.0.0")

    def test_deploy_failure(self):
        def deployer(version):
            return False

        tester = RollbackTester()
        tester.register_deployer(deployer)
        tester.register_probe(healthy_probe())
        with pytest.raises(RollbackTestError):
            tester.run("2.0.0", "1.0.0")

    def test_new_version_unhealthy(self):
        def deployer(version):
            return True

        tester = RollbackTester()
        tester.register_deployer(deployer)
        tester.register_probe(lambda: {"ok": False, "detail": "down", "latency_ms": 0, "version": ""})
        with pytest.raises(RollbackTestError):
            tester.run("2.0.0", "1.0.0")

    def test_rollback_failure(self):
        calls = []

        def deployer(version):
            calls.append(version)
            return version == "2.0.0"

        tester = RollbackTester()
        tester.register_deployer(deployer)
        tester.register_probe(healthy_probe(version="2.0.0"))
        with pytest.raises(RollbackTestError):
            tester.run("2.0.0", "1.0.0")

    def test_version_mismatch_detected(self):
        def deployer(version):
            return True

        tester = RollbackTester()
        tester.register_deployer(deployer)
        tester.register_probe(healthy_probe(version="9.9.9"))
        with pytest.raises(RollbackTestError):
            tester.run("2.0.0", "1.0.0")

    def test_version_ignored_when_absent(self):
        def deployer(version):
            return True

        tester = RollbackTester()
        tester.register_deployer(deployer)
        tester.register_probe(lambda: {"ok": True, "latency_ms": 1.0, "version": "", "detail": ""})
        result = tester.run("2.0.0", "1.0.0")
        assert result["recovered"] is True


class TestDeploymentVerifier:
    def test_verify_passes(self):
        verifier = DeploymentVerifier()
        verifier.register_probe(healthy_probe())
        result = verifier.verify("1.0.0-rc.1")
        assert result["passed"] is True
        assert len(result["checks"]) == 3

    def test_verify_default_version(self):
        verifier = DeploymentVerifier()
        verifier.register_probe(healthy_probe(version="1.0.0-rc.1"))
        result = verifier.verify()
        assert result["passed"] is True

    def test_verify_version_mismatch_fails(self):
        verifier = DeploymentVerifier()
        verifier.register_probe(healthy_probe(version="2.0.0"))
        with pytest.raises(VerificationError):
            verifier.verify("1.0.0")

    def test_verify_latency_fails(self):
        verifier = DeploymentVerifier()
        verifier.register_probe(healthy_probe(latency_ms=900.0))
        with pytest.raises(VerificationError):
            verifier.verify("1.0.0-rc.1")

    def test_verify_requires_probe(self):
        with pytest.raises(VerificationError):
            DeploymentVerifier().verify()

    def test_last_verifications(self):
        verifier = DeploymentVerifier()
        verifier.register_probe(healthy_probe())
        verifier.verify("1.0.0-rc.1")
        assert len(verifier.last_verifications()) == 1


class TestGitOps:
    def test_manifest_to_dict(self):
        manifest = GitOpsManifest("Application", "ai-router", "ai-router", {"targetRevision": "v1.0.0"})
        data = manifest.to_dict()
        assert data["kind"] == "Application"
        assert data["metadata"]["name"] == "ai-router"
        assert data["spec"]["targetRevision"] == "v1.0.0"

    def test_manifest_from_dict(self):
        manifest = GitOpsManifest.from_dict(
            {"kind": "Application", "metadata": {"name": "x", "namespace": "ns"}, "spec": {"targetRevision": "v1.0.0"}}
        )
        assert manifest.kind == "Application"
        assert manifest.namespace == "ns"
        assert manifest.target_revision == "v1.0.0"

    def test_target_revision_nested(self):
        manifest = GitOpsManifest.from_dict(
            {"kind": "Application", "metadata": {"name": "x"}, "spec": {"source": {"targetRevision": "v2.0.0"}}}
        )
        assert manifest.target_revision == "v2.0.0"

    def test_images(self):
        manifest = GitOpsManifest("Application", "x", spec={"images": "ghcr.io/x/a:v1.0.0, ghcr.io/x/b:v1.0.1"})
        assert manifest.images() == ["ghcr.io/x/a:v1.0.0", "ghcr.io/x/b:v1.0.1"]

    def test_validate_ok(self):
        manifest = GitOpsManifest(
            "Application",
            "ai-router",
            spec={"targetRevision": "v1.0.0", "images": "ghcr.io/salmansaidibrohim267-prog/AI-Router:v1.0.0"},
        )
        assert GitOpsValidator().validate(manifest) == []
        assert GitOpsValidator().validate_or_raise(manifest) is True

    def test_validate_problems(self):
        validator = GitOpsValidator()
        assert "missing" in str(validator.validate(GitOpsManifest("", "")))
        assert "unsupported" in str(validator.validate(GitOpsManifest("Pod", "x", spec={"targetRevision": "v1"})))
        problems = validator.validate(GitOpsManifest("Application", "x", spec={"targetRevision": "v1", "images": "ghcr.io/x/a:latest"}))
        assert any("immutable" in p for p in problems)
        problems = validator.validate(GitOpsManifest("Application", "x", spec={"images": "not an image!"}))
        assert any("malformed" in p for p in problems)

    def test_validate_or_raise(self):
        manifest = GitOpsManifest("Application", "x", spec={"targetRevision": "v1", "images": "ghcr.io/x/a:latest"})
        with pytest.raises(GitOpsError):
            GitOpsValidator().validate_or_raise(manifest)

    def test_load_yaml(self):
        yaml_text = "apiVersion: argoproj.io/v1alpha1\nkind: Application\nmetadata:\n  name: ai-router\nspec:\n  targetRevision: v1.0.0\n"
        manifest = GitOpsValidator().load_yaml(yaml_text)
        assert manifest.name == "ai-router"
        assert manifest.target_revision == "v1.0.0"

    def test_load_yaml_invalid(self):
        with pytest.raises(GitOpsError):
            GitOpsValidator().load_yaml(": : : not yaml")

    def test_load_yaml_non_mapping(self):
        with pytest.raises(GitOpsError):
            GitOpsValidator().load_yaml("[1, 2, 3]")

    def test_apply(self):
        manifest = GitOpsManifest("Application", "x", spec={"targetRevision": "v1.0.0"})
        result = GitOpsValidator().apply(manifest, dry_run=True)
        assert result["dry_run"] is True
        result = GitOpsValidator().apply(manifest)
        assert result["applied"] is True

    def test_apply_invalid_raises(self):
        with pytest.raises(GitOpsError):
            GitOpsValidator().apply(GitOpsManifest("", "x"))


class TestDeploymentPipeline:
    def test_pipeline_flow(self):
        pipeline = DeploymentPipeline()
        pipeline.gates.register("coverage", lambda: {"passed": True, "value": 96.0})
        pipeline.gates.register("p95_latency_ms", lambda: {"passed": True, "value": 100.0})
        pipeline.gates.register("error_rate", lambda: {"passed": True, "value": 0.5})
        pipeline.gates.register("tests_passed", lambda: {"passed": True, "value": 1})
        pipeline.smoke.set_steps([SmokeStep("health")])
        pipeline.smoke.register_probe("health", healthy_probe())
        pipeline.rollback.register_deployer(lambda v: True)
        pipeline.rollback.register_probe(healthy_probe())
        pipeline.verify.register_probe(healthy_probe())

        result = pipeline.run()
        assert result["environment"] == "staging"
        assert result["version"] == "1.0.0-rc.1"
        assert result["verification"]["passed"] is True
        assert pipeline.last_run() is result

    def test_pipeline_injected_components(self):
        gates = QualityGateRunner()
        gates.register("coverage", lambda: {"passed": True, "value": 100.0})
        smoke = SmokeTester()
        smoke.set_steps([SmokeStep("health")])
        smoke.register_probe("health", healthy_probe())
        rollback = RollbackTester()
        rollback.register_deployer(lambda v: True)
        rollback.register_probe(healthy_probe())
        verify = DeploymentVerifier()
        verify.register_probe(healthy_probe())
        gitops = GitOpsValidator()

        pipeline = DeploymentPipeline(gates_runner=gates, smoke_tester=smoke, rollback_tester=rollback, verifier=verify, gitops=gitops)
        result = pipeline.run(gate_results=[], smoke_results=[])
        assert result["verification"]["passed"] is True
        assert len(pipeline.runs()) == 1

    def test_pipeline_raises_on_gate_failure(self):
        pipeline = DeploymentPipeline()
        pipeline.gates.register("coverage", lambda: {"passed": False, "value": 50.0})
        with pytest.raises(QualityGateError):
            pipeline.run()

    def test_factory(self):
        pipeline = create_deployment_pipeline(DeployConfig())
        assert isinstance(pipeline, DeploymentPipeline)
