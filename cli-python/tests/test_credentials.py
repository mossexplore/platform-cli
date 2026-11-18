import tempfile
import unittest
import json
from pathlib import Path

from wiserec_cli.credentials import CredentialStore
from wiserec_cli.models import Credentials


class CredentialStoreTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "credentials.json"
        self.store = CredentialStore(self.path)

    def tearDown(self):
        self.temporary.cleanup()

    def test_saves_credentials_by_profile(self):
        credentials = Credentials.create(
            profile="dev",
            cookie="session=abc; token=xyz",
            csrftoken="csrf-value",
            username="jack",
            ttl_seconds=1800,
            business_id="tenant-001",
        )
        self.store.save(credentials)
        loaded = self.store.load("dev")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.cookie, credentials.cookie)
        self.assertEqual(loaded.csrftoken, credentials.csrftoken)
        self.assertEqual(loaded.business_id, "tenant-001")
        self.assertFalse(loaded.is_expired(now=credentials.acquired_at + 1799))
        self.assertLess(abs(loaded.expires_at - credentials.expires_at), 1)
        self.assertTrue(loaded.is_expired(now=loaded.expires_at))
        stored = json.loads(self.path.read_text())["profiles"]["dev"]
        self.assertRegex(stored["acquired_at"], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\+08:00$")
        self.assertRegex(stored["expires_at"], r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\+08:00$")

    def test_delete_only_current_profile(self):
        for profile in ("dev", "test"):
            self.store.save(
                Credentials.create(
                    profile=profile,
                    cookie=f"session={profile}",
                    csrftoken=f"csrf-{profile}",
                    username="jack",
                    ttl_seconds=1800,
                )
            )
        self.store.delete("dev")
        self.assertIsNone(self.store.load("dev"))
        self.assertIsNotNone(self.store.load("test"))

    def test_legacy_numeric_times_are_read_and_rewritten_as_beijing_strings(self):
        legacy = Credentials(
            profile="dev", cookie="old", csrftoken="csrf", username="jack",
            acquired_at=1_700_000_000, expires_at=1_700_001_800,
        )
        data = legacy.to_dict()
        data["acquired_at"] = legacy.acquired_at
        data["expires_at"] = legacy.expires_at
        self.path.write_text(json.dumps({"profiles": {"dev": data}}))

        loaded = self.store.load("dev")
        self.assertEqual((loaded.acquired_at, loaded.expires_at),
                         (legacy.acquired_at, legacy.expires_at))
        stored = json.loads(self.path.read_text())["profiles"]["dev"]
        self.assertEqual(stored["acquired_at"], "2023-11-15 06:13:20+08:00")
        self.assertEqual(stored["expires_at"], "2023-11-15 06:43:20+08:00")

    def test_extend_only_current_credentials(self):
        original = Credentials.create("dev", "old", "csrf", "jack", 60)
        self.store.save(original)
        extended = self.store.extend_if_current(original, 1800)
        self.assertGreater(extended.expires_at, original.expires_at + 1000)
        replacement = Credentials.create("dev", "new", "csrf", "jack", 60)
        self.store.save(replacement)
        self.store.extend_if_current(original, 1800)
        self.assertEqual(self.store.load("dev").cookie, "new")

if __name__ == "__main__":
    unittest.main()
