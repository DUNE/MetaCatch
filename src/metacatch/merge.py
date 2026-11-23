"""Functions for merging metadata dictionaries."""

import copy
import itertools
from functools import partial
from collections import defaultdict
from collections.abc import Iterator, Iterable
from typing import Callable
from metacatch.config import EF

# Merge functions for different types of metadata values

def safe_sort(values):
    """Sort a list of values, using string representation if values are not comparable"""
    try:
        values.sort()
    except TypeError:
        values.sort(key=repr)
    return values

def strict_merge(values):
    """Merge values with strict equality, returning a conflict error if any values differ"""
    # Get the list of unique values
    unique = []
    errors = EF.NONE
    for v in values:
        if v is None:
            errors |= EF.MRG_MISSING
        elif v not in unique:
            unique.append(copy.deepcopy(v))
    # If there are no good values, return an empty list with the missing error flag
    if not unique:
        return [], EF.MRG_MISSING
    # If we have only one unique value, it is still a merge conflict if there were missing values
    if len(unique) == 1:
        if errors:
            errors |= EF.MRG_CONFLICT
        return unique, errors
    # If we have multiple unique values, it is always a merge conflict
    errors |= EF.MRG_CONFLICT
    # Sort the unique values for consistent output, if possible
    return safe_sort(unique), errors

def equal_merge(values):
    """Merge non-None values with strict equality, deleting the key if values differ"""
    # Get the list of unique values
    unique = None
    errors = EF.NONE
    empty = True
    for v in values:
        empty = False
        if v is None:
            errors |= EF.MRG_MISSING
        elif unique is None:
            unique = copy.deepcopy(v)
        elif unique != v:
            errors |= EF.MRG_DELETED
            unique = None
            break
    # If we have a unique value, return it with any missing error flags
    if empty:
        errors |= EF.MRG_MISSING
    if unique is not None:
        return [unique], errors
    # If we short-circuited, we might need to continue iterating to check for missing values
    if errors & EF.MRG_DELETED and not errors & EF.MRG_MISSING:
        for v in values:
            if v is None:
                errors |= EF.MRG_MISSING
                break
    # Return an empty list with the appropriate error flags
    return [], errors

def set_union(values):
    """Merge sets by taking the union of all values"""
    union = set(next(values))
    first = set(union)
    for s in values:
        union.update(s)
    return [union], EF.NONE if union == first else EF.MRG_MODIFIED

def set_intersection(values):
    """Merge sets by taking the intersection of all values"""
    intersect = set(next(values))
    union = set(intersect)
    first = set(intersect)
    for s in values:
        intersect.intersection_update(s)
        union.update(s)
    missing = union - intersect
    if missing:
        return [intersect, missing], EF.MRG_SUBSET
    return [intersect], EF.NONE if intersect == first else EF.MRG_MODIFIED

def dict_union(values):
    """Merge dictionaries by taking the union of all keys with matching values"""
    first = next(values)
    result = copy.deepcopy(first)
    collisions = {}
    for d in values:
        for k, v in d.items():
            if k in collisions:
                if v not in collisions[k]:
                    collisions[k].append(copy.deepcopy(v))
            elif k not in result:
                result[k] = copy.deepcopy(v)
            elif result[k] != v:
                collisions[k] = [result.pop(k), copy.deepcopy(v)]
    if collisions:
        # Sort the collision values for consistent output, if possible
        for vals in collisions.values():
            safe_sort(vals)
        return [result, collisions], EF.MRG_CONFLICT | EF.MRG_SUBSET
    return [result], EF.NONE if result == first else EF.MRG_MODIFIED

def dict_intersection(values):
    """Merge dictionaries by taking the intersection of all keys with matching values"""
    first = next(values)
    result = copy.deepcopy(first)
    missing = defaultdict(list)
    for next_dict in values:
        # Remove keys that are in the result but missing from the next dictionary
        for key in (result.keys() - next_dict.keys()):
            missing[key] = [result.pop(key)]
        # Process keys from the next dictionary
        for key, val in next_dict.items():
            # Record keys that are in the next dictionary but missing from the result
            if key not in result:
                if val not in missing[key]:
                    missing[key].append(copy.deepcopy(val))
            # Remove keys that are in both dictionaries but have different values
            elif result[key] != val:
                missing[key] = [result.pop(key), copy.deepcopy(val)]
    if missing:
        # Sort the missing values for consistent output, if possible
        for vals in missing.values():
            safe_sort(vals)
        return [result, missing], EF.MRG_SUBSET
    return [result], EF.NONE if result == first else EF.MRG_MODIFIED

# Allowed merging methods for different types of metadata values
MERGE_METHODS = {
    None: {
        None:           strict_merge,
        "strict":       strict_merge,
        "equal":        equal_merge,
        "delete":       lambda vals: ([], EF.MRG_DELETED),
    },
    bool: {
        "any":          lambda vals: ([any(vals)], EF.NONE),
        "all":          lambda vals: ([all(vals)], EF.NONE),
    },
    int: {
        "sum":          lambda vals: ([sum(vals)], EF.NONE),
        "min":          lambda vals: ([min(vals)], EF.NONE),
        "max":          lambda vals: ([max(vals)], EF.NONE),
    },
    float: {
        "sum":          lambda vals: ([sum(vals)], EF.NONE),
        "min":          lambda vals: ([min(vals)], EF.NONE),
        "max":          lambda vals: ([max(vals)], EF.NONE),
    },
    str: {
        "append":       lambda vals, arg="": ([arg.join(vals)], EF.MRG_ORDERED),
        "sorted":       lambda vals, arg="": ([arg.join(sorted(set(vals)))], EF.NONE),
    },
    list: {
        "append":       lambda vals: ([sum((copy.deepcopy(v) for v in vals), [])], EF.MRG_ORDERED),
    },
    set: {
        "union":        set_union,
        "intersect":    set_intersection,
    },
    dict: {
        "union":        dict_union,
        "intersect":    dict_intersection,
    },
}

# Allowed arguments for (type, merge_mode) pairs that accept an additional argument
MERGE_METHOD_ARGS: dict[tuple[type|None, str|None], Callable] = {
    (str, "append"):    lambda arg: arg,
    (str, "sorted"):    lambda arg: arg,
}

class IterTracker:
    """Class to track errors when iterating over metadata values for merging"""
    def __init__(self, iterable):
        if not isinstance(iterable, Iterator):
            self.iterable = iter(iterable)
        else:
            self.iterable = iterable
        self.missing = False
        self.multivalued = False
        self.empty = True
        self.first = None
        # Get the first item from the iterable to determine if it is empty
        self.first = next(self, None)
        self.multivalued = False # Reset multivalued flag after checking first item
        if self.first is not None:
            self.empty = False
            # Put the first item back into the iterable for future iterations
            self.iterable = itertools.chain([self.first], self.iterable)

    @property
    def errors(self):
        """Return the error flags for this iterator"""
        if self.missing and self.multivalued:
            return EF.MRG_MISSING | EF.MRG_MODIFIED
        # Iterate through the rest of the values to check for missing values
        for item in self.iterable:
            if item is None:
                self.missing = True
            elif item != self.first:
                self.multivalued = True
            if self.missing and self.multivalued:
                return EF.MRG_MISSING | EF.MRG_MODIFIED
        # Finished iterating through all values, return the appropriate error flags
        errors = EF.NONE
        if self.missing:
            errors |= EF.MRG_MISSING
        if self.multivalued:
            errors |= EF.MRG_MODIFIED
        return errors

    def __iter__(self):
        for item in self.iterable:
            if item is None:
                self.missing = True
                continue
            if item != self.first:
                self.multivalued = True
            yield item

    def __next__(self, default=None):
        for item in self:
            return item
        return default

def typed_merge(merge_func: Callable, values: Iterable) -> tuple:
    """Perform the merge operation using the specified merge function and values"""
    # Wrap the values in an IterTracker to track missing inputs
    values = IterTracker(values)
    if values.empty:
        return [], EF.MRG_MISSING
    # Run the merge function on the good values
    result, errors = merge_func(values)
    if not result or result[0] != values.first:
        errors |= EF.MRG_MODIFIED
    # Add iteration error flags and return
    return result, errors | values.errors

def method(val_type: type|None, mode: str|None) -> Callable:
    """Get the merge function for a given type and mode"""
    def err(msg: str, *args, **kwargs):
        mode_str = f"mode {repr(mode)} on type {val_type.__name__ if val_type else 'any'}"
        return msg.format(mode_str, *args, **kwargs)
    # Check if the mode string contains an argument in parentheses
    arg = None
    if mode and '(' in mode and mode.endswith(')'):
        mode, arg = mode[:-1].split('(', 1)
    # Check for a specialized merge method for the type and mode
    merge_func = MERGE_METHODS.get(val_type, {}).get(mode)
    method_type = val_type
    # If we don't have a merge method for the type, check for a generic method
    if merge_func is None:
        merge_func = MERGE_METHODS[None].get(mode)
        method_type = None
    # If we still don't have a merge method, raise an error
    if merge_func is None:
        raise ValueError(err("No merge function for {}"))
    # If we have an argument, we need to make sure it is valid
    if arg is not None:
        # Check if the (type, mode) pair even accepts an argument
        arg_check = MERGE_METHOD_ARGS.get((method_type, mode))
        if arg_check is None:
            raise ValueError(err("Merge {} does not accept an argument"))
        # Validate the argument
        try:
            arg = arg_check(arg)
        except ValueError as e:
            raise ValueError(err("Invalid argument {1} for merge {0}: {2}", arg, e)) from e
        # Create a new merge function that includes the argument
        merge_func = partial(merge_func, arg=arg)
    # If method_type is None, just return the merge function as-is
    if method_type is None:
        return merge_func
    # Otherwise, we need to wrap the merge function to check the types of the values
    return partial(typed_merge, merge_func)
