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

# Markers used in export format
IMPL_MARKER = "// === IMPLEMENTATION ==="


def safe_str(value):
    """Safely convert value to string"""
    try:
        return str(value)
    except:
        return "N/A"


def parse_st_file(file_path):
    """
    Parse an ST file and extract declaration and implementation sections.
    Returns tuple (declaration, implementation).
    """
    try:
        with codecs.open(file_path, "r", "utf-8") as f:
            content = f.read()
    except Exception as e:
        print("Error reading file " + file_path + ": " + safe_str(e))
        return None, None
    
    declaration = None
    implementation = None
    
    if IMPL_MARKER in content:
        parts = content.split(IMPL_MARKER)
        declaration = parts[0].strip()
        implementation = parts[1].strip() if len(parts) > 1 else None
    else:
        # No implementation marker - entire content is declaration
        declaration = content.strip()
    
    return declaration, implementation


def build_object_cache():
    """Builds lookup caches for project objects"""
    print("Building object cache...")
    
    guid_map = {}
    name_map = {}
    
    if not projects.primary:
        return guid_map, name_map

    try:
        all_objects = projects.primary.get_children(recursive=True)
    except:
        return guid_map, name_map
    
    for obj in all_objects:
        try:
            # GUID Cache
            g = safe_str(obj.guid)
            if g != "N/A":
                guid_map[g] = obj
            
            # Name Cache
            n = safe_str(obj.get_name())
            if n not in name_map:
                name_map[n] = []
            name_map[n].append(obj)
        except:
            continue
            
    return guid_map, name_map


def find_object_by_guid(guid, guid_map):
    """Find a CODESYS object by its GUID using cache"""
    return guid_map.get(guid)


def find_object_by_name(name, name_map, parent_name=None):
    """
    Find a CODESYS object by name using cache.
    Returns first match or None.
    """
    found = name_map.get(name)
    if not found:
        return None
    
    if len(found) == 1:
        return found[0]
    
    # Multiple matches - filter by parent if provided
    if parent_name:
        for obj in found:
            try:
                if hasattr(obj, "parent") and obj.parent:
                    if obj.parent.get_name() == parent_name:
                        return obj
            except:
                continue
    
    # Return first match if no parent filter or no parent match
    return found[0]


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


def import_project(import_dir):
    """Import ST files from folder structure back into CODESYS project"""
    
    if not projects.primary:
        system.ui.error("No project open!")
        return
    
    print("=== Starting Project Import ===")
    start_time = time.time()
    print("Import directory: " + import_dir)
    
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
    guid_map, name_map = build_object_cache()
    
    untracked_items = []
    
    # Build a set of folders that ARE tracked (as parents of known objects)
    tracked_folders = set()
    for rel_path in objects_meta.keys():
        parts = rel_path.split("/")
        for i in range(1, len(parts)):
            tracked_folders.add("/".join(parts[:i]))
            
    for root, dirs, files in os.walk(import_dir):
        # Prune hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for name in dirs:
            rel_path = os.path.relpath(os.path.join(root, name), import_dir).replace(os.sep, "/")
            if rel_path not in tracked_folders:
                untracked_items.append(rel_path + " (folder)")
                
        for name in files:
            if name in ["_metadata.json", "BASE_DIR"] or name.startswith('.'):
                continue
            if not name.endswith(".st"):
                continue
            rel_path = os.path.relpath(os.path.join(root, name), import_dir).replace(os.sep, "/")
            if rel_path not in objects_meta:
                untracked_items.append(rel_path)
    
    updated_count = 0
    failed_count = 0
    skipped_count = 0
    
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
        
        # Update object
        if update_object_code(obj, declaration, implementation):
            print("  Updated: " + safe_str(obj.get_name()))
            updated_count += 1
        else:
            print("  No changes applied")
            skipped_count += 1
    
    print("=== Import Complete ===")
    print("Updated: " + str(updated_count) + " objects")
    print("Failed: " + str(failed_count) + " objects")
    print("Skipped: " + str(skipped_count) + " objects")
    
    elapsed_time = time.time() - start_time
    print("Time elapsed: {:.2f} seconds".format(elapsed_time))
    print("Completed at: " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
    
    system.ui.info("Import complete!\n\nUpdated: " + str(updated_count) + " objects\nFailed: " + str(failed_count) + "\nSkipped: " + str(skipped_count) + "\nTime elapsed: {:.2f} seconds".format(elapsed_time))
    
    # Warn about untracked items
    if untracked_items:
        warning_msg = "WARNING: Found items on disk that are NOT in _metadata.json.\n"
        warning_msg += "These blocks (and their hierarchy) should be created manually in CODESYS:\n\n"
        
        # Sort and limit list for display
        untracked_items.sort()
        display_list = untracked_items[:20]
        warning_msg += "\n".join(display_list)
        
        if len(untracked_items) > 20:
            warning_msg += "\n... and " + str(len(untracked_items) - 20) + " more items."
            
        system.ui.warning(warning_msg)


def main():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "BASE_DIR")
    
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            base_dir = f.read().strip()
    else:
        system.ui.warning("Base directory is not set! Please run 'Project_directory.py' first.")
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
