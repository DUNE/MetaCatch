"""Functions that actually perform the metadata validation checks."""

import copy
from collections import ChainMap
from metacatch import specification, config
from metacatch.config import ValidationError as VE
from metacatch.config import ErrorSeverity as ES

USR_ERRORS = {
    ES.ERROR: [
        (VE.USR_DELETED,    "Key {k} val {v} should be deleted by user override"),
        (VE.USR_OVERRIDE,   "Key {k} val {vi} should be set to user override {vf}"),
        (VE.USR_DEFAULT,    "Missing key {k} should be set to user default value {vf}"),
    ],
    ES.FIX: [
        (VE.USR_DELETED,    "Deleted key {k} val {v} by user override"),
        (VE.USR_OVERRIDE,   "Set key {k} val {vi} to user override {vf}"),
        (VE.USR_DEFAULT,    "Set missing key {k} to user default value {vf}"),
    ],
    None: (VE.USR_ERRORS,   "Key {k} val {v} is {e}"),
}

KEY_ERRORS = {
    ES.CRITICAL: [
        (VE.KEY_REQUIRED | VE.USR_DELETED, "Deleted key {k} is required for {c} files!"),
        (VE.KEY_REQUIRED,   "Missing key {k} is required for {c} files!"),
        (VE.KEY_ILLEGAL,    "Key {ki} is malformed, {o}"),
        (VE.KEY_INVALID,    "Key {ki} is invalid, {o}"),
    ],
    ES.ERROR: [
        (VE.KEY_REQUIRED,   "Missing key {k} required for {c} files (default value {v})"),
        (VE.KEY_CONFLICT,   "Key {ki} val {vi} conflicts with replacement key {kf} val {vf}"),
        (VE.KEY_REDUNDANT,  "Key {ki} is redundant with replacement key {kf}"),
        (VE.KEY_ILLEGAL,    "Key {ki} is malformed, {o}"),
        (VE.KEY_RETIRED,    "Key {k} is retired"),
        (VE.KEY_REPLACED,   "Key {ki} is retired, use {kf} instead"),
        (VE.KEY_INVALID,    "Key {ki} is invalid, {o}"),
        (VE.KEY_UNKNOWN,    "Key {ki} is unknown, {o}"),
    ],
    ES.FIX: [
        (VE.KEY_REQUIRED,   "Set missing key {k} to default value {v} (required for {c} files)"),
        (VE.KEY_CONFLICT,   "Ignored redundant key {ki} in favor of {kf} with value {vf}"),
        (VE.KEY_REDUNDANT,  "Ignored redundant key {ki} in favor of {kf}"),
        (VE.KEY_ILLEGAL,    "Replaced malformed key {ki} -> {kf}"),
        (VE.KEY_RETIRED,    "Deleted retired key {k}"),
        (VE.KEY_REPLACED,   "Replaced retired key {ki} -> {kf}"),
        (VE.KEY_INVALID,    "Replaced invalid key {ki} -> {kf}"),
    ],
    ES.WARNING: [
        (VE.KEY_DEPRECATED, "Key {k} is deprecated"),
        (VE.KEY_UNKNOWN,    "Key {k} is unknown, are you sure it is correct?"),
    ],
    ES.INFO: [
        (VE.KEY_DESC,       "Key {k} is valid, but has no description"),
    ],
    None: (VE.KEY_ERRORS,   "Key {ki} is {e}, {o}"),
}

VAL_ERRORS = {
    ES.CRITICAL: [
        (VE.VAL_INVALID,    "Key {k} val {vi} is invalid, {o}"),
        (VE.VAL_TYPE,       "Key {k} val {vi} is the wrong type, expected {t}"),
        (VE.VAL_RETIRED,    "Key {k} val {v} is retired, {o}"),
    ],
    ES.ERROR: [
        (VE.VAL_CHECK,      "Key {k} val {vi} failed check {vf}"),
        (VE.VAL_REPLACED,   "Key {k} val {vi} is retired, use {vf} instead"),
        (VE.VAL_RETIRED,    "Key {k} val {vi} is retired, consider using default value {vf}"),
        (VE.VAL_TYPE,       "Key {k} val {vi} is the wrong type, {o}"),
        (VE.VAL_INVALID,    "Key {k} val {vi} is invalid, {o}"),
        (VE.VAL_MIN,        "Key {k} val {vi} is below minimum value {vf}"),
        (VE.VAL_MAX,        "Key {k} val {vi} is above maximum value {vf}"),
    ],
    ES.FIX: [
        (VE.VAL_REPLACED,   "Key {k} replaced retired val {vi} -> {vf}"),
        (VE.VAL_RETIRED,    "Key {k} replaced retired val {vi} with default value {vf}"),
        (VE.VAL_TYPE,       "Key {k} replaced val of wrong type {vi} -> {vf}"),
        (VE.VAL_INVALID,    "Key {k} replaced invalid val {vi} -> {vf}"),
        (VE.VAL_MIN,        "Key {k} set val {vi} to minimum value {vf}"),
        (VE.VAL_MAX,        "Key {k} set val {vi} to maximum value {vf}"),
    ],
    ES.WARNING: [
        (VE.VAL_DEPRECATED, "Key {k} val {v} is deprecated"),
    ],
    ES.INFO: [
        (VE.VAL_DESC,       "Key {k} val {v} is valid, but has no description"),
        (VE.VAL_CONVERTED,  "Key {k} val {vi} converted to {vf}"),
    ],
    None: (VE.VAL_ERRORS,   "Key {k} val {vi} is {e}, {o}"),
}

class MetaKey:
    """Class representing a metadata key-value pair and any fixes."""

    def __init__(self, name: str, value, errors: VE = VE(0)):
        self.orig_key = name
        self.orig_val = value
        self.names = [name]
        self.vals = [value] if value is not None else []
        self.errors = errors
        self.spec = specification.meta_keys.get(name, specification.KeySpec())

    @property
    def ambiguous(self):
        """Return True if the key is ambiguous (no clear match in the specification)"""
        # Unknown keys don't count as ambiguous
        if self.errors == VE.KEY_UNKNOWN:
            return False
        return len(self.names) != 1

    @property
    def name(self) -> str|None:
        """Return the key name or None if ambiguous"""
        if self.ambiguous:
            return None
        return self.names[0]

    def set_names(self, names: list[str], reason: VE):
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

    def set_name(self, name: str, reason: VE):
        """Set the key name to a new value and record the reason for the change"""
        self.set_names([name], reason)

    @property
    def bad_value(self) -> bool:
        """Return True if the key has no valid value"""
        return len(self.vals) != 1 or VE.DELETED in self.errors

    @property
    def value(self):
        """Return the value (or None if ambiguous or invalid)"""
        return None if self.bad_value else self.vals[0]

    @property
    def output(self):
        """Return the value, converting it for serialization if necessary"""
        val = self.value
        if VE.VAL_CONVERTED in self.errors:
            val = self.spec.deconvert(val)
        return val

    def set_values(self, vals: list, reason: VE):
        """Set the values to a new list and record the reason for the change"""
        self.errors |= reason
        if self.vals == vals and all(type(v) == type(nv) for v, nv in zip(self.vals, vals)):
            return
        self.vals = vals
        if not reason:
            raise ValueError(f"Setting key {self.name_str} val {self.val_str} requires a reason")

    def set_value(self, value, reason: VE):
        """Set the value to a new value and record the reason for the change"""
        self.set_values([value], reason)

    def __getitem__(self, index: int):
        """Make the MetaKey act like a tuple of (name, value) for unpacking"""
        if index == 0:
            return self.name
        if index == 1:
            return self.value
        raise IndexError(f"MetaKey has no index {index}")

    @property
    def name_str(self) -> str:
        """Return a string representation of the key name(s)"""
        if not self.names:
            return f"'{self.orig_key}' -> None"
        if self.ambiguous:
            return f"'{self.orig_key}' -> {self.names}"
        if self.names[0] == self.orig_key:
            return repr(self.names[0])
        return f"'{self.orig_key}' -> '{self.names[0]}'"

    @staticmethod
    def _fmt_val(v):
        """Format a value for display"""
        if isinstance(v, set) and len(v) > 5:
            return f"{{{repr(sorted(v)[:5])[1:-1]}, ...}}"
        if isinstance(v, list) and len(v) > 5:
            return f"[{repr(v[:5])[1:-1]}, ...]"
        return repr(v)

    @property
    def val_str(self) -> str:
        """Return a string representation of the value(s)"""
        if not self.vals:
            return f"{self._fmt_val(self.orig_val)} -> None"
        if len(self.vals) > 1:
            opts = ", ".join(repr(v) for v in self.vals)
            return f"{self._fmt_val(self.orig_val)} -> [{opts}]"
        if self.vals[0] == self.orig_val and type(self.vals[0]) == type(self.orig_val):
            return self._fmt_val(self.vals[0])
        return f"{self._fmt_val(self.orig_val)} -> {self._fmt_val(self.vals[0])}"

    @property
    def condition(self) -> str:
        """Return the name of the requirement condition, if any"""
        return self.spec.condition_name or "no"

    @property
    def typename(self) -> str:
        """Return the name of the key's type, if any"""
        return str(self.spec.type)

    def __repr__(self):
        errs = self.errors.name if self.errors else "GOOD"
        return f"{self.name_str}: {self.val_str} <{errs}>"

    def validate(self):
        """Validate the key and value against the specification"""
        # User defaults and overrides have already been validated
        if self.errors & VE.USR_ERRORS:
            return
        # Ambiguous and unknown keys have no spec to validate against
        if self.ambiguous or VE.KEY_UNKNOWN in self.errors:
            return
        # Get the specification for the key
        self.spec = specification.meta_keys.get(self.name, specification.KeySpec())
        self.errors |= self.spec.status
        # Check if the value is valid for the key's type
        val_options, val_errors = self.spec.check(self.orig_val)
        self.set_values(val_options, val_errors)
        # Check if the key and value have descriptions
        if not self.spec.description:
            self.errors |= VE.KEY_DESC
        if not self.spec.describe(self.value):
            self.errors |= VE.VAL_DESC

    @staticmethod
    def _fmt_opts(options: list) -> str:
        """Return a string representation of a list of options"""
        if not options:
            return "no valid matches found!"
        if len(options) == 1:
            return f"did you mean '{options[0]}'?"
        return f"did you mean one of {options}?"

    def _fmt_msg(self, msg: str, **kwargs) -> str:
        """Format a message with the key and value information"""
        subs = {
            "ki": repr(self.orig_key),
            "kf": repr(self.name),
            "k":  self.name_str,
            "vi": self._fmt_val(self.orig_val),
            "vf": self._fmt_val(self.vals[0]) if self.vals else "None",
            "v":  self.val_str,
        }
        subs.update(kwargs)
        return msg.format_map(subs)

    def _get_error(self, msgs: dict, sev: ES, opts: list|None = None, **kwargs) -> tuple[ES, str]:
        """Return the first message with a matching error flag"""
        if opts is not None:
            kwargs["o"] = self._fmt_opts(opts)
        for err, msg in msgs.get(sev, []):
            if (err & self.errors) == err:
                return (sev, self._fmt_msg(msg, **kwargs))
        # No matching message found
        config.log(f"No message found for key {self}")
        err, msg = msgs[None]
        err_name = (self.errors & err).name or "GOOD"
        return (ES.CRITICAL, self._fmt_msg(msg, e=err_name, **kwargs))

    def _get_severity(self, key: bool, fix: bool) -> ES:
        """Return the base severity of a validation error"""
        # Get the key or value error flags only
        errors = self.errors & (VE.KEY_ERRORS if key else VE.VAL_ERRORS)
        # Critical flags or ambiguous keys/values are always critical severity
        ambiguous = self.ambiguous if key else self.bad_value
        if errors & VE.CRITICAL or ambiguous:
            return ES.CRITICAL
        # Error flags are error severity normally but fix severity if in fix mode
        if errors & VE.ERROR:
            if errors & VE.UNFIXABLE:
                return ES.ERROR
            return ES.FIX if fix else ES.ERROR
        # Warning flags are warning severity
        if errors & VE.WARNING:
            return ES.WARNING
        # Info flags are info severity
        if errors & VE.INFO:
            return ES.INFO
        # Otherwise, the key/value is valid so return no severity
        return ES.NONE

    def report(self, fix: bool = False) -> tuple[ES, str]:
        """Return a tuple of (severity, message) for the most severe error"""
        error = (ES.NONE, "")

        # If we have a user error flag, it takes precedence
        if self.errors & VE.USR_ERRORS:
            error = self._get_error(USR_ERRORS, ES.FIX if fix else ES.ERROR)

        # Get the list of key options and severity for any key errors
        severity = self._get_severity(key=True, fix=fix)
        opts = self.names
        # Special case for unknown keys
        if self.errors & VE.KEY_ERRORS == VE.KEY_UNKNOWN:
            opts = self.names[1:] # names[0] is the original key and names[1:] are close matches
            if not opts:
                severity = ES.WARNING
        # Check for required keys that have been deleted or have no default value
        if VE.KEY_REQUIRED in self.errors and (self.errors & VE.USR_DELETED or not self.vals):
            severity = ES.CRITICAL
        # Replace the existing error if the key error is more severe
        if severity > error[0]:
            error = self._get_error(KEY_ERRORS, severity, opts, c=self.condition)

        # Get the severity for any value errors
        severity = self._get_severity(key=False, fix=fix)
        # Suppress type conversions for bools and sets, since they will be converted back
        if (self.errors & VE.VAL_ERRORS == VE.VAL_CONVERTED and
            isinstance(self.vals[0], (bool, set))):
            severity = ES.NONE
        # Replace the existing error if the value error is more severe
        if severity > error[0]:
            error = self._get_error(VAL_ERRORS, severity, self.vals, t=self.typename)

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

    @property
    def output(self) -> dict:
        """Return a dictionary of valid keys, converting values for serialization if necessary"""
        return {k.name: o for k in self.items() if (o := k.output) is not None}

    # Methods for adding individual keys

    def add_bad(self, key: MetaKey, reason: VE = VE(0)):
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
                key.set_value(good_val, VE.KEY_CONFLICT)
            self.add_bad(key, VE.KEY_REDUNDANT)
            return
        # Run basic validation checks on the key and add it to the good keys
        key.validate()
        self._good_keys[name] = key

    # Methods for adding multiple keys

    def add_replaced(self, keys: dict, chains: dict):
        """Add keys that have been replaced by other keys in the specification"""
        for name, chain in sorted(chains.items(), key=lambda x: len(x[1])):
            key = keys.pop(name)
            key.set_name(chain[-1], VE.KEY_REPLACED)
            self.add_key(key)

    def add_formatted(self, keys: dict):
        """Add keys that match the specification after formatting"""
        chains = {}
        added = []
        for name, key in keys.items():
            # Skip keys that are already formatted correctly
            if (formatted := specification.format_key(name)) == name:
                continue
            key.set_name(formatted, VE.KEY_ILLEGAL)
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
                key.errors |= VE.KEY_ILLEGAL
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
            key.set_names(key.names + matches, VE.KEY_UNKNOWN)
            # If there are no other errors, add the key to the MetaDict
            if key.errors == VE.KEY_UNKNOWN:
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
            key.set_names([m for m,_ in matches], VE.KEY_INVALID)
            # If we don't have a clear match, just add to the list of bad keys
            if key.ambiguous:
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
            self.add_key(MetaKey(name, copy.deepcopy(value), VE.USR_DEFAULT))
            config.log(f"Set missing key '{name}' to user default value: {repr(value)}")
        # Process overrides
        for name, value in overrides.items():
            key = self.item(name)
            # If the override is None, mark the key as deleted
            if value is None:
                if key is None:
                    self.add_key(key := MetaKey(name, None, VE.USR_DEFAULT))
                key.errors = VE.USR_DELETED
                config.log(f"Deleted key '{name}' by user override")
            # If the key does not exist, add it as a default
            elif key is None:
                self.add_key(MetaKey(name, copy.deepcopy(value), VE.USR_DEFAULT))
                config.log(f"Set missing key '{name}' to user override value: {repr(value)}")
            # If the override is different from the existing value, update and flag it
            elif key.value != value:
                key.errors = VE.USR_OVERRIDE
                key.set_value(copy.deepcopy(value), VE.USR_OVERRIDE)
                config.log(f"Overrode key '{name}' with user value: {repr(value)}")
            # If the key exists and the value is the same, do nothing

    def validate(self, file_data: dict, fix: bool = False) -> list[tuple[ES, str]]:
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
                if key.errors & VE.DELETED:
                    key.errors |= VE.KEY_REQUIRED
                continue
            spec = specification.meta_keys[name]
            self.add_key(MetaKey(name, copy.deepcopy(spec.default), VE.KEY_REQUIRED))

    def run_checks(self, file_data: dict):
        """Run any checks defined in the specification on the MetaDict"""
        self.checks = []
        metadata = ChainMap(self, file_data) #type: ignore
        # Check for missing required categories
        for category, spec in specification.categories.items():
            if not spec.required or any(k.startswith(category + ".") for k in self):
                continue
            self.checks.append((ES.CRITICAL, f"Missing required category '{category}'"))
        # Run any checks defined in the key specifications
        for key in self.items():
            for check, expr in key.spec.checks:
                try:
                    if expr(ChainMap({"self": key.value}, metadata)):
                        continue
                except Exception: # pylint: disable=broad-exception-caught
                    pass
                check = check.replace("self", key.name)
                self.checks.append((ES.CRITICAL, f"Failed check ({check})"))

    def report(self, fix: bool = False) -> list[tuple[ES, str]]:
        """Return a list of (severity, message) tuples for all keys above the threshold"""
        reports = [r for k in self.items() if (r := k.report(fix=fix))[0] > ES.NONE]
        reports.extend((k.report(fix=fix) for k in self._bad_keys.values()))
        reports.extend(self.checks)
        return sorted(reports, key=lambda x: (-x[0].value, x[1]))

def validate_defaults(defaults: dict, overrides: dict) -> list[tuple[ES, str]]:
    """Make sure user defaults and overrides are valid according to the specification"""
    errors = []
    for key, vo in overrides.items():
        # Check for conflicts between user defaults and overrides
        error = (ES.NONE, "")
        if key in defaults:
            rd = repr(defaults.pop(key))
            ro = repr(vo)
            if rd == ro:
                continue
            if vo is None:
                error = (ES.ERROR, f"Deleted key '{key}' negates user default val {rd}")
                continue
            error = (ES.ERROR, f"Overridden key '{key}' val {ro} replaces user default {rd}")
        # Overrides of None delete the key, so just check they are not required
        if vo is None and (spec := specification.meta_keys.get(key)) and spec.absolute:
            error = (ES.CRITICAL, f"Deleted key '{key}' is required for all files!")
        if error[0] > ES.NONE:
            errors.append(error)
    # Check that all user defaults are valid according to the specification
    validated_defaults = MetaDict(defaults)
    for sev, msg in validated_defaults.report():
        if sev > ES.INFO:
            errors.append((sev, f"Default {msg[0].lower()}{msg[1:]}"))
    # Check that non-deleted user overrides are valid according to the specification
    validated_overrides = MetaDict({k: v for k, v in overrides.items() if v is not None})
    for sev, msg in validated_overrides.report():
        if sev > ES.INFO:
            errors.append((sev, f"Overridden {msg[0].lower()}{msg[1:]}"))
    return sorted(errors, key=lambda x: (-x[0].value, x[1]))

def validate_file(
    file_data: dict,
    fix: bool = False,
    defaults: dict|None = None,
    overrides: dict|None = None
) -> list[tuple[ES, str]]:
    """Validate a metadata dictionary against the specification"""
    # Extract the metadata dictionary and convert it to a MetaDict, with defaults and overrides
    metadata = file_data.pop("metadata", None)
    if metadata is None:
        return [(ES.CRITICAL, "Invalid file data, did you provide only the metadata dictionary?")]
    meta_dict = MetaDict(metadata, defaults=defaults, overrides=overrides)
    # Validate the MetaDict and get the error report
    report = meta_dict.validate(file_data, fix=fix)
    # Insert the MetaDict back into the file data, and then return the report
    file_data["metadata"] = meta_dict
    return report
