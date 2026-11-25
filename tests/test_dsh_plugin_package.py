import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_dsh_plugin as builder


class BundleTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory(prefix="wiserec-bundle-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.plugin = self.root / "source"
        shutil.copytree(builder.PLUGIN, self.plugin, ignore=shutil.ignore_patterns("dist", "__pycache__"))
        self.settings = self.plugin / "config.json"
        self.base = json.loads(self.settings.read_text(encoding="utf-8"))
        reset = patch.object(builder, "PLUGIN", self.plugin)
        credentials = patch.dict("os.environ", {"DSH_TELEMETRY_INGEST_TOKEN": ""})
        reset.start()
        credentials.start()
        self.addCleanup(reset.stop)
        self.addCleanup(credentials.stop)

    def write(self, **fields):
        self.settings.write_text(json.dumps({**self.base, "build": fields}), encoding="utf-8")

    def build(self, bundle_only=True):
        return builder.build(self.root / "dist", "a" * 40, bundle_only=bundle_only)

    def entries(self, data):
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            return {entry.name.removeprefix("package/"): archive.extractfile(entry).read() for entry in archive}

    def test_install_docs_ship_in_the_bundle_and_keep_the_short_notice(self):
        readme_path = self.plugin / "INSTALL.md"
        readme = readme_path.read_bytes()
        title, notice, features, *sections = readme_path.read_text(encoding="utf-8").strip().split("\n\n")
        self.assertTrue(title.startswith("# "))
        self.assertIn("申请使用权限，审批通过后即可使用", notice)
        self.assertIn("平台会记录使用情况", notice)
        guide = "\n\n".join(sections)
        for phrase in ("多个会话各自绑定", "自动保活", "会话标题", "登录与保活状态", "ml env use", "ml auth ping status"):
            self.assertIn(phrase, guide)
        self.assertNotRegex(readme.decode("utf-8"), r"遥测|上报|上传|Langfuse")
        for include in (True, False):
            with self.subTest(include_telemetry=include):
                self.write(includeTelemetry=include, telemetryEndpoint="https://telemetry.fixture.test/v1/traces")
                bundle = self.build()
                files = self.entries(bundle.read_bytes())
                self.assertEqual(files["README.md"], readme)
                self.assertEqual(json.loads(files["package.json"])["description"], notice + features)
                self.assertNotIn("INSTALL.md", files)
                self.assertNotRegex(readme.decode("utf-8"), r"遥测|上报|上传|Langfuse")
                with zipfile.ZipFile(self.build(bundle_only=False)) as wrapper:
                    self.assertEqual(wrapper.read("README.md"), readme)

    def test_default_full_writes_endpoint_and_keeps_host_packages_external(self):
        endpoint = "https://telemetry.fixture.test/v1/traces"
        self.write(telemetryEndpoint=endpoint, telemetryContentEnvironments=["sit"])
        with patch.dict("os.environ", {"DSH_TELEMETRY_INGEST_TOKEN": "fixture-token"}):
            full = self.build()
            wrapper = self.build(bundle_only=False)
        files = self.entries(full.read_bytes())
        manifest = json.loads(files["package.json"])
        metadata = json.loads(files["release.json"])
        self.assertTrue(metadata["includeTelemetry"])
        self.assertTrue(set(builder.TELEMETRY_FILES) <= files.keys())
        self.assertIn("session-title.js", files)
        self.assertEqual(manifest["exports"]["./telemetry"], "./telemetry/index.js")
        self.assertNotIn("dependencies", manifest)
        self.assertFalse(any("node_modules" in filename for filename in files))
        self.assertNotIn("build", json.loads(files["config.json"]))
        self.assertIn(b'session-telemetry-otel\n  disabled: true', files["cordis.patch.yml"])
        self.assertIn(endpoint.encode(), files["cordis.patch.yml"])
        self.assertIn(b'contentEnvironments: ["sit"]', files["cordis.patch.yml"])
        self.assertIn(b'fixture-token', files["cordis.patch.yml"])
        self.assertNotIn(b'fixture-token', files["release.json"])
        with zipfile.ZipFile(wrapper) as archive:
            bundled = archive.read(full.name)
            self.assertEqual(bundled, full.read_bytes())
            manifest = json.loads(archive.read("release.json"))
            self.assertEqual(manifest["bundle_sha256"], hashlib.sha256(bundled).hexdigest())
            self.assertTrue(manifest["includeTelemetry"])

        changed = "https://changed.fixture.test/v1/traces"
        self.write(includeTelemetry=True, telemetryEndpoint=changed, telemetryContentEnvironments=["*"])
        update = self.entries(self.build().read_bytes())
        self.assertIn(changed.encode(), update["cordis.patch.yml"])
        self.assertIn(b'contentEnvironments: ["*"]', update["cordis.patch.yml"])
        self.assertNotIn(endpoint.encode(), update["cordis.patch.yml"])

    def test_keepalive_build_ignores_telemetry_and_preserves_base_bundle(self):
        self.write(includeTelemetry=True, telemetryEndpoint="https://telemetry.fixture.test/v1/traces")
        full = self.build()
        self.write(includeTelemetry=False, telemetryEndpoint="not a URL", telemetryContentEnvironments=42)
        with patch.dict("os.environ", {"DSH_TELEMETRY_INGEST_TOKEN": "invalid token"}):
            keepalive = self.build()
        self.assertNotEqual(full.parent, keepalive.parent)
        files = self.entries(keepalive.read_bytes())
        self.assertIn("session-title.js", files)
        self.assertFalse(json.loads(files["release.json"])["includeTelemetry"])
        self.assertFalse(any(filename.startswith("telemetry/") for filename in files))
        self.assertNotIn("./telemetry", json.loads(files["package.json"])["exports"])
        self.assertNotIn("build", json.loads(files["config.json"]))
        self.assertEqual(files["cordis.patch.yml"], (self.plugin / "cordis.patch.yml").read_bytes())
        self.assertNotIn(b"not a URL", b"".join(files.values()))

    def test_invalid_build_values_do_not_create_artifacts(self):
        for config in (
            {"includeTelemetry": "false"},
            {"includeTelemetry": True},
            {"telemetryEndpoint": "https://auth:private@telemetry.fixture.test/v1/traces"},
            {"telemetryEndpoint": "https://telemetry.fixture.test/v1/traces?private=value"},
            {"telemetryEndpoint": "not-a-url"},
            {"telemetryEndpoint": "https://telemetry.fixture.test:invalid/v1/traces"},
            {"telemetryEndpoint": "https://telemetry.fixture.test/v1/logs"},
            {"telemetryEndpoint": "https://telemetry.fixture.test/v1/traces", "telemetryContentEnvironments": "sit"},
            {"telemetryEndpoint": "http://telemetry.fixture.test/v1/traces", "telemetryContentEnvironments": ["sit"]},
            {"telemetryEndpoint": "http://telemetry.fixture.test/v1/traces", "telemetryContentEnvironments": ["*"]},
            {"telemetryEndpoint": "https://telemetry.fixture.test/v1/traces", "telemetryContentEnvironments": ["*", "sit"]},
        ):
            with self.subTest(config=config):
                self.write(**config)
                with self.assertRaises(ValueError):
                    self.build()
                self.assertFalse((self.root / "dist").exists())


if __name__ == "__main__":
    unittest.main()
