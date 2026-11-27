"""Functions for synchronizing the MetaCatch specification with the online MetaCat database"""

import sys
import enum
import argparse
import shutil
import datetime
import metacat.webapi as metacat
import metacat.common.auth_client as metacat_auth
from metacatch import config, specification

DEBUG = True

client = metacat.MetaCatClient()

SERVER_CATEGORY_DEFAULTS = {
    "description":          None,
    "required":             False,
    "restricted":           False,
    #"owner_user":          None,
    #"owner_role":          None,
    #"creator":             None,
    #"created_timestamp":   None,
    #"definitions":         {},
}

SERVER_KEY_DEFAULTS = {
    "description":  None,
    "type":         "any",
    "required":     False,
    "min":          None,
    "max":          None,
    "pattern":      "",
    #"values":      [],
}

class SyncMode(enum.IntEnum):
    """Enumeration of the different synchronization modes"""
    MINIMAL = enum.auto()
    BASIC = enum.auto()
    FULL = enum.auto()

# Functions to fetch the existing category specifications

def read_server_category(server_spec: dict) -> tuple[str, dict]:
    """Convert a server category specification to standard format"""
    name = server_spec["path"]
    spec = {}
    for param in SERVER_CATEGORY_DEFAULTS:
        spec[param] = server_spec[param]
    keys = {}
    for key, key_srv_spec in server_spec.get("definitions", {}).items():
        key_spec = {}
        for param, val in key_srv_spec.items():
            if param == "values":
                key_spec[param] = set(val)
            else:
                key_spec[param] = val
        keys[key] = key_spec
    spec["keys"] = keys
    return name, spec

def server_categories():
    """Get the categories and keys from the MetaCat server"""
    categories = {}
    for category in client.list_categories():
        name, spec = read_server_category(category)
        categories[name] = spec
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
    key_type = spec.get("type", SERVER_KEY_DEFAULTS["type"])
    key_str = f"  {bullet} {key:<{key_len}} {key_type:>9} {req_str}"
    indent = len(key_str)
    tab = 15
    if "pattern" in spec:
        key_str += f" ~ '{spec['pattern']}'"
    if "min" in spec or "max" in spec:
        min_str = repr(spec["min"]) if "min" in spec else ""
        max_str = repr(spec["max"]) if "max" in spec else ""
        key_str += f" [{min_str} - {max_str}]"
    if "values" in spec:
        key_str += f" {log_values(spec['values'], indent=indent)}"
    if desc := spec.get("description"):
        if len(key_str) < indent + tab:
            key_str += " " * (indent + tab - len(key_str))
        width, _ = shutil.get_terminal_size(fallback=(80, 20))
        space = width - len(key_str.splitlines()[-1]) - 3
        if len(desc) > space:
            words = desc.split()
            min_words = 3
            if sum(len(w) for w in words[:min_words]) + 2 > space:
                key_str += f"\n{' ' * (indent + tab)}"
            else:
                desc = " ".join(words[:min_words])
                for i, word in enumerate(words[min_words:]):
                    if len(desc) + len(word) + 1 > space:
                        desc += f"\n{' ' * (indent + tab + 3)}" + " ".join(words[i+min_words:])
                        break
                    desc += " " + word
        key_str += f" {config.Color.DIM}# {desc}{config.Color.RESET}"
    return key_str

def log_category(bullet: str, path: str, cat_len: int, spec: dict, old: dict|None = None) -> str:
    """Return a string representation of a category's specification"""
    req_str = log_flag("R", "required", spec, old, invert=False)
    res_str = log_flag("O", "restricted", spec, old, invert=True)
    desc = spec.get("description")
    if not desc and old is not None:
        desc = old.get("description")
    dim, bold, reset = config.Color.DIM, config.Color.BOLD, config.Color.RESET
    desc = f" {dim}# {desc}" if desc else ""
    return f"{bold}{bullet} {path:<{cat_len+9}} {res_str} {req_str}{desc}{reset}"

def log_removed(categories: dict, key_len: int = 0):
    """Log categories that will be removed from the MetaCat database"""
    if len(categories) == 0:
        return
    if len(categories) == 1:
        print("Removing 1 category:")
    else:
        print(f"Removing {len(categories)} categories:")
    for path, spec in sorted(categories.items(), reverse=True):
        print(log_category("-", path, key_len, spec))
        for key, key_spec in sorted(spec['keys'].items()):
            print(log_key('-', key, key_len, key_spec))

def log_created(categories: dict, key_len: int = 0):
    """Log categories that will be created in the MetaCat database"""
    if len(categories) == 0:
        return
    if len(categories) == 1:
        print("Creating 1 category:")
    else:
        print(f"Creating {len(categories)} categories:")
    for path, spec in sorted(categories.items()):
        print(log_category("+", path, key_len, spec))
        for key, key_spec in sorted(spec['keys'].items()):
            print(log_key('+', key, key_len, key_spec))

def log_updated(categories: dict, key_len: int = 0):
    """Log categories that will be updated in the MetaCat database"""
    if len(categories) == 0:
        return
    if len(categories) == 1:
        print("Updating 1 category:")
    else:
        print(f"Updating {len(categories)} categories:")
    for path, (new_spec, old_spec) in sorted(categories.items()):
        print(log_category("*", path, key_len, new_spec, old_spec))
        changed_keys = []
        for key, old_key_spec in sorted(old_spec['keys'].items()):
            if key not in new_spec['keys']:
                print(log_key('-', key, key_len, old_key_spec))
                continue
            new_key_spec = new_spec['keys'][key]
            if new_key_spec == old_key_spec:
                continue
            changed_keys.append(log_key('*', key, key_len, new_key_spec))
        for key, new_key_spec in sorted(new_spec['keys'].items()):
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

def clean_key(spec: dict) -> dict:
    """Return a cleaned-up version of a key specification"""
    out = {}
    for key, default in SERVER_KEY_DEFAULTS.items():
        if key in spec and spec[key] != default:
            out[key] = spec[key]
    if values := spec.get("values", None):
        out["values"] = sorted(values)
    return out

def remove_category(path: str):
    """Remove a category from the MetaCat database"""
    # Attempt to remove the category
    if DEBUG:
        print(f"client.remove_category('{path}')")
        return
    try:
        response = client.remove_category(path)
    # Check error conditions
    except metacat.webapi.PermissionDeniedError:
        print("Modifying MetaCat categories requires admin privileges!")
        sys.exit(1)
    except metacat.webapi.NotFoundError:
        print(f"Cannot remove nonexistent category {path}")
        return
    except metacat.webapi.BadRequestError as e:
        if e.Message.startswith(f"Category {path} has subcategories: "):
            subcats = e.Message.split(":", 1)[1]
            print(f"Cannot remove category {path} because it has subcategories: {subcats}")
        else:
            print(f"Cannot remove category {path}: {e}")
        sys.exit(1)
    # No exceptions, check the response for success
    if response != "null":
        print(f"Removing category {path} returned unexpected response: {response}")
        sys.exit(1)
    # Success?
    print(f"Removed category {path}")

def create_category(path: str, spec: dict):
    """Create a category in the MetaCat database"""
    # Extract the category information from the spec
    desc = spec.get("description", None)
    req = spec.get("required", False)
    res = spec.get("restricted", True)
    keys = {k: clean_key(v) for k, v in spec["keys"].items()}
    # Attempt to create the category
    if DEBUG:
        args = f"'{path}', description={repr(desc)}, restricted={res}, required={req},"
        print(f"client.create_category({args}\n",
              f"    definitions={keys})")
        return
    try:
        response = client.create_category(path, description=desc, restricted=res, required=req,
                                          definitions=keys)
    # Check error conditions
    except metacat.webapi.PermissionDeniedError:
        print("Modifying MetaCat categories requires admin privileges!")
        sys.exit(1)
    except metacat.webapi.NotFoundError as e:
        if e.Message.startswith("Parent category ") and e.Message.endswith(" does not exist"):
            parent = e.Message[16:-15]
            print(f"Cannot create category {path} because parent {parent} does not exist")
        else:
            print(f"Cannot create category {path}: {e}")
        sys.exit(1)
    except metacat.webapi.AlreadyExistsError:
        print(f"Cannot create category {path} because it already exists")
        sys.exit(1)
    # No exceptions, check the response for success
    if not isinstance(response, dict):
        print(f"Creating category {path} returned unexpected response: {response}")
        sys.exit(1)
    res_path, res_spec = read_server_category(response)
    if res_path != path:
        print(f"Creating category {path} returned unexpected path: {res_path}")
        sys.exit(1)
    if (res_desc := res_spec.get("description", None)) != desc:
        print(f"Creating category {path} returned unexpected description: {res_desc}")
        sys.exit(1)
    if (res_req := res_spec.get("required", False)) != req:
        print(f"Creating category {path} returned unexpected required flag: {res_req}")
        sys.exit(1)
    if (res_res := res_spec.get("restricted", True)) != res:
        print(f"Creating category {path} returned unexpected restricted flag: {res_res}")
        sys.exit(1)
    if (res_keys := {k: clean_key(v) for k, v in res_spec.get("keys", {}).items()}) != keys:
        print(f"Creating category {path} returned unexpected keys: {res_keys}")
        sys.exit(1)
    # Success?
    print(f"Created category {path}")

def update_category(path: str, spec: dict):
    """Update a category in the MetaCat database"""
    # Extract the category information from the spec
    desc = spec.get("description", None)
    req = spec.get("required", False)
    res = spec.get("restricted", True)
    keys = {k: clean_key(v) for k, v in spec["keys"].items()}
    # Attempt to update the category
    if DEBUG:
        args = f"'{path}', description={repr(desc)}, restricted={res}, required={req},"
        print(f"client.update_category({args}\n",
              f"    mode='replace', definitions={keys})")
        return
    try:
        response = client.update_category(path, description=desc, restricted=res, required=req,
                                          mode='replace', definitions=keys)
    # Check error conditions
    except metacat.webapi.PermissionDeniedError:
        print("Modifying MetaCat categories requires admin privileges!")
        sys.exit(1)
    except metacat.webapi.NotFoundError as e:
        if e.Message == "Category not found":
            print(f"Cannot update nonexistent category {path}")
        else:
            print(f"Cannot update category {path}: {e}")
        sys.exit(1)
    # No exceptions, check the response for success
    if not isinstance(response, dict):
        print(f"Updating category {path} returned unexpected response: {response}")
        sys.exit(1)
    res_path, res_spec = read_server_category(response)
    if res_path != path:
        print(f"Updating category {path} returned unexpected path: {res_path}")
        sys.exit(1)
    if (res_desc := res_spec.get("description", None)) != desc:
        print(f"Creating category {path} returned unexpected description: {res_desc}")
        sys.exit(1)
    if (res_req := res_spec.get("required", False)) != req:
        print(f"Creating category {path} returned unexpected required flag: {res_req}")
        sys.exit(1)
    if (res_res := res_spec.get("restricted", True)) != res:
        print(f"Creating category {path} returned unexpected restricted flag: {res_res}")
        sys.exit(1)
    if (res_keys := {k: clean_key(v) for k, v in res_spec.get("keys", {}).items()}) != keys:
        print(f"Creating category {path} returned unexpected keys: {res_keys}")
        sys.exit(1)
    # Success?
    print(f"Updated category {path}")

def check_auth(minutes: float = 5):
    """Check if the user is authenticated with the MetaCat server"""
    try:
        response = client.auth_info()
    except metacat_auth.AuthenticationError:
        print("You are not currently authenticated with the MetaCat server.\n",
              "Please run 'metacat auth login' before attempting to modify categories.")
        sys.exit(1)
    user, expiration = response
    if not isinstance(expiration, (int, float)):
        print("You are not currently authenticated with the MetaCat server.\n",
              "Please run 'metacat auth login' before attempting to modify categories.")
        sys.exit(1)
    remaining = (expiration - datetime.datetime.now().timestamp()) / 60
    if remaining < minutes:
        print(f"Current authentication expires in {int(remaining)} minutes.\n",
              "Please rerun 'metacat auth login' before attempting to modify categories.")
        sys.exit(1)

def apply_changes(added: dict, changed: dict, deleted: dict):
    """Apply the changes to the MetaCat database"""
    check_auth()
    go = input("Apply these changes to the MetaCat database? (yes/no): ")
    if go.lower() not in ("yes", "y"):
        print("Changes not applied.")
        return
    # Remove categories in reverse order so subcategories are removed before their parents
    for path in sorted(deleted, reverse=True):
        remove_category(path)
    # Create categories in order so parents are created before their subcategories
    for path, spec in sorted(added.items()):
        create_category(path, spec)
    # Update categories in order, although it shouldn't matter since they already exist
    for path, (spec, _) in sorted(changed.items()):
        update_category(path, spec)

def sync():
    """Compare the local MetaCatch specification with the online MetaCat database"""
    print("Running MetaCatch synchronization...")
    local_cats = specification.export()
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
    if not added and not changed and not deleted:
        print("No changes to the MetaCat database")
        return
    if len(unchanged) > 0:
        print(f"No changes to {len(unchanged)} categories:")
        for cat in sorted(unchanged.keys()):
            print(f"  {cat}")
    log_changes(added, changed, deleted)
    apply_changes(added, changed, deleted)

def main():
    """Main function to run the MetaCatch synchronization utility"""
    parser = argparse.ArgumentParser(
        description="Synchronize the MetaCatch specification with the online MetaCat database")
    _args = parser.parse_args()
    sync()
