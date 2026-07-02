# -*- coding: utf-8 -*-
"""
ide_apply_patch.pyw - Apply a prepared IMPORT.xml patch to the IDE.
Must be compatible with IronPython 2.7.
"""

from __future__ import print_function

import copy
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET

from ide_runtime_common import normalize_guid, object_name


def _normalize_line_endings(value):
    if value is None:
        return None
    return str(value).replace("\r\n", "\n").replace("\r", "\n")


class ApplyPatchResult(object):
    def __init__(self):
        self.success = True
        self.error = ""
        self.applied_guids = []
        self.native_guids = []
        self.textual_guids = []
        self.created_paths = []
        self.deleted_guids = []
        self.failed_guids = []
        self.failures = []

    def __nonzero__(self):
        return bool(self.success)

    def __bool__(self):
        return bool(self.success)

    def add_applied(self, guid, mode):
        guid = normalize_guid(guid)
        if guid and guid not in self.applied_guids:
            self.applied_guids.append(guid)
        if mode == "native" and guid and guid not in self.native_guids:
            self.native_guids.append(guid)
        if mode == "textual" and guid and guid not in self.textual_guids:
            self.textual_guids.append(guid)

    def add_created(self, path):
        path = str(path or "")
        if path and path not in self.created_paths:
            self.created_paths.append(path)

    def add_deleted(self, guid):
        guid = normalize_guid(guid)
        if guid and guid not in self.deleted_guids:
            self.deleted_guids.append(guid)

    def fail(self, error, guid=None):
        self.success = False
        self.error = str(error)
        normalized_guid = normalize_guid(guid)
        if normalized_guid and normalized_guid not in self.failed_guids:
            self.failed_guids.append(normalized_guid)
        self.failures.append(
            {
                "guid": normalized_guid,
                "error": self.error,
            }
        )
        return self

    def summary(self):
        parts = []
        if self.applied_guids:
            parts.append("applied={0}".format(len(self.applied_guids)))
        if self.created_paths:
            parts.append("created={0}".format(len(self.created_paths)))
        if self.deleted_guids:
            parts.append("deleted={0}".format(len(self.deleted_guids)))
        if self.failed_guids:
            parts.append("failed_guids={0}".format(",".join(self.failed_guids)))
        if self.error:
            parts.append("error=" + self.error)
        return "; ".join(parts) or ("success" if self.success else "failed")


def _parse_patch(patch_path):
    root = ET.parse(patch_path).getroot()
    return {
        "root": root,
        "guids": _patch_object_guids(root),
        "texts": _patch_text_by_guid(root),
        "build_attrs": _patch_build_attrs_by_guid(root),
        "text_creates": _text_create_entries(root),
        "text_deletes": _text_delete_entries(root),
    }


def _patch_object_guids(root):
    guids = []
    for elem in root.iter():
        if elem.attrib.get("Name") != "MetaObject":
            continue
        for child in list(elem):
            if child.attrib.get("Name") == "Guid" and child.text:
                guid = normalize_guid(child.text)
                if guid and guid not in guids:
                    guids.append(guid)
                break
    return guids


def _children(element):
    try:
        return list(element)
    except Exception:
        return []


def _named_child(element, name):
    for child in _children(element):
        if child.attrib.get("Name") == name:
            return child
    return None


def _named_descendant(element, name):
    for child in element.iter():
        if child.attrib.get("Name") == name:
            return child
    return None


def _local_name(tag):
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _text_lines_value(text_lines_elem):
    if text_lines_elem is None:
        return None
    lines = []
    for line_elem in _children(text_lines_elem):
        text_elem = _named_child(line_elem, "Text")
        if text_elem is not None:
            lines.append(text_elem.text or "")
    if not lines:
        return None
    return "\n".join(lines)


def _text_blob(section):
    if section is None:
        return None
    blob = _named_descendant(section, "TextBlobForSerialisation")
    if blob is not None:
        return blob.text or ""
    text_lines = _named_descendant(section, "TextLines")
    if text_lines is not None:
        value = _text_lines_value(text_lines)
        if value is not None:
            return value
    return None


def _patch_text_by_guid(root):
    result = {}
    for entry in root.iter():
        meta = _named_child(entry, "MetaObject")
        if meta is None:
            continue
        guid_elem = _named_child(meta, "Guid")
        if guid_elem is None or not guid_elem.text:
            continue
        obj_elem = _named_child(entry, "Object")
        if obj_elem is None:
            continue

        guid = normalize_guid(guid_elem.text)
        implementation = _text_blob(_named_child(obj_elem, "Implementation"))
        declaration = _text_blob(_named_child(obj_elem, "Interface"))
        if declaration is None:
            declaration = _text_blob(_named_child(obj_elem, "Declaration"))
        result[guid] = {
            "declaration": declaration,
            "implementation": implementation,
        }
    return result


def _text_create_entries(root):
    result = []
    for elem in root.iter():
        if _local_name(elem.tag) != "CreateTextObject":
            continue
        declaration = None
        implementation = None
        for child in list(elem):
            child_name = _local_name(child.tag)
            if child_name == "Declaration":
                declaration = child.text or ""
            elif child_name == "Implementation":
                implementation = child.text or ""
        result.append(
            {
                "path": elem.attrib.get("Path", ""),
                "name": elem.attrib.get("Name", ""),
                "kind": elem.attrib.get("Kind", ""),
                "type_guid": elem.attrib.get("TypeGuid", ""),
                "parent_name": elem.attrib.get("ParentName", ""),
                "declaration": declaration,
                "implementation": implementation,
            }
        )
    return result


def _text_delete_entries(root):
    result = []
    for elem in root.iter():
        if _local_name(elem.tag) != "DeleteTextObject":
            continue
        result.append(
            {
                "guid": elem.attrib.get("Guid", ""),
                "name": elem.attrib.get("Name", ""),
                "parent_name": elem.attrib.get("ParentName", ""),
                "path": elem.attrib.get("Path", ""),
            }
        )
    return result


def _related_view_paths(rel_path):
    normalized = str(rel_path or "").replace("\\", "/").strip()
    if not normalized:
        return []
    base, ext = os.path.splitext(normalized)
    ext = ext.lower()
    paths = [normalized]
    if ext == ".st":
        paths.append(base + ".xml")
    elif ext == ".xml":
        paths.append(base + ".st")
    return paths


def cleanup_deleted_view_files(view_root, manifest_path, delete_entries):
    """Remove deleted object view files from disk and prune manifest entries."""
    if not view_root or not delete_entries:
        return []

    removed = []
    guids_removed = set()
    for entry in delete_entries:
        guid = normalize_guid(entry.get("guid"))
        if guid:
            guids_removed.add(guid)
        for rel_path in _related_view_paths(entry.get("path")):
            full_path = os.path.join(view_root, rel_path.replace("/", os.sep))
            if os.path.isfile(full_path):
                try:
                    os.remove(full_path)
                    removed.append(rel_path)
                except Exception as error:
                    print(
                        "Warning: could not remove deleted view file {0}: {1}".format(
                            rel_path, error
                        )
                    )

    if not manifest_path or not os.path.isfile(manifest_path):
        return removed
    if not guids_removed and not removed:
        return removed

    removed_paths = set(str(path).replace("\\", "/") for path in removed)

    try:
        with open(manifest_path, "r") as handle:
            manifest = json.load(handle)
    except Exception:
        return removed

    kept = []
    for entry in manifest.get("entries", []) or []:
        entry_guid = normalize_guid(entry.get("guid"))
        entry_paths = set()
        for rel_path in _related_view_paths(entry.get("xml_path")):
            entry_paths.add(str(rel_path).replace("\\", "/"))
        for rel_path in entry.get("projection_paths") or []:
            entry_paths.add(str(rel_path).replace("\\", "/"))
        drop_entry = entry_guid in guids_removed or bool(
            entry_paths.intersection(removed_paths)
        )
        if drop_entry:
            for rel_path in _related_view_paths(entry.get("xml_path")):
                full_path = os.path.join(view_root, rel_path.replace("/", os.sep))
                if os.path.isfile(full_path):
                    try:
                        os.remove(full_path)
                        if rel_path not in removed:
                            removed.append(rel_path)
                    except Exception:
                        pass
            for rel_path in entry.get("projection_paths") or []:
                full_path = os.path.join(
                    view_root, str(rel_path).replace("/", os.sep)
                )
                if os.path.isfile(full_path):
                    try:
                        os.remove(full_path)
                        rel_text = str(rel_path).replace("\\", "/")
                        if rel_text not in removed:
                            removed.append(rel_text)
                    except Exception:
                        pass
            continue
        kept.append(entry)

    manifest["entries"] = kept
    try:
        with open(manifest_path, "w") as handle:
            json.dump(manifest, handle, indent=2)
    except Exception as error:
        print("Warning: could not update manifest after delete: {0}".format(error))
    return removed


def _bool_text(value):
    return str(value or "").strip().lower() == "true"


def _patch_build_attrs_by_guid(root):
    result = {}
    xml_to_attr = {
        "ExcludeFromBuild": "exclude_from_build",
        "LinkAlways": "link_always",
        "External": "external_implementation",
        "EnableSystemCall": "enable_system_call",
    }
    for entry in root.iter():
        meta = _named_child(entry, "MetaObject")
        if meta is None:
            continue
        guid_elem = _named_child(meta, "Guid")
        if guid_elem is None or not guid_elem.text:
            continue

        attrs = {}
        for xml_name, attr_name in xml_to_attr.items():
            elem = _named_descendant(meta, xml_name)
            if elem is not None and elem.text is not None:
                attrs[attr_name] = _bool_text(elem.text)

        if attrs:
            result[normalize_guid(guid_elem.text)] = attrs
    return result


def _entry_guid(entry):
    meta = _named_child(entry, "MetaObject")
    if meta is None:
        return ""
    guid_elem = _named_child(meta, "Guid")
    if guid_elem is None or not guid_elem.text:
        return ""
    return normalize_guid(guid_elem.text)


def _write_filtered_patch(source_root, target_guids):
    target = {}
    for guid in target_guids:
        target[normalize_guid(guid)] = True

    filtered_root = ET.Element(source_root.tag, source_root.attrib)

    for structured_view in list(source_root):
        filtered_view = copy.deepcopy(structured_view)
        entry_list = _named_descendant(filtered_view, "EntryList")
        if entry_list is None:
            continue

        kept = 0
        for entry in list(entry_list):
            if _entry_guid(entry) not in target:
                entry_list.remove(entry)
            else:
                kept += 1

        if kept:
            filtered_root.append(filtered_view)

    handle, filtered_path = tempfile.mkstemp(suffix=".xml")
    os.close(handle)
    ET.ElementTree(filtered_root).write(
        filtered_path, encoding="utf-8", xml_declaration=True
    )
    return filtered_path


def _write_patch_without_text_creates(source_root):
    filtered_root = copy.deepcopy(source_root)
    for child in list(filtered_root):
        local_name = _local_name(child.tag)
        if local_name in ("CreateTextObjects", "DeleteTextObjects"):
            filtered_root.remove(child)
    handle, filtered_path = tempfile.mkstemp(suffix=".xml")
    os.close(handle)
    ET.ElementTree(filtered_root).write(
        filtered_path, encoding="utf-8", xml_declaration=True
    )
    return filtered_path


def _filter_native_patch_root(source_root, exclude_guids=None):
    """Return a patch root suitable for import_native, minus text-only entries."""
    exclude = set()
    for guid in exclude_guids or []:
        normalized = normalize_guid(guid)
        if normalized:
            exclude.add(normalized)

    filtered_root = copy.deepcopy(source_root)
    for child in list(filtered_root):
        if _local_name(child.tag) in ("CreateTextObjects", "DeleteTextObjects"):
            filtered_root.remove(child)

    for structured_view in list(filtered_root):
        if _local_name(structured_view.tag) != "StructuredView":
            continue
        entry_list = _named_descendant(structured_view, "EntryList")
        if entry_list is None:
            continue
        kept = 0
        for entry in list(entry_list):
            if _entry_guid(entry) in exclude:
                entry_list.remove(entry)
            else:
                kept += 1
        if kept == 0:
            filtered_root.remove(structured_view)

    if len(list(filtered_root)) == 0:
        return None
    return filtered_root


def apply_textual_patches_from_patch(project, patch_root, exclude_guids=None):
    """Apply declaration/implementation updates via the text API.

    Returns GUIDs handled textually so callers can omit them from import_native.
    """
    exclude = set()
    for guid in exclude_guids or []:
        normalized = normalize_guid(guid)
        if normalized:
            exclude.add(normalized)

    guid_map = _build_guid_map(project)
    patch_guids = _patch_object_guids(patch_root)
    patch_texts = _patch_text_by_guid(patch_root)
    patch_build_attrs = _patch_build_attrs_by_guid(patch_root)
    handled = []

    for guid in patch_guids:
        if guid in exclude:
            continue
        obj = guid_map.get(guid)
        texts = patch_texts.get(guid)
        if obj is None or texts is None:
            continue
        if not _can_apply_textual_patch(obj, texts):
            continue
        text_updated = _apply_textual_patch(obj, texts)
        attrs_updated = _apply_build_attrs_patch(
            obj, patch_build_attrs.get(guid, {})
        )
        if text_updated or attrs_updated:
            handled.append(guid)
    return handled


def _build_guid_map(project):
    guid_map = {}
    try:
        objects = project.get_children(recursive=True)
    except Exception:
        return guid_map

    for obj in objects:
        try:
            guid = normalize_guid(obj.guid)
            if guid:
                guid_map[guid] = obj
        except Exception:
            pass
    return guid_map


def _children_of(obj):
    try:
        return obj.get_children()
    except Exception:
        return []


def _find_child_transparent(parent, name):
    name_lower = str(name or "").lower()
    if not name_lower:
        return None
    for child in _children_of(parent):
        if object_name(child).lower() == name_lower:
            return child
    for child in _children_of(parent):
        if object_name(child).lower() == "plc logic":
            for grandchild in _children_of(child):
                if object_name(grandchild).lower() == name_lower:
                    return grandchild
    return None


def _create_folder(parent, name):
    if hasattr(parent, "create_folder"):
        return parent.create_folder(name)
    folder_guid = "{738bea1e-99bb-4f04-90bb-a7a567e74e3a}"
    if hasattr(parent, "create_child"):
        return parent.create_child(name, _to_system_guid(folder_guid))
    return None


def _ensure_container_path_with_chain(project, rel_path):
    path = str(rel_path or "").replace("\\", "/")
    if "/" in path:
        path = path.rsplit("/", 1)[0]
    else:
        path = ""
    if not path or path == ".":
        return project, [project]

    current = project
    chain = [project]
    for part in path.split("/"):
        if not part or part.startswith("."):
            continue
        found = _find_child_transparent(current, part)
        if found is None:
            try:
                found = _create_folder(current, part)
            except Exception as e:
                print("Failed to create folder '{0}': {1}".format(part, e))
                found = None
            if found is None:
                found = _find_child_transparent(current, part)
        if found is None:
            return None, chain
        current = found
        chain.append(current)
    return current, chain


def _find_pou_type_enum():
    candidates = []
    try:
        candidates.append(PouType)
    except Exception:
        pass
    try:
        import __main__

        if hasattr(__main__, "PouType"):
            candidates.append(__main__.PouType)
    except Exception:
        pass
    try:
        from ScriptEngine import PouType as script_engine_pou_type

        candidates.append(script_engine_pou_type)
    except Exception:
        pass
    return candidates[0] if candidates else None


def _pou_type_name(declaration):
    text = str(declaration or "").lstrip().upper()
    if text.startswith("FUNCTION_BLOCK"):
        return "FunctionBlock"
    if text.startswith("FUNCTION"):
        return "Function"
    return "Program"


# Matches the return type in a 'FUNCTION <name> : <TYPE>' header line.
# <TYPE> is captured greedily so it covers STRING(80), qualified names
# (NS.TYPE), and arrays (ARRAY[..] OF X); trailing comments are stripped
# separately.  FUNCTION_BLOCK headers do not match (no ' : ' after name).
_FUNCTION_RETURN_RE = re.compile(
    r"^\s*FUNCTION\s+\w+\s*:\s*(.+?)\s*$", re.IGNORECASE
)


def _pou_return_type(declaration):
    """Extract the return type from a FUNCTION declaration header.

    Returns the type string (e.g. 'BOOL', 'STRING(80)', 'My.UserType') or
    None when the declaration has no scalar return type (a FUNCTION without
    a return type, or a non-FUNCTION POU).
    """
    text = str(declaration or "")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Skip leading pragmas / attributes / comments before the header.
        if line.startswith("{") or line.startswith("//") or line.startswith("(*"):
            continue
        match = _FUNCTION_RETURN_RE.match(line)
        if match is None:
            # First meaningful line is the header; if it has no ' : <type>'
            # (plain FUNCTION, FUNCTION_BLOCK, PROGRAM) there is no return type.
            return None
        return_type = match.group(1)
        # Drop any trailing line comment that follows the type.
        for marker in ("//", "(*"):
            idx = return_type.find(marker)
            if idx != -1:
                return_type = return_type[:idx]
        return_type = return_type.strip()
        return return_type or None
    return None


def _call_create_pou(container, name, pou_type, return_type=None):
    """Call container.create_pou, passing return_type only when given.

    The CODESYS signature is create_pou(name, type, return_type, ...); the
    parameter is required for FUNCTION POUs and rejected/ignored otherwise.
    Tries positional first, then keyword, for cross-version compatibility.
    """
    if return_type is None:
        return container.create_pou(name, pou_type)
    try:
        return container.create_pou(name, pou_type, return_type)
    except TypeError:
        return container.create_pou(name, pou_type, return_type=return_type)


def _create_pou(container, name, declaration):
    if not hasattr(container, "create_pou"):
        return None
    pou_type_enum = _find_pou_type_enum()
    if pou_type_enum is None:
        return None
    pou_type_name = _pou_type_name(declaration)
    pou_type = getattr(pou_type_enum, pou_type_name, None)
    if pou_type is None and pou_type_name == "FunctionBlock":
        pou_type = getattr(pou_type_enum, "Function_Block", None)
    if pou_type is None:
        pou_type = getattr(pou_type_enum, "Program", None)
    if pou_type is None:
        return None
    if pou_type_name == "Function":
        return_type = _pou_return_type(declaration)
        if not return_type:
            raise Exception(
                "Cannot create FUNCTION '{0}': no return type found in its "
                "declaration. Expected a header line 'FUNCTION {0} : <TYPE>'.".format(
                    name
                )
            )
        return _call_create_pou(container, name, pou_type, return_type)
    return _call_create_pou(container, name, pou_type)


# Multiple GUID candidates per kind, tried in order.
# Different CODESYS versions may use different type GUIDs for the same
# logical object type.  The first GUID that successfully creates an object
# wins.  A patch may provide an explicit TypeGuid (preferred), followed by
# built-in fallback candidates below.
KIND_TYPE_GUIDS = {
    "persistent_gvl": [
        "{3183921b-cc91-4712-9781-c3b6555122b5}",
        "{261bd6e6-249c-4232-bb6f-84c2fbeef430}",
    ],
    "task_local_gvl": [
        "{c2cda7a9-0ba4-4146-b563-22a42fa0eb72}",
    ],
    "property_accessor": [
        "{792f2eb6-721e-4e64-ba20-bc98351056db}",
    ],
}


def _find_create_container(container, create_method_name):
    """Walk up the parent chain to find a container that has the given create_* method."""
    visited = set()
    current = container
    while current is not None:
        if hasattr(current, create_method_name):
            return current
        obj_id = id(current)
        if obj_id in visited:
            break
        visited.add(obj_id)
        try:
            current = current.parent
        except Exception:
            break
    return None


def _create_container_candidates(container, container_chain=None, method_name=None):
    """Return likely create targets, deepest path container first.

    CODESYS IronPython objects may not report scripting methods reliably via
    hasattr/getattr.  Callers should still attempt the method and catch errors.
    """
    result = []
    seen = set()

    def add(candidate):
        if candidate is None:
            return
        obj_id = id(candidate)
        if obj_id in seen:
            return
        seen.add(obj_id)
        result.append(candidate)

    for candidate in reversed(list(container_chain or [])):
        add(candidate)

    current = container
    while current is not None:
        add(current)
        try:
            current = current.parent
        except Exception:
            break

    if method_name:
        target = _find_create_container(container, method_name)
        add(target)

    return result


def _to_system_guid(guid_string):
    """Convert a GUID string to System.Guid for CODESYS IronPython compatibility.

    In IronPython, create_child(name, type_guid) expects a System.Guid object
    rather than a plain Python string.  This helper tries the conversion and
    falls back to the raw string if System is unavailable (e.g. CPython).
    """
    try:
        import System
    except ImportError:
        return guid_string
    try:
        return System.Guid(guid_string.strip("{}"))
    except Exception:
        # System.Guid might reject the format; fall back to raw string.
        return guid_string


def _create_child_with_guid(target, name, guid_candidates):
    """Try create_child(name, type_guid) with each GUID candidate.

    The CODESYS IronPython API requires System.Guid for the type_guid
    parameter.  This helper attempts the call with each GUID (converting
    to System.Guid when necessary) and returns the first successful result.
    """
    if not isinstance(guid_candidates, (list, tuple)):
        guid_candidates = [guid_candidates]
    for guid_string in guid_candidates:
        guid_value = _to_system_guid(guid_string)
        try:
            obj = target.create_child(name, guid_value)
            if obj is not None:
                return obj
        except Exception:
            pass
    return None


def _create_text_object(container, entry, container_chain=None):
    kind = str(entry.get("kind") or "").lower()
    name = entry.get("name") or ""
    declaration = entry.get("declaration")
    type_guid = entry.get("type_guid") or ""

    if kind == "pou":
        obj = _create_pou(container, name, declaration)
        if obj is not None:
            return obj
    if kind == "gvl":
        target = _find_create_container(container, "create_gvl")
        if target is not None:
            return target.create_gvl(name)
    if kind in ("persistent_gvl", "task_local_gvl", "property_accessor"):
        # CODESYS Scripting API has no create_persistent / create_task_local_gvl method.
        # Use create_child(name, type_guid) with the appropriate type GUID,
        # walking up the parent chain to find a container that supports create_child.

        # Build candidate list: explicit TypeGuid first, then profile/create_type_guids,
        # then built-in fallbacks.
        candidates = []
        if type_guid:
            candidates.append(type_guid)
        for fallback in KIND_TYPE_GUIDS.get(kind) or []:
            if fallback not in candidates:
                candidates.append(fallback)

        for target in _create_container_candidates(
            container, container_chain, "create_child"
        ):
            obj = _create_child_with_guid(target, name, candidates)
            if obj is not None:
                return obj

        # Fallback for persistent_gvl: try known method name variants.
        if kind == "persistent_gvl":
            for method_name in (
                "create_persistentvars",
                "create_persistent",
                "create_persistent_variable_list",
            ):
                for target in _create_container_candidates(
                    container, container_chain, method_name
                ):
                    try:
                        method = getattr(target, method_name)
                        obj = method(name)
                        if obj is not None:
                            return obj
                    except Exception:
                        pass

    if kind == "dut":
        target = _find_create_container(container, "create_dut")
        if target is not None:
            return target.create_dut(name)
    if kind == "method" and hasattr(container, "create_method"):
        return container.create_method(name)
    if kind == "action" and hasattr(container, "create_action"):
        return container.create_action(name)
    if kind == "property" and hasattr(container, "create_property"):
        return container.create_property(name)
    raise Exception("Unsupported text object creation kind or API: {0}".format(kind))


def _apply_text_create(project, entry, created_by_name):
    container, container_chain = _ensure_container_path_with_chain(
        project, entry.get("path")
    )
    if container is None:
        raise Exception("Could not resolve container for {0}".format(entry.get("path")))

    parent_name = entry.get("parent_name")
    if parent_name:
        parent = created_by_name.get(str(parent_name).lower())
        if parent is None:
            parent = _find_child_transparent(container, parent_name)
        if parent is None:
            raise Exception(
                "Could not resolve parent POU '{0}' for {1}".format(
                    parent_name, entry.get("path")
                )
            )
        container = parent

    existing = _find_child_transparent(container, entry.get("name"))
    if existing is not None:
        obj = existing
    else:
        obj = _create_text_object(
            container,
            entry,
            container_chain=container_chain,
        )
    if obj is None:
        raise Exception(
            "CODESYS did not return created object for {0}".format(entry.get("path"))
        )

    _apply_textual_patch(obj, entry)
    created_by_name[object_name(obj).lower()] = obj
    print("Created textual object from: " + str(entry.get("path")))
    return True


def _apply_text_creates(project, text_creates, created_by_name, result):
    for entry in text_creates:
        try:
            _apply_text_create(project, entry, created_by_name)
            result.add_created(entry.get("path"))
        except Exception as error:
            print(
                "Error creating textual object {0}: {1}".format(
                    entry.get("path"), error
                )
            )
            return result.fail(error)
    return None


def _apply_text_delete(project, entry, guid_map):
    guid = normalize_guid(entry.get("guid"))
    name = entry.get("name") or ""
    parent_name = entry.get("parent_name") or ""

    obj = guid_map.get(guid) if guid else None
    if obj is None and parent_name:
        container, _ = _ensure_container_path_with_chain(
            project, entry.get("path") or ""
        )
        if container is not None:
            parent = _find_child_transparent(container, parent_name)
            if parent is not None:
                obj = _find_child_transparent(parent, name)
    if obj is None and name:
        name_lower = name.lower()
        for candidate in guid_map.values():
            if object_name(candidate).lower() == name_lower:
                obj = candidate
                break

    if obj is None:
        raise Exception(
            "Could not resolve object to delete: {0}".format(guid or name)
        )
    if not hasattr(obj, "remove"):
        raise Exception(
            "Object does not support remove(): {0}".format(object_name(obj))
        )
    obj.remove()
    print("Deleted textual object: " + str(guid or name))
    return guid or name


def _apply_text_deletes(project, text_deletes, guid_map, result):
    for entry in text_deletes:
        try:
            deleted = _apply_text_delete(project, entry, guid_map)
            result.add_deleted(deleted)
        except Exception as error:
            print(
                "Error deleting textual object {0}: {1}".format(
                    entry.get("guid") or entry.get("name"), error
                )
            )
            return result.fail(error, entry.get("guid"))
    return None


def _replace_text_document(doc, value):
    if doc is None:
        return False
    value = _normalize_line_endings(value or "")
    try:
        current = _normalize_line_endings(getattr(doc, "text", None) or "")
    except Exception:
        current = ""
    if current == value:
        return False
    try:
        doc.text = value
    except Exception:
        try:
            doc.replace(value)
        except Exception:
            return False
    try:
        return _normalize_line_endings(getattr(doc, "text", None) or "") == value
    except Exception:
        return True


def _patch_has_text_lines(root):
    for elem in root.iter():
        if elem.attrib.get("Name") == "TextLines":
            return True
    return False


def _compare_report_by_guid(report_path):
    try:
        with open(report_path, "r") as handle:
            report = json.load(handle)
    except Exception:
        return {}
    index = {}
    objects = report.get("objects") or {}
    for category in ("modified", "added"):
        for obj in objects.get(category) or []:
            guid = normalize_guid(obj.get("guid", ""))
            if guid:
                index[guid] = obj
    return index


def _st_projection_path_from_report_obj(obj):
    if not obj:
        return ""
    paths = obj.get("projection_changed_paths") or []
    if paths:
        return str(paths[0]).replace("\\", "/")
    projection_diff = obj.get("projection_diff") or {}
    return str(projection_diff.get("path") or "").replace("\\", "/")


def _apply_st_content_to_object(obj, content, log_fn=None):
    log = log_fn or print
    decl, impl = _split_st_update_content(_normalize_line_endings(content))
    payload = {"declaration": decl or None, "implementation": impl or None}
    if not _can_apply_textual_patch(obj, payload):
        log(
            "Object has no text API for: {0}".format(
                object_name(obj) or getattr(obj, "guid", "")
            )
        )
        return False
    updated = _apply_textual_patch(obj, payload)
    if not updated:
        log(
            "Text API apply made no change for: {0}".format(
                object_name(obj) or getattr(obj, "guid", "")
            )
        )
    return updated


def _apply_st_from_view_disk(
    project, view_root, st_rel_path, guid, guid_map, log_fn=None
):
    log = log_fn or print
    if not view_root or not st_rel_path:
        return False
    full_path = os.path.join(view_root, st_rel_path.replace("/", os.sep))
    if not os.path.isfile(full_path):
        log("Missing .st on disk: " + str(st_rel_path))
        return False
    try:
        with open(full_path, "r") as handle:
            content = handle.read()
    except Exception as error:
        log("Could not read {0}: {1}".format(st_rel_path, error))
        return False
    obj = guid_map.get(normalize_guid(guid))
    if obj is None:
        log("GUID not found in project: " + str(guid))
        return False
    if _apply_st_content_to_object(obj, content, log_fn=log):
        log(
            "Applied .st from disk for {0}".format(
                object_name(obj) or st_rel_path
            )
        )
        return True
    return False


def _apply_disk_st_for_guids(
    project, view_root, guids, compare_report_path, guid_map, log_fn=None
):
    log = log_fn or print
    report_index = (
        _compare_report_by_guid(compare_report_path)
        if compare_report_path and os.path.exists(compare_report_path)
        else {}
    )
    applied = []
    for guid in guids or []:
        normalized = normalize_guid(guid)
        if not normalized:
            continue
        report_obj = report_index.get(normalized) or {}
        st_path = _st_projection_path_from_report_obj(report_obj)
        if not st_path:
            continue
        if _apply_st_from_view_disk(
            project, view_root, st_path, normalized, guid_map, log_fn=log
        ):
            applied.append(normalized)
    return applied


def _text_document(obj, attr_name, flag_name):
    if obj is None or not hasattr(obj, attr_name):
        return None
    return getattr(obj, attr_name)


def _apply_textual_patch(obj, texts):
    updated = False
    declaration = texts.get("declaration")
    implementation = texts.get("implementation")

    declaration_doc = _text_document(
        obj, "textual_declaration", "has_textual_declaration"
    )
    if declaration is not None and declaration_doc is not None:
        updated = _replace_text_document(declaration_doc, declaration) or updated

    implementation_doc = _text_document(
        obj, "textual_implementation", "has_textual_implementation"
    )
    if implementation is not None and implementation_doc is not None:
        updated = _replace_text_document(implementation_doc, implementation) or updated

    return updated


def _set_bool_property(target, prop_name, value):
    if target is None or not hasattr(target, prop_name):
        return None
    current_value = getattr(target, prop_name)
    if bool(current_value) == bool(value):
        return False
    setattr(target, prop_name, bool(value))
    return True


def _apply_build_attrs_patch(obj, attrs):
    updated = False
    for prop_name, value in attrs.items():
        result = None
        try:
            build_props = getattr(obj, "build_properties", None)
            valid_check = prop_name + "_is_valid"
            if build_props is not None and hasattr(build_props, valid_check):
                if not getattr(build_props, valid_check):
                    result = False
            if result is None:
                result = _set_bool_property(build_props, prop_name, value)
            if result is None:
                result = _set_bool_property(obj, prop_name, value)
        except Exception as e:
            print(
                "Warning: could not apply build property {0}: {1}".format(prop_name, e)
            )
            result = False

        if result is True:
            updated = True
    return updated


def _split_st_update_content(content):
    marker = "// --- implementation ---"
    normalized = (content or "").replace("\r\n", "\n").replace("\r", "\n")
    if marker in normalized:
        parts = normalized.split(marker, 1)
        return parts[0].strip(), parts[1].strip()
    return normalized.strip(), ""


def _apply_modified_st_from_compare_report(
    project, report_path, exclude_guids=None, log_fn=None
):
    log = log_fn or print
    try:
        with open(report_path, "r") as handle:
            report = json.load(handle)
    except Exception as error:
        log("Could not read compare report: {0}".format(error))
        return [], []

    exclude = set()
    for guid in exclude_guids or []:
        normalized = normalize_guid(guid)
        if normalized:
            exclude.add(normalized)

    guid_map = _build_guid_map(project)
    updated_names = []
    updated_guids = []
    for obj in ((report.get("objects") or {}).get("modified") or []):
        projection_diff = obj.get("projection_diff") or {}
        if str(projection_diff.get("format", "")).lower() != "st":
            continue
        disk_content = projection_diff.get("disk_content")
        if not disk_content:
            continue
        guid = normalize_guid(obj.get("guid", ""))
        if guid in exclude:
            continue
        target = guid_map.get(guid)
        if target is None:
            log(
                "Could not find modified text object: {0}".format(
                    obj.get("name") or obj.get("guid")
                )
            )
            continue
        decl, impl = _split_st_update_content(disk_content)
        payload = {
            "declaration": decl or None,
            "implementation": impl or None,
        }
        if not _can_apply_textual_patch(target, payload):
            log(
                "Text object not patchable via text API: {0}".format(
                    obj.get("name") or guid
                )
            )
            continue
        if _apply_textual_patch(target, payload):
            updated_names.append(obj.get("name") or guid or "?")
            if guid:
                updated_guids.append(guid)
        else:
            log(
                "Text update did not apply for {0}".format(
                    obj.get("name") or guid
                )
            )
    return updated_names, updated_guids


def _can_apply_textual_patch(obj, texts):
    declaration = texts.get("declaration")
    implementation = texts.get("implementation")

    if (
        declaration is not None
        and _text_document(obj, "textual_declaration", "has_textual_declaration")
        is not None
    ):
        return True
    if (
        implementation is not None
        and _text_document(obj, "textual_implementation", "has_textual_implementation")
        is not None
    ):
        return True
    return False


def _apply_native_patch(project, obj, patch_path):
    parent = None
    try:
        parent = obj.parent
    except Exception:
        parent = None

    if parent is not None and hasattr(parent, "import_native"):
        parent.import_native(patch_path)
    else:
        project.import_native(patch_path)


def _apply_native_patches(project, guid_map, patch_root, native_guids, result):
    for guid in native_guids:
        obj = guid_map.get(guid)
        if obj is None:
            continue
        filtered_patch_path = None
        try:
            filtered_patch_path = _write_filtered_patch(patch_root, [guid])
            print("Applying native patch for non-textual object: " + str(guid))
            _apply_native_patch(project, obj, filtered_patch_path)
            result.add_applied(guid, "native")
        except Exception as error:
            result.fail(error, guid)
            raise
        finally:
            if filtered_patch_path and os.path.exists(filtered_patch_path):
                try:
                    os.remove(filtered_patch_path)
                except Exception:
                    pass


def _modified_st_paths_from_compare_report(report_path):
    try:
        with open(report_path, "r") as handle:
            report = json.load(handle)
    except Exception:
        return set()
    paths = set()
    for obj in ((report.get("objects") or {}).get("modified") or []):
        for path in obj.get("projection_changed_paths") or []:
            paths.add(str(path).replace("\\", "/"))
        projection_diff = obj.get("projection_diff") or {}
        path = projection_diff.get("path")
        if path:
            paths.add(str(path).replace("\\", "/"))
    return paths


def apply_patch(system, project, patch_path, view_root=None, compare_report_path=None, log_fn=None, selected_guids=None):
    """
    Applies the pre-computed IMPORT.xml to the current project.

    When ``selected_guids`` is provided (selective/diff import), the post-import
    view sync only re-exports the objects that were touched instead of the whole
    project, which keeps a diff import fast on large projects.
    """
    selected_guid_set = set()
    for guid in selected_guids or []:
        normalized = normalize_guid(guid)
        if normalized:
            selected_guid_set.add(normalized)
    log = log_fn or print
    result = ApplyPatchResult()
    log("Applying patch from: " + patch_path)
    if not os.path.exists(patch_path):
        log("Patch file not found.")
        return result.fail("Patch file not found.")

    try:
        patch_data = _parse_patch(patch_path)
        patch_root = patch_data["root"]
        patch_guids = patch_data["guids"]
        patch_texts = patch_data["texts"]
        patch_build_attrs = patch_data["build_attrs"]
        text_creates = patch_data["text_creates"]
        text_deletes = patch_data["text_deletes"]
        guid_map = _build_guid_map(project)
        created_by_name = {}
        exclude_native_guids = set()
        family_updated_names = []

        try:
            import ide_collapsed_pou_import as _cpi
        except Exception:
            _cpi = None

        if _cpi is not None and view_root:
            families = _cpi.collect_affected_families(
                project,
                patch_root,
                text_creates=text_creates,
                compare_report_path=compare_report_path,
                view_root=view_root,
                guid_map=guid_map,
            )
            if families:
                only_st_paths = None
                if compare_report_path and os.path.exists(compare_report_path):
                    only_st_paths = _modified_st_paths_from_compare_report(
                        compare_report_path
                    )
                family_result = _cpi.apply_collapsed_families(
                    project,
                    view_root,
                    families,
                    log_fn=log,
                    only_st_paths=only_st_paths or None,
                    guid_map=guid_map,
                )
                exclude_native_guids.update(
                    family_result.get("updated_guids")
                    or family_result.get("excluded_guids")
                    or []
                )
                family_updated_names = family_result.get("updated_names") or []
                skipped_paths = family_result.get("skipped_create_paths") or set()
                text_creates = [
                    entry
                    for entry in text_creates
                    if entry.get("path") not in skipped_paths
                ]

        delete_error = _apply_text_deletes(
            project, text_deletes, guid_map, result
        )
        if delete_error is not None:
            return delete_error
        if text_deletes:
            guid_map = _build_guid_map(project)
            if view_root:
                manifest_path = os.path.join(
                    os.path.dirname(patch_path), "manifest.json"
                )
                cleanup_deleted_view_files(view_root, manifest_path, text_deletes)

        def _finish():
            if (
                compare_report_path
                and os.path.exists(compare_report_path)
                and result.success
            ):
                report_names, report_guids = _apply_modified_st_from_compare_report(
                    project,
                    compare_report_path,
                    exclude_guids=result.applied_guids,
                    log_fn=log,
                )
                for guid in report_guids:
                    result.add_applied(guid, "textual")
                if report_names:
                    log(
                        "Applied compare-report text updates: {0}".format(
                            ", ".join(report_names)
                        )
                    )
            if view_root and result.success:
                try:
                    import ide_view_sync as _ivs

                    project_root = os.path.abspath(os.path.join(view_root, os.pardir))
                    manifest_path = os.path.join(
                        os.path.dirname(patch_path), "manifest.json"
                    )
                    # For a selective import that neither created nor deleted
                    # objects, only re-export the touched objects so the post
                    # import sync doesn't re-serialize the whole project.
                    sync_guids = None
                    if (
                        selected_guid_set
                        and not result.created_paths
                        and not result.deleted_guids
                    ):
                        sync_guids = result.applied_guids or sorted(selected_guid_set)
                    _ivs.sync_view_after_import(
                        project,
                        project_root,
                        view_root,
                        manifest_path,
                        log_fn=log,
                        selected_guids=sync_guids,
                    )
                except Exception as error:
                    log(
                        "Warning: post-import view sync failed: {0}".format(error)
                    )
            return result

        existing_targets = [
            guid
            for guid in patch_guids
            if guid in guid_map and guid not in exclude_native_guids
        ]
        existing_objects = [guid_map[guid] for guid in existing_targets]

        if existing_objects:
            textual_handled = []
            for guid in existing_targets:
                obj = guid_map.get(guid)
                texts = patch_texts.get(guid)
                if obj is None or texts is None:
                    continue
                if not _can_apply_textual_patch(obj, texts):
                    continue
                try:
                    text_updated = _apply_textual_patch(obj, texts)
                    attrs_updated = _apply_build_attrs_patch(
                        obj, patch_build_attrs.get(guid, {})
                    )
                except Exception as error:
                    log(
                        "Error applying textual patch for object {0}: {1}".format(
                            guid, error
                        )
                    )
                    return result.fail(error, guid)
                if text_updated or attrs_updated:
                    log("Applied textual patch for object: " + str(guid))
                else:
                    log("Textual patch already current for object: " + str(guid))
                textual_handled.append(guid)
                result.add_applied(guid, "textual")

            if len(textual_handled) == len(existing_objects):
                create_error = _apply_text_creates(
                    project, text_creates, created_by_name, result
                )
                if create_error is not None:
                    return create_error
                return _finish()

            native_guids = []
            for guid in patch_guids:
                if guid in exclude_native_guids:
                    continue
                if guid in guid_map and guid not in textual_handled:
                    native_guids.append(guid)

            if native_guids and view_root:
                disk_applied = _apply_disk_st_for_guids(
                    project,
                    view_root,
                    native_guids,
                    compare_report_path,
                    guid_map,
                    log_fn=log,
                )
                for guid in disk_applied:
                    result.add_applied(guid, "textual")
                    if guid not in textual_handled:
                        textual_handled.append(guid)
                native_guids = [
                    guid
                    for guid in native_guids
                    if normalize_guid(guid) not in disk_applied
                ]

            if native_guids and not _patch_has_text_lines(patch_root):
                _apply_native_patches(
                    project, guid_map, patch_root, native_guids, result
                )
            elif native_guids:
                log(
                    "Skipped native import for TextLines patch; unapplied: {0}".format(
                        ", ".join(native_guids)
                    )
                )
            create_error = _apply_text_creates(
                project, text_creates, created_by_name, result
            )
            if create_error is not None:
                return create_error
            return _finish()

        if patch_guids:
            pending_guids = [
                guid
                for guid in patch_guids
                if guid not in exclude_native_guids
                and normalize_guid(guid) not in result.applied_guids
            ]
            if pending_guids and view_root:
                disk_applied = _apply_disk_st_for_guids(
                    project,
                    view_root,
                    pending_guids,
                    compare_report_path,
                    guid_map,
                    log_fn=log,
                )
                for guid in disk_applied:
                    result.add_applied(guid, "textual")
                pending_guids = [
                    guid
                    for guid in pending_guids
                    if normalize_guid(guid) not in disk_applied
                ]
            native_patch_path = None
            try:
                if pending_guids and not _patch_has_text_lines(patch_root):
                    filtered_root = _filter_native_patch_root(
                        patch_root, exclude_guids=list(exclude_native_guids)
                    )
                    if filtered_root is not None:
                        handle, native_patch_path = tempfile.mkstemp(suffix=".xml")
                        os.close(handle)
                        ET.ElementTree(filtered_root).write(
                            native_patch_path, encoding="utf-8", xml_declaration=True
                        )
                        project.import_native(native_patch_path)
                        for guid in pending_guids:
                            result.add_applied(guid, "native")
                elif pending_guids:
                    log(
                        "Skipped native import for TextLines-only patch: {0}".format(
                            ", ".join(pending_guids)
                        )
                    )
            finally:
                if native_patch_path and os.path.exists(native_patch_path):
                    try:
                        os.remove(native_patch_path)
                    except Exception:
                        pass
        create_error = _apply_text_creates(
            project, text_creates, created_by_name, result
        )
        if create_error is not None:
            return create_error

        return _finish()
    except Exception as e:
        log("Error applying patch: " + str(e))
        return result.fail(e)
