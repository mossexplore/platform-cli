"""Stage the shared, supported WiseRec Skill and slash command for installers."""

import hashlib
import json
from shutil import copyfile


def stage_skill_resources(repository, resources, cli_version):
    directory = repository / "skill/wiserec-platform"
    prefix = "skills/wiserec-platform/"
    sources = [
        (repository / "skill/commands/ml.md", "commands/ml.md"),
        (directory / "SKILL.md", prefix + "SKILL.md"),
        *((path, prefix + path.relative_to(directory).as_posix())
          for path in sorted((directory / "references").rglob("*.md"))),
    ]
    source_hashes = {relative: hashlib.sha256(source.read_bytes()).hexdigest()
                     for source, relative in sources}
    source_digest = hashlib.sha256(json.dumps(
        source_hashes, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    hashes = {}
    for source, relative in sources:
        target = resources / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.name == "SKILL.md":
            text = source.read_text(encoding="utf-8")
            if text.count("\nmetadata:\n") != 1:
                raise ValueError("Formal skill needs exactly one metadata mapping")
            text = text.replace("\nmetadata:\n", "\nmetadata:\n"
                                f'  source_cli_version: "{cli_version}"\n'
                                f'  source_sha256: "{source_digest}"\n', 1)
            target.write_text(text, encoding="utf-8")
        else:
            copyfile(source, target)
        hashes[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
    (resources / "manifest.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    return hashes
