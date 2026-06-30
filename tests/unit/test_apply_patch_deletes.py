# -*- coding: utf-8 -*-

import os
import tempfile

from ide_apply_patch import apply_patch
from ide_apply_patch_regression import FakeObject, FakeProject


def test_apply_patch_deletes_method_by_guid():
    project = FakeProject()
    app = project._add_child(FakeObject(project, "Application", project))
    parent = app._add_child(FakeObject(project, "FB_RemoteController_TEST", app))
    method = parent._add_child(
        FakeObject(project, "T07_StopDownLatchesRetract", parent)
    )
    method.guid = "a8b1beb5-9eb9-4aa9-9f78-9f733a4eb4c2"

    patch = (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<Project>"
        "<DeleteTextObjects>"
        '<DeleteTextObject Guid="a8b1beb5-9eb9-4aa9-9f78-9f733a4eb4c2"'
        ' Name="T07_StopDownLatchesRetract" ParentName="FB_RemoteController_TEST"'
        ' Path="Device/Application/FB_RemoteController_TEST.T07_StopDownLatchesRetract.st" />'
        "</DeleteTextObjects>"
        "</Project>"
    )

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False, mode="w") as handle:
        handle.write(patch)
        patch_path = handle.name

    try:
        result = apply_patch(None, project, patch_path)
        assert result.success
        assert "a8b1beb5-9eb9-4aa9-9f78-9f733a4eb4c2" in result.deleted_guids
        assert "remove:T07_StopDownLatchesRetract" in project.events
        assert method not in parent.children
    finally:
        os.remove(patch_path)
