"""Functions for synchronizing the MetaCatch specification with the online MetaCat database"""

import enum
import argparse
import shutil
from metacat.webapi import MetaCatClient #pylint: disable=import-error
from metacatch import config, specification

DEBUG = True

class SyncMode(enum.IntEnum):
    """Enumeration of the different synchronization modes"""
    MINIMAL = enum.auto()
    BASIC = enum.auto()
    FULL = enum.auto()

# Functions to fetch the existing category specifications

def local_categories(mode: SyncMode = SyncMode.MINIMAL):
    """Get the categories and keys from the local MetaCatch specification"""
    config.load()
    categories = {}
    subcategories = set()
    opt_cats = set()
    empty_cats = set()
    for category, local_spec in specification.categories.items():
        if local_spec.subcategory:
            subcategories.add(category)
            continue
        spec = local_spec.server_spec(mode <= SyncMode.BASIC)
        # In minimal mode, only include required categories and keys
        if mode == SyncMode.MINIMAL:
            if not spec["required"]:
                spec["keys"] = {}
            else:
                spec["keys"] = {k: v for k, v in spec["keys"].items() if v["required"]}
        # Skip empty categories
        empty = False
        for param in ("keys", "required", "restricted", "description"):
            if param in spec and spec[param]:
                #empty = False
                break
        if empty:
            empty_cats.add(category)
            continue
        categories[category] = spec
    if subcategories:
        print(f"Skipping {len(subcategories)} subcategories:")
        for cat in sorted(subcategories):
            print(f"  {cat}")
    if opt_cats:
        print(f"Skipping {len(opt_cats)} optional categories:")
        for cat in sorted(opt_cats):
            print(f"  {cat}")
    if empty_cats:
        print(f"Skipping {len(empty_cats)} empty categories:")
        for cat in sorted(empty_cats):
            print(f"  {cat}")
    return categories

def server_categories():
    """Get the categories and keys from the MetaCat server"""
    client = MetaCatClient()
    categories = {}
    for category in client.list_categories():
        # Other fields: owner_user, owner_role, description, creator, created_timestamp
        spec = {
            "description": category["description"] or "",
            "required": category["required"],
            "restricted": category["restricted"],
            "keys": category["definitions"]
        }
        # Convert the list of allowed values to a set for easier comparison
        for key_spec in spec["keys"].values():
            if "values" in key_spec:
                key_spec["values"] = set(key_spec["values"])
        categories[category["path"]] = spec
    return categories

# Functions to log the differences between the local and server specifications

def log_values(values: set, indent: int = 0) -> str:
    """Return a string representation of a list of values"""
    # Retired keys may have no allowed values, so we need to handle that case
    if not values:
        return "()"
    # If the terminal is too narrow just let it handle wrapping
    width, _ = shutil.get_terminal_size(fallback=(80, 20))
    indent = indent + 2 # account for the ' (' before the values list
    val_len = width - indent - 1
    val_list = sorted(values)
    if val_len < 2*max(len(repr(v)) for v in val_list) + 2:
        val_str = ", ".join(repr(v) for v in val_list)
        return f"({val_str})"
    # Manually wrap the values with an indent to make it more readable
    indent_str = " " * indent
    tmp_str = repr(val_list[0])
    val_str = "("
    for val in val_list[1:]:
        new_val = repr(val)
        if len(tmp_str) + len(new_val) + 2 > val_len:
            val_str = f"{val_str}{tmp_str},\n{indent_str}"
            tmp_str = new_val
        else:
            tmp_str = f"{tmp_str}, {new_val}"
    val_str = f"{val_str}{tmp_str})"
    return val_str

def log_flag(flag: str, key: str, spec: dict, old: dict|None = None, invert: bool = False) -> str:
    """Return a string representation of a flag's value"""
    value = spec.get(key, False)
    if invert:
        value = not value
    if old is None:
        return " "+flag if value else "  "
    old_value = old.get(key, False)
    if invert:
        old_value = not old_value
    if old_value:
        return " "+flag if value else "-"+flag
    return "+"+flag if value else "  "

def log_key(bullet: str, key: str, key_len: int, spec: dict) -> str:
    """Return a string representation of a key's specification"""
    req_str = " R" if spec.get("required", False) else "  "
    key_str = f"  {bullet} {key:<{key_len}} {spec['type']:>9} {req_str}"
    if "pattern" in spec:
        key_str += f" ~ '{spec['pattern']}'"
    if "min" in spec or "max" in spec:
        min_str = repr(spec["min"]) if "min" in spec else ""
        max_str = repr(spec["max"]) if "max" in spec else ""
        key_str += f" [{min_str} - {max_str}]"
    if "values" in spec:
        key_str += f" {log_values(spec['values'], indent=len(key_str))}"
    return key_str

def log_category(bullet: str, path: str, cat_len: int, spec: dict, old: dict|None = None) -> str:
    """Return a string representation of a category's specification"""
    req_str = log_flag("R", "required", spec, old, invert=False)
    res_str = log_flag("O", "restricted", spec, old, invert=True)
    desc = spec.get("description", "")
    if not desc and old is not None:
        desc = old.get("description", "")
    if desc:
        desc = f" # {desc}"
    return f"{bullet} {path:<{cat_len+9}} {res_str} {req_str}{desc}"

def log_removed(categories: dict, key_len: int = 0):
    """Log categories that will be removed from the MetaCat database"""
    if len(categories) == 0:
        return
    if len(categories) == 1:
        print("Removing 1 category:")
    else:
        print(f"Removing {len(categories)} categories:")
    for path, spec in sorted(categories.items(), key=lambda x: len(x[1]['keys'])):
        print(log_category("-", path, key_len, spec))
        for key, key_spec in spec['keys'].items():
            print(log_key('-', key, key_len, key_spec))

def log_created(categories: dict, key_len: int = 0):
    """Log categories that will be created in the MetaCat database"""
    if len(categories) == 0:
        return
    if len(categories) == 1:
        print("Creating 1 category:")
    else:
        print(f"Creating {len(categories)} categories:")
    for path, spec in sorted(categories.items(), key=lambda x: len(x[1]['keys'])):
        print(log_category("+", path, key_len, spec))
        for key, key_spec in spec['keys'].items():
            print(log_key('+', key, key_len, key_spec))

def log_updated(categories: dict, key_len: int = 0):
    """Log categories that will be updated in the MetaCat database"""
    if len(categories) == 0:
        return
    if len(categories) == 1:
        print("Updating 1 category:")
    else:
        print(f"Updating {len(categories)} categories:")
    for path, (new_spec, old_spec) in categories.items():
        print(log_category("*", path, key_len, new_spec, old_spec))
        changed_keys = []
        for key, old_key_spec in old_spec['keys'].items():
            if key not in new_spec['keys']:
                print(log_key('-', key, key_len, old_key_spec))
                continue
            new_key_spec = new_spec['keys'][key]
            if new_key_spec == old_key_spec:
                continue
            changed_keys.append(log_key('*', key, key_len, new_key_spec))
        for key, new_key_spec in new_spec['keys'].items():
            if key not in old_spec['keys']:
                print(log_key('+', key, key_len, new_key_spec))
        for line in changed_keys:
            print(line)

def log_changes(added: dict, changed: dict, deleted: dict):
    """Log the changes that will be made to the MetaCat database"""
    key_len = max((len(cat) for cat in added.keys() | changed.keys() | deleted.keys()), default=0)
    for cats in (added, deleted):
        for spec in cats.values():
            key_len = max(key_len, max((len(key) for key in spec['keys'].keys()), default=0))
    for specs in changed.values():
        for spec in specs:
            key_len = max(key_len, max((len(key) for key in spec['keys'].keys()), default=0))
    log_removed(deleted, key_len)
    log_created(added, key_len)
    log_updated(changed, key_len)

# Functions to actually update the MetaCat database

def apply_changes(added: dict, changed: dict, deleted: dict):
    """Apply the changes to the MetaCat database"""
    go = input("Apply these changes to the MetaCat database? (yes/no): ")
    if go.lower() not in ("yes", "y"):
        print("Changes not applied.")
        return
    client = MetaCatClient()
    for path in deleted:
        if DEBUG:
            print(f"client.remove_category('{path}')")
        else:
            client.remove_category(path)
    for path, spec in added.items():
        res = spec.get("restricted", True)
        req = spec.get("required", False)
        if DEBUG:
            print(f"client.create_category(path='{path}', restricted={res}, required={req},")
            print(f"    definitions={spec['keys']})")
        else:
            client.create_category(path=path, restricted=res, required=req,
                definitions=spec["keys"]
            )
    for path, (spec, _) in changed.items():
        res = spec.get("restricted", True)
        req = spec.get("required", False)
        if DEBUG:
            print(f"client.update_category(path='{path}', restricted={res}, required={req},")
            print(f"    mode='replace', definitions={spec['keys']})")
        else:
            client.update_category(path=path, restricted=res, required=req,
                definitions=spec["keys"], mode='replace'
            )

def sync(mode: SyncMode = SyncMode.MINIMAL):
    """Compare the local MetaCatch specification with the online MetaCat database"""
    print(f"Running MetaCatch synchronization in {mode.name.lower()} mode...")
    local_cats = local_categories(mode=mode)
    server_cats = server_categories()
    added = {}
    changed = {}
    unchanged = {}
    for category, local_spec in local_cats.items():
        if category not in server_cats:
            added[category] = local_spec
            continue
        server_spec = server_cats[category]
        if server_spec == local_spec:
            unchanged[category] = local_spec
            continue
        changed[category] = (local_spec, server_spec)
    deleted = {cat: spec for cat, spec in server_cats.items() if cat not in local_cats}
    if len(unchanged) > 0:
        print(f"No changes to {len(unchanged)} categories:")
        for cat in sorted(unchanged.keys()):
            print(f"  {cat}")
    if len(added) == 0 and len(changed) == 0 and len(deleted) == 0:
        print("No changes to the MetaCat database")
        return
    log_changes(added, changed, deleted)
    apply_changes(added, changed, deleted)

def main():
    """Main function to run the MetaCatch synchronization utility"""
    parser = argparse.ArgumentParser(
        description="Synchronize the MetaCatch specification with the online MetaCat database")
    modes = [mode.name.lower() for mode in SyncMode]
    parser.add_argument("mode", choices=modes, default=modes[0],
                        help=f"Synchronization mode (default: {modes[0]})")
    args = parser.parse_args()
    mode = SyncMode[args.mode.upper()]
    sync(mode=mode)
