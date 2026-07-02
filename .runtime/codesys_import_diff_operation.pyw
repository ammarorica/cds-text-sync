# -*- coding: utf-8 -*-
"""
codesys_import_diff_operation.pyw - Fast import driven by git diff.

Instead of comparing the whole project view against the IDE, this operation
asks git which view files changed, maps those files back to their object GUIDs
via the export manifest, and then runs a selective import limited to just those
GUIDs. This lets a user quickly apply only what they edited since the last
commit.

Must stay compatible with the CODESYS IronPython 2.7 bridge (no f-strings).
"""
from __future__ import print_function
import json
import os
import subprocess
import sys

from codesys_runtime import resolve_runtime
from codesys_utils import load_base_dir, init_logging, resolve_projects


def _run_git(args, cwd):
    """Run a git command and return stdout text, or None on failure."""
    cmd = ["git"] + list(args)
    kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "cwd": cwd}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    try:
        proc = subprocess.Popen(cmd, **kwargs)
        out, err = proc.communicate()
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    if out is None:
        return ""
    try:
        return out.decode("utf-8", "replace")
    except Exception:
        return out


def _git_repo_root(cwd):
    text = _run_git(["rev-parse", "--show-toplevel"], cwd)
    if text is None:
        return None
    text = text.strip()
    return text or None


def _changed_repo_paths(repo_root, git_ref=None):
    """Collect repo-relative paths of files that changed.

    When git_ref is given we diff the working tree against it. Otherwise we
    gather every uncommitted change: staged, unstaged, and untracked.
    """
    paths = set()

    if git_ref:
        text = _run_git(["diff", "--name-only", git_ref, "--"], repo_root)
        for line in (text or "").splitlines():
            line = line.strip()
            if line:
                paths.add(line)
        return paths

    for args in (
        ["diff", "--name-only", "--"],           # unstaged edits
        ["diff", "--name-only", "--cached", "--"],  # staged edits
        ["ls-files", "--others", "--exclude-standard"],  # untracked files
    ):
        text = _run_git(args, repo_root)
        for line in (text or "").splitlines():
            line = line.strip()
            if line:
                paths.add(line)
    return paths


def _relative_to_view(abs_path, view_root):
    try:
        rel = os.path.relpath(abs_path, view_root)
    except Exception:
        return None
    rel = rel.replace(os.sep, "/")
    if rel == "." or rel.startswith("../") or rel == "..":
        return None
    return rel


def _load_manifest_path_map(manifest_path, normalize_guid):
    """Build a map of view-relative file path -> object GUID from the manifest."""
    path_to_guid = {}
    if not os.path.exists(manifest_path):
        return path_to_guid
    try:
        with open(manifest_path, "r") as handle:
            manifest = json.load(handle)
    except Exception:
        return path_to_guid

    for entry in manifest.get("entries", []) or []:
        guid = normalize_guid(entry.get("guid") or "")
        if not guid:
            continue
        managed = []
        if entry.get("xml_path"):
            managed.append(entry.get("xml_path"))
        if entry.get("view_path"):
            managed.append(entry.get("view_path"))
        for projection_path in entry.get("projection_paths") or []:
            managed.append(projection_path)
        for raw_path in managed:
            if not raw_path:
                continue
            key = str(raw_path).replace("\\", "/").lstrip("./").lower()
            path_to_guid[key] = guid
    return path_to_guid


def _match_guids(changed_paths, repo_root, view_root, path_to_guid, normalize_guid):
    guids = []
    seen = {}
    matched_files = []
    for repo_rel in sorted(changed_paths):
        abs_path = os.path.normpath(os.path.join(repo_root, repo_rel))
        view_rel = _relative_to_view(abs_path, view_root)
        if not view_rel:
            continue
        guid = path_to_guid.get(view_rel.lower())
        if not guid:
            continue
        guid = normalize_guid(guid)
        if guid and guid not in seen:
            seen[guid] = True
            guids.append(guid)
        matched_files.append(view_rel)
    return guids, matched_files


def main(params=None, runtime=None):
    params = params or {}
    runtime = resolve_runtime(runtime, caller_globals=globals(), params=params)

    base_dir, error = load_base_dir()
    if error:
        runtime.ui.warning(error)
        return {"status": "error", "error": error}

    init_logging(base_dir)
    projects_obj = resolve_projects(runtime.projects, runtime.caller_globals)

    if projects_obj is None or not projects_obj.primary:
        message = "Error: 'projects' object not found or no project open."
        runtime.ui.error(message)
        return {"status": "error", "error": message}

    system = runtime.system
    project = projects_obj.primary

    utility_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bridge_dir = os.path.join(utility_root, "src", "ide_bridge")
    if bridge_dir not in sys.path:
        sys.path.insert(0, bridge_dir)

    try:
        import ide_run_action
        import ide_runtime_common

        project_layout = ide_runtime_common.layout(
            base_dir,
            view_root=params.get("view_root"),
            layout_mode=params.get("layout"),
        )
        view_root = project_layout.view_root
        manifest_path = os.path.join(project_layout.dump_root, "manifest.json")

        repo_root = _git_repo_root(view_root) or _git_repo_root(base_dir)
        if not repo_root:
            message = (
                "Could not locate a git repository for the project view.\n"
                "Make sure the sync folder is inside a git working tree."
            )
            runtime.ui.error(message)
            return {"status": "error", "error": message}

        git_ref = params.get("git_ref") or params.get("git_diff_ref")
        changed_paths = _changed_repo_paths(repo_root, git_ref=git_ref)
        if not changed_paths:
            runtime.ui.info(
                "No git changes detected. Nothing to import."
            )
            return {"status": "success", "action": "none"}

        path_to_guid = _load_manifest_path_map(
            manifest_path, ide_runtime_common.normalize_guid
        )
        if not path_to_guid:
            message = (
                "Export manifest not found or empty at:\n{0}\n\n"
                "Run an export first so changed files can be mapped to objects."
            ).format(manifest_path)
            runtime.ui.warning(message)
            return {"status": "error", "error": "manifest_missing"}

        selected_guids, matched_files = _match_guids(
            changed_paths,
            repo_root,
            view_root,
            path_to_guid,
            ide_runtime_common.normalize_guid,
        )

        if not selected_guids:
            runtime.ui.info(
                "Found {0} changed file(s) in git, but none map to tracked "
                "project objects under:\n{1}".format(len(changed_paths), view_root)
            )
            return {"status": "success", "action": "none"}

        ide_runtime_common.log_info(
            "Git-diff import: {0} changed object(s) from {1} matched file(s).".format(
                len(selected_guids), len(matched_files)
            )
        )

        if ide_run_action.run_action(
            "import",
            system,
            project,
            base_dir,
            view_root=params.get("view_root"),
            layout_mode=params.get("layout"),
            selected_guids=selected_guids,
        ):
            runtime.ui.info(
                "Git-diff import completed for {0} changed object(s).".format(
                    len(selected_guids)
                )
            )
            return {
                "status": "success",
                "action": "import",
                "selected_guids": selected_guids,
                "matched_files": matched_files,
            }

        runtime.ui.error("Git-diff import failed. Check logs in the external engine.")
        return {"status": "error", "action": "import"}
    except Exception as e:
        runtime.ui.error("Error running git-diff import: " + str(e))
        return {"status": "error", "error": str(e)}
