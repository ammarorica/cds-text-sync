# -*- coding: utf-8 -*-
"""
Project_parameters.py - Configure Project parameters
1. Set sync timeout
2. Toggle XML Export

Updates parameters in _metadata.json
"""
import os
import codecs
import json
from codesys_utils import safe_str, load_base_dir, load_metadata, save_metadata

def configure_timeout(base_dir, metadata):
    # Get current timeout
    current_timeout = metadata.get("sync_timeout", 10000)
    
    # Offer predefined timeout options
    message = "Current AutoSync timeout: " + str(current_timeout) + "ms\n\nSelect new timeout interval:"
    options = (
        "2 seconds (2000ms)",
        "5 seconds (5000ms)",
        "10 seconds (10000ms) - Default",
        "15 seconds (15000ms)",
        "30 seconds (30000ms)",
        "Cancel"
    )
    
    result = system.ui.choose(message, options)
    
    if result[0] == 5:  # Cancel
        return False
    
    # Map selection to timeout value
    timeout_map = {
        0: 2000,
        1: 5000,
        2: 10000,
        3: 15000,
        4: 30000
    }
    
    new_timeout = timeout_map.get(result[0])
    if new_timeout is None:
        return False
    
    metadata["sync_timeout"] = new_timeout
    return True

def configure_xml_export(base_dir, metadata):
    # Get current setting (Default to False)
    current_setting = metadata.get("export_xml", False)
    status_text = "ENABLED" if current_setting else "DISABLED"
    
    message = "XML Export is currently: " + status_text + "\n\nDo you want to enable or disable native XML export?\n(Visualizations, Alarms, TextLists, etc.)"
    
    options = (
        "Enable XML Export",
        "Disable XML Export",
        "Cancel"
    )
    
    result = system.ui.choose(message, options)
    
    if result[0] == 2: # Cancel
        return False
        
    new_setting = (result[0] == 0) # True if Enable chosen
    
    if new_setting == current_setting:
        return False
        
    metadata["export_xml"] = new_setting
    return True

def main():
    base_dir, error = load_base_dir()
    if error:
        system.ui.warning(error)
        return
    
    # Load metadata
    metadata = load_metadata(base_dir)
    if not metadata:
        system.ui.error("_metadata.json not found! Run 'Project_export.py' first.")
        return
    
    # Main Menu
    current_timeout = int(metadata.get("sync_timeout", 10000) / 1000)
    current_xml = "ENABLED" if metadata.get("export_xml", False) else "DISABLED"
    
    msg = "Project Parameters Configuration:\n\n"
    msg += "1. Sync Timeout: " + str(current_timeout) + "s\n"
    msg += "2. Export XML: " + current_xml + "\n"
    
    options = (
        "Set sync timeout",
        "Toggle XML export",
        "Exit"
    )
    
    result = system.ui.choose(msg, options)
    
    changed = False
    if result[0] == 0:
        changed = configure_timeout(base_dir, metadata)
    elif result[0] == 1:
        changed = configure_xml_export(base_dir, metadata)
    else:
        return
        
    if changed:
        if save_metadata(base_dir, metadata):
            print("Parameters updated.")
            # Recursive call to show menu again with updated values
            main()
        else:
            system.ui.error("Error saving metadata!")

if __name__ == "__main__":
    main()
