"""Classes and functions to manage metadata specifications"""

import sys
import re
from collections import defaultdict, ChainMap
from metacatch import config, keytypes, expression, fuzzy
from metacatch.keytypes import KeyType
from metacatch.config import EF

categories = {}
conditions = {}
file_keys = {"name": str, "namespace": str}
meta_keys = {}
replaced_keys: dict[str, str] = {}
keys_by_length = defaultdict(set)

class SpecError(Exception):
    """Exception raised for errors in the metadata specification"""

class Condition():
    """Class to represent a condition in the metadata specification"""
    def __init__(self, spec):
        if spec is True:
            self.expr = None
            self.category = None
        elif isinstance(spec, str):
            self.expr = expression.parse(spec)
            self.category = None
        elif isinstance(spec, dict):
            if "expression" in spec:
                self.expr = expression.parse(spec["expression"])
            else:
                self.expr = None
            self.category = spec.get("category", None)
        else:
            raise SpecError(f"Invalid condition specification: {repr(spec)}")
        self.keys = set()

    def add_key(self, key: str):
        """Add a key that depends on this condition"""
        self.keys.add(key)

    def errors(self):
        """Return a list of errors in the condition, if any"""
        errors = []
        if self.category is not None:
            if not isinstance(self.category, str):
                errors.append(f"Depends on invalid category {repr(self.category)}")
            elif self.category not in categories:
                errors.append(f"Depends on unknown category '{self.category}'")
            elif categories[self.category].required:
                errors.append(f"Depends on required category '{self.category}'")
        if self.expr is not None:
            ee = self.expr.errors(ChainMap(file_keys, meta_keys))
            if ee:
                errors.append(f"Invalid expression '{str(self.expr)}'\n  " + "\n  ".join(ee))
        return errors

    def __call__(self, metadata: dict) -> bool:
        """Evaluate the condition on a metadata dictionary"""
        if self.expr is None and self.category is None:
            return True
        if self.expr is not None and self.expr(metadata):
            return True
        if self.category is not None:
            return any(key.startswith(self.category) for key in metadata)
        return False

class Category():
    """Class to represent a category in the metadata specification"""
    required_default = False
    restricted_default = True

    def __init__(self, name: str, spec = None):
        self.name = name
        if isinstance(spec, (str, type(None))):
            self.description = spec if spec else None
            self.required = self.required_default
            self.restricted = self.restricted_default
        elif isinstance(spec, dict):
            self.description = spec.get("description", None)
            self.required = spec.get("required", self.required_default)
            self.restricted = spec.get("restricted", self.restricted_default)
        else:
            raise SpecError(f"Invalid category specification: {repr(spec)}")
        self.keys = set()
        self.parent = None
        self.children = []
        self.conditional = False

    @property
    def subcategory(self):
        """Return True if the category is a subcategory"""
        return '.' in self.name

    def set_required(self):
        """Mark the category as required"""
        self.required = True
        if self.parent is not None:
            self.parent.set_required()

    def set_parent(self, parent):
        """Set the parent category"""
        self.parent = parent
        parent.children.append(self)
        if self.required:
            parent.set_required()

    def update(self, spec):
        """Update the category specification"""
        if isinstance(spec, (str, type(None))):
            self.description = spec or ""
        elif isinstance(spec, dict):
            self.description = spec.get("description", self.description)
            self.restricted = spec.get("restricted", self.restricted)
            if spec.get("required", False):
                self.set_required()
        else:
            raise SpecError(f"Invalid category specification: {repr(spec)}")

    def add_key(self, key):
        """Add a key to the category"""
        cat, name = key.rsplit('.', 1)
        if cat != self.name:
            raise SpecError(f"Key '{key}' does not belong to category '{self.name}'")
        self.keys.add(name)

    @property
    def all_keys(self):
        """Return a list of all keys in the category and its subcategories"""
        out = set(self.name + '.' + k for k in self.keys)
        for child in self.children:
            out.update(child.all_keys)
        return out

    def validate_conditions(self):
        """Validate conditional category requirements"""
        if self.required:
            return
        cond_self = False
        cond_parent = False
        for key in self.keys:
            spec = meta_keys.get(f"{self.name}.{key}", None)
            if spec is None or not (cond_cat := spec.required_category):
                continue
            if cond_cat == self.name:
                cond_self = True
            elif self.name.startswith(cond_cat + '.'):
                cond_parent = True
        if cond_self and cond_parent:
            raise SpecError(f"Conflicting category-based conditions in category '{self.name}'")
        self.conditional = cond_parent

    def server_spec(self, basic = False):
        """Return a dictionary of the category's specification used by the MetaCat database"""
        # In basic mode, treat categories as unrestricted
        restricted = self.restricted and not basic
        out = {
            "description": self.description,
            "required": self.required or self.conditional,
            "restricted": restricted,
            "keys": {}
        }
        for key in self.keys:
            spec = meta_keys.get(f"{self.name}.{key}", KeySpec({"status": "RETIRED"}))
            # In basic mode, skip keys without a full specification
            if basic and not spec.description:
                continue
            # If the category is restricted, skipping retired keys will make them invalid
            if restricted and spec.retired:
                continue
            # Add the key's specification to the category's specification
            out["keys"][key] = spec.server_spec(self.name)
        return out

class KeySpec:
    """Specification for a generic metadata key, see config/meta_keys.yaml for details"""
    desc = "generic metadata key"
    params = {"description", "required", "status", "type", "merge", "fixes", "checks", "default"}

    def __init__(self, spec: dict|None = None):
        if spec is None:
            spec = {}
            self.status = EF.KEY_UNKNOWN
        elif not spec:
            self.status = EF.KEY_SPEC | EF.KEY_DEPRECATED
        else:
            self.set_status(spec.get("status", "current"))
        self.description: str = spec.get("description", "")
        self.required = spec.get("required", False)
        if self.deprecated and self.absolute:
            raise SpecError("Deprecated keys cannot be absolute requirements")
        if self.retired and self.required:
            raise SpecError("Retired keys cannot be absolute or conditional requirements")
        if self.conditional and self.required not in conditions:
            raise SpecError(f"Unknown requirement condition '{self.required}'")
        self.type = KeyType(spec.get("type", None), spec.get("merge", None))
        self.fixes = spec.get("fixes", {})
        if any(not self.type.check(k) for k in self.fixes.values()):
            raise SpecError("Fixes contain values of the wrong type")
        if 'default' in spec:
            if not self.type.check(spec['default']):
                raise SpecError("Default value is of the wrong type")
            self.fixes[None] = spec['default']
        self.checks = [(c, expression.parse(c)) for c in spec.get("checks", [])]
        bad_params = spec.keys() - self.params
        if len(bad_params) == 1:
            raise SpecError(f"Invalid parameter for {self.desc}: {repr(bad_params.pop())}")
        if bad_params:
            param_str = ", ".join(repr(p) for p in sorted(bad_params))
            raise SpecError(f"Invalid parameters for {self.desc}: {param_str}")

    def set_status(self, status: str):
        """Set the status of the key"""
        statuses = {
            "current": EF.NONE,
            "deprecated": EF.KEY_DEPRECATED,
            "retired": EF.KEY_RETIRED
        }
        if (flag := statuses.get(status.lower(), None)) is None:
            raise SpecError(f"Invalid status '{status}': must be one of {list(statuses.keys())}")
        self.status = flag

    @property
    def current(self):
        """Return True if the key is current"""
        return not self.status & (EF.KEY_DEPRECATED | EF.KEY_RETIRED)

    @property
    def deprecated(self):
        """Return True if the key is deprecated"""
        return self.status & EF.KEY_DEPRECATED

    @property
    def retired(self):
        """Return True if the key is retired"""
        return self.status & EF.KEY_RETIRED

    @property
    def unknown(self):
        """Return True if the key is unknown"""
        return self.status & EF.KEY_UNKNOWN

    @property
    def absolute(self):
        """Return True if the key is an absolute requirement"""
        return self.required is True

    @property
    def conditional(self):
        """Return True if the key is a conditional requirement"""
        return isinstance(self.required, str)

    @property
    def condition_name(self) -> str:
        """Return the name of the requirement condition, if any"""
        if self.absolute:
            return "all"
        if self.conditional:
            return self.required
        return "no"

    @property
    def required_category(self):
        """Return the category that requires the key, if any"""
        if self.conditional:
            return conditions[self.required].category
        return None

    @property
    def default(self):
        """Return the default value for the key, if any"""
        return self.fixes.get(None, None)

    @property
    def options(self) -> list:
        """Return the list of valid options for the key, if any"""
        return [self.default] if self.default is not None else []

    def server_spec(self, category: str = "") -> dict:
        """Return a dictionary of the key's specification used by the MetaCat database"""
        out = {}
        if self.description:
            out["description"] = self.description
        if (type_name := self.type.server_spec()) != "any":
            out["type"] = type_name
        if self.absolute:
            out["required"] = True
        # Adjust the required flag for category-based conditions
        cond_cat = self.required_category
        if category and cond_cat and (category == cond_cat or category.startswith(cond_cat + '.')):
            out["required"] = True
        # If the key is retired, give it an empty set of valid values
        if self.retired:
            out["values"] = set()
            if not self.type.optionable:
                out["type"] = "any"
        return out

    def fix(self, value):
        """Get the fixed value for a key, if any"""
        try:
            return self.fixes.get(value, None)
        except TypeError:
            return None

    def convert(self, value) -> tuple[list, EF]:
        """Convert a value to the key's type, if possible"""
        try:
            converted = self.type.convert(value)
        except ValueError:
            return [], EF.VAL_TYPE
        # If the converted value is unchanged, return without any error flags
        if converted == value and type(converted) == type(value):
            return [converted], EF.NONE
        # Flag that the value was converted, and check if it was a type error
        errors = EF.VAL_CONVERTED
        if not self.type.check(value):
            errors |= EF.VAL_TYPE
        return [converted], errors

    def check(self, value) -> tuple[list, EF]:
        """Check if a value is valid for the key"""
        # First check for any known fixes for the value
        if (fixed := self.fix(value)) is not None:
            return [fixed], EF.VAL_REPLACED
        if value is None:
            return self.options, EF.VAL_NONE
        # Then check the type of the value
        converted, errors = self.convert(value)
        if not converted:
            return [], errors
        # Check the known fixes again for the converted value
        if (fixed := self.fix(converted[0])) is not None:
            return [fixed], errors | EF.VAL_REPLACED
        # Otherwise, return the converted value and any error flags
        return converted, errors

    def deconvert(self, value):
        """Deconvert a value from the key's type to a JSON-serializable type"""
        return self.type.deconvert(value)

    def merge(self, values) -> tuple[list, EF]:
        """Merge a list of values for the key using the key's merge method"""
        return self.type.merge(values)

    def describe(self, value) -> str:
        """Return a description of the key value"""
        return repr(value)

class BoolKeySpec(KeySpec):
    """Specification for a boolean metadata key"""
    desc = "boolean metadata key"
    params = KeySpec.params | {"values"}

    def __init__(self, spec: dict):
        # Pop fixes and defaults from the spec to avoid type checking errors
        fixes = spec.pop("fixes", {})
        if 'default' in spec:
            fixes[None] = spec.pop("default")
        # Do the normal KeySpec initialization
        super().__init__(spec)
        # Get the true and false values from the spec
        self.true, self.false = True, False
        self.set_values(spec.get("values", []))
        # Add the fixes to the key, making sure they are valid
        for bad, fix in fixes.items():
            if fix is True or fix == self.true:
                self.fixes[bad] = True
            elif fix is False or fix == self.false:
                self.fixes[bad] = False
            else:
                msg = "Default value" if bad is None else "Fixed values"
                true_str = "True" if self.true is True else f"True, {repr(self.true)}"
                false_str = "False" if self.false is False else f"False, {repr(self.false)}"
                raise SpecError(f"{msg} must be one of: {true_str}, {false_str}")

    def set_values(self, values: list):
        """Set the true and false values for the key"""
        # If no values are provided, use the default true and false values
        if not values:
            return
        if not isinstance(values, list) or len(values) != 2:
            raise SpecError("Values must be a list containing a true and false value")
        # If the values are actually booleans, we don't need to do anything
        if values[0] is True and values[1] is False or values[0] is False and values[1] is True:
            return
        # Figure out which value is which, and make sure we have a valid pair
        try:
            bool0 = self.type.convert(values[0])
            bool1 = self.type.convert(values[1])
        except ValueError as e:
            raise SpecError(f"Values {values} could not be converted to booleans") from e
        if bool0 == bool1:
            raise SpecError(f"Values {values} both evaluate to {bool0}")
        if bool0:
            self.true, self.false = values[0], values[1]
        else:
            self.true, self.false = values[1], values[0]
        # Flag that the key has custom values and needs to be deconverted
        self.status |= EF.VAL_CONVERTED

    @property
    def options(self) -> list:
        """Return the list of valid options for the key"""
        return [self.true, self.false]

    def server_spec(self, category: str = "") -> dict:
        """Return a dictionary of the key's specification used by the MetaCat database"""
        # Get the generic key specification, and return it if the key is retired
        out = super().server_spec(category)
        if self.retired:
            return out
        # If the key is actually represented as a boolean, we're done
        if self.true is True and self.false is False:
            return out
        # Otherwise, figure out the appropriate key type
        val_type = keytypes.server_type(self.true)
        if val_type != keytypes.server_type(self.false):
            out.pop("type", None)
        else:
            out["type"] = val_type
        # Add the set of valid values to the specification
        out["values"] = {self.true, self.false}
        return out

    def check(self, value) -> tuple[list, EF]:
        """Check if a value is valid for the key"""
        # Check for None values first, since they are not valid booleans
        if value is None:
            return [self.true, self.false], EF.VAL_NONE
        # Check for actual boolean values or the custom true/false values
        if value is True or value == self.true:
            return [True], EF.NONE if self.true is True else EF.VAL_CONVERTED
        if value is False or value == self.false:
            return [False], EF.NONE if self.false is False else EF.VAL_CONVERTED
        # Check for any known fixes for the value
        if (fixed := self.fix(value)) is not None:
            return [fixed], EF.VAL_REPLACED
        # Try to convert the value to a boolean
        return self.convert(value)[0], EF.VAL_TYPE

    def deconvert(self, value):
        """Deconvert a value from the key's type to a JSON-serializable type"""
        if value is True:
            return self.true
        if value is False:
            return self.false
        raise ValueError(f"Cannot deconvert non-boolean value {repr(value)}")

    def describe(self, value) -> str:
        """Return a description of the key value"""
        if value:
            return f"True ({repr(self.true)})"
        return f"False ({repr(self.false)})"

class OptionKeySpec(KeySpec):
    """Specification for a metadata key with an explicit set of options"""
    desc = "metadata key with options"
    params = KeySpec.params | {"options", "warnings", "errors"}

    def __init__(self, spec: dict):
        if "min" in spec or "max" in spec or "pattern" in spec:
            raise SpecError("Explicit options lists override min/max/pattern specifications")
        super().__init__(spec)
        if not self.type.optionable:
            raise SpecError("Option lists are only valid for numeric or string keys")
        self.val_options = self.parse_options(spec.get("options", {}))
        self.old_options = self.parse_options(spec.get("warnings", {}))
        self.bad_options = self.parse_options(spec.get("errors", {}))
        if not self.val_options:
            raise SpecError("Option keys must have at least one valid option")
        if not (
            self.val_options.keys().isdisjoint(self.old_options)
            and self.val_options.keys().isdisjoint(self.bad_options)
            and self.old_options.keys().isdisjoint(self.bad_options)
        ):
            raise SpecError("Valid, deprecated, and invalid options must be disjoint")
        if not all (self.type.check(opt) for opt in self.val_options):
            raise SpecError("Options list contains values of the wrong type")
        if not all (self.type.check(opt) for opt in self.old_options):
            raise SpecError("Deprecated options list contains values of the wrong type")
        if self.default is not None and self.default not in self.val_options:
            raise SpecError(f"Default value ({repr(self.default)}) is not valid")

    def parse_options(self, spec: dict):
        """Parse a dictionary of options for the key"""
        if not isinstance(spec, dict):
            raise SpecError("Options must be dictionaries mapping values to descriptions")
        return {v: (d if d is not None else "") for v, d in spec.items()}

    @property
    def options(self) -> list:
        """Return the list of valid options for the key"""
        if (default := self.default) is None:
            return sorted(self.val_options)
        return [default] + sorted(self.val_options.keys() - {default})

    def server_spec(self, category: str = "") -> dict:
        """Return a dictionary of the key's specification used by the MetaCat database"""
        # Get the generic key specification, and return it if the key is retired
        out = super().server_spec(category)
        if self.retired:
            return out
        # Add the set of valid and deprecated options to the specification
        out["values"] = self.val_options.keys() | self.old_options.keys()
        return out

    def check(self, value) -> tuple[list, EF]:
        """Check if the value is valid according to the key's specification"""
        # Do standard type checking and conversion
        vals, errors = super().check(value)
        if not vals or errors & EF.VAL_NONE:
            return vals, errors
        orig_val = value
        value = vals[0]
        # If the value is retired, suggest the list of valid options
        if value in self.bad_options:
            return self.options, errors | EF.VAL_RETIRED
        # If the value is valid or deprecated, return the appropriate error flag
        for opts, err in [(self.val_options, EF.NONE), (self.old_options, EF.VAL_DEPRECATED)]:
            if value in opts:
                return [value], errors | err
        # If the key is invalid, suggest valid or deprecated options using fuzzy matching
        errors |= EF.VAL_INVALID
        good_opts = set(self.val_options) | set(self.old_options)
        matches = fuzzy.match(orig_val, good_opts)
        for opts, err in [(self.val_options, EF.NONE), (self.old_options, EF.VAL_DEPRECATED)]:
            vals = [v for v,_ in matches if v in opts]
            if vals:
                return vals, errors | err
        # If we get here, give up and return all valid options
        return self.options, errors

    def describe(self, value) -> str:
        """Return a description for the value"""
        if value in self.val_options:
            return self.val_options[value]
        if value in self.old_options:
            return self.old_options[value]
        if value in self.bad_options:
            return self.bad_options[value]
        return ""

class ParamKeySpec(KeySpec):
    """Specification for a metadata key with a numeric range and/or regex pattern"""
    desc = "parametric metadata key"
    params = KeySpec.params | {"min", "max", "pattern"}

    def __init__(self, spec: dict):
        super().__init__(spec)
        self.min = spec.get("min", None)
        self.max = spec.get("max", None)
        self.pattern = spec.get("pattern", None)
        if self.min is not None:
            if not self.type.ordered:
                raise SpecError("Min value is only valid for numeric or string keys")
            if not self.type.check(self.min):
                raise SpecError(f"Minimum value ({repr(self.min)}) is the wrong type")
        if self.max is not None:
            if not self.type.ordered:
                raise SpecError("Max value is only valid for numeric or string keys")
            if not self.type.check(self.max):
                raise SpecError(f"Maximum value ({repr(self.max)}) is the wrong type")
        if self.pattern is not None:
            if self.type != str:
                raise SpecError("Pattern specification is only valid for string keys")
            if not isinstance(self.pattern, str):
                raise SpecError(f"Pattern specification ({repr(self.pattern)}) must be a string")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise SpecError(f"Min value ({repr(self.min)}) > max value ({repr(self.max)})")

    def server_spec(self, category: str = "") -> dict:
        """Return a dictionary of the key's specification used by the MetaCat database"""
        # Get the generic key specification, and return it if the key is retired
        out = super().server_spec(category)
        if self.retired:
            return out
        # Add the min, max, and pattern to the specification if they are defined
        if self.min is not None:
            out["min"] = self.min
        if self.max is not None:
            out["max"] = self.max
        if self.pattern is not None:
            out["pattern"] = self.pattern
        return out

    def check(self, value) -> tuple[list, EF]:
        """Check if the value is valid according to the key's specification"""
        # Do standard type checking and conversion
        vals, errors = super().check(value)
        if not vals or errors & EF.VAL_NONE:
            return vals, errors
        # Check if the value is within the min/max range
        val = vals[0]
        if self.min is not None and val < self.min:
            return [self.min], errors | EF.VAL_MIN
        if self.max is not None and val > self.max:
            return [self.max], errors | EF.VAL_MAX
        # Check if the value matches the regex pattern
        if self.pattern is not None and not re.fullmatch(self.pattern, val):
            return [self.pattern], errors | EF.VAL_PATTERN
        # If we get here, the value passed all checks
        return [val], errors

# Functions for checking key names and finding key specifications

def format_key(key: str) -> str:
    """Convert a key to standard format"""
    chars = []
    # Convert to valid characters only
    for c in key:
        # Get character substitution, if any
        c = config.char_substitutions.get(c, c)
        # Letters must be lowercase
        if c.isalpha():
            chars.append(c.lower())
        # The first character of a segment must be a letter
        elif not chars or chars[-1] == '.':
            continue
        # Digits, underscores, and dots are allowed if they don't start a segment
        elif c.isdigit() or c in {'_', '.'}:
            chars.append(c)
        else:
            chars.append('_')
    # Remove trailing dots
    while chars and chars[-1] == '.':
        chars.pop()
    return ''.join(chars)

def key_chain(key: str) -> list[str]:
    """Get the chain of replacements for a given key"""
    chain = []
    while key := replaced_keys.get(key, ""):
        chain.append(key)
    return chain

def key_categories(key: str) -> list[str]:
    """Get the list of categories for a given key"""
    segments = key.split('.')
    return ['.'.join(segments[:i]) for i in range(len(segments)-1, 0, -1)]

def close_keys(key: str, value, init: str = "") -> list[tuple[str, int]]:
    """Return a list of (key, distance) tuples for close matches to the given key value pair"""
    matches = fuzzy.match_sorted(key, keys_by_length, init=init)
    # Check if any matches are replaced, and eliminate redundant matches
    match_dict = {}
    for match, dist in matches:
        if (chain := key_chain(match)):
            match = chain[-1]
            dist += len(chain)
        match_dict[match] = min(dist, match_dict.get(match, float('inf')))
    matches = sorted(match_dict.items(), key=lambda x: x[1])
    # If there is no ambiguity, return the results
    if len(matches) <= 1:
        return matches
    # Check if the value is valid for any of the remaining keys
    errs = {m: meta_keys[m].check(value) for m,_ in matches}
    # Try to disambiguate filtering out bad matches in order of severity
    for condition in [
        lambda m: not meta_keys[m].retired,             # retired keys
        lambda m: len(errs[m][0]) == 1,                 # unrecoverable values
        lambda m: not errs[m][1] & EF.VAL_RETIRED,      # retired values
        lambda m: not errs[m][1] & ~EF.VAL_DEPRECATED,  # value errors
        lambda m: meta_keys[m].current,                 # deprecated keys
        lambda m: not errs[m][1]                        # deprecated values
    ]:
        good_matches = [m for m in matches if condition(m[0])]
        if not good_matches:
            # If we have an initial match, it is OK to return an empty list of additional matches
            if init:
                return []
            # Otherwise, stop and return the matches we have so far
            return matches
        # If we have a single good match, return it
        if not init and len(good_matches) == 1:
            return good_matches
        # If we have multiple good matches, keep them and continue filtering
        matches = good_matches
    # Failed to disambiguate, return all remaining matches
    return matches

# Functions for loading and verifying the metadata specification

def parse(spec: dict) -> KeySpec:
    """Parse a key specification from the config file and return a KeySpec object"""
    if spec.get("type", None) == "bool":
        return BoolKeySpec(spec)
    if "options" in spec or "warnings" in spec or "errors" in spec:
        return OptionKeySpec(spec)
    if "min" in spec or "max" in spec or "pattern" in spec:
        return ParamKeySpec(spec)
    return KeySpec(spec)

def define_category(category: str, spec: dict|str|None = None) -> Category:
    """Add a new category to the configuration"""
    if existing := categories.get(category, None):
        # If we're auto-generating a category, don't overwrite an existing one
        if spec is None:
            return existing
        # If we're explicitly defining a category that was already auto-generated, update it
        if not existing.description:
            existing.update(spec)
            return existing
        # Raise an error if we have duplicate explicit category definitions
        raise SpecError(f"Redefining existing category '{category}'")
    if format_key(category) != category:
        raise SpecError(f"Category '{category}' does not conform to the standard format")
    new_category = Category(category, spec)
    categories[category] = new_category
    if '.' in category:
        parent = category.rsplit('.', 1)[0]
        new_category.set_parent(define_category(parent))
    return new_category

def define_key(key: str, spec: dict):
    """Add a new metadata key to the configuration"""
    if key in meta_keys or key in replaced_keys:
        raise SpecError(f"Key '{key}' already exists")
    keys_by_length[len(key)].add(key)
    # Add the key to the appropriate category
    category = None
    if (format_key(key) == key and '.' in key):
        category = define_category(key.rsplit('.', 1)[0])
        category.add_key(key)
    # String specifications indicate a direct replacement for the key
    if isinstance(spec, str):
        replaced_keys[key] = spec
        return
    # Make sure the specification is a dictionary, even if it is empty
    if not spec:
        spec = {}
    # Try to parse the key specification dictionary
    try:
        key_obj = parse(spec)
    except (SpecError, ValueError) as e:
        raise SpecError(f"Key '{key}': {e}") from e
    meta_keys[key] = key_obj
    # If the key is illegal, raise an error unless it is also retired
    if category is None:
        if key_obj.retired:
            return
        if '.' not in key:
            raise SpecError(f"Key '{key}' is missing a category prefix (must contain a '.')")
        raise SpecError(f"Key '{key}' does not conform to the standard format")
    # If keys are absolute requirements, mark the category as required
    if key_obj.absolute:
        category.set_required()
        conditions[None].add_key(key)
    elif key_obj.required:
        conditions[key_obj.required].add_key(key)

def verify_spec():
    """Check the metadata specification for errors and inconsistencies"""
    # Verify that all conditions are valid
    for cond, cond_obj in conditions.items():
        if errors := cond_obj.errors():
            raise SpecError(f"Condition '{cond}':\n  " + "\n  ".join(errors))
    # Verify that all categories are valid
    for cat in categories.values():
        cat.validate_conditions()
    # Verify that all replaced keys point to valid keys
    for key, sub in replaced_keys.items():
        chain = [key, sub]
        while sub in replaced_keys:
            if sub in chain[:-1]:
                raise SpecError(f"Key '{key}' replacement chain contains a loop {chain[1:]}")
            sub = replaced_keys[sub]
            chain.append(sub)
        if sub not in meta_keys:
            raise SpecError(f"Key '{key}' replacement chain ends on invalid key {chain[1:]}")
    # Verify that keys with checks have valid expressions
    for key, spec in meta_keys.items():
        for check, expr in spec.checks:
            if errors := expr.errors(ChainMap({"self": spec}, file_keys, meta_keys)):
                raise SpecError(f"Key '{key}': check '{check}':\n  " + "\n  ".join(errors))

def extract_field(spec_dict: dict, field: str, extras: list[str], name: str) -> dict:
    """Extract a field from the specification dictionary, including any extra fields"""
    out = spec_dict.pop(field, {})
    prefixes = {field + ' '} | {e.strip() + ' ' for e in extras}
    for extra in {k for k in spec_dict if any(k.startswith(p) for p in prefixes)}:
        key = extra.split(' ', 1)[1]
        if key in out:
            raise SpecError(f"Redefining existing {name} '{key}'")
        out[key] = spec_dict.pop(extra)
    return out

def load_categories(spec_dict: dict):
    """Load the category definitions from the specification"""
    cat_dict = extract_field(spec_dict, "CATEGORIES", ["CATEGORY"], "category")
    defaults = cat_dict.pop(None, {})
    if isinstance((required := defaults.get("required", None)), bool):
        Category.required_default = required
    if isinstance((restricted := defaults.get("restricted", None)), bool):
        Category.restricted_default = restricted
    for cat, spec in cat_dict.items():
        define_category(cat, spec)

def load_conditions(spec_dict: dict):
    """Load the condition definitions from the specification"""
    conditions[None] = Condition(True)
    for cond, spec in extract_field(spec_dict, "CONDITIONS", ["CONDITION"], "condition").items():
        if cond == "all":
            raise SpecError("Condition name 'all' is reserved for absolute requirements")
        conditions[cond] = Condition(spec)

def load():
    """Load the spec from the specification.yaml file"""
    spec_dict = config.read("specification.yaml")
    try:
        load_categories(spec_dict)
        load_conditions(spec_dict)
        for key, spec in spec_dict.items():
            define_key(key, spec)
        verify_spec()
    except SpecError as e:
        print(f"SpecError: {e}")
        sys.exit(1)

# Initialization

if not meta_keys:
    load()
