# -*- coding: utf-8 -*-
"""
Project_parameters.py - Configure Project parameters
1. Toggle XML Export
2. Toggle Project Binary Backup

Updates parameters in Project Information > Properties
"""
import os
from codesys_utils import safe_str, load_base_dir, get_project_prop, set_project_prop

def main():
    base_dir, error = load_base_dir()
    if error:
        system.ui.warning(error)
        return
    
    while True:
        # Get current settings
        export_xml = get_project_prop("cds-sync-export-xml", False)
        backup_binary = get_project_prop("cds-sync-backup-binary", False)
        save_after_import = get_project_prop("cds-sync-save-after-import", True)

        # Build menu options
        xml_opt = "[x] Export Native XML (Visu/Alarms)" if export_xml else "[ ] Export Native XML (Visu/Alarms)"
        backup_opt = "[x] Backup .project binary (Git LFS)" if backup_binary else "[ ] Backup .project binary (Git LFS)"
        save_opt = "[x] Save Project after Import" if save_after_import else "[ ] Save Project after Import"
        
        message = "Configure Project Sync Parameters:\n(Settings are saved in Project Information)"
        
        options = (
            xml_opt,
            backup_opt,
            save_opt,
            "Exit"
        )
        
        try:
            result = system.ui.choose(message, options)
        except:
            return

        if result is None: # Dialog closed
            return
            
        choice = result[0]
        
        if choice == 0: # Toggle XML
            set_project_prop("cds-sync-export-xml", not export_xml)
            print("Updated XML Export -> " + str(not export_xml))
            
        elif choice == 1: # Toggle Backup
            set_project_prop("cds-sync-backup-binary", not backup_binary)
            print("Updated Binary Backup -> " + str(not backup_binary))
            
        elif choice == 2: # Toggle Save
            set_project_prop("cds-sync-save-after-import", not save_after_import)
            print("Updated Save After Import -> " + str(not save_after_import))
            
        else: # Exit
            return

if __name__ == "__main__":
    main()
