# -*- coding: utf-8 -*-
"""
ide_export_snapshot.pyw - Export entire project to a native IDE.xml snapshot.
Must be compatible with IronPython 2.7.
"""
from __future__ import print_function
import os
import tempfile

import ide_runtime_common


RESOURCE_EXTENSIONS = set([
    ".bmp",
    ".cfg",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".json",
    ".png",
    ".sh",
    ".svg",
    ".txt",
    ".xml",
])


def _missing_external_path_from_name(name):
    if "|" not in name:
        return None
    candidate = name.split("|", 1)[1].strip()
    if not candidate:
        return None
    extension = os.path.splitext(candidate)[1].lower()
    if extension in RESOURCE_EXTENSIONS:
        return candidate
    if not (os.path.isabs(candidate) or (len(candidate) > 2 and candidate[1] == ":")):
        return None
    if os.path.exists(candidate):
        return None
    return candidate


def _object_guid(obj):
    try:
        return ide_runtime_common.normalize_guid(obj.guid)
    except Exception:
        return None


def _selected_guid_set(selected_guids):
    if not selected_guids:
        return None
    result = set()
    for guid in selected_guids:
        normalized = ide_runtime_common.normalize_guid(guid)
        if normalized:
            result.add(normalized)
    return result or None


def _collapsed_pou_ancestor(obj):
    """Return the highest ancestor (or self) that owns methods (a collapsed POU).

    Collapsed POUs (function blocks/programs) expose their methods, actions and
    properties as child objects, but the disk view represents the whole family
    together. A correct diff therefore needs the entire parent POU in the
    snapshot, not just the edited child. Objects with a ``create_method`` API are
    the collapsed containers, so we walk up recording the top-most one.
    """
    ancestor = None
    current = obj
    while current is not None:
        try:
            if hasattr(current, "create_method"):
                ancestor = current
        except Exception:
            pass
        try:
            current = current.parent
        except Exception:
            break
    return ancestor


def _expand_export_roots(candidates, selected):
    """Map selected GUIDs to the objects that must be exported for a valid diff.

    A selected object that lives inside a collapsed POU is replaced by that POU
    so the whole family is serialized (recursively). Standalone objects export
    themselves.
    """
    by_guid = {}
    for obj in candidates:
        guid = _object_guid(obj)
        if guid and guid not in by_guid:
            by_guid[guid] = obj

    roots = []
    seen = set()
    for guid in selected:
        obj = by_guid.get(guid)
        if obj is None:
            continue
        root = _collapsed_pou_ancestor(obj) or obj
        key = id(root)
        if key not in seen:
            seen.add(key)
            roots.append(root)
    return roots


def _exportable_snapshot_objects(project, selected_guids=None):
    """Return (objects, skipped, recursive) for the native export.

    When ``selected_guids`` is given, only the selected objects (expanded to
    their collapsed POU parents) are exported, recursively, so collapsed
    sub-objects diff correctly. Otherwise the full project is exported flat
    (recursive=False) because ``get_children(recursive=True)`` already lists
    every object.
    """
    skipped = []
    try:
        candidates = project.get_children(recursive=True)
    except Exception:
        # Could not flatten the tree; fall back to a full recursive export.
        return project.get_children(), skipped, True

    selected = _selected_guid_set(selected_guids)
    if selected is not None:
        # Filtered exports must be recursive so descendants of the selected
        # objects (e.g. collapsed POU children) are serialized alongside them.
        return _expand_export_roots(candidates, selected), skipped, True

    objects = []
    for obj in candidates:
        name = ide_runtime_common.object_name(obj)
        missing_path = _missing_external_path_from_name(name)
        if missing_path:
            skipped.append((name, missing_path))
            continue
        objects.append(obj)
    return objects, skipped, False


def _replace_file(source_path, target_path):
    if os.path.exists(target_path):
        os.remove(target_path)
    os.rename(source_path, target_path)


def _print_skipped_external_resources(skipped, log_fn=None):
    unique = []
    seen = set()
    for name, missing_path in skipped:
        key = name + "\n" + missing_path
        if key in seen:
            continue
        seen.add(key)
        unique.append((name, missing_path))

    limit = 10
    for name, missing_path in unique[:limit]:
        message = "Skipping missing external resource during snapshot export: " + name + " -> " + missing_path
        if log_fn:
            log_fn(message)
        else:
            print(message)
    if len(unique) > limit:
        message = "Skipped {0} more missing external resources during snapshot export.".format(len(unique) - limit)
        if log_fn:
            log_fn(message)
        else:
            print(message)


def export_snapshot(system, project, output_path, log_fn=None, selected_guids=None):
    """
    Exports the project into a single native XML file.

    When ``selected_guids`` is provided, only those objects (and their
    descendants) are exported, which dramatically speeds up selective/diff
    imports on large projects. Falls back to a full export when no selected
    object can be resolved. Uses a temporary target to avoid CODESYS overwrite
    prompts.
    """
    if log_fn:
        log_fn("Exporting snapshot to: " + output_path)
    else:
        print("Exporting snapshot to: " + output_path)
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    fd, tmp_path = tempfile.mkstemp(prefix="cds_ide_snapshot_", suffix=".xml", dir=output_dir or None)
    os.close(fd)
    try:
        os.remove(tmp_path)
    except Exception:
        pass

    try:
        objects, skipped, use_recursive = _exportable_snapshot_objects(
            project, selected_guids=selected_guids
        )
        if selected_guids and not objects:
            message = (
                "No snapshot objects matched the selected GUIDs; "
                "exporting the full project instead."
            )
            if log_fn:
                log_fn(message)
            else:
                print(message)
            objects, skipped, use_recursive = _exportable_snapshot_objects(project)
        _print_skipped_external_resources(skipped, log_fn=log_fn)
        project.export_native(objects, tmp_path, recursive=bool(use_recursive))
        _replace_file(tmp_path, output_path)
        return True
    except Exception as e:
        if log_fn:
            log_fn("Error exporting snapshot: " + str(e))
        else:
            print("Error exporting snapshot: " + str(e))
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return False
