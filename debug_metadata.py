# -*- coding: utf-8 -*-
"""
Debug script to check metadata and project info
"""
import os
import codecs
import json
from codesys_utils import safe_str, load_base_dir, load_metadata, build_object_cache
from codesys_constants import EXPORTABLE_TYPES

def main():
    # 1. API Exploration First (doesn't depend on load_base_dir)
    print("=== CODESYS API Exploration ===")
    if not "projects" in globals() or not projects.primary:
        print("ERROR: No project open in CODESYS!")
        return
        
    proj = projects.primary
    print("Current project object: " + str(proj))
    
    # Check attributes
    attrs = dir(proj)
    print("\nProject attributes/methods containing 'info':")
    print([a for a in attrs if "info" in a.lower()])
    
    # Detect Project Info Method
    info_obj = None
    if hasattr(proj, "project_info"):
        print("Using: proj.project_info")
        info_obj = proj.project_info
    elif hasattr(proj, "get_project_info"):
        print("Using: proj.get_project_info()")
        info_obj = proj.get_project_info()
    else:
        print("CRITICAL: No known way to access Project Information found!")

    if info_obj:
        print("Project Info Contents Exploration:")
        access_methods = [
            ("Indexing info_obj['cds-sync-folder']", lambda: info_obj["cds-sync-folder"]),
            ("Property sets info_obj.property_sets", lambda: info_obj.property_sets),
            ("Values property info_obj.values", lambda: info_obj.values),
            ("Summary property info_obj.summary", lambda: info_obj.summary),
            ("Direct getattr 'cds-sync-folder'", lambda: getattr(info_obj, "cds-sync-folder", "MISSING"))
        ]
        
        for name, method in access_methods:
            try:
                res = method()
                print("  SUCCESS: " + name + " -> " + str(res))
            except Exception as e:
                print("  FAILED: " + name + " -> " + str(e))
        
        # Try to iterate if somehow possible
        try:
             print("Keys via dir(): " + str(dir(info_obj)))
        except: pass
        
    # 2. Now try to load base dir using the utility
    print("\n=== Sync Configuration Check ===")
    base_dir, error = load_base_dir()
    if error:
        print("Status: " + error)
    else:
        print("Base directory: " + base_dir)
    
    print("Current project: " + safe_str(projects.primary))
    
    # --- API EXPLORATION ---
    print("\n--- API Exploration (Searching for Project Info) ---")
    proj_attrs = dir(projects.primary)
    found_info_methods = [a for a in proj_attrs if "info" in a.lower()]
    print("Available 'info' related attributes/methods: " + str(found_info_methods))
    
    # Try common alternatives
    for alt in ["get_project_info", "project_info", "get_info"]:
        if hasattr(projects.primary, alt):
            try:
                val = getattr(projects.primary, alt)
                if callable(val):
                    print("Found method: " + alt + "() -> " + str(val()))
                else:
                    print("Found property: " + alt + " -> " + str(val))
            except Exception as e:
                print("Error accessing " + alt + ": " + str(e))

    if hasattr(projects.primary, "path"):
        print("\nProject path: " + safe_str(projects.primary.path))
    
    print("")
    
    # Load metadata
    metadata = load_metadata(base_dir)
    if metadata:
        print("Metadata file exists:")
        print("  - Project name in metadata: " + metadata.get("project_name", "N/A"))
        print("  - Project path in metadata: " + metadata.get("project_path", "N/A"))
        print("  - Export timestamp: " + metadata.get("export_timestamp", "N/A"))
        print("  - Number of objects: " + str(len(metadata.get("objects", {}))))
        
        # Show first few GUIDs from metadata
        print("")
        print("Sample GUIDs from metadata:")
        objects_meta = metadata.get("objects", {})
        count = 0
        for rel_path, obj_info in objects_meta.items():
            print("  - " + obj_info.get("name", "?") + " = " + obj_info.get("guid", "N/A")[:16] + "...")
            count += 1
            if count >= 3:
                break
    else:
        print("No metadata file found")
    
    print("")
    
    # Build object cache
    print("Building object cache...")
    guid_map, name_map = build_object_cache(projects.primary)
    print("  - Found " + str(len(guid_map)) + " objects with GUIDs")
    print("  - Found " + str(len(name_map)) + " unique names")
    
    print("")
    print("Sample exportable objects from current project:")
    try:
        all_objects = projects.primary.get_children(recursive=True)
        count = 0
        for obj in all_objects:
            try:
                obj_type = safe_str(obj.type)
                if obj_type not in EXPORTABLE_TYPES:
                    continue
                    
                obj_name = obj.get_name()
                obj_guid = safe_str(obj.guid)
                print("  - " + obj_name + " = " + obj_guid[:16] + "...")
                count += 1
                if count >= 3:
                    break
            except:
                continue
        
        if count == 0:
            print("  WARNING: No exportable objects found!")
    except Exception as e:
        print("Error getting objects: " + safe_str(e))
    
    # Check if metadata GUIDs exist in project
    if metadata and guid_map:
        print("")
        print("Checking if metadata GUIDs exist in project:")
        objects_meta = metadata.get("objects", {})
        found_count = 0
        missing_count = 0
        
        for rel_path, obj_info in objects_meta.items():
            guid = obj_info.get("guid")
            if guid in guid_map:
                found_count += 1
            else:
                missing_count += 1
                if missing_count <= 3:
                    print("  MISSING: " + obj_info.get("name", "?") + " (GUID: " + guid[:16] + "...)")
        
        print("")
        print("Result: " + str(found_count) + " found, " + str(missing_count) + " missing")
        
        if missing_count == len(objects_meta):
            print("ERROR: NONE of the metadata GUIDs were found in the project!")
            print("This means the metadata is from a DIFFERENT project instance.")

if __name__ == "__main__":
    main()
