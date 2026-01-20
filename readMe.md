# cds-text-sync

**Version**: `0.9.6-beta`

> [!WARNING]
> **⚠️ BETA SOFTWARE - USE WITH CAUTION ⚠️**
>
> This product is **NOT YET RELEASED** and is currently in active development.
> - Features may be incomplete or unstable
> - Breaking changes may occur without notice
> - **ALWAYS backup your CODESYS project before using these scripts**
> - Test thoroughly in non-production environments first

> [!IMPORTANT]
> **Disclaimer**: This is a third-party tool. It is NOT an official product of CODESYS Group and is not affiliated with, sponsored by, or endorsed by CODESYS Group. This tool is provided "as is" and is not a replacement for official CODESYS products (such as CODESYS Git).

This repository contains a set of Python scripts for **CODESYS** that facilitate two modern Git-based workflows:

### 1. 🔍 Monitor & History (The "Observer" Workflow)
- **Goal**: Track the work of different engineers and maintain a granular history of project changes.
- **Method**: Exports the entire project—including Visualizations, Alarms, Task Configs, and Project Info—to **Native XML** files.
- **Benefit**: Even binary-heavy parts of the project become visible in Git, allowing you to see *who* changed *what* and *when*, directly in your version control system. Changes made inside the CODESYS IDE are captured and stored safely.

### 2. ⚡ External Editing & Sync (The "Developer" Workflow)
- **Goal**: Edit code using modern external tools (VS Code, Copilot/LLMs) and sync changes back to CODESYS.
- **Method**: Exports logic (POUs, GVLs, DUTs) to clean **Structured Text (.st)** files.
- **Benefit**: You can refactor code, use AI assistants, or mass-edit variables externally. The `Project_import.py` script then seamlessly updates your open CODESYS project with the new logic.

---

![Workflow Preview](img/WorkflowPreview.gif)

## 🚀 Key Features

- **Hybrid Export**: Choose between "Code Only" (ST) for development or "Full Project" (ST + XML) for archival and history tracking.
- **Git Friendly**: Organizes all exports into a clean folder structure matching your project tree.
- **Smart Metadata**: Uses GUIDs to ensure reliable syncing even if you rename or move objects.
- **Reversible Sync**: Round-trip editing for Structured Text files.
- **Safety**: Built-in checks to prevent overwriting the wrong project.

---

## 🛠️ Installation

1. **Copy Files**: Copy all `.py` files to the CODESYS scripts directory:
   `C:\Users\<YourUsername>\AppData\Local\CODESYS\ScriptDir\`

2. **Access in CODESYS**:
   - The scripts will be available in **Tools > Scripting > Scripts > P**.
   - Note: They appear in the "P" sub-menu because they all start with `Project_`.

3. **Add to Toolbar (Optional but Recommended)**:
   - Go to **Tools > Customize > Toolbars**.
   - Select **Standard** (or create a new one).
   - Click **Add Command**.
   - Look for **ScriptEngine Commands > P**.
   - Add the desired scripts to your toolbar for one-click access.

---

## 📖 Script Overview

### Core Scripts

#### 1. `Project_directory.py`
**The First Step.** Run this to select the folder on your computer where your code should be synced. This creates a `BASE_DIR` file in the script directory to remember your choice.

#### 2. `Project_export.py`
Exports the current CODESYS project to the selected directory.
- Creates `.st` files for all POUs, Methods, Actions, Properties, GVLs, and DUTs.
- Generates a `_metadata.json` file with project info, sync settings, and object mappings.
- **Safety Check**: Warns if exporting to a directory containing a different project's files.
- **CRITICAL**: Do not delete `_metadata.json`, as it's required for importing.

#### 3. `Project_import.py`
Reads the `.st` files in your sync directory and updates the CODESYS project.
- **Smart Update**: Matches existing files to CODESYS objects using metadata.
- **New Creation**: Automatically creates new Folders, POUs, GVLs, and DUTs found in the file system.
- **Child Objects**: Supports creating Methods, Actions, and Properties (e.g., `MyPOU.MyAction.st`).
- **Warning**: This will overwrite the code in your open CODESYS project. Always have a backup!

#### 4. `Project_ImportSync.py`
Auto-synchronize external file changes to CODESYS (one-way: Folder → IDE).
- Monitors exported `.st` files for changes
- Automatically updates CODESYS objects when files are modified
- Configurable sync interval via `Project_parameters.py`
- Run once to START, run again to STOP

#### 5. `Project_parameters.py`
Configuration hub for the toolset.
- **Sync Timeout**: Set the check interval for AutoSync (2s - 30s).
- **XML Export**: Toggle Native XML export ON/OFF.
  - **ON**: Exports Visualizations, Alarms, TextLists, etc., for full project history.
  - **OFF**: Exports only ST code for faster, cleaner external development.

#### 6. `Erase_comments_add_Header.py`
Utility to remove comments and add copyright headers to exported files.

### Shared Modules

#### `codesys_constants.py`
Central repository for CODESYS type GUIDs and constants.
- Defines `EXPORTABLE_TYPES` (ST) and `XML_TYPES` (Native XML)

#### `codesys_utils.py`
Common utility functions used across all scripts.

---

## 🔄 Recommended Workflow

### For Version Control & History:
1.  Open **`Project_parameters.py`** and **Enable XML Export**.
2.  Run **`Project_export.py`**.
3.  Commit the result to Git. You now have a snapshot of your entire project, including HMI and configuration.

### For External Development:
1.  Open **`Project_parameters.py`** and **Disable XML Export** (or leave it auto-disabled after the first run).
2.  Run **`Project_export.py`**.
3.  Open the `.st` files in VS Code / Cursor to edit logic.
4.  Run **`Project_import.py`** (or AutoSync) to push logic changes back to the PLC.

**Why different modes?**
- **XML** files are great for history but can be complex to merge or edit manually.
- **ST** files are perfect for editing but don't capture the visual layout of an HMI screen.

---

## ⚠️ Important Notes

- **⚠️ BETA STATUS**: This software is in active development. **Always backup your project** before using any script.
- **Metadata**: The `_metadata.json` file contains project info and object mappings. You can manually edit sync settings if needed, but don't modify the `objects` section.
- **Backups**: Always save a `.project` backup before running an import.
- **Creating New Blocks**: You can now create new `.st` files and folders directly in your OS. The import script will automatically create the corresponding objects (POUs, GVLs, Folders) in CODESYS.

---

## 📝 Changelog

### Version 0.9.6-beta (2026-01-20)

**New Features:**
- **Full Folder Support**: The importer now creates new folder structures (nested directories) to match your file system.
- **New Object Creation**: You can create `.st` files externally, and they will be imported as new POUs, GVLs, or DUTs.
- **Child Object Support**: Methods, Actions, and Properties (e.g., `Parent.Child.st`) are now correctly identified and created under their parent POU.
- **Robust Import**: Implemented a two-pass import process (Parents then Children) to ensure 100% reliable object creation.

### Version 0.9.2-beta (2026-01-20)

**Major Refactoring:**
- Extracted common code into shared modules (`codesys_constants.py` and `codesys_utils.py`)
- Reduced code duplication by ~300 lines across 5 scripts
- Centralized CODESYS type GUIDs and constants
- Improved maintainability and consistency

**Bug Fixes:**
- **CRITICAL FIX**: Fixed `build_object_cache()` not finding objects when called from imported modules
  - Issue: Imported modules don't have access to CODESYS global variables (`projects`)
  - Solution: Modified function to accept project as parameter
  - Impact: Import and AutoSync now work correctly
- Updated all scripts to pass `projects.primary` to `build_object_cache()`

**New Files:**
- `codesys_constants.py` - Shared constants and type definitions
- `codesys_utils.py` - Shared utility functions
- `debug_metadata.py` - Diagnostic tool for troubleshooting
- `REFACTORING_SUMMARY.md` - Detailed refactoring documentation

**See Also:**
- [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md) for detailed refactoring information

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
