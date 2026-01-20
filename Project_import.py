# -*- coding: utf-8 -*-
"""
Project_import.py - Import edited ST files back into CODESYS project

Reads _metadata.json to match files to CODESYS objects by GUID, then updates
the textual declaration and implementation from the ST files.

Usage: Run from CODESYS IDE after exporting with Project_export.py and editing files
"""
import os
import codecs
import json
import time
from codesys_constants import IMPL_MARKER, TYPE_GUIDS
from codesys_utils import (
    safe_str, parse_st_file, build_object_cache, 
    find_object_by_guid, find_object_by_name, load_base_dir,
    calculate_hash, save_metadata
)

# Shared constants and utilities imported from modules





def update_object_code(obj, declaration, implementation):
    """
    Update object's textual declaration and/or implementation.
    Returns True if any update was made.
    """
    updated = False
    obj_name = safe_str(obj.get_name())
    
    # Update declaration
    if declaration:
        try:
            if hasattr(obj, "has_textual_declaration") and obj.has_textual_declaration:
                obj.textual_declaration.replace(declaration)
                updated = True
            else:
                print("  Warning: " + obj_name + " has no textual declaration property")
        except Exception as e:
            print("  Error updating declaration for " + obj_name + ": " + safe_str(e))
    
    # Update implementation
    if implementation:
        try:
            if hasattr(obj, "has_textual_implementation") and obj.has_textual_implementation:
                obj.textual_implementation.replace(implementation)
                updated = True
            else:
                # This is normal for GVLs and DUTs - they only have declaration
                pass
        except Exception as e:
            print("  Error updating implementation for " + obj_name + ": " + safe_str(e))
    
    return updated





def determine_object_type(content):
    """Determine CODESYS object type from ST content"""
    content = content.strip()
    lines = content.splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("(*") or line.startswith("//") or line.startswith("{"):
            continue
        
        # Check keywords
        parts = line.split()
        if not parts:
            continue
        word = parts[0].upper()
        
        if word == "PROGRAM":
            return TYPE_GUIDS["pou"]
        if word == "FUNCTION_BLOCK":
            return TYPE_GUIDS["pou"]
        if word == "FUNCTION":
            return TYPE_GUIDS["pou"]
        if word == "VAR_GLOBAL":
            return TYPE_GUIDS["gvl"]
        if word == "TYPE":
            return TYPE_GUIDS["dut"]
        if word == "INTERFACE":
            return TYPE_GUIDS["itf"]
        break
    return None


def ensure_folder_path(path_str):
    """
    Ensure folder structure exists in CODESYS project.
    path_str: relative path string e.g. "Folder/SubFolder"
    Returns the parent object (folder) or None if failed.
    """
    # Find the Application or PLC Logic container to avoid device tree
    start_obj = None
    
    def find_application_recursive(obj, depth=0):
        """Recursively search for Application or PLC Logic container"""
        if depth > 3:  # Limit recursion depth
            return None
            
        try:
            children = obj.get_children()
            for child in children:
                try:
                    child_type = safe_str(child.type)
                    child_name = safe_str(child.get_name())
                    
                    if depth == 0:
                        print("    - " + child_name + " (type: " + child_type + ")")
                    
                    # Found Application - this is what we want!
                    if child_type == TYPE_GUIDS["application"]:
                        return child
                    
                    # Search inside devices and PLC Logic
                    if child_type == TYPE_GUIDS["device"] or child_type == TYPE_GUIDS["plc_logic"]:
                        result = find_application_recursive(child, depth + 1)
                        if result:
                            return result
                except:
                    continue
        except:
            pass
        return None
    
    try:
        print("  Searching for Application/PLC Logic container...")
        children = projects.primary.get_children()
        print("  Found " + str(len(children)) + " top-level children")
        
        start_obj = find_application_recursive(projects.primary, 0)
        
        if start_obj:
            try:
                container_name = safe_str(start_obj.get_name())
                container_type = safe_str(start_obj.type)
                print("  >>> Using container: " + container_name + " (type: " + container_type + ")")
            except:
                print("  >>> Found container")
    except Exception as e:
        print("  Error getting project children: " + safe_str(e))
        pass
    
    # Fallback to primary project if we can't find Application
    if start_obj is None:
        print("  Warning: Could not find Application/PLC Logic container, using project root")
        start_obj = projects.primary
    
    if not path_str or path_str == ".":
        return start_obj
        
    parts = path_str.replace("\\", "/").split("/")
    current_obj = start_obj
    
    for part in parts:
        if not part: continue
        
        # Try to find child with this name (case-insensitive)
        matches = []
        try:
            children = current_obj.get_children()
        except:
            children = []
            
        for child in children:
            if child.get_name().lower() == part.lower():
                # Exclude devices from matching - we only want code structure
                try:
                    child_type = safe_str(child.type)
                    if child_type == TYPE_GUIDS["device"]:
                        continue  # Skip devices
                except:
                    pass
                matches.append(child)
        
        found = None
        
        # Debug: show what we found
        if len(matches) > 0:
            print("  Found " + str(len(matches)) + " match(es) for '" + part + "':")
            for m in matches:
                try:
                    m_type = safe_str(m.type)
                    m_name = safe_str(m.get_name())
                    has_create = "Yes" if hasattr(m, "create_child") else "No"
                    
                    # Identify type name
                    type_name = "unknown"
                    for k, v in TYPE_GUIDS.items():
                        if v == m_type:
                            type_name = k
                            break
                    
                    print("    - " + m_name + " (type: " + type_name + ", can create children: " + has_create + ")")
                except:
                    pass
        
        # Priority 1: Exact Folder Match (check type, not instance GUID)
        for m in matches:
            try:
                obj_type = safe_str(m.type)
                if obj_type == TYPE_GUIDS["folder"]:
                    found = m
                    print("  >>> Selected folder: " + safe_str(m.get_name()))
                    break
            except:
                pass
                
        # Priority 2: Object that definitely supports children (Application, etc)
        if not found:
            for m in matches:
                if hasattr(m, "create_child"):
                    found = m
                    try:
                        print("  Selected object with create_child: " + safe_str(m.get_name()) + " (type: " + safe_str(m.type) + ")")
                    except:
                        print("  Selected object with create_child")
                    break
                    
        # Priority 3: Existing exact match checking (fallback)
        if not found and matches:
             # Just use the first one if we couldn't find a better one
             # This might fail later if it's the wrong one, but we have no other choice if we don't want to try creating duplicate
             found = matches[0]
             print("  Selected first match: " + safe_str(found.get_name()))

        if found:
            current_obj = found
        else:
            # Create folder
            try:
                # Get parent name safely
                try:
                    parent_name = safe_str(current_obj.get_name())
                except:
                    parent_name = "Project Root"
                    
                print("  Creating folder: " + part + " in " + parent_name)
                
                # Check if parent supports creating children
                if not hasattr(current_obj, "create_child"):
                    print("  Error: Parent object " + parent_name + " does not support create_child (Attribute missing)")
                    # Debug info
                    try:
                        print("  Parent GUID: " + safe_str(current_obj.guid))
                        print("  Parent Type: " + safe_str(current_obj.type))
                        # Identify what this object type is
                        obj_type = safe_str(current_obj.type)
                        for k, v in TYPE_GUIDS.items():
                             if v == obj_type:
                                 print("  Parent Type Name: " + k)
                    except:
                        pass
                    return None
                    
                current_obj = current_obj.create_child(part, TYPE_GUIDS["folder"])
            except Exception as e:
                print("  Error creating folder " + part + ": " + safe_str(e))
                return None
                
    return current_obj


def import_project(import_dir):
    """Import ST files from folder structure back into CODESYS project"""
    
    if not projects.primary:
        system.ui.error("No project open!")
        return
    
    print("=== Starting Project Import ===")
    start_time = time.time()
    print("Import directory: " + import_dir)
    
    # Find Application container early for object creation
    print("Searching for Application/PLC Logic container...")
    app_container = None
    
    def find_application_recursive(obj, depth=0):
        """Recursively search for Application or PLC Logic container"""
        if depth > 3:
            return None
        try:
            children = obj.get_children()
            for child in children:
                try:
                    child_type = safe_str(child.type)
                    if child_type == TYPE_GUIDS["application"]:
                        return child
                    if child_type == TYPE_GUIDS["device"] or child_type == TYPE_GUIDS["plc_logic"]:
                        result = find_application_recursive(child, depth + 1)
                        if result:
                            return result
                except:
                    continue
        except:
            pass
        return None
    
    try:
        app_container = find_application_recursive(projects.primary, 0)
        if app_container:
            try:
                container_name = safe_str(app_container.get_name())
                print(">>> Using Application container: " + container_name)
            except:
                print(">>> Found Application container")
    except Exception as e:
        print("  Error searching for Application: " + safe_str(e))
    
    if not app_container:
        print("  Warning: Could not find Application container")
    
    # Load metadata
    metadata_path = os.path.join(import_dir, "_metadata.json")
    if not os.path.exists(metadata_path):
        system.ui.error("_metadata.json not found!\n\nPlease run Project_export.py first to generate the metadata file.")
        return
    
    try:
        with codecs.open(metadata_path, "r", "utf-8") as f:
            metadata = json.load(f)
    except Exception as e:
        system.ui.error("Error reading _metadata.json: " + safe_str(e))
        return
    
    objects_meta = metadata.get("objects", {})
    print("Found " + str(len(objects_meta)) + " objects in metadata")
    
    # Build cache for fast lookup
    print("Building object cache...")
    guid_map, name_map = build_object_cache(projects.primary)
    
    untracked_items = []
    
    # Build a set of folders that ARE tracked (as parents of known objects)
    tracked_folders = set()
    for rel_path in objects_meta.keys():
        parts = rel_path.split("/")
        for i in range(1, len(parts)):
            tracked_folders.add("/".join(parts[:i]))
    
    # Identify new files not in metadata
    new_files = []
    for root, dirs, files in os.walk(import_dir):
        # Prune hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for name in files:
            if name in ["_metadata.json", "BASE_DIR"] or name.startswith('.'):
                continue
            if not name.endswith(".st"):
                continue
            
            rel_path = os.path.relpath(os.path.join(root, name), import_dir).replace(os.sep, "/")
            if rel_path not in objects_meta:
                new_files.append((rel_path, os.path.join(root, name)))
    
    updated_count = 0
    failed_count = 0
    skipped_count = 0
    created_count = 0
    
    # Process each file in metadata
    for rel_path, obj_info in objects_meta.items():
        file_path = os.path.join(import_dir, rel_path.replace("/", os.sep))
        
        if not os.path.exists(file_path):
            print("Skipped (file missing): " + rel_path)
            skipped_count += 1
            continue
        
        obj_guid = obj_info.get("guid")
        obj_name = obj_info.get("name")
        parent_name = obj_info.get("parent")
        
        print("Processing: " + rel_path)
        
        # Find object - prefer GUID matching
        obj = None
        if obj_guid and obj_guid != "N/A":
            obj = find_object_by_guid(obj_guid, guid_map)
        
        # Fallback to name matching
        if obj is None and obj_name:
            obj = find_object_by_name(obj_name, name_map, parent_name)
        
        if obj is None:
            print("  Failed: Object not found in project")
            failed_count += 1
            continue
        
        # Parse file
        declaration, implementation = parse_st_file(file_path)
        
        if declaration is None and implementation is None:
            print("  Skipped: No content in file")
            skipped_count += 1
            continue
            
        # Check content hash
        # Reconstruct content exactly as export does to be sure
        full_content = declaration
        if implementation:
            full_content += "\n\n// === IMPLEMENTATION ===\n" + implementation
            
        current_hash = calculate_hash(full_content)
        stored_hash = obj_info.get("content_hash", "")
        
        if current_hash == stored_hash:
            print("  Skipped: Content unchanged (Hash match)")
            skipped_count += 1
            continue
        
        # Update object
        if update_object_code(obj, declaration, implementation):
            print("  Updated: " + safe_str(obj.get_name()))
            updated_count += 1
            # Update hash in metadata
            obj_info["content_hash"] = current_hash
        else:
            print("  No changes applied")
            skipped_count += 1
            
    # Process new files
    if new_files:
        print("=== Processing New Files ===")
        for rel_path, file_path in new_files:
            print("Found new file: " + rel_path)
            
            # Parse content
            declaration, implementation = parse_st_file(file_path)
            content_check = declaration if declaration else implementation
            if not content_check:
                print("  Skipped: Empty file")
                skipped_count += 1
                continue
                
            type_guid = determine_object_type(content_check)
            if not type_guid:
                print("  Skipped: Unknown object type")
                skipped_count += 1
                continue
            
            # Extract object name from file path
            path_parts = rel_path.split("/")
            obj_name = os.path.splitext(path_parts[-1])[0]
            parent_path = "/".join(path_parts[:-1])
            print("  Object name: " + obj_name)
            
            # Determine the specific object type from content
            pou_type = None
            is_gvl = False
            
            if type_guid == TYPE_GUIDS["gvl"]:
                is_gvl = True
            elif type_guid == TYPE_GUIDS["pou"]:
                # Determine POU type from content
                content_upper = content_check.upper()
                if "PROGRAM " in content_upper:
                    pou_type = "program"
                elif "FUNCTION_BLOCK " in content_upper or "FUNCTIONBLOCK " in content_upper:
                    pou_type = "functionblock"
                elif "FUNCTION " in content_upper:
                    pou_type = "function"
                else:
                    pou_type = "program"  # Default to program
            
            # Get the Application object for creation
            app_obj = app_container  # Use the Application container we found at the start
            
            try:
                # Check for existing - be more specific to avoid name collisions
                existing = None
                try:
                    all_objects = app_obj.get_children(recursive=True)
                    for child in all_objects:
                        if child.get_name() == obj_name:
                            # Double-check by comparing type to avoid name collisions
                            try:
                                child_type = safe_str(child.type)
                                if (is_gvl and child_type == TYPE_GUIDS["gvl"]) or \
                                   (pou_type and child_type == TYPE_GUIDS["pou"]):
                                    existing = child
                                    break
                            except:
                                pass
                except:
                    pass
                
                if existing:
                    print("  Object already exists: " + obj_name)
                    obj = existing
                else:
                    print("  Creating object: " + obj_name)
                    
                    # Use dedicated creation methods
                    if is_gvl:
                        print("    Using create_gvl()")
                        obj = app_obj.create_gvl(obj_name)
                        created_count += 1
                    elif pou_type:
                        print("    Using create_pou() with type: " + pou_type)
                        obj = app_obj.create_pou(obj_name, pou_type)
                        created_count += 1
                    else:
                        print("  Error: Unknown object type for creation")
                        failed_count += 1
                        continue
                        
                    # Move object to correct folder
                    if parent_path:
                        print("    Moving object to: " + parent_path)
                        dest_folder = ensure_folder_path(parent_path)
                        if dest_folder:
                            try:
                                obj.move(dest_folder)
                                print("    Moved successfully.")
                            except Exception as e:
                                print("    Error moving object: " + safe_str(e))
                        else:
                            print("    Warning: Could not find destination folder to move object.")
                    
                if update_object_code(obj, declaration, implementation):
                    print("  Code updated.")
                    updated_count += 1
                    
                    # Update metadata with new object and hash
                    # Reconstruct content
                    full_content = declaration
                    if implementation:
                        full_content += "\n\n// === IMPLEMENTATION ===\n" + implementation
                    
                    new_hash = calculate_hash(full_content)
                    
                    # Get parent name safely
                    parent_name = "Application"
                    try:
                        if hasattr(obj, "parent") and obj.parent:
                            parent_name = safe_str(obj.parent.get_name())
                    except:
                        pass
                    
                    objects_meta[rel_path] = {
                        "guid": safe_str(obj.guid),
                        "type": type_guid,
                        "name": obj_name,
                        "parent": parent_name,
                        "content_hash": new_hash
                    }
            except Exception as e:
                print("  Error creating/updating: " + safe_str(e))
                failed_count += 1
    
    # Save updated metadata with new hashes
    if updated_count > 0 or created_count > 0:
        print("Saving updated metadata...")
        save_metadata(import_dir, metadata)
    
    print("=== Import Complete ===")
    print("Updated: " + str(updated_count) + " objects")
    print("Created: " + str(created_count) + " objects")
    print("Failed: " + str(failed_count) + " objects")
    print("Skipped: " + str(skipped_count) + " objects")
    
    elapsed_time = time.time() - start_time
    print("Time elapsed: {:.2f} seconds".format(elapsed_time))
    print("Completed at: " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
    
    system.ui.info("Import complete!\n\nUpdated: " + str(updated_count) + "\nCreated: " + str(created_count) + "\nFailed: " + str(failed_count) + "\nSkipped: " + str(skipped_count) + "\nTime elapsed: {:.2f} seconds".format(elapsed_time))
    
    # Untracked warning removed as we now handle new files


def main():
    base_dir, error = load_base_dir()
    if error:
        system.ui.warning(error)
        return
    
    # Confirmation dialog
    message = "WARNING: This operation will overwrite CODESYS objects with data from:\n" + base_dir + "\n\nAre you sure you want to proceed?"
    result = system.ui.choose(message, ("Yes, Overwrite Data", "No, Cancel"))
    
    if result[0] != 0:
        print("Import cancelled by user.")
        return

    import_project(base_dir)


if __name__ == "__main__":
    main()
