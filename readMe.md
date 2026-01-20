# cds-text-sync

**Version**: `0.9.1-beta`

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

This repository contains a set of Python scripts for **CODESYS** that enable a reversible, text-based workflow for project development. It allows you to export your CODESYS project code to a structured folder system, edit it using modern tools (like VS Code or LLMs), and import the changes back into CODESYS.

![Workflow Preview](img/WorkflowPreview.gif)

## 🚀 Key Features

- **Reversible Sync**: Round-trip export and import of POUs, GVLs, and DUTs.
- **Git Friendly**: Exports code to standard `.st` (Structured Text) files organized by project hierarchy.
- **Metadata-Driven**: Uses GUIDs and metadata to ensure reliable updates even if objects are moved or renamed in the project.
- **Safety Checks**: Project identity verification on export.

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

### 1. `Project_directory.py`
**The First Step.** Run this to select the folder on your computer where your code should be synced. This creates a `BASE_DIR` file in the script directory to remember your choice.

### 2. `Project_export.py`
Exports the current CODESYS project to the selected directory.
- Creates `.st` files for all POUs, Methods, Actions, Properties, GVLs, and DUTs.
- Generates a `_metadata.json` file with project info, sync settings, and object mappings.
- **Safety Check**: Warns if exporting to a directory containing a different project's files.
- **CRITICAL**: Do not delete `_metadata.json`, as it's required for importing.

### 3. `Project_import.py`
Reads the `.st` files in your sync directory and updates the CODESYS project.
- Matches files to CODESYS objects using the metadata.
- **Untracked File Warning**: If you create new `.st` files or folders directly in the file system, the script will skip them and warn you with a popup list after importing.
- **Warning**: This will overwrite the code in your open CODESYS project. Always have a backup!

### 4. `Project_set_sync_timeout.py`
Configure the sync check interval for exports.
- Offers predefined timeout options (2s, 5s, 10s, 15s, 30s)
- Updates timeout settings in `_metadata.json`

---

## 🔄 Recommended Workflow

1. **Configure**: Run `Project_directory.py` and select your local Git repository folder.
2. **Export**: Run `Project_export.py`.
3. **Commit**: Use Git to track your changes.
4. **Edit**: Open the `.st` files in your favorite editor (VS Code, etc.) and make changes.
   - **Tip**: If you need a new POU/GVL, create it (even as an empty block) in **CODESYS IDE first**, then run Export. This ensures the object has a valid GUID in the metadata.
5. **Review**: Use Git to review your edits.
6. **Import**: Run `Project_import.py` in CODESYS to bring the changes back into the PLC environment.

---

## ⚠️ Important Notes

- **⚠️ BETA STATUS**: This software is in active development. **Always backup your project** before using any script.
- **Metadata**: The `_metadata.json` file contains project info and object mappings. You can manually edit sync settings if needed, but don't modify the `objects` section.
- **Backups**: Always save a `.project` backup before running an import.
- **Creating New Blocks**: The best workflow is to **create the block name in CODESYS IDE first**, export it, and then fill the content externally. Creating files manually in the folder system will trigger a warning during import because they lack metadata.

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
