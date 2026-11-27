"""Types and type conversion functions for metadata values"""

from metacatch import merge

# Mappings from the type names in the specification to actual Python types
BASIC_TYPES = {
    "str":      str,
    "int":      int,
    "float":    float,
    "bool":     bool
}

COLLECTION_TYPES = {
    "list":     list,
    "dict":     dict,
    "set":      set
}

# Mapping from Python types to the type names used in the MetaCat database
SERVER_TYPES = {
    None:       "any",
    str:        "text",
    int:        "int",
    float:      "float",
    bool:       "boolean",
    list:       "list",
    dict:       "dict",
    set:        "list"
}

def server_type(val) -> str:
    """Return the type name used in the MetaCat database for a given value"""
    if isinstance(val, type):
        return SERVER_TYPES[val]
    return SERVER_TYPES[type(val)]

# Mappings of target: set(sources) for allowed and free (no error raised) type conversions
FREE_CONVERSIONS = {
    float:  {int},
    set:    {list},
}

ALLOWED_CONVERSIONS = {
    bool:   {int,   float,  str},
    int:    {float, str},
    float:  {int,   str},
    str:    {bool,  int,    float},
    set:    {list}
}

# Actual conversion functions for each type, used by the convert() function below

def safe_bool(value):
    """Convert semantically to a boolean, if possible"""
    true_values = {1, "true", "yes", "on", "t", "y"}
    false_values = {0, "false", "no", "off", "f", "n"}
    normalized = value.lower() if isinstance(value, str) else value
    if normalized in true_values:
        return True
    if normalized in false_values:
        return False
    raise ValueError(f"Could not convert {type(value).__name__} to bool: {repr(value)}")

def safe_set(value):
    """Convert a value to a set, if possible without duplicate entries"""
    out = set(value)
    if len(out) != len(value):
        raise ValueError(f"Could not convert {type(value).__name__} to set: duplicate entries")
    return out

CONVERSIONS = {
    bool:   safe_bool,
    int:    int,
    float:  float,
    str:    str,
    set:    safe_set
}

def convert(value, target_type):
    """Convert a value to a target type, if possible"""
    if target_type is None:
        return value
    if isinstance(value, target_type):
        return value
    if target_type in CONVERSIONS and type(value) in ALLOWED_CONVERSIONS.get(target_type, set()):
        return CONVERSIONS[target_type](value)
    raise ValueError(f"Could not convert {type(value).__name__} to {target_type.__name__}")

# Class to represent the type information for a metadata key

class KeyType:
    """Class to track type information for a metadata key"""
    def __init__(self, type_spec, merge_mode):
        self.parse_type(type_spec)
        self.merge = merge.method(self.type, merge_mode)

    def parse_type(self, spec):
        """Parse a value according to the key's type specification"""
        self.type: type | None = None
        self.val_type: type | None = None
        self.key_type: type | None = None
        # Handle the case where no type is specified or the type is "any"
        if spec is None or spec == "any":
            return
        # Handle the case where the type is a basic type (str, int, float, bool)
        if spec in BASIC_TYPES:
            self.type = BASIC_TYPES[spec]
            return
        # Handle the case where the type is a collection type (list, dict, set)
        con_type, val_type = (spec+'[').split('[', 1)
        if con_type not in COLLECTION_TYPES:
            raise ValueError(f"Invalid type specification '{spec}'")
        self.type = COLLECTION_TYPES[con_type]
        # Handle key types for dicts (e.g., dict[str, int])
        if self.type is dict:
            if ',' in val_type:
                key_type, val_type = val_type.split(',', 1)
                self.key_type = BASIC_TYPES.get(key_type.strip())
                if self.key_type is None:
                    raise ValueError(f"Invalid dict key type specification '{spec}'")
        # Handle value types for collections (e.g., list[int], dict[str, float])
        if not val_type:
            return
        if not val_type.endswith("]["):
            raise ValueError(f"Invalid type specification '{spec}'")
        self.val_type = BASIC_TYPES.get(val_type[:-2].strip())
        if self.val_type is None:
            raise ValueError(f"Invalid {con_type} value type specification '{spec}'")

    def check(self, value):
        """Check if a value is of the key's type or can be freely converted to it"""
        if self.type is None:
            return True
        if type(value) not in {self.type} | (FREE_CONVERSIONS.get(self.type, set())):
            return False
        if self.val_type is None:
            return True
        good_vals = {self.val_type} | (FREE_CONVERSIONS.get(self.val_type, set()))
        if self.type is not dict:
            return all(type(v) in good_vals for v in value)
        if not all(type(v) in good_vals for v in value.values()):
            return False
        if self.key_type is None:
            return True
        good_keys = {self.key_type} | (FREE_CONVERSIONS.get(self.key_type, set()))
        return all(type(k) in good_keys for k in value.keys())

    def convert(self, value):
        """Convert a value to the key's type, if possible"""
        def error(msg):
            raise ValueError(f"Could not convert {type(value).__name__} {msg}")
        # Skip conversion if the key has no type
        if self.type is None:
            return value
        # Make sure the base types are compatible
        allowed_types = {self.type} | (ALLOWED_CONVERSIONS.get(self.type, set()))
        if type(value) not in allowed_types:
            error(f"to {self.type.__name__}")
        # If the key has no value type, convert the value directly
        if self.val_type is None:
            return convert(value, self.type)
        # Convert value types for simple collections (list, set)
        good_vals = {self.val_type} | (ALLOWED_CONVERSIONS.get(self.val_type, set()))
        if self.type is not dict:
            if not all(type(v) in good_vals for v in value):
                error(f"values to {self.val_type.__name__}")
            out = self.type(convert(v, self.val_type) for v in value)
            if len(out) != len(value):
                error(f"values to {self.val_type.__name__}: duplicate entries")
            return out
        # Convert value and key types for dictionaries
        if not all(type(v) in good_vals for v in value.values()):
            error(f"values to {self.val_type.__name__}")
        if self.key_type is not None:
            good_keys = {self.key_type} | (ALLOWED_CONVERSIONS.get(self.key_type, set()))
            if not all(type(k) in good_keys for k in value.keys()):
                error(f"keys to {self.key_type.__name__}")
            out = {convert(k, self.key_type): convert(v, self.val_type) for k, v in value.items()}
            if len(out) != len(value):
                error(f"keys to {self.key_type.__name__}: duplicate entries")
        else:
            out = {k: convert(v, self.val_type) for k, v in value.items()}
        return out

    def deconvert(self, value):
        """Deconvert a value from the key's type to a JSON-serializable type"""
        # Convert sets to sorted lists
        if self.type is set:
            return sorted(value)
        # Convert sets inside lists or dicts to sorted lists
        if self.val_type is set:
            if self.type is dict:
                return {k: sorted(v) for k, v in value.items()}
            return [sorted(v) for v in value]
        # Other types are already JSON-serializable, so return the value as is
        return value

    def __str__(self):
        """Return a string representation of the key's type"""
        if self.type is None:
            return "any"
        if self.val_type is None:
            return self.type.__name__
        if self.key_type is None:
            return f"{self.type.__name__}[{self.val_type.__name__}]"
        return f"{self.type.__name__}[{self.key_type.__name__}, {self.val_type.__name__}]"

    def __eq__(self, other):
        """Check if another type is equal to this one"""
        if isinstance(other, type):
            return self.type is other
        if isinstance(other, KeyType):
            return (
                self.type is other.type and
                self.val_type is other.val_type and
                self.key_type is other.key_type
            )
        return False

    @property
    def ordered(self):
        """Return True if the type is ordered (int, float, str)"""
        return self.type in {int, float, str}

    @property
    def optionable(self):
        """Return True if the type is valid for option lists (int, float, str)"""
        return self.type in {int, float, str}

    def export(self):
        """Return the type specification used by the MetaCat database"""
        if self.type is None:
            return "any"
        # Deal with array types (int[], float[], text[], boolean[])
        if self.type in [list, set] and self.val_type:
            return SERVER_TYPES[self.val_type] + "[]"
        # Otherwise, return the basic type
        return SERVER_TYPES[self.type]
