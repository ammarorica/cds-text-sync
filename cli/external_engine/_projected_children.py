# -*- coding: utf-8 -*-
"""Shared helpers for projected children under collapsed POUs."""

from _project_profiles import kind_for_type_guid

PROJECTED_CHILD_KINDS = ("method", "action", "property", "property_accessor")


def projected_child_key(node, model, profile):
    kind = kind_for_type_guid(profile, (node.type or "").strip().lower())
    if kind not in PROJECTED_CHILD_KINDS:
        return None
    parent_guid = node.parent_guid
    if not parent_guid:
        return None
    parent = model.get_node(parent_guid)
    if parent is None or not model.is_collapsed_object(parent):
        return None
    return (parent_guid, (node.name or "").strip().lower(), kind)


def projected_child_maps(ide_model, folder_model, profile):
    ide_map = {}
    folder_map = {}
    for guid, node in ide_model.nodes.items():
        key = projected_child_key(node, ide_model, profile)
        if key:
            ide_map[key] = guid
    for guid, node in folder_model.nodes.items():
        key = projected_child_key(node, folder_model, profile)
        if key:
            folder_map[key] = guid
    return ide_map, folder_map


def folder_guid_for_ide(ide_guid, ide_model, folder_model, profile):
    ide_map, folder_map = projected_child_maps(ide_model, folder_model, profile)
    for key, mapped_ide_guid in ide_map.items():
        if mapped_ide_guid == ide_guid:
            return folder_map.get(key)
    return None
