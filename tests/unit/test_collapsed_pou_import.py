# -*- coding: utf-8 -*-

import os

from ide_apply_patch_regression import FakeObject, FakeProject
from ide_collapsed_pou_import import (
    apply_collapsed_families,
    collect_affected_families,
    family_name_from_st_path,
    iter_family_st_files,
)


def test_family_name_from_child_st_path():
    assert family_name_from_st_path("Device/Application/FB_Main.Method.st") == "FB_Main"
    assert family_name_from_st_path("FB_Main.st") == "FB_Main"


def test_iter_family_st_files_finds_parent_and_children(tmp_path):
    views = str(tmp_path / "views")
    os.makedirs(os.path.join(views, "Device", "Application"))
    parent_path = os.path.join(views, "Device", "Application", "FB_Main.st")
    child_path = os.path.join(views, "Device", "Application", "FB_Main.MethodA.st")
    with open(parent_path, "w") as handle:
        handle.write(
            "FUNCTION_BLOCK FB_Main\nVAR\nEND_VAR\n\n"
            "// --- implementation ---\n\n"
            "x := 1;\n"
        )
    with open(child_path, "w") as handle:
        handle.write(
            "METHOD MethodA : BOOL\nVAR\nEND_VAR\n\n"
            "// --- implementation ---\n\n"
            "MethodA := TRUE;\n"
        )

    entries = iter_family_st_files(views, "FB_Main")
    names = sorted(entry["name"] for entry in entries)
    assert names == ["FB_Main", "MethodA"]


def test_apply_collapsed_families_updates_parent_and_child(tmp_path):
    views = str(tmp_path / "views")
    os.makedirs(os.path.join(views, "Device", "Application"))
    parent_path = os.path.join(views, "Device", "Application", "FB_Main.st")
    child_path = os.path.join(views, "Device", "Application", "FB_Main.MethodA.st")
    with open(parent_path, "w") as handle:
        handle.write(
            "FUNCTION_BLOCK FB_Main\nVAR\nEND_VAR\n\n"
            "// --- implementation ---\n\n"
            "x := 2;\n"
        )
    with open(child_path, "w") as handle:
        handle.write(
            "METHOD MethodA : BOOL\nVAR\nEND_VAR\n\n"
            "// --- implementation ---\n\n"
            "MethodA := TRUE;\n"
        )

    project = FakeProject()
    app = project._add_child(FakeObject(project, "Application", project))
    fb = app._add_child(FakeObject(project, "FB_Main", app))
    fb.textual_declaration.text = "FUNCTION_BLOCK FB_Main\nVAR\nEND_VAR"
    fb.textual_implementation.text = "x := 1;"
    method = fb._add_child(FakeObject(project, "MethodA", fb))
    method.textual_declaration.text = "METHOD MethodA : BOOL\nVAR\nEND_VAR"
    method.textual_implementation.text = "MethodA := FALSE;"

    result = apply_collapsed_families(project, views, ["FB_Main"])
    assert "x := 2;" in fb.textual_implementation.text
    assert "MethodA := TRUE;" in method.textual_implementation.text
    assert fb.guid.lower() in result["updated_guids"]
    assert method.guid.lower() in result["updated_guids"]


def test_apply_collapsed_families_leaves_failed_child_out_of_updated_guids(
    tmp_path, monkeypatch
):
    views = str(tmp_path / "views")
    os.makedirs(os.path.join(views, "Device", "Application"))
    child_path = os.path.join(views, "Device", "Application", "FB_Main.MethodA.st")
    with open(child_path, "w") as handle:
        handle.write(
            "METHOD MethodA : BOOL\nVAR\nEND_VAR\n\n"
            "// --- implementation ---\n\n"
            "MethodA := TRUE;\n"
        )

    project = FakeProject()
    app = project._add_child(FakeObject(project, "Application", project))
    fb = app._add_child(FakeObject(project, "FB_Main", app))
    method = fb._add_child(FakeObject(project, "MethodA", fb))
    method.textual_declaration.text = "METHOD MethodA : BOOL\nVAR\nEND_VAR"
    method.textual_implementation.text = "MethodA := FALSE;"

    monkeypatch.setattr(
        "ide_collapsed_pou_import._iap._apply_textual_patch",
        lambda _obj, _payload: False,
    )

    result = apply_collapsed_families(project, views, ["FB_Main"])
    assert result["updated_guids"] == set()
    assert result["updated_names"] == []


def test_collect_affected_families_from_child_create():
    project = FakeProject()
    app = project._add_child(FakeObject(project, "Application", project))
    fb = app._add_child(FakeObject(project, "FB_Main", app))
    method = fb._add_child(FakeObject(project, "MethodA", fb))

    creates = [
        {
            "path": "Device/Application/FB_Main.MethodA.st",
            "name": "MethodA",
            "parent_name": "FB_Main",
        }
    ]
    families = collect_affected_families(project, None, text_creates=creates)
    assert "FB_Main" in families


def test_filter_family_entries_limits_to_changed_paths(tmp_path):
    views = str(tmp_path / "views")
    os.makedirs(os.path.join(views, "Device", "Application"))
    parent_path = os.path.join(views, "Device", "Application", "FB_Main.st")
    method_path = os.path.join(views, "Device", "Application", "FB_Main.MethodA.st")
    accessor_path = os.path.join(
        views, "Device", "Application", "FB_Main.ActuatorsCommandRequested.Get.st"
    )
    for path, body in (
        (parent_path, "FUNCTION_BLOCK FB_Main\nVAR\nEND_VAR\n"),
        (method_path, "METHOD MethodA\nEND_METHOD\n"),
        (accessor_path, "METHOD Get\nEND_METHOD\n"),
    ):
        with open(path, "w") as handle:
            handle.write(body)

    entries = iter_family_st_files(views, "FB_Main")
    from ide_collapsed_pou_import import _filter_family_entries

    filtered = _filter_family_entries(
        entries,
        ["Device/Application/FB_Main.MethodA.st"],
    )
    assert [entry["path"] for entry in filtered] == [
        "Device/Application/FB_Main.MethodA.st"
    ]


def test_families_from_disk_view_gaps_detects_missing_xml_and_st(tmp_path):
    views = str(tmp_path / "views")
    os.makedirs(os.path.join(views, "Device", "Application"))
    st_only = os.path.join(views, "Device", "Application", "FB_Main.NewMethod.st")
    xml_only = os.path.join(views, "Device", "Application", "FB_Main.OldMethod.xml")
    with open(st_only, "w") as handle:
        handle.write("METHOD NewMethod\nEND_METHOD")
    with open(xml_only, "w") as handle:
        handle.write("<Single/>")

    from ide_collapsed_pou_import import _families_from_disk_view_gaps

    families = _families_from_disk_view_gaps(views)
    assert "FB_Main" in families
