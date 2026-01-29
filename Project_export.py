# -*- coding: utf-8 -*-
"""
Project_export.py - Export CODESYS project to git-friendly folder structure

Exports all textual objects (POUs, GVLs, DUTs) to .st files organized in
folders matching the CODESYS project hierarchy. Creates a single _metadata.json
file containing GUID mappings, sync settings, and project info for reliable import.

Features:
- Project identity check: Warns if exporting to a directory with different project
- Initializes autosync and sync_timeout fields for Project_AutoSync.py
- Preserves consistent field order in metadata JSON

Usage: Run from CODESYS IDE after setting BASE_DIR with Project_directory.py
"""
import os
import codecs
import json
import time
from codesys_constants import TYPE_GUIDS, EXPORTABLE_TYPES, IMPL_MARKER, XML_TYPES
from codesys_utils import (
    safe_str, clean_filename, load_base_dir, 
    save_metadata, calculate_hash, format_st_content
)

# Shared constants and utilities imported from modules


def get_object_path(obj, stop_at_application=True):
    """
    Build the path from object to Application root.
    Returns list of folder names from Application (exclusive) to object (exclusive).
    """
    path_parts = []
    current = obj
    
    while current is not None:
        try:
            if not hasattr(current, "parent") or current.parent is None:
                break
            
            parent = current.parent
            parent_type = safe_str(parent.type)
            
            # Stop at Application level
            if stop_at_application and parent_type == TYPE_GUIDS["application"]:
                break
            
            # Stop at Plc Logic or Device level
            if parent_type in [TYPE_GUIDS["plc_logic"], TYPE_GUIDS["device"]]:
                break
            
            # Add parent name to path if it's a folder or other container
            parent_name = clean_filename(parent.get_name())
            path_parts.insert(0, parent_name)
            current = parent
            
        except Exception as e:
            print("Error building path: " + safe_str(e))
            break
    
    return path_parts


def get_parent_pou_name(obj):
    """Get parent POU/Interface name for nested objects (actions, methods, properties)"""
    try:
        if hasattr(obj, "parent") and obj.parent:
            parent_type = safe_str(obj.parent.type)
            if parent_type in [TYPE_GUIDS["pou"], TYPE_GUIDS["itf"]]:
                return obj.parent.get_name()
    except:
        pass
    return None


def export_object_content(obj):
    """
    Extract declaration and implementation text from object.
    Returns tuple (declaration, implementation) or (None, None) if no content.
    """
    declaration = None
    implementation = None
    
    try:
        if hasattr(obj, "has_textual_declaration") and obj.has_textual_declaration:
            declaration = obj.textual_declaration.text
    except Exception as e:
        print("Warning: Could not read declaration for " + safe_str(obj.get_name()) + ": " + safe_str(e))
    
    try:
        if hasattr(obj, "has_textual_implementation") and obj.has_textual_implementation:
            implementation = obj.textual_implementation.text
    except Exception as e:
        print("Warning: Could not read implementation for " + safe_str(obj.get_name()) + ": " + safe_str(e))
    
    return declaration, implementation




def export_native_xml(obj, file_path):
    """Export object in native CODESYS format (XML)"""
    # Delete existing file to avoid CODESYS overwrite prompts
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print("Warning: Could not delete existing XML " + file_path)
            
    try:
        # Visualizations and other non-IEC objects must be exported using native format
        projects.primary.export_native([obj], file_path, recursive=True)
        return True
    except Exception as e:
        print("Error exporting Native XML for " + safe_str(obj.get_name()) + ": " + safe_str(e))
        return False


def cleanup_orphaned_files(export_dir, current_objects):
    """
    Find and optionally delete files in export_dir that are not in current_objects.
    """
    orphaned_items = []
    
    # We'll collect everything first to show a preview
    for root, dirs, files in os.walk(export_dir):
        # Calculate relative path from export_dir
        rel_root = os.path.relpath(root, export_dir)
        if rel_root == ".":
            rel_root = ""
            
        # Check files
        for f in files:
            # Skip reserved files
            if f in ["_metadata.json", "_config.json", "_metadata.csv", "BASE_DIR"] or f.startswith("."):
                continue
            
            # Only consider our export types to be safe
            if not (f.endswith(".st") or f.endswith(".xml")):
                continue
                
            rel_path = os.path.join(rel_root, f).replace("\\", "/")
            if rel_path not in current_objects:
                orphaned_items.append(rel_path)

    if not orphaned_items:
        return True

    # Prompt user
    message = "The following files exist in the export directory but are NOT in the CODESYS project (orphans):\n\n"
    # Show first 15 files as preview
    for item in orphaned_items[:15]:
        message += "- " + item + "\n"
    if len(orphaned_items) > 15:
        message += "... and " + str(len(orphaned_items) - 15) + " more.\n"
    
    message += "\nWould you like to delete these orphaned files?"
    
    # buttons: Delete, Ignore, Cancel
    try:
        result = system.ui.choose(message, ("Delete Orphans", "Ignore", "Cancel Export"))
    except:
        # Fallback for environments where choose is not available or fails
        print("UI Choose not available, skipping cleanup.")
        return True
    
    if result[0] == 0: # Delete
        print("Cleaning up orphaned files...")
        for rel_path in orphaned_items:
            full_path = os.path.join(export_dir, rel_path.replace("/", os.sep))
            try:
                if os.path.exists(full_path):
                    os.remove(full_path)
                    print("Deleted: " + rel_path)
            except Exception as e:
                print("Error deleting " + rel_path + ": " + safe_str(e))
        
        # Now clean up empty directories
        # Use topdown=False to delete subdirectories before parents
        for root, dirs, files in os.walk(export_dir, topdown=False):
            rel_root = os.path.relpath(root, export_dir)
            if rel_root == "." or not rel_root:
                continue
            
            rel_path = rel_root.replace("\\", "/")
            
            # Check if this folder or any of its children should exist
            folder_needed = False
            for obj_path in current_objects:
                if obj_path.startswith(rel_path + "/"):
                    folder_needed = True
                    break
            
            if not folder_needed and rel_path not in current_objects:
                # If directory is empty, delete it
                try:
                    if not os.listdir(root):
                        os.rmdir(root)
                        print("Deleted empty folder: " + rel_path)
                except:
                    pass
        return True
    elif result[0] == 1: # Ignore
        print("Orphaned files ignored.")
        return True
    else: # Cancel
        print("Export cancelled during cleanup.")
        return False


def export_project(export_dir):
    """Export all project objects to folder structure with metadata"""
    
    if not projects.primary:
        system.ui.error("No project open!")
        return
    
    # Create export directory
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)
    
    print("=== Starting Project Export ===")
    start_time = time.time()
    print("Export directory: " + export_dir)
    
    # Metadata structure
    current_project_name = safe_str(projects.primary)
    metadata = {
        "project_name": current_project_name,
        "export_timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "autosync": "STOPPED",
        "sync_timeout": 10000,
        "export_xml": False,
        "objects": {}
    }
    
    try:
        if hasattr(projects.primary, "path"):
            metadata["project_path"] = safe_str(projects.primary.path)
    except:
        pass
    
    # Check if metadata already exists with different project
    metadata_path = os.path.join(export_dir, "_metadata.json")
    if os.path.exists(metadata_path):
        try:
            with codecs.open(metadata_path, "r", "utf-8") as f:
                existing_metadata = json.load(f)
            
            # Preserve existing settings
            if "export_xml" in existing_metadata:
                metadata["export_xml"] = existing_metadata["export_xml"]
            if "autosync" in existing_metadata:
                metadata["autosync"] = existing_metadata["autosync"]
            if "sync_timeout" in existing_metadata:
                metadata["sync_timeout"] = existing_metadata["sync_timeout"]

            existing_project = existing_metadata.get("project_name", "")
            if existing_project and existing_project != current_project_name:
                message = "WARNING: This directory contains exports from a different project!\n\n"
                message += "Current project: " + current_project_name + "\n"
                message += "Existing exports: " + existing_project + "\n\n"
                message += "Exporting will OVERWRITE the existing files.\n\n"
                message += "Are you sure you want to proceed?"
                
                result = system.ui.choose(message, ("Yes, Overwrite", "No, Cancel"))
                
                if result[0] != 0:
                    print("Export cancelled by user - project mismatch")
                    return
        except:
            # If we can't read existing metadata, continue with export
            pass
    
    # Get all objects recursively
    all_objects = projects.primary.get_children(recursive=True)
    print("Found " + str(len(all_objects)) + " total objects")
    
    exported_count = 0
    skipped_count = 0
    
    for obj in all_objects:
        try:
            obj_type = safe_str(obj.type)
            obj_name = obj.get_name()
            obj_guid = safe_str(obj.guid)
            
            # Special handling for folders - create directory and convert
            if obj_type == TYPE_GUIDS["folder"]:
                path_parts = get_object_path(obj)
                clean_name = clean_filename(obj_name)
                
                # Add folder itself to path
                path_parts.append(clean_name)
                
                target_dir = os.path.join(export_dir, *path_parts) if path_parts else export_dir
                
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir)
                    print("Created folder: " + "/".join(path_parts))
                
                # Add to metadata
                rel_path = "/".join(path_parts)
                metadata["objects"][rel_path] = {
                    "guid": obj_guid,
                    "type": obj_type,
                    "name": obj_name,
                    "parent": safe_str(obj.parent.get_name()) if hasattr(obj, "parent") and obj.parent else None,
                    "content_hash": ""
                }
                exported_count += 1
                
                continue

            # Skip non-exportable types
            if obj_type not in EXPORTABLE_TYPES:
                continue
            
            # Check if object is XML type
            is_xml = obj_type in XML_TYPES

            # Skip XML objects if disabled in metadata
            if is_xml and not metadata.get("export_xml", False):
                continue

            # Check if object has any textual content
            has_content = False
            try:
                if hasattr(obj, "has_textual_declaration") and obj.has_textual_declaration:
                    has_content = True
                if hasattr(obj, "has_textual_implementation") and obj.has_textual_implementation:
                    has_content = True
            except:
                pass
            
            # Allow export if it has content OR is an XML type
            if not has_content and not is_xml:
                skipped_count += 1
                continue
            
            # Build file path
            path_parts = get_object_path(obj)
            clean_name = clean_filename(obj_name)
            
            # Handle nested objects (actions, methods, properties)
            parent_pou = get_parent_pou_name(obj)
            if parent_pou and obj_type in [TYPE_GUIDS["action"], TYPE_GUIDS["method"], 
                                           TYPE_GUIDS["property"], TYPE_GUIDS["property_accessor"]]:
                # Nested objects: ParentPOU.MethodName.st
                file_name = clean_filename(parent_pou) + "." + clean_name + ".st"
                # Remove parent POU from path since it's in filename
                if path_parts and path_parts[-1] == parent_pou:
                    path_parts = path_parts[:-1]
                if path_parts and path_parts[-1] == parent_pou:
                    path_parts = path_parts[:-1]
            elif is_xml:
                file_name = clean_name + ".xml"
            else:
                file_name = clean_name + ".st"
            
            # Create target directory
            target_dir = os.path.join(export_dir, *path_parts) if path_parts else export_dir
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
            
            # Write content (ST or XML)
            file_path = os.path.join(target_dir, file_name)
            
            if is_xml:
                if not export_native_xml(obj, file_path):
                    print("Failed to export XML: " + file_name)
                    skipped_count += 1
                    continue
            else:
                # Textual export
                declaration, implementation = export_object_content(obj)
                content = format_st_content(declaration, implementation)
                
                if not content.strip():
                    skipped_count += 1
                    continue
                    
                with codecs.open(file_path, "w", "utf-8") as f:
                    f.write(content)
                
                # Calculate hash for metadata
                content_hash = calculate_hash(content)
            
            # Build relative path for metadata
            if path_parts:
                parts_for_join = path_parts + [file_name]
                rel_path = os.path.join(*parts_for_join)
            else:
                rel_path = file_name
            rel_path = rel_path.replace("\\", "/")  # Normalize path separators
            
            # Store metadata
            metadata["objects"][rel_path] = {
                "guid": obj_guid,
                "type": obj_type,
                "name": obj_name,
                "parent": safe_str(obj.parent.get_name()) if hasattr(obj, "parent") and obj.parent else None,
                "content_hash": locals().get("content_hash", ""),
                "last_modified": safe_str(os.path.getmtime(file_path))
            }
            
            print("Exported: " + rel_path)
            exported_count += 1
            
        except Exception as e:
            print("Error exporting " + safe_str(obj) + ": " + safe_str(e))
    
    # Cleanup orphaned files (files on disk not in current export)
    if not cleanup_orphaned_files(export_dir, metadata["objects"]):
        return
    
    # Write metadata file with consistent field order
    if save_metadata(export_dir, metadata):
        print("Created: _config.json and _metadata.csv")
    else:
        print("Error writing metadata")
    
    print("=== Export Complete ===")
    elapsed_time = time.time() - start_time
    print("Exported: " + str(exported_count) + " files")
    print("Skipped: " + str(skipped_count) + " objects (no textual content)")
    print("Time elapsed: {:.2f} seconds".format(elapsed_time))
    print("Completed at: " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
    
    system.ui.info("Export complete!\n\nExported: " + str(exported_count) + " files\nLocation: " + export_dir + "\nTime elapsed: {:.2f} seconds".format(elapsed_time))


def main():
    base_dir, error = load_base_dir()
    if error:
        system.ui.warning(error)
        return
    
    export_project(base_dir)


if __name__ == "__main__":
    main()