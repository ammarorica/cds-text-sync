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
import re
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
    # Remove comments and pragmas to avoid false matches
    
    # 1. Remove (* ... *) multiline comments
    content = re.sub(r"\(\*[\s\S]*?\*\)", "", content)
    
    # 2. Remove { ... } pragmas/attributes
    content = re.sub(r"\{[\s\S]*?\}", "", content)
    
    # 3. Remove // ... single line comments
    content = re.sub(r"//.*", "", content)
    
    content = content.strip()
    lines = content.splitlines()
    
    for line in lines:
        line = line.strip()
        if not line:
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
        
        # If we found a valid starting word, we are done. 
        # If the first non-comment non-empty word isn't a keyword, 
        # it might be that the file is malformed or this logic needs extension.
        # But usually ST files start with one of these.
        
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
                    
                    # if depth == 0:
                    #    print("    - " + child_name + " (type: " + child_type + ")")
                    
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
        # print("  Searching for Application/PLC Logic container...")
        children = projects.primary.get_children()
        # print("  Found " + str(len(children)) + " top-level children")
        
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
                
                # Try using create_folder first (preferred), then create_child
                parent_obj = current_obj
                current_obj = None
                
                if hasattr(parent_obj, "create_folder"):
                    try:
                        current_obj = parent_obj.create_folder(part)
                        print("    Created using create_folder()")
                    except Exception as e:
                        print("    create_folder failed: " + safe_str(e))
                        
                if not current_obj and hasattr(parent_obj, "create_child"):
                    try:
                         # 738bea1e-99bb-4f04-90bb-a7a567e74e3a is Folder GUID
                        current_obj = parent_obj.create_child(part, "738bea1e-99bb-4f04-90bb-a7a567e74e3a") 
                        print("    Created using create_child()")
                    except Exception as e:
                         print("    create_child failed: " + safe_str(e))
                         
                # Verification / Recovery if API returned None but created it
                if not current_obj:
                    # check if it exists now
                    try:
                        children = parent_obj.get_children()
                        for child in children:
                            if child.get_name().lower() == part.lower():
                                current_obj = child
                                print("    Verified: Folder created successfully (Retrieved via lookup)")
                                break
                    except:
                        pass

                if not current_obj:
                    print("  Error: Parent object " + parent_name + " does not support create_folder or create_child")
                    # Debug info
                    try:
                        print("  Parent GUID: " + safe_str(current_obj.guid))
                        print("  Parent Type: " + safe_str(current_obj.type))
                        # Identify what this object type is
                        obj_type = safe_str(current_obj.type)
                        for k, v in TYPE_GUIDS.items():
                             if v == obj_type:
                                 print("  Parent Type Name: " + k)
                        print("  Available methods: " + str([d for d in dir(current_obj) if "create" in d.lower()]))
                    except:
                        pass
                    return None
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
    new_folders = []
    
    for root, dirs, files in os.walk(import_dir):
        # Prune hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for d in dirs:
             rel_path = os.path.relpath(os.path.join(root, d), import_dir).replace(os.sep, "/")
             if rel_path not in objects_meta and rel_path not in tracked_folders:
                 new_folders.append(rel_path)
        
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

        # Skip folders - they don't have text content to update
        if obj_info.get("type") == TYPE_GUIDS["folder"] or os.path.isdir(file_path):
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
            
    # Process new folders first
    if new_folders:
        print("=== Processing New Folders ===")
        # Sort by length to create parents before children
        new_folders.sort(key=len)
        
        for folder_path in new_folders:
            print("Creating new folder: " + folder_path)
            created_folder = ensure_folder_path(folder_path)
            if created_folder:
                created_count += 1
                # Add to metadata
                objects_meta[folder_path] = {
                    "guid": safe_str(created_folder.guid),
                    "type": TYPE_GUIDS["folder"],
                    "name": safe_str(created_folder.get_name()),
                    "parent": safe_str(created_folder.parent.get_name()) if created_folder.parent else "N/A",
                    "content_hash": ""
                }
            else:
                print("  Failed to create folder: " + folder_path)
                failed_count += 1

    # Process new files in two passes: Parents first, then Children
    if new_files:
        print("=== Processing New Files ===")
        
        parent_ops = []
        child_ops = []
        
        # Pass 1: Classification
        for rel_path, file_path in new_files:
             declaration, implementation = parse_st_file(file_path)
             content_check = declaration if declaration else implementation
             if not content_check:
                print("  Skipped (Empty): " + rel_path)
                skipped_count += 1
                continue
                
             type_guid = determine_object_type(content_check)
             
             path_parts = rel_path.split("/")
             base_name = os.path.splitext(path_parts[-1])[0]
             
             is_child = False
             child_info = None

             # Special handling for Property Accessors (Get/Set)
             if base_name in ["Get", "Set"] and len(path_parts) > 1:
                 type_guid = TYPE_GUIDS["property_accessor"]
                 p_name = path_parts[-2] # Parent is the folder containing the file
                 c_name = base_name
                 child_info = (p_name, c_name)
                 is_child = True
             
             # If no type detected or explicit method/prop keywords, check naming convention
             if not is_child and (not type_guid or type_guid in [TYPE_GUIDS["method"], TYPE_GUIDS["property"], TYPE_GUIDS["action"]]):
                 if "." in base_name:
                     parts = base_name.rsplit(".", 1)
                     p_name = parts[0]
                     c_name = parts[1]
                     # It's a candidate for child
                     child_info = (p_name, c_name)
                     # If we didn't get a type from content, try to guess
                     if not type_guid:
                        content_upper = content_check.upper()
                        if "METHOD " in content_upper:
                             type_guid = TYPE_GUIDS["method"]
                        elif "PROPERTY " in content_upper:
                             type_guid = TYPE_GUIDS["property"]
                        else:
                             type_guid = TYPE_GUIDS["action"]
                     is_child = True

             op_data = {
                 "rel_path": rel_path,
                 "file_path": file_path,
                 "base_name": base_name,
                 "type_guid": type_guid,
                 "content_check": content_check,
                 "declaration": declaration,
                 "implementation": implementation,
                 "is_child": is_child,
                 "child_info": child_info
             }
             
             if is_child:
                 child_ops.append(op_data)
             else:
                 parent_ops.append(op_data)

        # Stats tracking for new files (avoiding nonlocal for IronPython compatibility)
        new_stats = {"updated": 0, "created": 0, "failed": 0, "skipped": 0}

        # Function to process an operation
        def process_op(op):
            rel_path = op["rel_path"]
            print("Processing: " + rel_path)
            
            type_guid = op["type_guid"]
            base_name = op["base_name"]
            is_child = op["is_child"]
            child_info = op["child_info"]
            content_check = op["content_check"]
            declaration = op["declaration"]
            implementation = op["implementation"]
            
            obj_name = base_name
            parent_obj = None
            
            # Resolve Parent for children
            if is_child and child_info:
                p_name, c_name = child_info
                
                # Find parent
                found_parent = find_object_by_name(p_name, name_map)
                if not found_parent:
                     # Case insensitive fallback
                     for name in name_map:
                        if name.lower() == p_name.lower():
                            found_parent = name_map[name][0]
                            break
                            
                if found_parent:
                    parent_obj = found_parent
                    obj_name = c_name
                    print("  Identified parent: " + safe_str(parent_obj.get_name()))
                else:
                    print("  Error: Parent '" + p_name + "' not found for child '" + c_name + "'. (Wait for next pass or check export)")
                    # Fallback: maybe it's not a child? 
                    if not type_guid:
                        print("  Skipped: Unknown object type and Parent not found")
                        new_stats["skipped"] += 1
                        return

            if not type_guid:
                print("  Skipped: Unknown object type")
                new_stats["skipped"] += 1
                return

            # Determine specific container and type details
            pou_type = None
            is_gvl = (type_guid == TYPE_GUIDS["gvl"])
            is_dut = (type_guid == TYPE_GUIDS["dut"])
            is_accessor = (type_guid == TYPE_GUIDS["property_accessor"])
            
            if type_guid == TYPE_GUIDS["pou"]:
                content_upper = content_check.upper()
                if "PROGRAM " in content_upper:
                    pou_type = PouType.Program
                elif "FUNCTION_BLOCK " in content_upper or "FUNCTIONBLOCK " in content_upper:
                    pou_type = PouType.FunctionBlock
                elif "FUNCTION " in content_upper:
                    pou_type = PouType.Function
                else:
                    pou_type = PouType.Program

            # Creation Container
            if is_child and parent_obj:
                create_container = parent_obj
            else:
                create_container = app_container
                
            if not create_container:
                print("  Error: No container found")
                new_stats["failed"] += 1
                return

            # Check existing
            try:
                existing = None
                try:
                    children = create_container.get_children() # Non-recursive for direct children
                    for child in children:
                        if child.get_name().lower() == obj_name.lower():
                             existing = child
                             break
                except:
                    pass
                
                if existing:
                    print("  Object already exists: " + obj_name)
                    obj = existing
                elif is_accessor:
                     # Accessors should exist if parent property exists. If not, we can't easily create them standalone
                     print("  Warning: Accessor " + obj_name + " not found in " + create_container.get_name())
                     new_stats["failed"] += 1
                     return
                else:
                    print("  Creating object: " + obj_name)
                    
                    if is_child:
                         # Child creation logic
                        try:
                            if hasattr(create_container, "create_child"):
                                obj = create_container.create_child(obj_name, type_guid)
                            else:
                                raise AttributeError("No create_child")
                        except:
                            # Fallbacks
                            if type_guid == TYPE_GUIDS["action"] and hasattr(create_container, "create_action"):
                                obj = create_container.create_action(obj_name)
                            elif type_guid == TYPE_GUIDS["method"] and hasattr(create_container, "create_method"):
                                try:
                                    obj = create_container.create_method(obj_name)
                                except:
                                    obj = create_container.create_method(obj_name, "BOOL")
                            elif type_guid == TYPE_GUIDS["property"] and hasattr(create_container, "create_property"):
                                obj = create_container.create_property(obj_name, "BOOL")
                            else:
                                print("    Error: Failed to create child object")
                                new_stats["failed"] += 1
                                return
                        new_stats["created"] += 1
                        
                    elif is_gvl:
                        obj = create_container.create_gvl(obj_name)
                        new_stats["created"] += 1
                    elif is_dut:
                        obj = create_container.create_dut(obj_name)
                        new_stats["created"] += 1
                    elif pou_type is not None:
                        # Simple creation, return type handled by declaration update
                        try:
                            if pou_type == PouType.Function:
                                # Parse return type for Function
                                return_type_str = "BOOL" # Default
                                try:
                                    # Look for FUNCTION <Name> : <Type>
                                    match = re.search(r"FUNCTION\s+\w+\s*:\s*([\w\.]+)", content_check, re.IGNORECASE)
                                    if match:
                                        return_type_str = match.group(1)
                                except:
                                    pass
                                
                                # Try to resolve return type to a GUID (required for create_pou)
                                ret_guid = None
                                found_type = find_object_by_name(return_type_str, name_map)
                                if found_type:
                                    try:
                                        ret_guid = found_type.guid
                                    except:
                                        pass

                                if ret_guid:
                                    print("    Creating Function with type: " + return_type_str)
                                    obj = create_container.create_pou(obj_name, pou_type, ret_guid)
                                else:
                                    # For elementary types or unresolved, create_pou fails if passed a string.
                                    # Fallback to Program allows import to proceed with correct code update.
                                    print("    Return type '" + return_type_str + "' is elementary or not found. Creating as Program.")
                                    obj = create_container.create_pou(obj_name, PouType.Program)
                            else:
                                obj = create_container.create_pou(obj_name, pou_type)
                        except Exception as e:
                            # Fallback just in case
                            if pou_type == PouType.Function:
                                print("    Warning: Creation failed (" + safe_str(e) + "). Fallback to Program.")
                                obj = create_container.create_pou(obj_name, PouType.Program)
                            else:
                                raise e
                        
                        new_stats["created"] += 1
                    else:
                        print("  Error: Unknown type for creation")
                        new_stats["failed"] += 1
                        return
                    
                    # Move object to correct folder
                    if not is_child:
                        path_parts = op["rel_path"].split("/")
                        parent_path = "/".join(path_parts[:-1])
                        if parent_path:
                             dest = ensure_folder_path(parent_path)
                             if dest:
                                 try:
                                     obj.move(dest)
                                 except:
                                     pass

                # Update Code and Metadata
                if update_object_code(obj, declaration, implementation):
                    print("  Code updated.")
                    new_stats["updated"] += 1
                    
                    # Rebuild hash and save metadata
                    full_content = declaration
                    if implementation:
                        full_content += "\n\n// === IMPLEMENTATION ===\n" + implementation
                    new_hash = calculate_hash(full_content)
                    
                    objects_meta[op["rel_path"]] = {
                        "guid": safe_str(obj.guid),
                        "type": type_guid,
                        "name": obj_name,
                        "parent": safe_str(obj.parent.get_name()) if hasattr(obj, "parent") and obj.parent else "Application",
                        "content_hash": new_hash
                    }
                    
                    # Add to cache for subsequent lookups (e.g. for children)
                    if obj_name not in name_map:
                        name_map[obj_name] = []
                    name_map[obj_name].append(obj)
                    
            except Exception as e:
                print("  Error processing " + obj_name + ": " + safe_str(e))
                new_stats["failed"] += 1

        print("--- Pass 1: Creating Parent Objects ---")
        for op in parent_ops:
            process_op(op)
            
        print("--- Pass 2: Creating Child Objects ---")
        for op in child_ops:
            process_op(op)
            
        # Merge stats
        updated_count += new_stats["updated"]
        created_count += new_stats["created"]
        failed_count += new_stats["failed"]
        skipped_count += new_stats["skipped"]
    
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
