"""Functions that actually perform the metadata validation checks."""

import copy
from collections import ChainMap
from metacatch import specification, config
from metacatch.config import ES, EF, EM, ER, Formatter

class KeyFormatter(Formatter):
    """Class to format output messages for a metadata key"""

    # Basic formatter functions for key and value fields
    formatters = {
        # Key formatters
        "ki":   lambda k, w: Formatter.keyname(k.orig_key),
        "kf":   lambda k, w: Formatter.keyname(k.name),
        "k":    lambda k, w: Formatter.keyname(k.name_str(w)),
        "ks":   lambda k, w: Formatter.value(k.names, w),
        "ko":   lambda k, w: Formatter.options(k.names, w),
        "kd":   lambda k, w: k.spec.description or "no description",
        "ke":   lambda k, w: (k.errors & EF.KEY_ERRORS).name or k.errors.name or "GOOD",
        # Value formatters
        "vi":   lambda k, w: Formatter.value(k.orig_val, w),
        "vf":   lambda k, w: Formatter.value(k.value, w),
        "v":    lambda k, w: Formatter.value(k.val_str(w)),
        "vs":   lambda k, w: Formatter.value(k.vals, w),
        "vo":   lambda k, w: Formatter.options(k.vals, w),
        "vd":   lambda k, w: k.spec.describe(k.value) or "no description",
        "ve":   lambda k, w: (k.errors & EF.VAL_ERRORS).name or k.errors.name or "GOOD",
        # Other formatters
        "ue":   lambda k, w: (k.errors & EF.USR_ERRORS).name or k.errors.name or "GOOD",
        "me":   lambda k, w: (k.errors & EF.MRG_ERRORS).name or k.errors.name or "GOOD",
        "e":    lambda k, w: k.errors.name or "GOOD",
        "t":    lambda k, w: str(k.spec.type),
        "c":    lambda k, w: k.spec.condition_name,
    }

    # Formatter functions that take an index argument (e.g., {k[0]} or {v[1]})
    idx_formatters = {
        # Key formatters
        "k":    lambda k, i, w: repr(k.nth_name(i)),
        "ks":   lambda k, i, w: repr(k.names[i:]),
        "ko":   lambda k, i, w: Formatter.options(k.names[i:], w),
        # Value formatters
        "v":    lambda k, i, w: Formatter.value(k.nth_value(i), w),
        "vs":   lambda k, i, w: Formatter.value(k.vals[i:], w),
        "vo":   lambda k, i, w: Formatter.options(k.vals[i:], w),
    }

    def __init__(self, key: "MetaKey", **kwargs):
        """Initialize the formatter with a MetaKey and optional overrides"""
        super().__init__(**kwargs)
        self.key = key

    def _check_field(self, field: str):
        """Check if the field is valid for this formatter"""
        if field in self.formatters:
            return
        super()._check_field(field)

    def _check_index(self, index: str) -> int:
        """Check if the index is valid for the current field"""
        if self.field in self.idx_formatters:
            return int(index)
        return super()._check_index(index)

    def __format__(self, fmt: str) -> str:
        """Format the error message for the key"""
        if (default := super().__format__(fmt)) or self.field is None:
            return default
        width = self.width(self.width_target)
        if self.index is None:
            out = self.formatters[self.field](self.key, width)
        else:
            out = self.idx_formatters[self.field](self.key, self.index, width)
        return format(out, fmt)

class MetaKey:
    """Class representing a metadata key-value pair and any fixes."""

    def __init__(self, name: str, value, errors: EF = EF.NONE):
        self.orig_key = name
        self.orig_val = value
        self.names = [name]
        self.vals = [value] if value is not None else []
        self.errors = errors
        self.spec = specification.meta_keys.get(name, specification.KeySpec())

    @property
    def bad_name(self):
        """Return True if the key has no valid name or is ambiguous"""
        if not self.names:
            return True
        if len(self.names) == 1:
            return False
        if self.errors & EF.UNAMBIGUOUS:
            return False
        return True

    @property
    def name(self) -> str|None:
        """Return the key name, or None if invalid or ambiguous"""
        if self.bad_name:
            return None
        return self.names[0]

    def nth_name(self, n: int) -> str|None:
        """Return the nth key name, or None if invalid or out of range"""
        if n < 0 or n >= len(self.names):
            return None
        return self.names[n]

    def set_names(self, names: list[str], reason: EF):
        """Set the key names to a new list and record the reason for the change"""
        self.errors |= reason
        if self.names == names:
            return
        self.names = names
        if not reason:
            raise ValueError(f"Renaming key {self.name_str} requires a reason")
        if len(self.names) == 1:
            self.spec = specification.meta_keys.get(self.names[0], specification.KeySpec())
        else:
            self.spec = specification.KeySpec()

    def set_name(self, name: str, reason: EF):
        """Set the key name to a new value and record the reason for the change"""
        self.set_names([name], reason)

    @property
    def bad_value(self) -> bool:
        """Return True if the key has no valid value or is ambiguous"""
        if not self.vals or EF.DELETED in self.errors:
            return True
        if len(self.vals) == 1:
            return False
        if self.errors & EF.UNAMBIGUOUS:
            return False
        return True

    @property
    def value(self):
        """Return the value, or None if invalid or ambiguous)"""
        return None if self.bad_value else self.vals[0]

    def nth_value(self, n: int):
        """Return the nth value, or None if invalid or out of range"""
        if n < 0 or n >= len(self.vals):
            return None
        return self.vals[n]

    @property
    def output(self):
        """Return the value, converting it for serialization if necessary"""
        val = self.value
        if EF.VAL_CONVERTED in self.errors:
            val = self.spec.deconvert(val)
        return val

    def set_values(self, vals: list, reason: EF):
        """Set the values to a new list and record the reason for the change"""
        self.errors |= reason
        if self.vals == vals and all(type(v) == type(nv) for v, nv in zip(self.vals, vals)):
            return
        self.vals = vals
        if not reason:
            raise ValueError(f"Setting key {self.name_str} val {self.val_str()} requires a reason")

    def set_value(self, value, reason: EF):
        """Set the value to a new value and record the reason for the change"""
        self.set_values([value], reason)

    def __getitem__(self, index: int):
        """Make the MetaKey act like a tuple of (name, value) for unpacking"""
        if index == 0:
            return self.name
        if index == 1:
            return self.value
        raise IndexError(f"MetaKey has no index {index}")

    def name_str(self, width: int = -1) -> str:
        """Return a string representation of the key name(s)"""
        # <original -> None>
        if not self.names:
            return f"{self.orig_key} -> None"
        # <original ~ (option1, option2, ... (+n))>
        if self.bad_name:
            width = Formatter.width(width, -len(self.orig_key)-7) # -7 for "< ~ ()>"
            return f"{self.orig_key} ~ ({Formatter.truncate(self.names, width)})"
        # <original>
        if self.names[0] == self.orig_key:
            return f"{self.names[0]}"
        # <original -> new>
        return f"{self.orig_key} -> {self.names[0]}"

    def val_str(self, width: int = -1) -> str:
        """Return a string representation of the value(s)"""
        # original -> None
        if not self.vals:
            width = Formatter.width(width, -8) # -8 for " -> None"
            return f"{Formatter.fit(self.orig_val, width)} -> None"
        # original ~ (option1, option2, ... (+n))
        if len(self.vals) > 1:
            width = Formatter.width(width, -3, 0.4) # -3 for " ~ "
            opts = Formatter.fit(self.vals, width)
            return f"{Formatter.fit(self.orig_val, width)} ~ ({opts[1:-1]})"
        # original
        if self.vals[0] == self.orig_val and type(self.vals[0]) == type(self.orig_val):
            return Formatter.fit(self.vals[0], width)
        # original -> new
        width = Formatter.width(width, -4, 0.5) # -4 for " -> "
        orig = Formatter.fit(self.orig_val, width)
        new = Formatter.fit(self.vals[0], width)
        return f"{orig} -> {new}"

    def __repr__(self):
        errs = self.errors.name if self.errors else "GOOD"
        return f"<{self.name_str()}>: {self.val_str()} |{errs}|"

    def validate(self):
        """Validate the key and value against the specification"""
        # User defaults and overrides and merged files have already been validated
        if self.errors & EF.USR_ERRORS or self.errors & EF.MRG_ERRORS:
            return
        # Skip keys if the value has already been modified
        if self.vals != [self.orig_val]:
            return
        # Skip keys that don't have a spec to validate against
        if self.bad_name or EF.KEY_UNKNOWN in self.errors:
            return
        # Get the specification for the key
        self.spec = specification.meta_keys.get(self.name, specification.KeySpec())
        self.errors |= self.spec.status
        # Check if the value is valid for the key's type
        val_options, val_errors = self.spec.check(self.orig_val)
        self.set_values(val_options, val_errors)
        # Check if the key and value have descriptions
        if not self.spec.description:
            self.errors |= EF.KEY_DESC
        if not self.spec.describe(self.value):
            self.errors |= EF.VAL_DESC

    def _get_severity(self, key: bool, fix: bool) -> ES:
        """Return the base severity of a validation error"""
        # Get the key or value error flags only
        errors = self.errors & (EF.KEY_ERRORS if key else EF.VAL_ERRORS)
        # Critical flags or bad keys/values are always critical severity
        if errors & EF.CRITICAL or (self.bad_name if key else self.bad_value):
            return ES.CRITICAL
        # Error flags are error severity
        if errors & EF.ERROR:
            # If we're in fix mode and the error is fixable, return fix severity instead
            if fix and not errors & EF.UNFIXABLE:
                return ES.FIX
            return ES.ERROR
        # Warning flags are warning severity
        if errors & EF.WARNING:
            return ES.WARNING
        # Info flags are info severity
        if errors & EF.INFO:
            return ES.INFO
        # Otherwise, the key/value is valid so return no severity
        return ES.NONE

    def _merge_report(self) -> EM:
        """Return a tuple of (severity, message) for the most severe merge error"""
        errors = self.errors & EF.MRG_ERRORS
        if not errors:
            return EM(ES.NONE)
        # Special case for subsets of dictionaries
        if self.spec.type == dict and errors & EF.MRG_SUBSET:
            # If this counts as a conflict, return a conflict message for each dict key
            if errors & EF.MRG_CONFLICT:
                msg = "{keys}  Merge encountered conficting values {vals}"
                sev = ES.CRITICAL
            # Otherwise, return a deletion message for each dict key
            else:
                msg = "{keys}  Deleted during merging"
                sev = ES.FIX
            msgs = []
            keys = []
            vals = []
            for idx, (key, key_vals) in enumerate(sorted(self.vals[1].items())):
                keys.append(f"{self.name_str()}['{key}']")
                vals.append(key_vals)
                msgs.append(msg.replace("keys", f"keys[{idx}]").replace("vals", f"vals[{idx}]"))
            return EM(sev, self.errors, "\n".join(msgs), Formatter(keys=keys, vals=vals))
        # Otherwise, get the severity and message normally
        if errors & EF.CRITICAL:
            severity = ES.CRITICAL
        elif errors & EF.ERROR:
            severity = ES.ERROR if errors & EF.UNFIXABLE else ES.FIX
        elif errors & EF.WARNING:
            severity = ES.WARNING
        else:
            severity = ES.INFO
        return EM.get("MRG", severity, errors, KeyFormatter(self))

    def report(self, fix: bool = False) -> EM:
        """Return a tuple of (severity, message) for the most severe error"""
        # First check for any merge error flags
        error = self._merge_report()

        # Next check for any user error flags
        severity = ES.FIX if fix else ES.ERROR
        if self.errors & EF.USR_ERRORS and severity > error:
            error = EM.get("USR", severity, self.errors, KeyFormatter(self))

        # Get the list of key options and severity for any key errors
        severity = self._get_severity(key=True, fix=fix)
        # Check for required keys that have been deleted or have no default value
        if EF.KEY_REQUIRED in self.errors and (self.errors & EF.USR_DELETED or not self.vals):
            severity = ES.CRITICAL
        # Unknwon keys with multiple options are errors
        elif EF.KEY_UNKNOWN in self.errors and len(self.names) > 1:
            severity = ES.ERROR
        # Replace the existing error if the key error is more severe
        if severity > error:
            error = EM.get("KEY", severity, self.errors, KeyFormatter(self))

        # Get the severity for any value errors
        severity = self._get_severity(key=False, fix=fix)
        # Skip value checks for deleted keys
        if self.errors & EF.DELETED:
            severity = ES.NONE
        # Suppress type conversions for bools and sets, since they will be converted back
        elif (self.errors & EF.VAL_ERRORS == EF.VAL_CONVERTED and
            isinstance(self.vals[0], (bool, set))):
            severity = ES.NONE
        # Replace the existing error if the value error is more severe
        if severity > error:
            error = EM.get("VAL", severity, self.errors, KeyFormatter(self))

        # Return the most severe error message
        return error

class MetaDict:
    """Class representing a validated metadata dictionary, plus any errors"""

    def __init__(self, metadata: dict, defaults: dict|None = None, overrides: dict|None = None):
        """Initialize the MetaDict with a dictionary of metadata"""
        self._good_keys = {}
        self._bad_keys = {}
        self.checks = []
        # Populate the MetaDict
        self.add_keys(metadata)
        # If defaults or overrides are provided, apply them
        if defaults is None or overrides is None:
            return
        self.set_defaults(defaults, overrides)

    # Methods to make the MetaDict behave like a dictionary

    def __contains__(self, key: str) -> bool:
        """Return True if the key is in the MetaDict"""
        return key in self._good_keys

    def __getitem__(self, key: str):
        """Return the value for the given key"""
        if key in self._good_keys:
            return self._good_keys[key].value
        raise KeyError(f"Key {key} not found in MetaDict")

    def get(self, key: str, default=None):
        """Return the value for the given key, or default if not found"""
        if key in self._good_keys:
            return self._good_keys[key].value
        return default

    def __setitem__(self, key: str, value):
        raise NotImplementedError("MetaDict does not support item assignment, use set_key()")

    def __delitem__(self, key: str):
        raise NotImplementedError("MetaDict does not support item deletion")

    def __len__(self) -> int:
        """Return the number of good keys in the MetaDict"""
        return len(self._good_keys)

    def __iter__(self):
        """Return an iterator over the good keys"""
        return iter(self._good_keys)

    def __repr__(self):
        good_keys = ", ".join(repr(k) for k in self._good_keys.values())
        bad_keys = ", ".join(repr(k) for k in self._bad_keys.values())
        return f"{{{good_keys}}} | {{{bad_keys}}}"

    def item(self, key: str) -> MetaKey|None:
        """Return the MetaKey for the given key, or None if not found"""
        if key in self._good_keys:
            return self._good_keys[key]
        if key in self._bad_keys:
            return self._bad_keys[key]
        return None

    def items(self):
        """Return an iterator over the good MetaKeys"""
        return self._good_keys.values()

    def keys(self):
        """Return an iterator over the good keys"""
        return self._good_keys.keys()

    def values(self):
        """Return an iterator over the good values"""
        return (k.value for k in self._good_keys.values())

    def bad_keys(self):
        """Return an iterator over the bad MetaKeys"""
        return self._bad_keys.keys()

    @property
    def output(self) -> dict:
        """Return a dictionary of valid keys, converting values for serialization if necessary"""
        return {k.name: o for k in self.items() if (o := k.output) is not None}

    # Methods for adding individual keys

    def add_bad(self, key: MetaKey, reason: EF = EF.NONE):
        """Add a bad key to the bad keys dictionary under its original name"""
        name = key.orig_key
        if name in self._bad_keys:
            raise KeyError(f"Bad key {name} already exists!")
        key.errors |= reason
        if not key.errors:
            raise ValueError(f"Bad key {name} has no error flags!")
        self._bad_keys[name] = key

    def add_key(self, key: MetaKey):
        """Add a single key-value pair to the MetaDict"""
        name = key.name
        # If the key is ambiguous, add it to the bad keys and return
        if name is None:
            self.add_bad(key)
            return
        # If the key already exists, flag it as redundant and check if the values conflict
        if name in self._good_keys:
            if key.orig_val != (good_val := self._good_keys[name].orig_val):
                key.set_value(good_val, EF.KEY_CONFLICT)
            self.add_bad(key, EF.KEY_REDUNDANT)
            return
        # Run basic validation checks on the key and add it to the good keys
        key.validate()
        self._good_keys[name] = key

    # Methods for adding multiple keys

    def add_replaced(self, keys: dict, chains: dict):
        """Add keys that have been replaced by other keys in the specification"""
        for name, chain in sorted(chains.items(), key=lambda x: len(x[1])):
            key = keys.pop(name)
            key.set_name(chain[-1], EF.KEY_REPLACED)
            self.add_key(key)

    def add_formatted(self, keys: dict):
        """Add keys that match the specification after formatting"""
        chains = {}
        added = []
        for name, key in keys.items():
            # Skip keys that are already formatted correctly
            if (formatted := specification.format_key(name)) == name:
                continue
            key.set_name(formatted, EF.KEY_ILLEGAL)
            # If the formatted key is in the spec, add it to the MetaDict
            if formatted in specification.meta_keys:
                self.add_key(key)
                added.append(name)
            # Check if the formatted key is part of a replacement chain
            elif (chain := specification.key_chain(formatted)):
                chains[key] = chain
        # Remove any keys that have been added to the MetaDict
        for name in added:
            keys.pop(name)
        # Add any replaced keys
        self.add_replaced(keys, chains)

    def get_matches(self, key: MetaKey, init: str = "") -> list[tuple[str, int]]:
        """Find close keys in the spec that are not already used"""
        matches = specification.close_keys(key.orig_key, key.orig_val, init=init)
        return [m for m in matches if m[0] not in self]

    def add_unknown(self, keys: dict):
        """Add unknown keys if they are in unrestricted categories"""
        bad = []
        added = []
        for name, key in keys.items():
            formatted = key.name
            categories = specification.key_categories(formatted)
            # If the key has no category, mark it as illegal and continue
            if not categories:
                key.errors |= EF.KEY_ILLEGAL
                continue
            # Find the longest (sub)category in the spec
            if config.misc["allow_unknown_subcategories"]:
                category = next((c for c in categories if c in specification.categories), "")
            else:
                category = categories[0]
            # Unknown keys are only allowed in unrestricted categories
            if not (cat_spec := specification.categories.get(category)) or cat_spec.restricted:
                continue
            # Check for ambiguity with existing keys in the spec
            matches = [m for m,_ in self.get_matches(key, formatted)]
            key.set_names(key.names + matches, EF.KEY_UNKNOWN)
            # If there are no other errors, add the key to the MetaDict
            if key.errors == EF.KEY_UNKNOWN:
                self.add_key(key)
                added.append(name)
            # Otherwise, save the key to add later
            else:
                bad.append(name)
        # Remove any keys that have been added to the MetaDict
        for name in added:
            keys.pop(name)
        # Add any bad keys we found after all the good keys have been added
        for key in bad:
            self.add_key(keys.pop(key))

    def add_approx(self, keys: dict):
        """Try using fuzzy matching to find valid specs for any remaining unknown keys"""
        singles = {}
        for name, key in keys.items():
            # Look for close matches to the key in the specification
            matches = self.get_matches(key)
            key.set_names([m for m,_ in matches], EF.KEY_INVALID)
            # If we don't have a clear match, just add to the list of bad keys
            if key.bad_name:
                self.add_key(key)
                continue
            # For unambiguous matches, we should check if multiple keys match the same spec
            match, dist = matches[0]
            # If the match is already used, add it and it will be flagged as redundant
            if match in self:
                self.add_key(key)
            # If this is a new key, add it to the singles dictionary for later processing
            else:
                singles.setdefault(match, []).append((name, dist))
        # For each target key, add the matching input keys in order of increasing edit distance
        for matches in singles.values():
            for match, _ in sorted(matches, key=lambda x: x[1]):
                self.add_key(keys[match])
        # Clear the remaining keys from the input
        keys.clear()

    def add_keys(self, metadata: dict):
        """Add keys from a metadata dictionary to the MetaDict"""
        # Convert keys to MetaKey objects
        metadata = {k: MetaKey(k, v) for k, v in metadata.items()}
        # Add exact matches to the keys from the spec
        for name in [n for n in metadata if n in specification.meta_keys]:
            self.add_key(metadata.pop(name))
        # Add replaced keys
        self.add_replaced(metadata, {k: c for k in metadata if (c := specification.key_chain(k))})
        # Add keys that match the spec after formatting
        self.add_formatted(metadata)
        # Add unknown keys in unrestricted categories
        self.add_unknown(metadata)
        # Try to suggest a valid key by fuzzy matching the key to the specification
        self.add_approx(metadata)

    def set_defaults(self, defaults: dict, overrides: dict):
        """Set defaults and overrides"""
        # Process defaults
        for name, value in defaults.items():
            # Existing keys or overrides take precedence over defaults
            if name in self or name in overrides:
                continue
            self.add_key(MetaKey(name, copy.deepcopy(value), EF.USR_DEFAULT))
            config.log(f"Set missing key '{name}' to user default value: {repr(value)}")
        # Process overrides
        for name, value in overrides.items():
            key = self.item(name)
            # If the override is None, mark the key as deleted
            if value is None:
                if key is None:
                    self.add_key(key := MetaKey(name, None, EF.USR_DEFAULT))
                key.errors = EF.USR_DELETED
                config.log(f"Deleted key '{name}' by user override")
            # If the key does not exist, add it as a default
            elif key is None:
                self.add_key(MetaKey(name, copy.deepcopy(value), EF.USR_DEFAULT))
                config.log(f"Set missing key '{name}' to user override value: {repr(value)}")
            # If the override is different from the existing value, update and flag it
            elif key.value != value:
                key.errors = EF.USR_OVERRIDE
                key.set_value(copy.deepcopy(value), EF.USR_OVERRIDE)
                config.log(f"Overrode key '{name}' with user value: {repr(value)}")
            # If the key exists and the value is the same, do nothing

    def validate(self, file_data: dict, fix: bool = False) -> ER:
        """Validate the MetaDict against the specification"""
        # Individual keys have already been validated when they were added to the MetaDict
        # Add any required keys that are missing from the MetaDict
        self.add_required(file_data)
        # Run any checks defined in the specification on the MetaDict
        self.run_checks(file_data)
        # Return a validation error report
        return self.report(fix)

    def add_required(self, file_data: dict):
        """Add any required keys that are missing from the MetaDict"""
        # Start with absolute requirements (condition=None)
        required = set(specification.conditions[None].keys)
        metadata = ChainMap(self, file_data) #type: ignore
        # Add any conditionally required keys based on the current MetaDict
        for name, condition in specification.conditions.items():
            if name is None or not condition(metadata):
                continue
            if config.DEBUG:
                nkeys = len(condition.keys)
                skeys = ", ".join(sorted(condition.keys))
                config.log(f"Condition '{name}' satisfied, adding {nkeys} required keys: {skeys}")
            required.update(condition.keys)
        # Add any missing required keys with default values if available
        for name in required:
            if key := self.item(name):
                if key.errors & EF.DELETED:
                    key.errors |= EF.KEY_REQUIRED
                continue
            spec = specification.meta_keys[name]
            self.add_key(MetaKey(name, copy.deepcopy(spec.default), EF.KEY_REQUIRED))

    def run_checks(self, file_data: dict):
        """Run any checks defined in the specification on the MetaDict"""
        self.checks = []
        metadata = ChainMap(self, file_data) #type: ignore
        # Check for missing required categories
        for category, spec in specification.categories.items():
            if not spec.required or any(k.startswith(category + ".") for k in self):
                continue
            msg = f"Missing required category '{category}'"
            self.checks.append(EM(ES.CRITICAL, EF.KEY_REQUIRED, msg))
        # Run any checks defined in the key specifications
        for key in self.items():
            for check, expr in key.spec.checks:
                try:
                    if expr(ChainMap({"self": key.value}, metadata)):
                        continue
                except Exception: # pylint: disable=broad-exception-caught
                    pass
                check = check.replace("self", key.name)
                self.checks.append(EM(ES.CRITICAL, EF.KEY_REQUIRED, f"Failed check ({check})"))

    def report(self, fix: bool = False) -> ER:
        """Return a list of (severity, message) tuples for all keys above the threshold"""
        report = ER()
        report.extend(k.report(fix) for k in self.items())
        report.extend((k.report(fix) for k in self._bad_keys.values()))
        report.extend(self.checks)
        return report

def validate_defaults(defaults: dict, overrides: dict) -> ER:
    """Make sure user defaults and overrides are valid according to the specification"""
    report = ER()
    for key, val in overrides.items():
        # Check for conflicts between user defaults and overrides
        error = EM(ES.NONE)
        if key in defaults:
            default = defaults.pop(key)
            if val == default:
                continue
            if val is None:
                msg = "{keys[0]}  Deletion negates user default {vals[0]}"
                fmt = Formatter(keys=[key], vals=[default])
                error = EM(ES.ERROR, EF.USR_DELETED | EF.USR_DEFAULT, msg, fmt)
            else:
                msg = "{keys[0]}  Override {vals[0]} replaces user default {vals[1]}"
                fmt = Formatter(keys=[key], vals=[val, default])
                error = EM(ES.ERROR, EF.USR_OVERRIDE | EF.USR_DEFAULT, msg, fmt)
        # Overrides of None delete the key, so just check they are not required
        if val is None and (spec := specification.meta_keys.get(key)) and spec.absolute:
            msg = "{keys[0]} (user del)  Key is required for all files!"
            fmt = Formatter(keys=[key])
            error = EM(ES.CRITICAL, EF.USR_DELETED | EF.KEY_REQUIRED, msg, fmt)
        report.add(error)
    # Check that all user defaults are valid according to the specification
    validated_defaults = MetaDict(defaults)
    report.extend(m.insert_label("Default") for m in validated_defaults.report())
    # Check that non-deleted user overrides are valid according to the specification
    validated_overrides = MetaDict({k: v for k, v in overrides.items() if v is not None})
    report.extend(m.insert_label("Override") for m in validated_overrides.report())
    return report

def validate_file(
    file_data: dict,
    fix: bool = False,
    defaults: dict|None = None,
    overrides: dict|None = None
) -> ER:
    """Validate a file dictionary against the specification"""
    # Make sure the file dictionary has all the required keys, including "metadata"
    required_keys = {"metadata"} | specification.file_keys.keys()
    if any(k not in file_data for k in required_keys):
        report = ER()
        if any(k in file_data for k in specification.meta_keys):
            msg = "Please provide the whole file dictionary, not just the metadata!"
        else:
            missing = required_keys - file_data.keys()
            msg = f"Invalid file dictionary, missing required keys: {missing}"
        report.add(EM(ES.CRITICAL, EF.KEY_REQUIRED, msg))
        return report
    # Extract the metadata dictionary and convert it to a MetaDict, with defaults and overrides
    metadata = MetaDict(file_data.pop("metadata"), defaults=defaults, overrides=overrides)
    # Validate the MetaDict and get the error report
    report = metadata.validate(file_data, fix=fix)
    report.name = f"{file_data['namespace']}:{file_data['name']}"
    # Insert the MetaDict back into the file data, and then return the report
    file_data["metadata"] = metadata
    return report

def merge_files(files: list[dict], name: str) -> tuple[dict, ER]:
    """Merge multiple file dictionaries into a single dictionary"""
    report = ER(name, merged=True)
    # Make sure all files have the same namespace
    namespaces = {f.get("namespace") for f in files}
    namespace = None
    if len(namespaces) > 1:
        msg = f"Cannot merge files with different namespaces: {namespaces}"
        report.add(EM(ES.CRITICAL, EF.MRG_CONFLICT, msg))
    elif not namespaces or (namespace := namespaces.pop()) is None:
        report.add(EM(ES.CRITICAL, EF.MRG_MISSING, "Cannot merge files with missing namespace!"))
    else:
        # Add the namespace to the report name
        report.name = f"{namespace}:{name}"
    # Make sure we have multiple files to merge
    if len(files) < 2:
        report.add(EM(ES.CRITICAL, EF.MRG_MISSING, "At least two files are required to merge!"))
    # Get the metadata dictionaries from all files and make sure they are validated
    input_metadata = [f["metadata"] for f in files]
    if not all(isinstance(m, MetaDict) for m in input_metadata):
        report.add(EM(ES.CRITICAL, EF.MRG_MISSING, "Validate files before merging!"))
    # Make sure none of the files are retired
    if any(f.get("retired") for f in files):
        report.add(EM(ES.CRITICAL, EF.MRG_MISSING, "Cannot merge retired files!"))
    # Make sure all file names have the same extension
    extensions = {f["name"].split('.', 1)[1] for f in files}
    if len(extensions) > 1:
        msg = f"Cannot merge files with different extensions: {extensions}"
        report.add(EM(ES.CRITICAL, EF.MRG_CONFLICT, msg))
    elif not name.endswith(ext := f".{extensions.pop()}"):
        msg = f"Merged file extension '{name.split('.')[-1]}' does not match input files '{ext}'"
        report.add(EM(ES.CRITICAL, EF.MRG_CONFLICT, msg))

    # Get parents of all files
    parent_fids = set()
    parent_dids = set()
    for f in files:
        for parent in f.get("parents", []):
            if fid := parent.get("fid"):
                parent_fids.add(fid)
            elif (par_name := parent.get("name")) and (par_ns := parent.get("namespace")):
                parent_dids.add(f"{par_ns}:{par_name}")
            else:
                msg = f"File {f.get('name')} has invalid parent dict: {parent}"
                report.add(EM(ES.CRITICAL, EF.VAL_INVALID, msg))
                break

    # Return the report if we found any critical errors in the base file data
    if report.severity == ES.CRITICAL or namespace is None:
        return {}, report

    # Create a new merged file dictionary with the given name and namespace
    merged_file = {
        "name": name,
        "namespace": namespace,
        "retired": False,
        "children": [],
        "parents": [{"fid": fid} for fid in parent_fids] + [{"did": did} for did in parent_dids],
    }

    # Get the set of valid metadata keys across all files
    merged_meta = MetaDict({})
    for key in set().union(*(m.keys() for m in input_metadata)):
        # Find the first file that has this key and use its value as the base
        first_key = next((m.item(key) for m in input_metadata if key in m), None)
        if first_key is None:
            raise ValueError(f"Key {key} not found in any file?")
        merged_key = copy.deepcopy(first_key)
        # Combine the error flags from all files for this key
        for m in input_metadata:
            if (k := m.item(key)) is not None:
                merged_key.errors |= k.errors
        # Actually merge the values for this key across all files
        merged_key.set_values(*merged_key.spec.merge(m.get(key) for m in input_metadata))
        # Add the merged key to the merged file's metadata
        merged_meta.add_key(merged_key)

    # Also get the set of bad keys across all files
    for key in set().union(*(m.bad_keys() for m in input_metadata)):
        # Find the first file that has this bad key and use its value as the base
        first_key = next((k for m in input_metadata if (k := m.item(key))), None)
        if first_key is None:
            raise ValueError(f"Bad key {key} not found in any file?")
        merged_key = copy.deepcopy(first_key)
        # Combine the error flags from all files for this bad key
        for m in input_metadata:
            if (k := m.item(key)) is not None:
                merged_key.errors |= k.errors
        # Add the merged bad key to the merged file's metadata
        merged_meta.add_bad(merged_key)

    # Validate the merged MetaDict and get the error report
    report.extend(merged_meta.validate(merged_file, fix=True))
    # Insert the MetaDict back into the file data, and then return it with the report
    merged_file["metadata"] = merged_meta
    return merged_file, report
