"""Tests for the release management subsystem (Stage 10.10)."""

import json
import os

import pytest

from app.release import (
    ArtifactManifest,
    ChangelogError,
    ChangelogGenerator,
    CommitEntry,
    ContainerRegistryPublisher,
    GitHubPublisher,
    LocalPublisher,
    PublishError,
    PublisherRegistry,
    ReleaseConfig,
    ReleaseEntry,
    ReleaseError,
    ReleaseLockedError,
    ReleaseManager,
    ReleaseSigner,
    SemanticVersion,
    Signature,
    SignatureVerificationError,
    SigningError,
    VersionError,
    VersionNotFoundError,
    canonical_json,
    create_publisher,
    create_release_manager,
)


class TestReleaseConfig:
    def test_defaults(self):
        config = ReleaseConfig()
        assert config.project_name == "ai-router"
        assert config.initial_version == "1.0.0-rc.1"
        assert config.registry == "ghcr.io/anomalyco"
        assert config.publishers == ["github"]
        assert config.pre_release_tags == ["rc", "beta", "alpha"]
        assert config.auto_publish is False

    def test_kwargs(self):
        config = ReleaseConfig(project_name="custom", signing_key="k", auto_publish=True)
        assert config.project_name == "custom"
        assert config.signing_key == "k"
        assert config.auto_publish is True

    def test_unknown_kwarg_raises(self):
        with pytest.raises(TypeError):
            ReleaseConfig(nope=1)

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("REL_REGISTRY", "registry.example.com")
        monkeypatch.setenv("REL_PUBLISHERS", "github,local")
        monkeypatch.setenv("REL_SBOM_ENABLED", "false")
        config = ReleaseConfig.from_env()
        assert config.registry == "registry.example.com"
        assert config.publishers == ["github", "local"]
        assert config.sbom_enabled is False

    def test_as_dict(self):
        data = ReleaseConfig().as_dict()
        assert data["project_name"] == "ai-router"
        assert data["publishers"] == ["github"]


class TestSemanticVersion:
    def test_parse_basic(self):
        version = SemanticVersion.parse("1.2.3")
        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3
        assert version.prerelease == ""
        assert str(version) == "1.2.3"

    def test_parse_prerelease_and_build(self):
        version = SemanticVersion.parse("1.2.3-rc.1+build.5")
        assert version.prerelease == "rc.1"
        assert version.build == "build.5"
        assert str(version) == "1.2.3-rc.1+build.5"

    def test_parse_invalid(self):
        with pytest.raises(VersionError):
            SemanticVersion.parse("1.2")
        with pytest.raises(VersionError):
            SemanticVersion.parse("v1.2.3")
        with pytest.raises(VersionError):
            SemanticVersion.parse("1.2.3.4")

    def test_negative_component_raises(self):
        with pytest.raises(VersionError):
            SemanticVersion(-1, 0, 0)

    def test_precedence(self):
        assert SemanticVersion.parse("1.0.0") > SemanticVersion.parse("1.0.0-rc.1")
        assert SemanticVersion.parse("1.0.0-rc.2") > SemanticVersion.parse("1.0.0-rc.1")
        assert SemanticVersion.parse("1.0.1") > SemanticVersion.parse("1.0.0")
        assert SemanticVersion.parse("2.0.0") > SemanticVersion.parse("1.9.9")
        assert SemanticVersion.parse("1.0.0") == SemanticVersion.parse("1.0.0+meta")

    def test_is_rc_and_number(self):
        assert SemanticVersion.parse("1.0.0-rc.3").is_rc()
        assert SemanticVersion.parse("1.0.0-rc.3").rc_number() == 3
        assert SemanticVersion.parse("1.0.0-rc").rc_number() == 1
        assert SemanticVersion.parse("1.0.0").rc_number() == 0
        assert SemanticVersion.parse("1.0.0-beta.1").is_rc() is False

    def test_is_prerelease(self):
        assert SemanticVersion.parse("1.0.0-rc.1").is_prerelease is True
        assert SemanticVersion.parse("1.0.0").is_prerelease is False

    def test_rc_number_non_numeric(self):
        assert SemanticVersion.parse("1.0.0-rc.beta").rc_number() == 0

    def test_le_ge(self):
        assert SemanticVersion.parse("1.0.0-rc.1") <= SemanticVersion.parse("1.0.0")
        assert SemanticVersion.parse("1.0.0") <= SemanticVersion.parse("1.0.0")
        assert SemanticVersion.parse("1.0.0") >= SemanticVersion.parse("1.0.0-rc.1")
        assert SemanticVersion.parse("1.0.0") >= SemanticVersion.parse("1.0.0")

    def test_eq_non_version(self):
        assert (SemanticVersion.parse("1.0.0") == "1.0.0") is False
        assert (SemanticVersion.parse("1.0.0") != "1.0.0") is True

    def test_bumps(self):
        version = SemanticVersion.parse("1.2.3")
        assert str(version.bump_major()) == "2.0.0"
        assert str(version.bump_minor()) == "1.3.0"
        assert str(version.bump_patch()) == "1.2.4"
        assert str(version.as_release()) == "1.2.3"
        assert str(version.as_rc(2)) == "1.2.3-rc.2"

    def test_next(self):
        version = SemanticVersion.parse("1.2.3-rc.1")
        assert str(version.next("rc")) == "1.2.3-rc.2"
        assert str(version.next("release")) == "1.2.3"
        assert str(version.next("patch")) == "1.2.4"
        with pytest.raises(VersionError):
            version.next("bogus")

    def test_to_dict(self):
        data = SemanticVersion.parse("1.0.0-rc.1").to_dict()
        assert data["major"] == 1
        assert data["version"] == "1.0.0-rc.1"

    def test_hashable(self):
        assert hash(SemanticVersion.parse("1.0.0")) == hash(SemanticVersion.parse("1.0.0"))


class TestChangelog:
    def test_commit_parse(self):
        entry = CommitEntry.parse("feat(router): add fallback routing")
        assert entry is not None
        assert entry.type == "feat"
        assert entry.scope == "router"
        assert entry.subject == "add fallback routing"
        assert entry.breaking is False

    def test_commit_parse_breaking_and_invalid(self):
        entry = CommitEntry.parse("fix!: drop legacy api", sha="abc")
        assert entry is not None
        assert entry.breaking is True
        assert entry.sha == "abc"
        assert CommitEntry.parse("not a commit") is None

    def test_release_sections(self):
        release = ReleaseEntry(
            version="1.0.0",
            commits=[
                CommitEntry("feat", "add x"),
                CommitEntry("fix", "repair y"),
                CommitEntry("docs", "improve docs"),
                CommitEntry("unknown_type", "falls through"),
            ],
        )
        sections = release.sections()
        assert "add x" in [c.subject for c in sections["added"]]
        assert "repair y" in [c.subject for c in sections["fixed"]]
        assert "improve docs" in [c.subject for c in sections["changed"]]
        assert "falls through" in [c.subject for c in sections["changed"]]

    def test_markdown_sections_and_breaking(self):
        release = ReleaseEntry(
            version="1.0.0",
            date="2026-08-01",
            commits=[CommitEntry("feat", "new feature"), CommitEntry("fix", "breaking fix", breaking=True)],
        )
        text = release.markdown()
        assert "## [1.0.0]" in text
        assert "### Added" in text
        assert "### Fixed" in text
        assert "### BREAKING CHANGES" in text
        assert "new feature" in text

    def test_markdown_empty_commits(self):
        release = ReleaseEntry(version="1.0.0")
        assert "Initial release." in release.markdown()

    def test_generate_empty_raises(self):
        generator = ChangelogGenerator()
        with pytest.raises(ChangelogError):
            generator.generate([])

    def test_generate_from_commits(self):
        generator = ChangelogGenerator()
        text = generator.generate_from_commits("1.0.0", ["feat: hello", "garbage line"], date="2026-08-01")
        assert "All notable changes" in text
        assert "hello" in text
        assert "garbage" not in text

    def test_parse_changelog_roundtrip(self):
        generator = ChangelogGenerator()
        text = generator.generate_from_commits("1.0.0", ["feat: hello", "fix: bug"], date="2026-08-01")
        releases = generator.parse_changelog(text)
        assert len(releases) == 1
        assert releases[0].version == "1.0.0"
        subjects = [c.subject for c in releases[0].commits]
        assert subjects == ["hello", "bug"]

    def test_parse_changelog_scope_and_breaking(self):
        generator = ChangelogGenerator()
        release = ReleaseEntry(
            version="2.0.0",
            date="2026-08-01",
            commits=[CommitEntry("feat", "drop legacy api", scope="router", breaking=True)],
        )
        parsed = generator.parse_changelog(generator.generate([release]))
        assert len(parsed) == 1
        assert len(parsed[0].commits) == 2
        scoped = [c for c in parsed[0].commits if c.scope]
        assert len(scoped) == 1
        assert scoped[0].scope == "router"
        assert scoped[0].breaking is True
        assert scoped[0].subject == "drop legacy api"


class TestSigning:
    def test_canonical_json(self):
        assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'

    def test_sign_and_verify(self):
        signer = ReleaseSigner("secret-key")
        signature = signer.sign({"version": "1.0.0"})
        assert signature.algorithm == "hmac-sha256"
        assert signer.verify(signature) is True

    def test_verify_tampered_payload(self):
        signer = ReleaseSigner("secret-key")
        signature = signer.sign({"version": "1.0.0"})
        signature.payload["version"] = "2.0.0"
        assert signer.verify(signature) is False

    def test_verify_or_raise(self):
        signer = ReleaseSigner("secret-key")
        signature = signer.sign({"version": "1.0.0"})
        assert signer.verify_or_raise(signature) is True
        signature.signature = "0" * 64
        with pytest.raises(SignatureVerificationError):
            signer.verify_or_raise(signature)

    def test_empty_key_raises(self):
        with pytest.raises(SigningError):
            ReleaseSigner("")

    def test_sign_string_deterministic(self):
        signer = ReleaseSigner("k")
        assert signer.sign_string("abc") == signer.sign_string("abc")

    def test_sign_artifact(self):
        signer = ReleaseSigner("k")
        signature = signer.sign_artifact("wheel", "1.0.0", "digest123")
        assert signer.verify_artifact("wheel", "1.0.0", "digest123", signature) is True
        assert signer.verify_artifact("wheel", "1.0.0", "other", signature) is False
        assert signer.verify_artifact("sdist", "1.0.0", "digest123", signature) is False

    def test_ed25519_style(self):
        from app.release import Ed25519StyleSigner

        signer = Ed25519StyleSigner("secret", "secret")
        signature = signer.sign({"v": 1})
        assert signature.algorithm == "ed25519-style"
        assert signer.verify(signature) is True
        assert Ed25519StyleSigner("secret", "other").verify(signature) is False


class TestPublishing:
    def test_github_publish_requires_transport(self):
        config = ReleaseConfig()
        publisher = GitHubPublisher(config)
        with pytest.raises(PublishError):
            publisher.publish("1.0.0", [])

    def test_github_publish_flow(self, tmp_path):
        calls = []

        def transport(method, url, headers, body):
            calls.append((method, url, body))
            if "assets?" in url:
                return {"id": 55}
            return {"id": 42}

        artifact = tmp_path / "wheel.whl"
        artifact.write_bytes(b"data")
        publisher = GitHubPublisher(ReleaseConfig(), transport=transport, token="tok")
        result = publisher.publish("1.0.0", [str(artifact)], "notes")
        assert result["release_id"] == 42
        assert result["uploads"] == [{"name": "wheel.whl", "asset_id": 55, "size": 4}]
        assert any(url == "https://api.github.com/repos/anomalyco/ai-router/releases" for _, url, _ in calls)
        release_body = [b for _, _, b in calls if isinstance(b, dict) and "tag_name" in b][0]
        assert release_body["tag_name"] == "v1.0.0"
        assert release_body["prerelease"] is False

    def test_github_prerelease_detection(self):
        calls = []

        def transport(method, url, headers, body):
            calls.append(body)
            return {"id": 1}

        publisher = GitHubPublisher(ReleaseConfig(), transport=transport)
        publisher.publish("1.0.0-rc.1", [])
        assert calls[0]["prerelease"] is True

    def test_github_upload_failure_raises(self):
        def transport(method, url, headers, body):
            if "assets?" in url:
                raise RuntimeError("boom")
            return {"id": 1}

        artifact = "/nonexistent/wheel.whl"
        publisher = GitHubPublisher(ReleaseConfig(), transport=transport)
        result = publisher.publish("1.0.0", [artifact])
        assert result["uploads"] == []

    def test_github_release_creation_failure(self):
        def transport(method, url, headers, body):
            raise RuntimeError("down")

        publisher = GitHubPublisher(ReleaseConfig(), transport=transport)
        with pytest.raises(PublishError):
            publisher.publish("1.0.0", [])

    def test_github_upload_failure_real_file(self, tmp_path):
        artifact = tmp_path / "wheel.whl"
        artifact.write_bytes(b"data")

        def transport(method, url, headers, body):
            if "assets?" in url:
                raise RuntimeError("upload failed")
            return {"id": 1}

        publisher = GitHubPublisher(ReleaseConfig(), transport=transport)
        with pytest.raises(PublishError):
            publisher.publish("1.0.0", [str(artifact)])

    def test_github_no_release_id_skips_uploads(self, tmp_path):
        artifact = tmp_path / "wheel.whl"
        artifact.write_bytes(b"data")
        calls = []

        def transport(method, url, headers, body):
            calls.append(url)
            return {}

        publisher = GitHubPublisher(ReleaseConfig(), transport=transport)
        result = publisher.publish("1.0.0", [str(artifact)])
        assert result["release_id"] is None
        assert result["uploads"] == []
        assert not any("assets" in url for url in calls)

    def test_registry_token_header(self):
        captured = []

        def transport(method, url, headers, body):
            captured.append(headers)
            return {"accepted": True}

        publisher = ContainerRegistryPublisher(ReleaseConfig(), transport=transport, token="tok")
        publisher.publish("1.0.0", [])
        assert all("Authorization" in headers and headers["Authorization"] == "Bearer tok" for headers in captured)

    def test_registry_push_failure(self):
        def transport(method, url, headers, body):
            raise RuntimeError("registry down")

        publisher = ContainerRegistryPublisher(ReleaseConfig(), transport=transport)
        with pytest.raises(PublishError):
            publisher.publish("1.0.0", [])

    def test_local_publish_missing_file(self, tmp_path):
        config = ReleaseConfig(artifacts_dir=str(tmp_path / "out"))
        result = LocalPublisher(config).publish("1.0.0", [str(tmp_path / "missing.whl")])
        assert result["artifacts"] == []

    def test_registry_publish(self):
        calls = []

        def transport(method, url, headers, body):
            calls.append((url, body))
            return {"accepted": True}

        publisher = ContainerRegistryPublisher(ReleaseConfig(), transport=transport)
        result = publisher.publish("1.0.0", [])
        assert result["image"] == "ghcr.io/anomalyco/ai-router"
        assert [tag for _, body in calls for tag in [body["tag"]]] == ["1.0.0", "latest", "1.0"]

    def test_registry_prerelease_single_tag(self):
        def transport(method, url, headers, body):
            return {"accepted": True}

        publisher = ContainerRegistryPublisher(ReleaseConfig(), transport=transport)
        result = publisher.publish("1.0.0-rc.1", [])
        assert len(result["tags"]) == 1
        assert result["tags"][0]["tag"] == "1.0.0-rc.1"

    def test_registry_requires_transport(self):
        with pytest.raises(PublishError):
            ContainerRegistryPublisher(ReleaseConfig()).publish("1.0.0", [])

    def test_local_publish(self, tmp_path):
        artifact = tmp_path / "wheel.whl"
        artifact.write_bytes(b"data")
        config = ReleaseConfig(artifacts_dir=str(tmp_path / "out"))
        result = LocalPublisher(config).publish("1.0.0", [str(artifact)], "notes")
        assert os.path.isdir(result["directory"])
        assert result["artifacts"] == [{"name": "wheel.whl", "path": os.path.join(result["directory"], "wheel.whl")}]
        manifest = json.loads((tmp_path / "out" / "1.0.0" / "manifest.json").read_text())
        assert manifest["version"] == "1.0.0"

    def test_publisher_registry(self):
        registry = PublisherRegistry()
        config = ReleaseConfig()
        assert isinstance(registry.create(config, "github"), GitHubPublisher)
        assert isinstance(registry.create(config, "local"), LocalPublisher)
        with pytest.raises(PublishError):
            registry.create(config, "bogus")

    def test_create_publisher_with_registry_override(self):
        config = ReleaseConfig()
        registry = PublisherRegistry()
        publisher = create_publisher(config, "local", registry=registry)
        assert isinstance(publisher, LocalPublisher)

    def test_publisher_registry_register(self):
        registry = PublisherRegistry()
        registry.register("custom", lambda config, **kw: LocalPublisher(config))
        assert isinstance(registry.create(ReleaseConfig(), "custom"), LocalPublisher)


class TestReleaseManager:
    def setup_method(self):
        self.manager = ReleaseManager()

    def test_next_version_from_empty(self):
        assert str(self.manager.next_version()) == "1.0.0-rc.1"

    def test_create_release(self):
        entry = self.manager.create_release("1.0.0", ["feat: first release"])
        assert entry.version == "1.0.0"
        assert self.manager.list_releases() == ["1.0.0"]
        assert self.manager.latest_version() == SemanticVersion.parse("1.0.0")

    def test_create_release_duplicate_raises(self):
        self.manager.create_release("1.0.0")
        with pytest.raises(ReleaseError):
            self.manager.create_release("1.0.0")

    def test_create_release_auto_version(self):
        entry = self.manager.create_release(bump="patch")
        assert entry.version == "1.0.0-rc.1"
        entry = self.manager.create_release(bump="release")
        assert entry.version == "1.0.0"

    def test_create_rc_sequence(self):
        rc1 = self.manager.create_rc()
        assert rc1.version == "1.0.0-rc.1"
        rc2 = self.manager.create_rc()
        assert rc2.version == "1.0.0-rc.2"

    def test_promote_to_release(self):
        self.manager.create_release("1.0.0-rc.1")
        entry = self.manager.promote_to_release("1.0.0-rc.1")
        assert entry.version == "1.0.0"
        with pytest.raises(ReleaseError):
            self.manager.promote_to_release("1.0.0")

    def test_next_version_from_rc_bump_patch(self):
        self.manager.create_release("1.0.0-rc.1")
        assert str(self.manager.next_version()) == "1.0.0-rc.2"

    def test_next_version_bumps(self):
        self.manager.create_release("1.0.0")
        assert str(self.manager.next_version("patch")) == "1.0.1"
        assert str(self.manager.next_version("minor")) == "1.1.0"
        assert str(self.manager.next_version("major")) == "2.0.0"

    def test_changelog_markdown(self):
        self.manager.create_release("1.0.0", ["feat: shiny"])
        text = self.manager.changelog_markdown()
        assert "## [1.0.0]" in text
        assert "shiny" in text

    def test_write_changelog(self, tmp_path):
        self.manager.create_release("1.0.0")
        path = self.manager.write_changelog(str(tmp_path / "nested" / "CHANGELOG.md"))
        assert os.path.exists(path)
        assert "## [1.0.0]" in open(path).read()

    def test_artifacts_and_signature(self, tmp_path):
        artifact = tmp_path / "app.whl"
        artifact.write_bytes(b"payload")
        self.manager.create_release("1.0.0")
        self.manager.add_artifact("1.0.0", "app.whl", str(artifact))
        manifest = self.manager.get_manifest("1.0.0")
        assert manifest is not None
        assert manifest.summary()["artifact_count"] == 1
        assert manifest.to_dict()["version"] == "1.0.0"
        assert manifest.artifacts[0]["digest"]

        signature = self.manager.sign_manifest("1.0.0")
        assert self.manager.verify_manifest("1.0.0") is True
        assert self.manager.export_signature("1.0.0")["algorithm"] == "hmac-sha256"

    def test_sign_without_manifest_raises(self):
        self.manager.create_release("1.0.0")
        with pytest.raises(ReleaseError):
            self.manager.sign_manifest("1.0.0")

    def test_verify_missing_signature_false(self):
        self.manager.create_release("1.0.0")
        assert self.manager.verify_manifest("1.0.0") is False

    def test_export_missing_signature_raises(self):
        with pytest.raises(ReleaseError):
            self.manager.export_signature("1.0.0")

    def test_build_artifact_manifest(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.write_bytes(b"1")
        b.write_bytes(b"22")
        self.manager.create_release("1.0.0")
        manifest = self.manager.build_artifact_manifest("1.0.0", {"a": str(a), "b": str(b)})
        assert manifest.summary()["artifact_count"] == 2
        assert manifest.summary()["total_size"] == 3

    def test_finalise_locks_artifacts(self, tmp_path):
        artifact = tmp_path / "a"
        artifact.write_bytes(b"1")
        self.manager.create_release("1.0.0")
        self.manager.finalise("1.0.0")
        assert self.manager.is_finalised("1.0.0")
        with pytest.raises(ReleaseLockedError):
            self.manager.add_artifact("1.0.0", "a", str(artifact))
        with pytest.raises(ReleaseLockedError):
            self.manager.build_artifact_manifest("1.0.0", {"a": str(artifact)})

    def test_finalise_missing_release_raises(self):
        with pytest.raises(VersionNotFoundError):
            self.manager.finalise("9.9.9")

    def test_publish_local(self, tmp_path):
        artifact = tmp_path / "a.whl"
        artifact.write_bytes(b"1")
        self.manager.create_release("1.0.0")
        self.manager.add_artifact("1.0.0", "a.whl", str(artifact))
        output = tmp_path / "out"
        self.manager.register_publisher("local", LocalPublisher(ReleaseConfig(artifacts_dir=str(output))))
        results = self.manager.publish("1.0.0", names=["local"])
        assert results["local"]["publisher"] == "local"
        assert os.path.exists(output / "1.0.0" / "a.whl")

    def test_publish_auto_create(self, tmp_path):
        artifact = tmp_path / "a.whl"
        artifact.write_bytes(b"1")
        config = ReleaseConfig(auto_publish=True, publishers=["local"], artifacts_dir=str(tmp_path / "out"))
        manager = ReleaseManager(config)
        manager.create_release("1.0.0")
        manager.add_artifact("1.0.0", "a.whl", str(artifact))
        results = manager.publish("1.0.0")
        assert "local" in results

    def test_publish_unknown_skipped(self):
        self.manager.create_release("1.0.0")
        assert self.manager.publish("1.0.0", names=["nope"]) == {}

    def test_history_persistence(self, tmp_path):
        history = str(tmp_path / "history.json")
        manager = ReleaseManager(history_file=history)
        manager.create_release("1.0.0", ["feat: one"])
        manager.finalise("1.0.0")
        manager.save_history()

        loaded = ReleaseManager(history_file=history)
        assert loaded.list_releases() == ["1.0.0"]
        assert loaded.is_finalised("1.0.0")
        release = loaded.get_release("1.0.0")
        assert release is not None
        assert release.commits[0].subject == "one"

    def test_history_corrupt_file(self, tmp_path):
        history = tmp_path / "bad.json"
        history.write_text("{corrupt")
        manager = ReleaseManager(history_file=str(history))
        assert manager.list_releases() == []

    def test_status(self):
        self.manager.create_release("1.0.0")
        status = self.manager.status()
        assert status["project"] == "ai-router"
        assert status["latest_version"] == "1.0.0"
        assert status["release_count"] == 1

    def test_get_release_missing(self):
        assert self.manager.get_release("9.9.9") is None

    def test_save_history_without_file_noop(self):
        assert self.manager.save_history() is None

    def test_factory(self):
        manager = create_release_manager(ReleaseConfig())
        assert isinstance(manager, ReleaseManager)


class TestArtifactManifest:
    def test_from_dict(self):
        manifest = ArtifactManifest.from_dict({"version": "1.0.0", "artifacts": [], "metadata": {"x": 1}})
        assert manifest.version == "1.0.0"
        assert manifest.metadata == {"x": 1}

    def test_add_missing_file(self, tmp_path):
        manifest = ArtifactManifest("1.0.0")
        manifest.add("gone", str(tmp_path / "missing"))
        assert manifest.artifacts[0]["digest"] == ""

    def test_add_dedupes(self, tmp_path):
        artifact = tmp_path / "a"
        artifact.write_bytes(b"1")
        manifest = ArtifactManifest("1.0.0")
        manifest.add("a", str(artifact))
        manifest.add("a", str(artifact))
        assert len(manifest.artifacts) == 1

    def test_payload(self):
        manifest = ArtifactManifest("1.0.0", [{"name": "a", "path": "/x", "digest": "d"}])
        assert manifest.payload() == {"version": "1.0.0", "artifacts": manifest.artifacts}
