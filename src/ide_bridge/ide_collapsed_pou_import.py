# -*- coding: utf-8 -*-
"""Import collapsed POUs (function blocks) and all projected children via text API only."""

from __future__ import print_function

import json
import os
import re

import ide_apply_patch as _iap
from ide_runtime_common import normalize_guid, object_name

METHOD_TYPE_GUID = "f8a58466-d7f6-439f-bbb8-d4600e41d099"
ACTION_TYPE_GUID = "8ac092e5-3128-4e26-9e7e-11016c6684f2"
PROPERTY_TYPE_GUID = "5a3b8626-d3e9-4f37-98b5-66420063d91e"
PROPERTY_ACCESSOR_TYPE_GUID = "792f2eb6-721e-4e64-ba20-bc98351056db"

_KIND_TYPE_GUID = {
    "method": METHOD_TYPE_GUID,
    "action": ACTION_TYPE_GUID,
    "property": PROPERTY_TYPE_GUID,
    "property_accessor": PROPERTY_ACCESSOR_TYPE_GUID,
}


def _read_text(path):
    with open(path, "r") as handle:
        return handle.read()


def _split_st_content(content):
    marker = "// --- implementation ---"
    normalized = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    if marker in normalized:
        parts = normalized.split(marker, 1)
        decl = parts[0].strip()
        impl = parts[1].strip()
        for end_kw in ("END_FUNCTION_BLOCK", "END_FUNCTION", "END_PROGRAM"):
            if impl.rstrip().endswith(end_kw):
                impl = impl.rstrip()[: -len(end_kw)].rstrip()
                break
        return decl, impl
    return normalized.strip(), ""


def _detect_st_kind(content):
    text = re.sub(r"\(\*[\s\S]*?\*\)", "", content or "")
    text = re.sub(r"//.*", "", text)
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        word = line.split()[0].upper()
        if word == "METHOD":
            return "method"
        if word == "ACTION":
            return "action"
        if word == "PROPERTY":
            return "property"
    return "method"


def family_name_from_st_path(path):
    basename = os.path.splitext(os.path.basename(str(path or "").replace("\\", "/")))[0]
    if not basename:
        return None
    if "." in basename:
        return basename.rsplit(".", 1)[0]
    return basename


def _family_from_report_object(obj):
    for candidate in (obj.get("view_path"), obj.get("path")):
        if not candidate:
            continue
        family = family_name_from_st_path(candidate)
        if family:
            return family
    return None


def collapsed_pou_ancestor(obj):
    current = obj
    while current is not None:
        try:
            if hasattr(current, "create_method"):
                return current
        except Exception:
            pass
        try:
            current = current.parent
        except Exception:
            break
    return None


def collect_affected_families(
    project, patch_root, text_creates=None, compare_report_path=None, view_root=None
):
    families = {}
    for entry in text_creates or []:
        parent_name = entry.get("parent_name")
        if parent_name:
            families[str(parent_name).lower()] = str(parent_name)
            continue
        family = family_name_from_st_path(entry.get("path"))
        if family:
            families[family.lower()] = family

    if patch_root is not None:
        guid_map = _iap._build_guid_map(project)
        for guid in _iap._patch_object_guids(patch_root):
            obj = guid_map.get(guid)
            if obj is None:
                continue
            ancestor = collapsed_pou_ancestor(obj)
            if ancestor is not None:
                name = object_name(ancestor)
                if name:
                    families[name.lower()] = name
            elif hasattr(obj, "create_method"):
                name = object_name(obj)
                if name:
                    families[name.lower()] = name

    if compare_report_path and os.path.exists(compare_report_path):
        try:
            report = json.loads(_read_text(compare_report_path))
        except Exception:
            report = {}
        objects = report.get("objects") or {}
        for category in ("modified", "added", "deleted"):
            for obj in objects.get(category) or []:
                family = _family_from_report_object(obj)
                if family:
                    families[family.lower()] = family

    for family in _families_from_disk_view_gaps(view_root):
        families[family.lower()] = family

    return list(families.values())


def _families_from_disk_view_gaps(view_root):
    """Find collapsed POU families with .st/.xml sidecar mismatches on disk."""
    if not view_root or not os.path.isdir(view_root):
        return []

    families = {}
    for root, _dirs, files in os.walk(view_root):
        for filename in files:
            lower_name = filename.lower()
            if lower_name.endswith(".st"):
                base_name = os.path.splitext(filename)[0]
                if "." not in base_name:
                    continue
                xml_name = base_name + ".xml"
                if not os.path.isfile(os.path.join(root, xml_name)):
                    rel_path = os.path.relpath(
                        os.path.join(root, filename), view_root
                    ).replace(os.sep, "/")
                    family = family_name_from_st_path(rel_path)
                    if family:
                        families[family.lower()] = family
                continue
            if not lower_name.endswith(".xml"):
                continue
            if lower_name == ".cds-object.xml":
                continue
            base_name = os.path.splitext(filename)[0]
            if "." not in base_name or base_name.startswith("."):
                continue
            st_name = base_name + ".st"
            if os.path.isfile(os.path.join(root, st_name)):
                continue
            rel_path = os.path.relpath(
                os.path.join(root, filename), view_root
            ).replace(os.sep, "/")
            family = family_name_from_st_path(rel_path)
            if family:
                families[family.lower()] = family
    return list(families.values())


def _parse_child_st_name(parent_name, base_name):
    prefix = parent_name + "."
    if not base_name.lower().startswith(prefix.lower()):
        return None
    tail = base_name[len(prefix) :]
    if re.search(r"\.(Get|Set)$", tail, re.IGNORECASE):
        prop_name, accessor = tail.rsplit(".", 1)
        return {
            "name": accessor,
            "kind": "property_accessor",
            "parent_name": prop_name,
        }
    return {
        "name": tail,
        "kind": None,
        "parent_name": parent_name,
    }


def iter_family_st_files(view_root, parent_name):
    parent_lower = parent_name.lower()
    if not view_root or not os.path.isdir(view_root):
        return []

    entries = []
    for root, _dirs, files in os.walk(view_root):
        for filename in files:
            if not filename.lower().endswith(".st"):
                continue
            base_name = os.path.splitext(filename)[0]
            rel_path = os.path.relpath(
                os.path.join(root, filename), view_root
            ).replace(os.sep, "/")
            if base_name.lower() == parent_lower:
                entries.append(
                    {
                        "path": rel_path,
                        "is_parent": True,
                        "name": parent_name,
                        "kind": "pou",
                        "parent_name": "",
                    }
                )
                continue
            child_info = _parse_child_st_name(parent_name, base_name)
            if child_info is None:
                continue
            full_path = os.path.join(view_root, rel_path.replace("/", os.sep))
            if not os.path.isfile(full_path):
                continue
            content = _read_text(full_path)
            kind = child_info.get("kind") or _detect_st_kind(content)
            entry = {
                "path": rel_path,
                "is_parent": False,
                "name": child_info["name"],
                "kind": kind,
                "parent_name": child_info.get("parent_name") or parent_name,
            }
            if kind in _KIND_TYPE_GUID:
                entry["type_guid"] = _KIND_TYPE_GUID[kind]
            entries.append(entry)
    entries.sort(key=lambda item: (0 if item.get("is_parent") else 1, item.get("path", "")))
    return entries


def _collect_object_guids(obj):
    guids = []
    normalized = normalize_guid(getattr(obj, "guid", ""))
    if normalized:
        guids.append(normalized)
    try:
        children = obj.get_children(recursive=True)
    except Exception:
        children = []
    for child in children or []:
        child_guid = normalize_guid(getattr(child, "guid", ""))
        if child_guid:
            guids.append(child_guid)
    return guids


def _find_parent_object(project, parent_name):
    parent_lower = str(parent_name or "").lower()
    if not parent_lower:
        return None
    for obj in _iap._build_guid_map(project).values():
        if object_name(obj).lower() == parent_lower:
            return obj
    return None


def apply_collapsed_families(project, view_root, family_names, log_fn=None):
    log = log_fn or print
    excluded_guids = set()
    updated_names = []
    skipped_create_paths = set()
    disk_cleanup_entries = []

    for parent_name in family_names or []:
        parent_obj = _find_parent_object(project, parent_name)
        if parent_obj is None:
            log("Collapsed POU family skipped, parent not found: " + str(parent_name))
            continue

        excluded_guids.update(_collect_object_guids(parent_obj))
        entries = iter_family_st_files(view_root, parent_name)
        if not entries:
            log("Collapsed POU family has no .st files on disk: " + str(parent_name))
            continue

        created_by_name = {parent_name.lower(): parent_obj}
        container, container_chain = None, None

        for entry in entries:
            full_path = os.path.join(
                view_root, str(entry["path"]).replace("/", os.sep)
            )
            if not os.path.isfile(full_path):
                continue
            content = _read_text(full_path)
            decl, impl = _split_st_content(content)
            payload = {
                "path": entry["path"],
                "name": entry["name"],
                "kind": entry["kind"],
                "parent_name": entry.get("parent_name") or "",
                "type_guid": entry.get("type_guid", ""),
                "declaration": decl,
                "implementation": impl,
            }
            skipped_create_paths.add(entry["path"])

            if entry.get("is_parent"):
                if _iap._apply_textual_patch(parent_obj, payload):
                    updated_names.append(entry["name"])
                continue

            if container is None:
                container, container_chain = _iap._ensure_container_path_with_chain(
                    project, entry["path"]
                )
            target_parent = created_by_name.get(
                str(entry.get("parent_name") or parent_name).lower()
            )
            if target_parent is None:
                target_parent = _iap._find_child_transparent(
                    container or parent_obj, entry.get("parent_name") or parent_name
                )
            if target_parent is None:
                target_parent = parent_obj
            child = _iap._find_child_transparent(target_parent, entry["name"])
            if child is None:
                child = _iap._create_text_object(
                    target_parent, payload, container_chain=container_chain
                )
            if child is None:
                log(
                    "Collapsed POU child not applied: {0}.{1}".format(
                        parent_name, entry["name"]
                    )
                )
                continue
            if _iap._apply_textual_patch(child, payload):
                updated_names.append(entry["name"])
            created_by_name[object_name(child).lower()] = child

        disk_child_names = {
            entry["name"].lower()
            for entry in entries
            if not entry.get("is_parent")
        }
        sample_dir = os.path.dirname(entries[0]["path"]).replace("\\", "/")
        if hasattr(parent_obj, "create_method"):
            for child in list(_iap._children_of(parent_obj)):
                child_name = object_name(child)
                if not child_name or child_name.lower() in disk_child_names:
                    continue
                if hasattr(child, "remove"):
                    try:
                        child.remove()
                        log(
                            "Removed IDE child missing from disk: {0}.{1}".format(
                                parent_name, child_name
                            )
                        )
                    except Exception as error:
                        log(
                            "Could not remove IDE child {0}.{1}: {2}".format(
                                parent_name, child_name, error
                            )
                        )
                        continue
                rel_base = "{0}/{1}.{2}".format(sample_dir, parent_name, child_name)
                disk_cleanup_entries.append(
                    {
                        "guid": normalize_guid(getattr(child, "guid", "")),
                        "name": child_name,
                        "parent_name": parent_name,
                        "path": rel_base + ".st",
                    }
                )

        excluded_guids.update(_collect_object_guids(parent_obj))
        log(
            "Collapsed POU family imported as text: {0} ({1} file(s))".format(
                parent_name, len(entries)
            )
        )

    return {
        "excluded_guids": excluded_guids,
        "updated_names": updated_names,
        "skipped_create_paths": skipped_create_paths,
        "disk_cleanup_entries": disk_cleanup_entries,
    }
