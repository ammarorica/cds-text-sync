# -*- coding: utf-8 -*-
"""Keep project-view/ files in sync with IDE after import."""

from __future__ import print_function

import json
import os

import ide_export_snapshot
import ide_runtime_common as _rc


CDS_OBJECT_XML = ".cds-object.xml"


def is_flat_st_sidecar_xml(filename):
    """True for Parent.Child.xml flat sidecars, not hierarchical .cds-object.xml."""
    name = os.path.basename(str(filename or "")).lower()
    if name == CDS_OBJECT_XML:
        return False
    base, ext = os.path.splitext(name)
    return ext == ".xml" and "." in base and not base.startswith(".")


def _log_or_print(log_fn, message):
    if log_fn:
        log_fn(message)
    else:
        print(message)


def _remove_file(view_root, rel_path):
    full_path = os.path.join(view_root, str(rel_path).replace("/", os.sep))
    if os.path.isfile(full_path):
        os.remove(full_path)
        return str(rel_path).replace("\\", "/")
    return None


def reconcile_view_files(view_root, manifest_path, log_fn=None):
    """Drop xml/manifest rows when the canonical .st projection file is gone."""
    removed = []
    if not view_root or not os.path.isdir(view_root):
        return removed

    manifest = {"entries": []}
    if manifest_path and os.path.isfile(manifest_path):
        try:
            with open(manifest_path, "r") as handle:
                manifest = json.load(handle)
        except Exception:
            manifest = {"entries": []}

    kept = []
    xml_paths_expecting_st = set()
    for entry in manifest.get("entries", []) or []:
        st_paths = [
            str(path).replace("\\", "/")
            for path in (entry.get("projection_paths") or [])
            if str(path).lower().endswith(".st")
        ]
        xml_path = str(entry.get("xml_path") or "").replace("\\", "/")
        if st_paths and xml_path:
            xml_paths_expecting_st.add(xml_path)

        if (
            st_paths
            and all(
                not os.path.isfile(os.path.join(view_root, path.replace("/", os.sep)))
                for path in st_paths
            )
            and os.path.basename(xml_path).lower() != CDS_OBJECT_XML
        ):
            for rel_path in [xml_path] + st_paths + list(entry.get("projection_paths") or []):
                rel_text = str(rel_path or "").replace("\\", "/")
                if not rel_text:
                    continue
                deleted = _remove_file(view_root, rel_text)
                if deleted:
                    removed.append(deleted)
            _log_or_print(
                log_fn,
                "Pruned view entry missing .st projection: {0}".format(
                    entry.get("name") or entry.get("guid")
                ),
            )
            continue
        kept.append(entry)

    if manifest_path:
        manifest["entries"] = kept
        try:
            with open(manifest_path, "w") as handle:
                json.dump(manifest, handle, indent=2)
        except Exception as error:
            _log_or_print(
                log_fn, "Warning: could not update manifest: {0}".format(error)
            )

    for root, _dirs, files in os.walk(view_root):
        for filename in files:
            if not is_flat_st_sidecar_xml(filename):
                continue
            rel_path = os.path.relpath(
                os.path.join(root, filename), view_root
            ).replace(os.sep, "/")
            base_name = os.path.splitext(filename)[0]
            st_rel = os.path.join(
                os.path.dirname(rel_path), base_name + ".st"
            ).replace("\\", "/")
            st_full = os.path.join(view_root, st_rel.replace("/", os.sep))
            if os.path.isfile(st_full):
                continue
            deleted = _remove_file(view_root, rel_path)
            if deleted:
                removed.append(deleted)
                _log_or_print(
                    log_fn, "Removed orphan xml without .st: {0}".format(deleted)
                )

    return removed


def sync_view_from_ide(project, project_root, log_fn=None):
    """Export a fresh IDE snapshot into project-view/ (xml sidecars + manifest)."""
    if project is None or not project_root:
        return False

    layout = _rc.layout(project_root)
    dump_dir = layout.dump_root
    if not os.path.exists(dump_dir):
        os.makedirs(dump_dir)

    snapshot_path = os.path.join(dump_dir, "IDE.post-import.xml")
    if not ide_export_snapshot.export_snapshot(None, project, snapshot_path):
        _log_or_print(log_fn, "Post-import IDE snapshot export failed.")
        return False

    args = [
        "export",
        "--project-root",
        project_root,
        "--snapshot",
        snapshot_path,
    ]
    ok = _rc.run_external_engine(args, project_root=project_root)
    if ok:
        _log_or_print(log_fn, "Post-import view export completed.")
    else:
        _log_or_print(log_fn, "Post-import view export failed.")
    return ok


def sync_view_after_import(project, project_root, view_root, manifest_path, log_fn=None):
    """Export IDE state to disk, then prune xml/manifest rows that lack a .st file."""
    ok = sync_view_from_ide(project, project_root, log_fn=log_fn)
    removed_legacy = _remove_legacy_cds_object_xml(view_root, log_fn=log_fn)
    reconciled = reconcile_view_files(view_root, manifest_path, log_fn=log_fn)
    if removed_legacy:
        _log_or_print(
            log_fn,
            "Removed legacy .cds-object.xml: {0}".format(", ".join(removed_legacy)),
        )
    if reconciled:
        _log_or_print(
            log_fn, "Reconciled view files: {0}".format(", ".join(reconciled))
        )
    return ok


def _remove_legacy_cds_object_xml(view_root, log_fn=None):
    removed = []
    if not view_root or not os.path.isdir(view_root):
        return removed
    for root, _dirs, files in os.walk(view_root):
        for filename in files:
            if filename.lower() != CDS_OBJECT_XML:
                continue
            rel_path = os.path.relpath(
                os.path.join(root, filename), view_root
            ).replace(os.sep, "/")
            deleted = _remove_file(view_root, rel_path)
            if deleted:
                removed.append(deleted)
    return removed
