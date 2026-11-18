"""Stage the shared Skill and metadata for the portable ZIP and MSI."""

import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
from uuid import UUID, uuid5
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
INSTALLER_NAMESPACE = UUID("432c0a6c-7def-4b10-b19f-baebdd4e5fe9")
sys.path.insert(0, str(ROOT / "scripts"))
from stage_skill_resources import stage_skill_resources
from sync_versions import read_versions, sync


def stage(work, include_msi):
    sync(ROOT, check=True)
    version = read_versions(ROOT)[0]["cli_go"]
    payload = work / "payload"
    payload.mkdir()
    resources = stage_skill_resources(ROOT, payload / "agent", version)
    shutil.copyfile(ROOT / "cli-go/README.md", payload / "README.md")
    shutil.copyfile(ROOT / "LICENSE", payload / "LICENSE")
    (payload / "release.json").write_text(json.dumps({
        "component": "cli_go", "version": version, "platform": "windows", "architecture": "amd64",
    }, indent=2) + "\n", encoding="utf-8")
    if include_msi:
        write_agent_components(work / "agent.wxs", resources)
    # Keep product identities stable for MSI maintenance and distinct across upgrades.
    return {"version": version, "productCode": installer_guid(version)}


def write_agent_components(path, resources):
    wix = ET.Element("Wix", xmlns="http://wixtoolset.org/schemas/v4/wxs")
    fragment = ET.SubElement(wix, "Fragment")
    group = ET.SubElement(fragment, "ComponentGroup", Id="AgentResources")
    directories = {}

    def directory_for(root, parts):
        key = (root, *parts)
        if key not in directories:
            if not parts:
                directories[key] = ET.SubElement(fragment, "DirectoryRef", Id=root)
            else:
                parent = directory_for(root, parts[:-1])
                directories[key] = ET.SubElement(parent, "Directory", Id=identifier(key), Name=parts[-1])
        return directories[key]

    def component(root, parts, marker):
        directory = directory_for(root, parts)
        component_id = identifier((root, *parts, marker))
        # WiX requires an explicit GUID for components with files and HKCU key paths.
        obj = ET.SubElement(directory, "Component", Id=component_id, Guid=installer_guid("component:" + component_id))
        ET.SubElement(obj, "RegistryValue", Root="HKCU", Key=r"Software\WiseRec\CLIGo\AgentResources",
                      Name=component_id, Type="integer", Value="1", KeyPath="yes")
        ET.SubElement(group, "ComponentRef", Id=component_id)
        return obj

    for relative in resources:
        kind, *parts, name = PurePosixPath(relative).parts
        roots = ("SharedSkills", "CacSkills") if kind == "skills" else ("OpenCodeCommands", "CacCommands")
        for root in roots:
            obj = component(root, parts, name)
            # Refresh package-managed resources even if the old copy was edited.
            ET.SubElement(obj, "RemoveFile", Id="Old_" + obj.attrib["Id"], Name=name, On="install")
            ET.SubElement(obj, "File", Id="File_" + obj.attrib["Id"],
                          Source="$(var.Payload)\\agent\\" + relative.replace("/", "\\"))

    # Disable the legacy entry points without recursively deleting unrelated files.
    for root in ("SharedCommands", "OpenCodeCommands", "CacCommands"):
        obj = component(root, (), "legacy-command")
        ET.SubElement(obj, "RemoveFile", Name="ml-lab.md", On="install")
    for root in ("SharedSkills", "OpenCodeSkills", "CacSkills"):
        obj = component(root, ("wiserec-platform-detailed",), "legacy-skill")
        ET.SubElement(obj, "RemoveFile", Name="SKILL.md", On="install")
    obj = component("OpenCodeSkills", ("wiserec-platform",), "legacy-skill")
    ET.SubElement(obj, "RemoveFile", Name="SKILL.md", On="install")

    for root, *parts in list(directories):
        obj = component(root, parts, "folder")
        ET.SubElement(obj, "RemoveFolder", Id="Folder_" + obj.attrib["Id"], On="uninstall")

    ET.indent(wix)
    ET.ElementTree(wix).write(path, encoding="utf-8", xml_declaration=True)


def identifier(parts):
    return "R_" + sha256("/".join(parts).encode("utf-8")).hexdigest()[:32]


def installer_guid(name):
    return "{" + str(uuid5(INSTALLER_NAMESPACE, name)).upper() + "}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--msi", action="store_true")
    args = parser.parse_args()
    print(json.dumps(stage(args.work, args.msi)))
