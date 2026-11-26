"""Stage the shared, supported WiseRec Skill and slash command for installers."""

import hashlib
import json
import re


def stage_skill_resources(repository, resources, cli_version, kb_enabled=False):
    directory = repository / "skill/wiserec-platform"
    prefix = "skills/wiserec-platform/"
    sources = [
        (repository / "skill/commands/ml.md", "commands/ml.md"),
        (directory / "SKILL.md", prefix + "SKILL.md"),
        *((path, prefix + path.relative_to(directory).as_posix())
          for path in sorted((directory / "references").rglob("*.md"))),
    ]
    addon = repository / "skill/addons/kb"
    if kb_enabled:
        sources.append((addon / "references/kb.md", prefix + "references/kb.md"))
    contents = {}
    for source, relative in sources:
        text = source.read_text(encoding="utf-8")
        if relative == prefix + "references/commands.md":
            pattern = r"<!-- KB_START -->\n(.*?)<!-- KB_END -->\n?"
            text, count = re.subn(pattern, r"\1" if kb_enabled else "", text, flags=re.S)
            if count != 1:
                raise ValueError("Expected exactly one KB section")
            text = text.rstrip() + "\n"
        if kb_enabled and relative == prefix + "SKILL.md":
            text += "\n" + (addon / "skill_section.md").read_text(encoding="utf-8")
        contents[relative] = text.encode("utf-8")
    source_hashes = {relative: hashlib.sha256(data).hexdigest() for relative, data in contents.items()}
    source_digest = hashlib.sha256(json.dumps(
        source_hashes, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    hashes = {}
    for source, relative in sources:
        target = resources / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.name == "SKILL.md":
            text = contents[relative].decode("utf-8")
            if text.count("\nmetadata:\n") != 1:
                raise ValueError("Formal skill needs exactly one metadata mapping")
            text = text.replace("\nmetadata:\n", "\nmetadata:\n"
                                f'  source_cli_version: "{cli_version}"\n'
                                f'  source_sha256: "{source_digest}"\n', 1)
            target.write_bytes(text.encode("utf-8"))
        else:
            target.write_bytes(contents[relative])
        hashes[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
    (resources / "manifest.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    return hashes
