# -*- coding: utf-8 -*-

import os
import tempfile
import xml.etree.ElementTree as ET

from _patch_builder import PatchBuilder
from _project_model import ProjectModel, ProjectNode
from _project_profiles import load_profile


METHOD_TYPE_GUID = "f8a58466-d7f6-439f-bbb8-d4600e41d099"
PARENT_GUID = "d84038a4-1d83-4078-8d48-ee053e0cc844"
METHOD_GUID = "f661868e-d452-4999-b956-5f9d0ab6e3e9"


def _build_models():
    ide_model = ProjectModel()
    folder_model = ProjectModel()

    parent = ProjectNode(PARENT_GUID, "FB_RemoteController_TEST", "pou-guid", None)
    folder_model.add_node(parent)

    st_path = "TESTs/FB_RemoteController_TEST._ClearRemoteButtons.st"
    st_content = (
        "METHOD PRIVATE _ClearRemoteButtons\n"
        "VAR_INPUT\n"
        "\tfbRemoteSim : REFERENCE TO FB_TeleRadioRemoteSim;\n"
        "END_VAR\n\n"
        "// --- implementation ---\n\n"
        "fbRemoteSim.QHW_bUpStep1 := FALSE;\n"
    )
    method = ProjectNode(METHOD_GUID, "_ClearRemoteButtons", METHOD_TYPE_GUID, PARENT_GUID)
    method.metadata["view_path"] = st_path.replace(".st", ".xml")
    method.metadata["projection_contents"] = {st_path: st_content}
    method.xml_text = "<Entry/>"
    folder_model.add_node(method)

    return ide_model, folder_model


def test_added_manifest_method_emits_create_text_object():
    ide_model, folder_model = _build_models()
    diff_result = {"added": [METHOD_GUID], "modified": [], "deleted": []}
    profile = load_profile("default")

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as handle:
        patch_path = handle.name

    try:
        builder = PatchBuilder(diff_result, ide_model, folder_model, profile=profile)
        assert builder.build_patch(patch_path) is True

        root = ET.parse(patch_path).getroot()
        creates = [
            elem
            for elem in root.iter()
            if elem.tag.endswith("CreateTextObject")
            or elem.tag == "CreateTextObject"
        ]
        assert len(creates) == 1
        create = creates[0]
        assert create.attrib.get("Kind") == "method"
        assert create.attrib.get("Name") == "_ClearRemoteButtons"
        assert create.attrib.get("ParentName") == "FB_RemoteController_TEST"
        assert "CreateTextObjects" in ET.tostring(root, encoding="unicode")

        patch_guids = []
        for elem in root.iter():
            if elem.attrib.get("Name") != "MetaObject":
                continue
            for child in list(elem):
                if child.attrib.get("Name") == "Guid" and child.text:
                    patch_guids.append(child.text.lower())
        assert METHOD_GUID not in patch_guids
    finally:
        if os.path.exists(patch_path):
            os.remove(patch_path)


def test_deleted_method_emits_delete_text_object():
    ide_model = ProjectModel()
    folder_model = ProjectModel()
    method_guid = "a8b1beb5-9eb9-4aa9-9f78-9f733a4eb4c2"
    parent_guid = PARENT_GUID
    parent = ProjectNode(parent_guid, "FB_RemoteController_TEST", "pou-guid", None)
    ide_model.add_node(parent)
    method = ProjectNode(
        method_guid,
        "T07_StopDownLatchesRetract",
        METHOD_TYPE_GUID,
        parent_guid,
    )
    ide_model.add_node(method)

    diff_result = {"added": [], "modified": [], "deleted": [method_guid]}
    profile = load_profile("default")

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as handle:
        patch_path = handle.name

    try:
        builder = PatchBuilder(diff_result, ide_model, folder_model, profile=profile)
        assert builder.build_patch(patch_path) is True

        root = ET.parse(patch_path).getroot()
        deletes = [
            elem
            for elem in root.iter()
            if elem.tag.endswith("DeleteTextObject")
            or elem.tag == "DeleteTextObject"
        ]
        assert len(deletes) == 1
        assert deletes[0].attrib.get("Name") == "T07_StopDownLatchesRetract"
        assert deletes[0].attrib.get("ParentName") == "FB_RemoteController_TEST"
    finally:
        if os.path.exists(patch_path):
            os.remove(patch_path)


def test_modified_projected_method_uses_ide_guid_in_patch():
    collapsed_type = "6f9dac99-8de1-4efc-8465-68ac443b7d08"
    folder_guid = "71498b85-11de-4b25-85c8-6d5b6d521bfe"
    ide_guid = "45430f7d-c566-400a-b260-e8730d037537"
    parent_guid = PARENT_GUID

    ide_model = ProjectModel()
    folder_model = ProjectModel()
    parent = ProjectNode(parent_guid, "FB_RemoteController_TEST", collapsed_type, None)
    parent.metadata["structured_view_guid"] = "{d9b2b2cc-ea99-4c3b-aa42-1e5c49e65b84}"
    ide_model.add_node(parent)
    folder_model.add_node(parent)

    st_content = (
        "METHOD PRIVATE T06_AutoUpLatchesWinchUp\nVAR\nEND_VAR\n\n"
        "// --- implementation ---\n\n"
        "changed := TRUE;\n"
    )
    folder_node = ProjectNode(
        folder_guid,
        "T06_AutoUpLatchesWinchUp",
        METHOD_TYPE_GUID,
        parent_guid,
    )
    folder_node.metadata["projection_contents"] = {
        "TESTs/FB_RemoteController_TEST.T06_AutoUpLatchesWinchUp.st": st_content,
    }
    folder_node.metadata["projection_changed_paths"] = [
        "TESTs/FB_RemoteController_TEST.T06_AutoUpLatchesWinchUp.st"
    ]
    folder_node.xml_text = (
        "<Single><Single Name='MetaObject'>"
        "<Single Name='Guid'>" + folder_guid + "</Single>"
        "<Single Name='Name'>T06_AutoUpLatchesWinchUp</Single>"
        "</Single></Single>"
    )
    folder_model.add_node(folder_node)

    ide_node = ProjectNode(
        ide_guid,
        "T06_AutoUpLatchesWinchUp",
        METHOD_TYPE_GUID,
        parent_guid,
    )
    ide_node.code = "old"
    ide_model.add_node(ide_node)

    diff_result = {"modified": [ide_guid], "added": [], "deleted": []}
    profile = load_profile("default")

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as handle:
        patch_path = handle.name

    try:
        builder = PatchBuilder(diff_result, ide_model, folder_model, profile=profile)
        assert builder.build_patch(patch_path) is True
        root = ET.parse(patch_path).getroot()
        guids = []
        for elem in root.iter():
            if elem.attrib.get("Name") == "Guid" and elem.text:
                guids.append(elem.text.strip().lower())
        assert ide_guid in guids
        assert folder_guid not in guids
    finally:
        if os.path.exists(patch_path):
            os.remove(patch_path)
