# -*- coding: utf-8 -*-
"""
codesys_utils.py - Shared utility functions for CODESYS scripts

Contains common utility functions used across export, import, and sync scripts.
"""
import os
import codecs
import json
from codesys_constants import IMPL_MARKER, FORBIDDEN_CHARS


def safe_str(value):
    """Safely convert value to string"""
    try:
        return str(value)
    except:
        return "N/A"


def clean_filename(name):
    """Clean filename from invalid characters"""
    clean_name = name
    for char in FORBIDDEN_CHARS:
        clean_name = clean_name.replace(char, "_")
    return clean_name


def load_base_dir():
    """
    Load base directory from BASE_DIR config file.
    Returns (base_dir, error_message) tuple.
    If successful, error_message is None.
    """
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "BASE_DIR")
    
    if not os.path.exists(config_path):
        return None, "Base directory is not set! Please run 'Project_directory.py' first."
    
    try:
        with open(config_path, "r") as f:
            base_dir = f.read().strip()
        
        if not os.path.exists(base_dir):
            return None, "Base directory does not exist: " + base_dir
        
        return base_dir, None
    except Exception as e:
        return None, "Error reading BASE_DIR: " + safe_str(e)


def load_metadata(base_dir):
    """Load metadata from _metadata.json"""
    metadata_path = os.path.join(base_dir, "_metadata.json")
    if not os.path.exists(metadata_path):
        return None
    
    try:
        with codecs.open(metadata_path, "r", "utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("Error reading metadata: " + safe_str(e))
        return None


def save_metadata(base_dir, metadata):
    """Save metadata to _metadata.json with config fields at the top"""
    metadata_path = os.path.join(base_dir, "_metadata.json")
    try:
        # Reconstruct metadata with desired field order
        ordered_metadata = {}
        
        # Configuration fields first
        if "project_name" in metadata:
            ordered_metadata["project_name"] = metadata["project_name"]
        if "project_path" in metadata:
            ordered_metadata["project_path"] = metadata["project_path"]
        if "export_timestamp" in metadata:
            ordered_metadata["export_timestamp"] = metadata["export_timestamp"]
        if "autosync" in metadata:
            ordered_metadata["autosync"] = metadata["autosync"]
        if "sync_timeout" in metadata:
            ordered_metadata["sync_timeout"] = metadata["sync_timeout"]
        if "export_xml" in metadata:
            ordered_metadata["export_xml"] = metadata["export_xml"]
        
        # Objects last
        if "objects" in metadata:
            ordered_metadata["objects"] = metadata["objects"]
        
        # Add any other fields that might exist
        for key in metadata:
            if key not in ordered_metadata:
                ordered_metadata[key] = metadata[key]
        
        with codecs.open(metadata_path, "w", "utf-8") as f:
            json.dump(ordered_metadata, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print("Error writing metadata: " + safe_str(e))
        return False


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


def build_object_cache(project=None):
    """
    Build lookup caches for project objects.
    Returns tuple (guid_map, name_map).
    
    Args:
        project: CODESYS project object. If None, will try to use global 'projects.primary'
    """
    guid_map = {}
    name_map = {}
    
    # Try to get project from parameter or global
    if project is None:
        try:
            project = projects.primary
        except NameError:
            # Not in CODESYS environment
            return guid_map, name_map
    
    if not project:
        return guid_map, name_map
    
    try:
        all_objects = project.get_children(recursive=True)
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
