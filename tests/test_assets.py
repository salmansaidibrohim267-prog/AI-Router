"""Tests for deployment assets, CI workflows, docs and the release artifact
(Stage 10.10)."""

import json
import os
import pathlib

import pytest

from app.deploy import GitOpsManifest, GitOpsValidator
from app.release import ReleaseManager, ReleaseConfig

ROOT = pathlib.Path(__file__).resolve().parent.parent
RELEASE_VERSION = "1.0.0-rc.1"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text()


class TestVersionAlignment:
    def test_pyproject_version(self):
        assert "version = \"1.0.0-rc.1\"" in _read("pyproject.toml")

    def test_dockerfile_version_arg(self):
        assert "ARG VERSION=1.0.0-rc.1" in _read("Dockerfile")

    def test_compose_build_version(self):
        assert 'VERSION: "1.0.0-rc.1"' in _read("docker-compose.yml")

    def test_helm_app_version(self):
        assert 'appVersion: "1.0.0-rc.1"' in _read("deployment/helm/ai-router/Chart.yaml")
        assert 'tag: "1.0.0-rc.1"' in _read("deployment/helm/ai-router/values.yaml")

    def test_k8s_image_tag(self):
        assert "ghcr.io/anomalyco/ai-router:1.0.0-rc.1" in _read("deployment/k8s/ai-router.yaml")

    def test_prod_compose_image_tag(self):
        assert "ghcr.io/anomalyco/ai-router:1.0.0-rc.1" in _read("deployment/docker-compose.prod.yml")

    def test_prod_dockerfile_version(self):
        assert "ARG VERSION=1.0.0-rc.1" in _read("deployment/Dockerfile.prod")

    def test_terraform_image_uri(self):
        assert "1.0.0-rc.1" in _read("deployment/terraform/variables.tf")

    def test_ansible_version(self):
        assert 'ai_router_version: "1.0.0-rc.1"' in _read("deployment/ansible/playbook.yml")


class TestDeploymentAssets:
    def test_k8s_manifests_present(self):
        for name in ["ai-router.yaml", "rbac.yaml", "kustomization.yaml"]:
            assert (ROOT / "deployment" / "k8s" / name).exists(), name

    def test_k8s_manifest_resources(self):
        text = _read("deployment/k8s/ai-router.yaml")
        for kind in ["ConfigMap", "Deployment", "Service", "HorizontalPodAutoscaler", "PodDisruptionBudget", "Ingress"]:
            assert f"kind: {kind}" in text

    def test_k8s_security_hardening(self):
        text = _read("deployment/k8s/ai-router.yaml")
        assert "runAsNonRoot: true" in text
        assert "readOnlyRootFilesystem: true" in text
        assert "allowPrivilegeEscalation: false" in text
        assert "drop: [\"ALL\"]" in text

    def test_k8s_probes(self):
        text = _read("deployment/k8s/ai-router.yaml")
        assert "/health" in text
        assert "/ready" in text

    def test_helm_chart_files(self):
        expected = ["Chart.yaml", "values.yaml", "templates/_helpers.tpl", "templates/deployment.yaml",
                    "templates/service.yaml", "templates/ingress.yaml", "templates/hpa.yaml",
                    "templates/pdb.yaml", "templates/configmap.yaml", "templates/serviceaccount.yaml"]
        for name in expected:
            assert (ROOT / "deployment" / "helm" / "ai-router" / name).exists(), name

    def test_terraform_files(self):
        for name in ["main.tf", "variables.tf", "outputs.tf"]:
            assert (ROOT / "deployment" / "terraform" / name).exists(), name

    def test_ansible_files(self):
        assert (ROOT / "deployment" / "ansible" / "playbook.yml").exists()
        assert (ROOT / "deployment" / "ansible" / "inventory" / "production.yml").exists()

    def test_gitops_application_valid(self):
        manifest = GitOpsValidator().load_yaml(_read("deployment/gitops/apps/ai-router/application.yaml"))
        assert manifest.kind == "Application"
        assert manifest.target_revision == "v1.0.0-rc.1"
        assert GitOpsValidator().validate(manifest) == []

    def test_gitops_application_paths(self):
        text = _read("deployment/gitops/apps/ai-router/application.yaml")
        assert "path: deployment/k8s" in text
        assert "CreateNamespace=true" in text


class TestWorkflows:
    def test_workflow_files(self):
        expected = ["ci.yml", "lint.yml", "test.yml", "benchmark.yml", "security.yml", "build-sign.yml", "release.yml"]
        for name in expected:
            assert (ROOT / ".github" / "workflows" / name).exists(), name

    def test_lint_tools(self):
        text = _read(".github/workflows/lint.yml")
        for tool in ["ruff", "mypy", "black", "flake8"]:
            assert tool in text

    def test_test_workflow_coverage_floor(self):
        assert "--cov-fail-under=95" in _read(".github/workflows/test.yml")

    def test_security_tools(self):
        text = _read(".github/workflows/security.yml")
        for tool in ["bandit", "pip-audit", "trivy", "syft"]:
            assert tool in text

    def test_build_sign(self):
        text = _read(".github/workflows/build-sign.yml")
        assert "cosign" in text
        assert "build-push-action" in text

    def test_release_workflow_uses_release_manager(self):
        text = _read(".github/workflows/release.yml")
        assert "app.release" in text
        assert "bump" in text

    def test_workflows_are_valid_yaml(self):
        import yaml

        for name in ["ci", "lint", "test", "benchmark", "security", "build-sign", "release"]:
            data = yaml.safe_load(_read(f".github/workflows/{name}.yml"))
            assert data is not None
            assert data["name"]


class TestDocs:
    def test_all_guides_present(self):
        expected = [
            "README.md", "architecture.md", "api.md", "sdk.md", "plugins.md",
            "deployment.md", "operations.md", "troubleshooting.md", "security.md",
            "migrations.md", "observability.md", "contributing.md",
        ]
        for name in expected:
            assert (ROOT / "docs" / name).exists(), name

    def test_readme_links_guides(self):
        text = _read("docs/README.md")
        for name in ["architecture.md", "api.md", "sdk.md", "plugins.md",
                     "deployment.md", "operations.md", "troubleshooting.md",
                     "security.md", "migrations.md", "observability.md", "contributing.md"]:
            assert name in text, name

    def test_docs_reference_v1(self):
        for name in ["deployment.md", "operations.md"]:
            assert "1.0.0-rc.1" in _read(f"docs/{name}")


class TestReleaseArtifact:
    def test_artifact_files(self):
        for name in ["ai-router-1.0.0-rc.1.tar.gz", "signature.json", "history.json"]:
            assert (ROOT / "dist" / "release" / name).exists(), name

    def test_signature_verifies(self):
        manager = ReleaseManager(ReleaseConfig(), history_file=str(ROOT / "dist" / "release" / "history.json"))
        assert manager.verify_manifest("1.0.0-rc.1") is True

    def test_release_is_finalised(self):
        manager = ReleaseManager(ReleaseConfig(), history_file=str(ROOT / "dist" / "release" / "history.json"))
        assert manager.is_finalised("1.0.0-rc.1")
        assert manager.latest_version() is not None
        assert str(manager.latest_version()) == "1.0.0-rc.1"

    def test_signature_json_shape(self):
        data = json.loads((ROOT / "dist" / "release" / "signature.json").read_text())
        assert data["algorithm"] == "hmac-sha256"
        assert data["signature"]
        assert data["payload"]["version"] == "1.0.0-rc.1"

    def test_changelog_contains_release(self):
        text = _read("CHANGELOG.md")
        assert "## [1.0.0-rc.1]" in text
        assert "### Added" in text
