# -*- coding: utf-8 -*-
"""
project_import_diff.py - Fast import entrypoint driven by git diff.

Unlike Project_import.py, which compares the entire project view against the
IDE, this script asks git which view files changed since the last commit (or a
given ref), maps those files back to their object GUIDs, and imports only those
objects. Use it to quickly apply just what you edited.

Optional params:
    git_ref     Diff the working tree against this ref (e.g. "HEAD~1", a branch,
                or a commit). When omitted, all uncommitted changes (staged,
                unstaged, and untracked) are used.
    view_root   Override the project view root.
    layout      Override the layout mode.
"""
from cds_bootstrap import run_project_command


def main(params=None):
    return run_project_command("import_diff", params=params, script_file=__file__, caller_globals=globals())


if __name__ == "__main__":
    main()
