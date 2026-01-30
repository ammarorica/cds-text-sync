# -*- coding: utf-8 -*-
import os

def set_base_directory():
    # CODESYS provides the 'system' object for UI interactions
    if not "projects" in globals() or not projects.primary:
        system.ui.error("No project open! Please open a project to set its sync directory.")
        return

    # Try to read current value for better UX
    initial_dir = ""
    try:
        if "cds-sync-folder" in projects.primary.project_info:
            initial_dir = projects.primary.project_info["cds-sync-folder"]
    except:
        pass

    # Open the dialog
    selected_path = system.ui.browse_directory_dialog("Select Sync Directory for this Project", initial_dir)
    
    if selected_path:
        # Save strictly to project properties
        try:
            projects.primary.project_info["cds-sync-folder"] = selected_path
            print("Success: Project sync directory updated to: " + selected_path)
            system.ui.info("Sync directory saved to Project Information > Properties.")
        except Exception as e:
            system.ui.error("Could not save to project properties: " + str(e))
            return
        
        # Check _metadata.json for project path mismatch
        try:
            metadata_path = os.path.join(selected_path, "_metadata.json")
            if os.path.exists(metadata_path):
                import json
                with open(metadata_path, 'r') as f:
                    data = json.load(f)
                
                json_path = data.get('project_path', '')
                
                # Safe way to get current project path
                current_path = ""
                try:
                    if "projects" in globals() and projects.primary:
                        current_path = projects.primary.path
                except:
                    pass
                
                if current_path and json_path and json_path != current_path:
                    message = "Metadata Mismatch Detected!\n\n"
                    message += "The selected directory contains exports from a different project:\n"
                    message += "Metadata Path: " + json_path + "\n"
                    message += "Current Project: " + current_path + "\n\n"
                    message += "Do you want to update the metadata to match the current project?"
                    
                    # Offer to update
                    res = system.ui.choose(message, ("Yes, Update Metadata", "No, Keep As Is"))
                    
                    if res and res[0] == 0:
                        data['project_path'] = current_path
                        try:
                            data['project_name'] = str(projects.primary)
                        except:
                            pass
                            
                        with open(metadata_path, 'w') as f:
                            json.dump(data, f, indent=2)
                        print("Updated _metadata.json project path to current project.")
                        system.ui.info("Metadata updated successfully.")
                        
        except Exception as e:
            print("Warning: Failed to check metadata: " + str(e))

    else:
        print("Operation cancelled by user.")

if __name__ == "__main__":
    set_base_directory()
