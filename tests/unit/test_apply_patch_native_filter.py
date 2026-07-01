# -*- coding: utf-8 -*-

import os
import xml.etree.ElementTree as ET

from ide_apply_patch import (
    _apply_st_from_view_disk,
    _filter_native_patch_root,
    _patch_object_guids,
    _patch_text_by_guid,
    apply_textual_patches_from_patch,
)
from ide_apply_patch_regression import FakeObject, FakeProject


def _patch_with_fb_and_method():
    fb_guid = "11111111-1111-1111-1111-111111111111"
    method_guid = "22222222-2222-2222-2222-222222222222"
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<Project>"
        "<StructuredView Guid=\"{sv}\">"
        "<Single Name=\"EntryList\">"
        "<Single Name=\"Entry\">"
        "<Single Name=\"MetaObject\">"
        "<Single Name=\"Guid\">{fb}</Single>"
        "</Single>"
        "<Single Name=\"Object\">"
        "<Single Name=\"Declaration\">"
        "<Single Name=\"TextBlobForSerialisation\">"
        "FUNCTION_BLOCK FB_Main\nVAR\nEND_VAR"
        "</Single>"
        "</Single>"
        "<Single Name=\"Implementation\">"
        "<Single Name=\"TextBlobForSerialisation\">changed := TRUE;</Single>"
        "</Single>"
        "</Single>"
        "</Single>"
        "<Single Name=\"Entry\">"
        "<Single Name=\"MetaObject\">"
        "<Single Name=\"Guid\">{method}</Single>"
        "</Single>"
        "<Single Name=\"Object\">"
        "<Single Name=\"Declaration\">"
        "<Single Name=\"TextBlobForSerialisation\">METHOD M</Single>"
        "</Single>"
        "</Single>"
        "</Single>"
        "</Single>"
        "</StructuredView>"
        "</Project>"
    ).format(sv="{aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa}", fb=fb_guid, method=method_guid)
    return ET.fromstring(xml), fb_guid, method_guid


def test_patch_text_by_guid_reads_text_lines_format():
    method_guid = "84c21081-e34d-458e-ae6a-d9eb5e5c0782"
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<Project><StructuredView>"
        "<Single><Single Name=\"MetaObject\">"
        "<Single Name=\"Guid\">{guid}</Single>"
        "</Single><Single Name=\"Object\">"
        "<Single Name=\"Interface\"><Single Name=\"TextDocument\">"
        "<Array Name=\"TextLines\"><Single><Single Name=\"Text\">"
        "METHOD PRIVATE _CyclicProcessing"
        "</Single></Single></Array>"
        "</Single></Single>"
        "<Single Name=\"Implementation\"><Single Name=\"TextDocument\">"
        "<Array Name=\"TextLines\"><Single><Single Name=\"Text\">"
        "fbHMIController.I_stMachineState := fbMachineStateAggregator.Q_stMachineState;"
        "</Single></Single></Array>"
        "</Single></Single>"
        "</Single></Single></StructuredView></Project>"
    ).format(guid=method_guid)
    root = ET.fromstring(xml)
    texts = _patch_text_by_guid(root)[method_guid]
    assert "METHOD PRIVATE _CyclicProcessing" in texts["declaration"]
    assert "I_stMachineState" in texts["implementation"]


def test_filter_native_patch_root_excludes_text_handled_guids():
    root, fb_guid, method_guid = _patch_with_fb_and_method()
    filtered = _filter_native_patch_root(root, exclude_guids=[fb_guid])
    assert filtered is not None
    remaining = _patch_object_guids(filtered)
    assert fb_guid not in remaining
    assert method_guid in remaining


def test_apply_st_from_view_disk_updates_method(tmp_path):
    views = str(tmp_path / "views")
    os.makedirs(os.path.join(views, "Device"))
    st_path = os.path.join(views, "Device", "FB_Main._CyclicProcessing.st")
    with open(st_path, "w") as handle:
        handle.write(
            "METHOD _CyclicProcessing\nVAR\nEND_VAR\n\n"
            "// --- implementation ---\n\n"
            "fbHMIController.I_stMachineState := fbMachineStateAggregator.Q_stMachineState;\n"
        )
    project = FakeProject()
    app = project._add_child(FakeObject(project, "Application", project))
    fb = app._add_child(FakeObject(project, "FB_Main", app))
    method_guid = "84c21081-e34d-458e-ae6a-d9eb5e5c0782"
    method = fb._add_child(FakeObject(project, "_CyclicProcessing", fb))
    method.guid = method_guid
    method.textual_declaration.text = "METHOD _CyclicProcessing\nVAR\nEND_VAR"
    method.textual_implementation.text = "old := 1;"
    guid_map = {method_guid: method}
    assert _apply_st_from_view_disk(
        project,
        views,
        "Device/FB_Main._CyclicProcessing.st",
        method_guid,
        guid_map,
    )
    assert "I_stMachineState" in method.textual_implementation.text


def test_apply_textual_patches_from_patch_updates_fb_without_native_import():
    root, fb_guid, _method_guid = _patch_with_fb_and_method()
    project = FakeProject()
    app = project._add_child(FakeObject(project, "Application", project))
    fb = app._add_child(FakeObject(project, "FB_Main", app))
    fb.guid = fb_guid
    fb.textual_declaration.text = "FUNCTION_BLOCK FB_Main\nVAR\nEND_VAR"
    fb.textual_implementation.text = "changed := FALSE;"

    handled = apply_textual_patches_from_patch(project, root)
    assert fb_guid in handled
    assert "changed := TRUE;" in fb.textual_implementation.text
    assert "import_native" not in project.events
