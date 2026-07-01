# -*- coding: utf-8 -*-

import json
import os
import tempfile

from ide_apply_patch import cleanup_deleted_view_files, _related_view_paths
from ide_view_sync import reconcile_view_files


def test_related_view_paths_pairs_st_and_xml():
    paths = _related_view_paths("Device/Application/FB.Method.st")
    assert "Device/Application/FB.Method.st" in paths
    assert "Device/Application/FB.Method.xml" in paths


def test_cleanup_deleted_view_files_removes_xml_and_prunes_manifest(tmp_path):
    views = str(tmp_path / "views")
    dump = str(tmp_path / ".dump")
    os.makedirs(os.path.join(views, "Device", "Application"))
    st_path = os.path.join(views, "Device", "Application", "FB.Method.st")
    xml_path = os.path.join(views, "Device", "Application", "FB.Method.xml")
    with open(st_path, "w") as handle:
        handle.write("METHOD Method\nEND_METHOD")
    with open(xml_path, "w") as handle:
        handle.write("<Single/>")

    manifest_path = os.path.join(dump, "manifest.json")
    os.makedirs(dump)
    with open(manifest_path, "w") as handle:
        json.dump(
            {
                "entries": [
                    {
                        "guid": "a8b1beb5-9eb9-4aa9-9f78-9f733a4eb4c2",
                        "name": "Method",
                        "xml_path": "Device/Application/FB.Method.xml",
                        "projection_paths": ["Device/Application/FB.Method.st"],
                    }
                ]
            },
            handle,
        )

    removed = cleanup_deleted_view_files(
        views,
        manifest_path,
        [
            {
                "guid": "a8b1beb5-9eb9-4aa9-9f78-9f733a4eb4c2",
                "name": "Method",
                "path": "Device/Application/FB.Method.st",
            }
        ],
    )

    assert not os.path.exists(st_path)
    assert not os.path.exists(xml_path)
    assert "Device/Application/FB.Method.st" in removed
    with open(manifest_path, "r") as handle:
        manifest = json.load(handle)
    assert manifest["entries"] == []


def test_reconcile_removes_xml_when_st_projection_missing(tmp_path):
    views = str(tmp_path / "views")
    dump = str(tmp_path / ".dump")
    os.makedirs(os.path.join(views, "Device", "Application"))
    xml_path = os.path.join(views, "Device", "Application", "FB.Method.xml")
    with open(xml_path, "w") as handle:
        handle.write("<Single/>")

    manifest_path = os.path.join(dump, "manifest.json")
    os.makedirs(dump)
    with open(manifest_path, "w") as handle:
        json.dump(
            {
                "entries": [
                    {
                        "guid": "a8b1beb5-9eb9-4aa9-9f78-9f733a4eb4c2",
                        "name": "Method",
                        "xml_path": "Device/Application/FB.Method.xml",
                        "projection_paths": ["Device/Application/FB.Method.st"],
                    }
                ]
            },
            handle,
        )

    removed = reconcile_view_files(views, manifest_path)
    assert not os.path.exists(xml_path)
    assert "Device/Application/FB.Method.xml" in removed
    with open(manifest_path, "r") as handle:
        manifest = json.load(handle)
    assert manifest["entries"] == []


def test_cleanup_deleted_view_files_prunes_manifest_by_path_without_guid(tmp_path):
    views = str(tmp_path / "views")
    dump = str(tmp_path / ".dump")
    os.makedirs(os.path.join(views, "Device", "Application"))
    xml_path = os.path.join(views, "Device", "Application", "FB.Method.xml")
    with open(xml_path, "w") as handle:
        handle.write("<Single/>")

    manifest_path = os.path.join(dump, "manifest.json")
    os.makedirs(dump)
    with open(manifest_path, "w") as handle:
        json.dump(
            {
                "entries": [
                    {
                        "guid": "a8b1beb5-9eb9-4aa9-9f78-9f733a4eb4c2",
                        "name": "Method",
                        "xml_path": "Device/Application/FB.Method.xml",
                        "projection_paths": ["Device/Application/FB.Method.st"],
                    }
                ]
            },
            handle,
        )

    removed = cleanup_deleted_view_files(
        views,
        manifest_path,
        [{"name": "Method", "path": "Device/Application/FB.Method.xml"}],
    )

    assert not os.path.exists(xml_path)
    with open(manifest_path, "r") as handle:
        manifest = json.load(handle)
    assert manifest["entries"] == []
    assert "Device/Application/FB.Method.xml" in removed
