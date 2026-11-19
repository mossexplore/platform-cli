"""Stage the shared Skill and metadata for the portable ZIP and MSI."""

import argparse
import json
from pathlib import Path
import shutil
import sys
from uuid import UUID, uuid5
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[3]
INSTALLER_NAMESPACE = UUID("432c0a6c-7def-4b10-b19f-baebdd4e5fe9")
sys.path.insert(0, str(ROOT / "scripts"))
from stage_skill_resources import stage_skill_resources
from sync_versions import sync_go


def stage(work, include_msi):
    version = sync_go(ROOT)
    payload = work / "payload"
    payload.mkdir()
    resources = stage_skill_resources(ROOT, payload / "agent", version)
    shutil.copyfile(ROOT / "cli-go/README.md", payload / "README.md")
    shutil.copyfile(ROOT / "LICENSE", payload / "LICENSE")
    (payload / "release.json").write_text(json.dumps({
        "component": "cli_go", "version": version, "platform": "windows", "architecture": "amd64",
    }, indent=2) + "\n", encoding="utf-8")
    if include_msi:
        with ZipFile(work / "agent-resources.zip", "w", ZIP_DEFLATED) as archive:
            for relative in resources:
                archive.write(payload / "agent" / relative, relative)
    # Keep product identities stable for MSI maintenance and distinct across upgrades.
    return {"version": version, "productCode": installer_guid(version)}


def installer_guid(name):
    return "{" + str(uuid5(INSTALLER_NAMESPACE, name)).upper() + "}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--msi", action="store_true")
    args = parser.parse_args()
    print(json.dumps(stage(args.work, args.msi)))
