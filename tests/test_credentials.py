import os
import tempfile
import unittest
from pathlib import Path

from router_brain import credentials
from router_brain.models import CredentialsError


class TestCredentials(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cred_path = Path(self.tmp.name) / ".credentials.yaml"
        self.cred_path.write_text("TEST_RB_KEY: sk-test-1234567890\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("TEST_RB_KEY", None)

    def test_read_from_file(self):
        val = credentials.resolve_key("TEST_RB_KEY", self.cred_path)
        self.assertEqual(val, "sk-test-1234567890")

    def test_env_overrides_file(self):
        os.environ["TEST_RB_KEY"] = "env-value-abcdefgh"
        self.cred_path.write_text("TEST_RB_KEY: file-value-xyz\n", encoding="utf-8")
        self.assertEqual(credentials.resolve_key("TEST_RB_KEY", self.cred_path), "env-value-abcdefgh")

    def test_missing_raises(self):
        with self.assertRaises(CredentialsError):
            credentials.resolve_key("NO_SUCH_KEY", self.cred_path)

    def test_redact_never_leaks_full(self):
        val = credentials.redact("sk-0123456789abcdef")
        self.assertNotIn("0123456789abcdef", val)
        self.assertIn("sk-", val)

    def test_redact_short(self):
        self.assertEqual(credentials.redact("abc"), "<redacted>")


if __name__ == "__main__":
    unittest.main()
