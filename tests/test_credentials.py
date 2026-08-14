import tempfile
import unittest
from pathlib import Path

from wisemlops_cli.credentials import CredentialStore
from wisemlops_cli.models import Credentials


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
        )
        self.store.save(credentials)
        loaded = self.store.load("dev")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.cookie, credentials.cookie)
        self.assertEqual(loaded.csrftoken, credentials.csrftoken)
        self.assertFalse(loaded.is_expired(now=credentials.acquired_at + 1799))
        self.assertTrue(loaded.is_expired(now=credentials.acquired_at + 1800))

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

    def test_migrates_legacy_credentials_without_deleting_source(self):
        legacy_path = Path(self.temporary.name) / "wo" / "credentials.json"
        new_path = Path(self.temporary.name) / "ml" / "credentials.json"
        legacy_store = CredentialStore(legacy_path)
        legacy_store.save(
            Credentials.create(
                profile="dev",
                cookie="legacy-cookie",
                csrftoken="legacy-csrf",
                username="jack",
                ttl_seconds=1800,
            )
        )

        migrated_store = CredentialStore(new_path, legacy_path=legacy_path)

        self.assertEqual(migrated_store.load("dev").cookie, "legacy-cookie")
        self.assertTrue(new_path.exists())
        self.assertTrue(legacy_path.exists())


if __name__ == "__main__":
    unittest.main()
