"""Package the WiseRec platform Skill for the business Skill installer."""

import argparse
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[2]
SKILL_NAME = "wiserec-platform"
RESOURCE_PREFIX = f"skills/{SKILL_NAME}/"

sys.path.insert(0, str(ROOT / "scripts"))
from stage_skill_resources import stage_skill_resources
from sync_versions import read_versions


def build(output_dir: Path, include_kb: bool) -> Path:
    version = read_versions(ROOT)[0]["cli_go"]
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{SKILL_NAME}.zip"

    # Build beside the destination so a failed build leaves any previous ZIP intact.
    with TemporaryDirectory(prefix=".build-platform-skill-", dir=output_dir) as work:
        work = Path(work)
        resources = work / "resources"
        files = stage_skill_resources(ROOT, resources, version, kb_enabled=include_kb)
        staged_zip = work / output.name
        with ZipFile(staged_zip, "w", ZIP_DEFLATED) as archive:
            archive.mkdir(SKILL_NAME)
            for relative in files:
                if relative.startswith(RESOURCE_PREFIX):
                    name = relative.removeprefix("skills/")
                    archive.write(resources / relative, name)
        staged_zip.replace(output)

    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "skill-business")
    parser.add_argument("--include-kb", action="store_true", help="Include the shared Wiki instructions.")
    args = parser.parse_args()
    try:
        output = build(args.output_dir, args.include_kb)
    except (OSError, ValueError) as exc:
        print(f"Could not build the platform Skill ZIP: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
