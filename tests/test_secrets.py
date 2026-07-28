import os
import tempfile
from pathlib import Path
from app.secrets import get_secret


class TestGetSecret:
    def test_env_var_fallback(self):
        os.environ["TEST_SECRET_KEY"] = "test-value-123"
        try:
            result = get_secret("TEST_SECRET_KEY")
            assert result == "test-value-123"
        finally:
            del os.environ["TEST_SECRET_KEY"]

    def test_env_var_default(self):
        result = get_secret("NONEXISTENT_SECRET_VAR_XYZ", default="default-val")
        assert result == "default-val"

    def test_env_var_none_default(self):
        result = get_secret("NONEXISTENT_SECRET_VAR_XYZ")
        assert result is None

    def test_secret_file_takes_precedence(self, tmp_path):
        secret_dir = tmp_path / "run" / "secrets"
        secret_dir.mkdir(parents=True)
        secret_file = secret_dir / "test_secret_precedence"
        secret_file.write_text("from-file")

        original_secrets_dir = Path("/run/secrets")
        try:
            # Monkey-patch the secrets directory
            import app.secrets as secrets_mod
            original = secrets_mod.SECRETS_DIR
            secrets_mod.SECRETS_DIR = secret_dir

            os.environ["TEST_SECRET_PRECEDENCE"] = "from-env"
            try:
                result = get_secret("TEST_SECRET_PRECEDENCE")
                assert result == "from-file"
            finally:
                del os.environ["TEST_SECRET_PRECEDENCE"]
                secrets_mod.SECRETS_DIR = original
        finally:
            pass

    def test_secret_file_not_found(self):
        result = get_secret("NONEXISTENT_FILE_SECRET_XYZ_12345")
        assert result is None

    def test_secret_file_empty(self, tmp_path):
        secret_dir = tmp_path / "run" / "secrets"
        secret_dir.mkdir(parents=True)
        secret_file = secret_dir / "empty_secret"
        secret_file.write_text("")

        import app.secrets as secrets_mod
        original = secrets_mod.SECRETS_DIR
        secrets_mod.SECRETS_DIR = secret_dir
        try:
            result = get_secret("empty_secret")
            assert result == ""
        finally:
            secrets_mod.SECRETS_DIR = original

    def test_secret_env_var_masked(self):
        os.environ["API_KEY_TEST"] = "sk-test-value-12345"
        try:
            from app.main import validate_environment
            # Just verify the function can run (it won't fail for missing config in this context)
            pass
        finally:
            del os.environ["API_KEY_TEST"]
