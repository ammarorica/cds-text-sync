# -*- coding: utf-8 -*-
"""
codesys_utils.py - Shared utility functions for CODESYS scripts

Contains common utility functions used across export, import, and sync scripts.
"""
import os
import codecs
import json
import hashlib
import csv
import sys
import traceback
import time
import threading

# --- Global Thread Lock ---
_metadata_thread_lock = threading.Lock()
from codesys_constants import IMPL_MARKER, FORBIDDEN_CHARS, TYPE_GUIDS


# --- Logging System ---
class Logger:
    def __init__(self):
        self.log_file = None
        
    def _initialize(self, base_dir=None):
        if self.log_file: return
        
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            self.log_file = os.path.join(script_dir, "sync_debug.log")
        except:
            # Fallback to local dir if everything fails
            self.log_file = "sync_debug.log"

    def log(self, level, message, include_traceback=False):
        self._initialize()
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_entry = "[%s] [%s] %s\n" % (timestamp, level, message)
        
        if include_traceback:
            log_entry += traceback.format_exc() + "\n"
            
        print("[%s] %s" % (level, message))
        
        try:
            with codecs.open(self.log_file, "a", "utf-8") as f:
                f.write(log_entry)
        except:
            pass

_logger = Logger()

def log_info(message):
    _logger.log("INFO", message)

def log_warning(message):
    _logger.log("WARNING", message)

def log_error(message, critical=False):
    _logger.log("ERROR", message, include_traceback=True)
    if critical:
        try:
            import system
            system.ui.error("CRITICAL ERROR: " + message + "\n\nSee sync_debug.log for details.")
        except:
            pass

# --- Utility Functions ---


def calculate_hash(content):
    """Calculate SHA256 hash of string content"""
    if content is None:
        return ""
    if isinstance(content, str):
        content = content.encode('utf-8')
    return hashlib.sha256(content).hexdigest()


def safe_str(value):
    """Safely convert value to string, handling Unicode in Python 2.7"""
    if value is None:
        return ""
    try:
        if sys.version_info[0] < 3:
            if isinstance(value, unicode):
                return value
            return unicode(value)
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
        log_error("Error reading BASE_DIR: " + safe_str(e))
        return None, "Error reading BASE_DIR. See log for details."


class MetadataLock:
    """
    File-based lock to prevent race conditions during metadata access.
    Combines threading lock for same-process safety and directory-based 
    lock for cross-process/script safety.
    """
    def __init__(self, base_dir, timeout=10):
        self.lock_path = os.path.join(base_dir, ".metadata.lock")
        self.timeout = timeout
        self.locked = False

    def acquire(self):
        start = time.time()
        while time.time() - start < self.timeout:
            try:
                # os.mkdir is atomic on Windows/Linux and fails if exists
                os.mkdir(self.lock_path)
                self.locked = True
                return True
            except OSError:
                # Directory exists or other OS error
                # We could check lock folder timestamp here to break stale locks
                try:
                    mtime = os.path.getmtime(self.lock_path)
                    if time.time() - mtime > 300: # Stale after 5 minutes
                        log_warning("Breaking stale metadata lock...")
                        os.rmdir(self.lock_path)
                        continue
                except:
                    pass
                time.sleep(0.5)
        return False

    def release(self):
        if self.locked:
            try:
                os.rmdir(self.lock_path)
            except:
                pass
            self.locked = False

    def __enter__(self):
        _metadata_thread_lock.acquire()
        if not self.acquire():
            _metadata_thread_lock.release()
            log_error("Metadata lock timeout")
            raise Exception("Metadata lock timeout: Another sync operation is in progress.")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        _metadata_thread_lock.release()


def load_metadata(base_dir):
    """
    Load metadata from _config.json and _metadata.csv.
    Maintains backward compatibility by returning a merged dictionary.
    """
    metadata = {}
    
    # 1. Load configuration from _config.json
    config_path = os.path.join(base_dir, "_config.json")
    if os.path.exists(config_path):
        try:
            with codecs.open(config_path, "r", "utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            log_error("Error reading _config.json: " + safe_str(e))
    
    if not metadata and not os.path.exists(os.path.join(base_dir, "_metadata.csv")):
        return None

    # 2. Load object metadata from _metadata.csv
    csv_path = os.path.join(base_dir, "_metadata.csv")
    if "objects" not in metadata:
        metadata["objects"] = {}
        
    if os.path.exists(csv_path):
        try:
            # Python 2/3 compatible opening for CSV
            if sys.version_info[0] < 3:
                f = open(csv_path, 'rb')
            else:
                f = open(csv_path, 'r', encoding='utf-8', newline='')
            
            try:
                reader = csv.reader(f, delimiter=';')
                header = next(reader, None) # Skip header: GUID;Name;Path;LastModified;Type;Parent;ContentHash
                
                if header:
                    for row in reader:
                        if not row: continue
                        if len(row) >= 7:
                            # In Python 2, we need to decode manually
                            if sys.version_info[0] < 3:
                                row = [cell.decode('utf-8') for cell in row]
                                
                            guid, name, path, last_mod, obj_type, parent, content_hash = row[:7]
                            metadata["objects"][path] = {
                                "guid": guid,
                                "name": name,
                                "last_modified": last_mod,
                                "type": obj_type,
                                "parent": parent if parent != "None" else None,
                                "content_hash": content_hash
                            }
            finally:
                f.close()
        except Exception as e:
            log_error("Error reading _metadata.csv: " + safe_str(e))
            
    return metadata


def format_st_content(declaration, implementation):
    """
    Format ST file content with clean structure.
    Uses markers for import script to parse sections.
    Ensures consistent whitespace for reliable hashing.
    """
    content = []
    
    decl = (declaration or "").strip()
    if decl:
        content.append(decl)
    
    impl = (implementation or "").strip()
    if impl:
        if content:
            content.append("")  # Empty line separator
        content.append(IMPL_MARKER)
        content.append(impl)
    
    return "\n".join(content)


def save_metadata(base_dir, metadata):
    """
    Save metadata: configuration to _config.json and objects to _metadata.csv.
    Uses atomic writes (temp file + replace) to prevent data corruption.
    """
    config_path = os.path.join(base_dir, "_config.json")
    csv_path = os.path.join(base_dir, "_metadata.csv")
    
    config_tmp = config_path + ".tmp"
    csv_tmp = csv_path + ".tmp"
    
    def _atomic_replace(src, dst):
        """Helper for atomic replacement, compatible with Python 2.7 and 3.x"""
        if hasattr(os, 'replace'):
            os.replace(src, dst)
        else:
            # Fallback for Python 2.7 (Windows)
            if os.path.exists(dst):
                os.remove(dst)
            os.rename(src, dst)

    try:
        # 1. Save configuration fields to JSON
        config_fields = [
            "project_name", "project_path", "export_timestamp", 
            "autosync", "sync_timeout", "export_xml"
        ]
        config_data = {}
        for field in config_fields:
            if field in metadata:
                config_data[field] = metadata[field]
        
        # Add any other non-object fields
        for key in metadata:
            if key != "objects" and key not in config_data:
                config_data[key] = metadata[key]
        
        with codecs.open(config_tmp, "w", "utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        
        _atomic_replace(config_tmp, config_path)
            
        # 2. Save object metadata to CSV
        if "objects" in metadata:
            # Debug: Count methods before saving
            method_count = sum(1 for obj in metadata["objects"].values() if obj.get("type") == TYPE_GUIDS.get("method"))
            print("DEBUG save_metadata: Saving " + str(len(metadata["objects"])) + " objects to CSV, including " + str(method_count) + " methods")
            
            if sys.version_info[0] < 3:
                f = open(csv_tmp, 'wb')
            else:
                f = open(csv_tmp, 'w', encoding='utf-8', newline='')
            
            try:
                writer = csv.writer(f, delimiter=';', quoting=csv.QUOTE_MINIMAL)
                # Header
                writer.writerow(["GUID", "Name", "Path", "LastModified", "Type", "Parent", "ContentHash"])
                
                # Sort objects by path for consistency
                paths = sorted(metadata["objects"].keys())
                rows_written = 0
                methods_written = 0
                
                for path in paths:
                    obj = metadata["objects"][path]
                    row = [
                        safe_str(obj.get("guid", "")),
                        safe_str(obj.get("name", "")),
                        safe_str(path),
                        safe_str(obj.get("last_modified", "")),
                        safe_str(obj.get("type", "")),
                        safe_str(obj.get("parent", "")),
                        safe_str(obj.get("content_hash", ""))
                    ]
                    
                    # In Python 2, we need to encode manually
                    if sys.version_info[0] < 3:
                        # Use unicode check for IronPython/Python 2 compatibility
                        unicode_type = unicode if sys.version_info[0] < 3 else str
                        row = [cell.encode('utf-8') if isinstance(cell, unicode_type) else str(cell) for cell in row]
                        
                    writer.writerow(row)
                    rows_written += 1
                    
                    # Debug: Count methods written
                    if obj.get("type") == TYPE_GUIDS.get("method"):
                        methods_written += 1
                        print("DEBUG save_metadata: Wrote method to CSV: " + path)
                
                print("DEBUG save_metadata: Wrote " + str(rows_written) + " rows to CSV, including " + str(methods_written) + " methods")
            finally:
                f.close()
            
            _atomic_replace(csv_tmp, csv_path)
        
        return True
    except Exception as e:
        log_error("Error saving split metadata: " + safe_str(e))
        # Cleanup temp files if they exist
        for tmp_file in [config_tmp, csv_tmp]:
            if os.path.exists(tmp_file):
                try: os.remove(tmp_file)
                except: pass
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
