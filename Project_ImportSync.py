# -*- coding: utf-8 -*-
"""
Project_AutoSync.py - Auto-synchronize external file changes to CODESYS

Monitors exported .st files for changes and automatically updates the corresponding
CODESYS objects. Runs in the background without blocking the IDE.

Features:
- One-way sync: Folder → IDE only
- State stored in _metadata.json (autosync: RUNNING/STOPPED)
- Configurable timeout via sync_timeout in metadata (default: 10000ms)
- Dynamic timeout updates: Changes apply immediately on next cycle
- Safety checks every cycle:
  * Metadata file exists
  * Project name matches (prevents syncing to wrong project)
  * Sync status is RUNNING

Workflow:
1. Create new blocks in CODESYS IDE
2. Run Project_export.py to export them
3. Run Project_AutoSync.py to start monitoring
4. Edit .st files in external editor (VS Code, etc.)
5. Changes automatically sync to CODESYS
6. Run Project_AutoSync.py again to stop

Usage: 
- Run once to START synchronization
- Run again to STOP synchronization
- Sync state and timeout stored in _metadata.json
"""
import os
import sys
import codecs
import json
import clr

clr.AddReference("System.Windows.Forms")
from System.Windows.Forms import Timer

# Implementation marker from export format
IMPL_MARKER = "// === IMPLEMENTATION ==="

# Default timeout
DEFAULT_TIMEOUT_MS = 10000

# Global state storage (only for timer reference)
if not hasattr(sys, "_codesys_autosync"):
    sys._codesys_autosync = {
        "timer": None,
        "base_dir": None,
        "file_states": {},
        "guid_map": {},
        "name_map": {}
    }

def safe_str(value):
    """Safely convert value to string"""
    try:
        return str(value)
    except:
        return "N/A"

def load_metadata(base_dir):
    """Load metadata from _metadata.json"""
    metadata_path = os.path.join(base_dir, "_metadata.json")
    if not os.path.exists(metadata_path):
        return None
    
    try:
        with codecs.open(metadata_path, "r", "utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("AutoSync: Error reading metadata: " + safe_str(e))
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
        print("AutoSync: Error writing metadata: " + safe_str(e))
        return False

def get_sync_status(metadata):
    """Get sync status from metadata"""
    return metadata.get("autosync", "STOPPED")

def get_sync_timeout(metadata):
    """Get sync timeout from metadata"""
    timeout = metadata.get("sync_timeout", DEFAULT_TIMEOUT_MS)
    try:
        timeout = int(timeout)
        if timeout < 500:
            return 500
        if timeout > 60000:
            return 60000
        return timeout
    except:
        return DEFAULT_TIMEOUT_MS

def set_sync_status(base_dir, metadata, status):
    """Set sync status in metadata"""
    metadata["autosync"] = status
    return save_metadata(base_dir, metadata)

def parse_st_file(file_path):
    """Parse ST file and extract declaration and implementation sections"""
    try:
        with codecs.open(file_path, "r", "utf-8") as f:
            content = f.read()
    except Exception as e:
        print("AutoSync: Error reading " + file_path + ": " + safe_str(e))
        return None, None
    
    declaration = None
    implementation = None
    
    if IMPL_MARKER in content:
        parts = content.split(IMPL_MARKER)
        declaration = parts[0].strip()
        implementation = parts[1].strip() if len(parts) > 1 else None
    else:
        declaration = content.strip()
    
    return declaration, implementation

def build_object_cache():
    """Build lookup caches for project objects"""
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

def find_object_by_guid(guid):
    """Find CODESYS object by GUID"""
    return sys._codesys_autosync["guid_map"].get(guid)

def find_object_by_name(name, parent_name=None):
    """Find CODESYS object by name"""
    name_map = sys._codesys_autosync["name_map"]
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
    
    return found[0]

def update_object_code(obj, declaration, implementation):
    """Update object's textual declaration and/or implementation"""
    updated = False
    obj_name = safe_str(obj.get_name())
    
    # Update declaration
    if declaration:
        try:
            if hasattr(obj, "has_textual_declaration") and obj.has_textual_declaration:
                obj.textual_declaration.replace(declaration)
                updated = True
        except Exception as e:
            print("AutoSync: Error updating declaration for " + obj_name + ": " + safe_str(e))
    
    # Update implementation
    if implementation:
        try:
            if hasattr(obj, "has_textual_implementation") and obj.has_textual_implementation:
                obj.textual_implementation.replace(implementation)
                updated = True
        except Exception as e:
            print("AutoSync: Error updating implementation for " + obj_name + ": " + safe_str(e))
    
    return updated

def sync_check():
    """Check for file changes and sync them to CODESYS"""
    base_dir = sys._codesys_autosync["base_dir"]
    file_states = sys._codesys_autosync["file_states"]
    
    if not base_dir or not os.path.exists(base_dir):
        return
    
    # Reload metadata to get current object list
    metadata = load_metadata(base_dir)
    if not metadata:
        print("AutoSync: Metadata file missing, stopping timer...")
        stop_sync_internal()
        return
    
    # Check if project name matches (user might have switched projects)
    if projects.primary:
        current_project = safe_str(projects.primary)
        metadata_project = metadata.get("project_name", "")
        if current_project != metadata_project:
            print("AutoSync: Project changed (was: " + metadata_project + ", now: " + current_project + "), stopping timer...")
            stop_sync_internal()
            return
    
    # Check if sync is still enabled
    if get_sync_status(metadata) != "RUNNING":
        print("AutoSync: Sync was stopped externally, stopping timer...")
        stop_sync_internal()
        return
    
    # Check if timeout changed and update timer if needed
    current_timeout = get_sync_timeout(metadata)
    state = sys._codesys_autosync
    if state["timer"] and state["timer"].Interval != current_timeout:
        state["timer"].Interval = current_timeout
        print("AutoSync: Timeout updated to " + str(current_timeout) + "ms")
    
    objects_meta = metadata.get("objects", {})
    
    for rel_path, obj_info in objects_meta.items():
        file_path = os.path.join(base_dir, rel_path.replace("/", os.sep))
        
        if not os.path.exists(file_path):
            continue
        
        try:
            # Check if file was modified
            current_mtime = os.path.getmtime(file_path)
            last_mtime = file_states.get(file_path, 0)
            
            if current_mtime <= last_mtime:
                continue
            
            # File changed - update it
            file_states[file_path] = current_mtime
            
            obj_guid = obj_info.get("guid")
            obj_name = obj_info.get("name")
            parent_name = obj_info.get("parent")
            
            # Find object
            obj = None
            if obj_guid and obj_guid != "N/A":
                obj = find_object_by_guid(obj_guid)
            
            if obj is None and obj_name:
                obj = find_object_by_name(obj_name, parent_name)
            
            if obj is None:
                print("AutoSync: Object not found for " + rel_path)
                continue
            
            # Parse and update
            declaration, implementation = parse_st_file(file_path)
            
            if declaration is None and implementation is None:
                continue
            
            if update_object_code(obj, declaration, implementation):
                print("AutoSync: Synced " + obj_name)
        
        except Exception as e:
            print("AutoSync: Error processing " + rel_path + ": " + safe_str(e))

def on_timer_tick(sender, args):
    """Timer callback - perform sync check"""
    try:
        sync_check()
    except Exception as e:
        print("AutoSync: Timer error: " + safe_str(e))

def stop_sync_internal():
    """Internal stop function (doesn't update metadata)"""
    state = sys._codesys_autosync
    
    if state["timer"]:
        state["timer"].Stop()
        state["timer"].Dispose()
        state["timer"] = None
    
    state["base_dir"] = None
    state["file_states"] = {}
    state["guid_map"] = {}
    state["name_map"] = {}

def start_sync():
    """Start background synchronization"""
    state = sys._codesys_autosync
    
    # Load base directory
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "BASE_DIR")
    
    if not os.path.exists(config_path):
        system.ui.warning("Base directory not set! Run 'Project_directory.py' first.")
        return
    
    with open(config_path, "r") as f:
        base_dir = f.read().strip()
    
    if not os.path.exists(base_dir):
        system.ui.error("Base directory does not exist: " + base_dir)
        return
    
    # Load metadata
    metadata = load_metadata(base_dir)
    if not metadata:
        system.ui.error("_metadata.json not found! Run 'Project_export.py' first.")
        return
    
    # Check if already running
    current_status = get_sync_status(metadata)
    if current_status == "RUNNING":
        print("AutoSync: Already running according to metadata")
        system.ui.warning("AutoSync is already RUNNING.\n\nIf the timer is not working, the script may have been interrupted.\nRun again to STOP, then run once more to START fresh.")
        return
    
    # Get timeout
    timeout_ms = get_sync_timeout(metadata)
    
    # Build object cache
    print("AutoSync: Building object cache...")
    guid_map, name_map = build_object_cache()
    
    # Initialize file states
    file_states = {}
    for rel_path in metadata.get("objects", {}).keys():
        file_path = os.path.join(base_dir, rel_path.replace("/", os.sep))
        if os.path.exists(file_path):
            file_states[file_path] = os.path.getmtime(file_path)
    
    # Store state
    state["base_dir"] = base_dir
    state["guid_map"] = guid_map
    state["name_map"] = name_map
    state["file_states"] = file_states
    
    # Update metadata status
    if not set_sync_status(base_dir, metadata, "RUNNING"):
        system.ui.error("Failed to update metadata status")
        return
    
    # Create and start timer
    timer = Timer()
    timer.Interval = timeout_ms
    timer.Tick += on_timer_tick
    timer.Start()
    
    state["timer"] = timer
    
    print("AutoSync: Started (Folder -> IDE, checking every " + str(timeout_ms) + "ms)")
    print("AutoSync: Monitoring " + str(len(file_states)) + " files in " + base_dir)
    system.ui.info("Auto-Sync STARTED\n\nDirection: Folder -> IDE\nInterval: " + str(timeout_ms) + "ms\nMonitoring: " + base_dir + "\nFiles: " + str(len(file_states)))

def stop_sync():
    """Stop background synchronization"""
    state = sys._codesys_autosync
    
    # Load base directory
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "BASE_DIR")
    
    if not os.path.exists(config_path):
        print("AutoSync: No base directory configured")
        return
    
    with open(config_path, "r") as f:
        base_dir = f.read().strip()
    
    if not os.path.exists(base_dir):
        print("AutoSync: Base directory does not exist")
        return
    
    # Load metadata
    metadata = load_metadata(base_dir)
    if not metadata:
        print("AutoSync: No metadata found")
        return
    
    # Check current status
    current_status = get_sync_status(metadata)
    if current_status != "RUNNING":
        print("AutoSync: Not running according to metadata")
        system.ui.info("AutoSync is already STOPPED")
        return
    
    # Stop timer
    stop_sync_internal()
    
    # Update metadata status
    if set_sync_status(base_dir, metadata, "STOPPED"):
        print("AutoSync: Stopped")
        system.ui.info("Auto-Sync STOPPED")
    else:
        system.ui.error("Failed to update metadata status")

def main():
    """Toggle sync on/off based on metadata state"""
    # Load base directory
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "BASE_DIR")
    
    if not os.path.exists(config_path):
        system.ui.warning("Base directory not set! Run 'Project_directory.py' first.")
        return
    
    with open(config_path, "r") as f:
        base_dir = f.read().strip()
    
    if not os.path.exists(base_dir):
        system.ui.error("Base directory does not exist: " + base_dir)
        return
    
    # Load metadata to check status
    metadata = load_metadata(base_dir)
    if not metadata:
        system.ui.error("_metadata.json not found! Run 'Project_export.py' first.")
        return
    
    # Toggle based on current status
    current_status = get_sync_status(metadata)
    if current_status == "RUNNING":
        stop_sync()
    else:
        start_sync()

if __name__ == "__main__":
    main()
