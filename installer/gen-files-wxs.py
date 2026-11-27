#!/usr/bin/env python3
"""Generate build-time WiX inputs for the reZonator2 MSI installer.

Usage (run from the repository root, e.g. in CI):
    python installer/gen-files-wxs.py .

Outputs (both are build-time artefacts, not committed):
  installer/files.wxs    - <Fragment> with a <DirectoryRef> mirroring deploy/
                           (one <Component> per file) and a <ComponentGroup>
                           named AppFiles referenced by reZonator2.wxs.
  installer/license.rtf  - RTF version of the LICENSE file, referenced by the
                           WixUI license dialog (WixVariable WixUILicenseRtf).

The file list is generated at build time (instead of committed) so the MSI
always matches whatever deploy/ actually contains (Qt DLLs, help files,
python312.dll/zip, ...). Component Ids are deterministic (derived from the
relative path), Guid="*" lets WiX generate stable GUIDs, and every component
is Bitness="always64" (the package is x64-only, -arch x64).
"""

import os
import re
import sys
import xml.etree.ElementTree as ET

NS = "http://wixtoolset.org/schemas/v4/wxs"
ET.register_namespace("", NS)


def sanitize(value):
    """Make a string usable as a WiX Id: [A-Za-z_][A-Za-z0-9_.]*, <= 72 chars."""
    value = re.sub(r"[^A-Za-z0-9_.]", "_", value)
    if value and value[0].isdigit():
        value = "_" + value
    return value[:72]


def unique_ids(names):
    """Deduplicate sanitized Ids by appending a counter on collision."""
    seen = {}
    out = []
    for name in names:
        base = sanitize(name)
        if base not in seen:
            seen[base] = 0
            out.append(base)
        else:
            seen[base] += 1
            out.append(sanitize("%s_%d" % (base, seen[base])))
    return out


def build_files_fragment(deploy_dir):
    """Walk deploy_dir and return (fragment_element, file_count)."""
    entries = []  # (rel_dir, filename) sorted deterministically
    for root, dirs, files in os.walk(deploy_dir):
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(root, name)
            rel = os.path.relpath(full, deploy_dir)
            rel_dir = os.path.dirname(rel)
            entries.append((rel_dir, name))
    entries.sort(key=lambda e: (e[0], e[1]))

    # Component / File Ids, deterministic from the relative path.
    comp_ids = unique_ids(
        "cmp_" + (d + "_" + f if d else f) for d, f in entries
    )
    file_ids = unique_ids(
        "fil_" + (d + "_" + f if d else f) for d, f in entries
    )

    fragment = ET.Element("{%s}Fragment" % NS)
    dir_ref = ET.SubElement(fragment, "{%s}DirectoryRef" % NS, {"Id": "INSTALLFOLDER"})
    group = ET.SubElement(fragment, "{%s}ComponentGroup" % NS, {"Id": "AppFiles"})

    # Nested <Directory> elements mirroring deploy/ subdirectories.
    dir_elements = {"": dir_ref}
    dir_id_seen = {}

    def directory_element(rel_dir):
        if rel_dir in dir_elements:
            return dir_elements[rel_dir]
        parent_rel = os.path.dirname(rel_dir)
        parent = directory_element(parent_rel)
        base = os.path.basename(rel_dir)
        did = "dir_" + rel_dir.replace(os.sep, "_")
        did = sanitize(did)
        if did in dir_id_seen:
            dir_id_seen[did] += 1
            did = sanitize("%s_%d" % (did, dir_id_seen[did]))
        else:
            dir_id_seen[did] = 0
        elem = ET.SubElement(
            parent, "{%s}Directory" % NS, {"Id": did, "Name": base}
        )
        dir_elements[rel_dir] = elem
        return elem

    for (rel_dir, name), comp_id, file_id in zip(entries, comp_ids, file_ids):
        parent = directory_element(rel_dir)
        comp = ET.SubElement(
            parent,
            "{%s}Component" % NS,
            {"Id": comp_id, "Guid": "*", "Bitness": "always64"},
        )
        # Source is resolved at build time: -d DeployDir=deploy (repo root).
        source = "$(var.DeployDir)" + "\\" + os.path.join(rel_dir, name).replace(
            os.sep, "\\"
        ) if rel_dir else "$(var.DeployDir)" + "\\" + name
        ET.SubElement(
            comp,
            "{%s}File" % NS,
            {"Id": file_id, "KeyPath": "yes", "Source": source},
        )
        ET.SubElement(group, "{%s}ComponentRef" % NS, {"Id": comp_id})

    return fragment, len(entries)


def build_license_rtf(license_path):
    """Convert the plain-text LICENSE file to a minimal RTF document."""
    with open(license_path, "r", encoding="utf-8") as fh:
        text = fh.read()
    # RTF escapes: backslash, braces; non-ASCII as \uN? (LICENSE is ASCII).
    text = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    lines = text.split("\n")
    body = "\\par\n".join(lines)
    return (
        "{\\rtf1\\ansi\\ansicpg1252\\deff0"
        "{\\fonttbl{\\f0\\fnil\\fcharset0 Tahoma;}}\n"
        "\\viewkind4\\uc1\\pard\\f0\\fs20 " + body + "\\par\n}"
    )


def main():
    if len(sys.argv) != 2:
        print("usage: gen-files-wxs.py <repo-root>", file=sys.stderr)
        return 2
    root = sys.argv[1]
    deploy_dir = os.path.join(root, "deploy")
    installer_dir = os.path.join(root, "installer")
    if not os.path.isdir(deploy_dir):
        print("deploy directory not found: %s" % deploy_dir, file=sys.stderr)
        return 1
    if not os.path.isdir(installer_dir):
        os.makedirs(installer_dir)

    fragment, count = build_files_fragment(deploy_dir)
    wxs = ET.Element("{%s}Wix" % NS)
    wxs.append(fragment)
    tree = ET.ElementTree(wxs)
    ET.indent(tree, space="  ")
    files_out = os.path.join(installer_dir, "files.wxs")
    tree.write(files_out, encoding="utf-8", xml_declaration=True)
    print("wrote %s (%d files)" % (files_out, count))

    license_path = os.path.join(root, "LICENSE")
    rtf_out = os.path.join(installer_dir, "license.rtf")
    with open(rtf_out, "w", encoding="utf-8", newline="") as fh:
        fh.write(build_license_rtf(license_path))
    print("wrote %s" % rtf_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
