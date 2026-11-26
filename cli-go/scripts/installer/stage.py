"""Stage the shared Skill and metadata for the portable ZIP and MSI."""

import argparse
import json
from pathlib import Path
import shutil
import sys
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from stage_skill_resources import stage_skill_resources
from sync_versions import sync_go


def stage(work, include_msi, config=None):
    version = sync_go(ROOT)
    payload = work / "payload"
    payload.mkdir()
    settings = json.loads(config.read_text(encoding="utf-8-sig")) if config else {}
    resources = stage_skill_resources(ROOT, payload / "agent", version,
                                      settings.get("knowledge_base", {}).get("enable") is True)
    shutil.copyfile(ROOT / "cli-go/README.md", payload / "README.md")
    shutil.copyfile(ROOT / "LICENSE", payload / "LICENSE")
    (payload / "release.json").write_text(json.dumps({
        "component": "cli_go", "version": version, "platform": "windows", "architecture": "amd64",
    }, indent=2) + "\n", encoding="utf-8")
    if include_msi:
        with ZipFile(work / "agent-resources.zip", "w", ZIP_DEFLATED) as archive:
            for relative in resources:
                archive.write(payload / "agent" / relative, relative)
    return {"version": version}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--msi", action="store_true")
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    print(json.dumps(stage(args.work, args.msi, args.config)))
