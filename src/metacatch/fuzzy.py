"""Utility functions for fuzzy string matching."""

from itertools import count
from metacatch import config

KEYBOARD_LAYOUTS = {
    "US_QWERTY": [[1.5, 1.7, 2.2],[
            '`1234567890-=',
            'qwertyuiop[]\\',
            "asdfghjkl;'",
            'zxcvbnm,./'
        ],[ # Shift
            '~!@#$%^&*()_+',
            'QWERTYUIOP{}|',
            'ASDFGHJKL:"',
            'ZXCVBNM<>?'
        ]]
}

KEY_POSITIONS = {}

def set_keyboard(layout: str):
    """Build dictionary of keyboard key positions for the given layout"""
    KEY_POSITIONS.clear()
    if layout is None:
        config.log("Setting keyboard layout to None, all character distances will be 2")
        return
    if layout not in KEYBOARD_LAYOUTS:
        raise ValueError(f"Unknown keyboard layout '{layout}'")
    config.log(f"Setting keyboard layout to {layout}")
    offsets, normal, shift = KEYBOARD_LAYOUTS[layout]
    shift_penalty = config.edit_distance["shift"]
    for y, x0 in enumerate([0] + offsets):
        KEY_POSITIONS.update({k: (x0+i, y, 0) for i, k in enumerate(normal[y])})
        KEY_POSITIONS.update({k: (x0+i, y, shift_penalty) for i, k in enumerate(shift[y])})

def char_distance(c1: str, c2: str) -> float:
    """
    Compute the edit distance for swapping two characters
    For arbitrary characters this distance is 2, equivalent to a deletion and an insertion.
    For nearby keys we use a reduced penalty based on the keyboard layout:
    edit distance = (physical distance)^2 / 2, with a maximum of 2.
    This results in the following approximate distances for nearby keys:
    - Shifted keys: 0.25
    - Adjacent keys: 0.5
    - Diagonal keys: 1.0
    """
    if c1 == c2:
        return 0.0
    if c1 not in KEY_POSITIONS or c2 not in KEY_POSITIONS:
        return 2.0  # If either character is not found, treat as completely different
    x1, y1, z1 = KEY_POSITIONS[c1]
    x2, y2, z2 = KEY_POSITIONS[c2]
    d_squared = (x1 - x2)**2 + (y1 - y2)**2 + (z1 - z2)**2
    return min(2.0, d_squared / 2.0) # Reduced penalty for nearby keys

def str_distance(str1: str, str2: str, limit: float = float('inf')) -> float:
    """
    Compute the edit distance between two strings, based roughly on
    https://en.wikipedia.org/wiki/Damerau%E2%80%93Levenshtein_distance
    Adding or removing a character has a cost of 1
    Swapping two adjacent characters has a cost of 1
    Replacing a character has a cost depending on keyboard proximity, computed by char_distance()
    
    :param str1: first string
    :param str2: second string
    :param limit: maximum allowed distance
    :return: edit distance (or infinity if it exceeds the limit)
    """
    # Check for identical strings
    if str1 == str2:
        return 0
    if limit == 0:
        return float('inf')
    # Check for empty strings
    if min(len(str1), len(str2)) == 0:
        return max(len(str1), len(str2))
    # If limit is set, check if the length difference already exceeds it
    if abs(len(str1) - len(str2)) > limit:
        return float('inf')
    # Initialize the first distance matrix row (for '' -> str2)
    row1 = [float('inf')] * (len(str2) + 1)
    row0 = [float(i) for i in range(len(str2) + 1)]
    # Iterate through each character in the first string
    for i1, c1 in enumerate(str1):
        # Initialize the next distance matrix row (for str1[:i1+1] -> str2)
        row2 = row1.copy()
        row1 = row0.copy()
        row0[0] = i1 + 1
        # Iterate through each character in the second string
        for i2, c2 in enumerate(str2):
            # Calculate the least costly edit operation
            insertion_cost = row0[i2] + 1
            deletion_cost = row1[i2 + 1] + 1
            substitution_cost = row1[i2] + char_distance(c1, c2)
            swap_cost = float('inf')
            if i1 > 0 and i2 > 0 and c1 == str2[i2 - 1] and str1[i1 - 1] == c2:
                swap_cost = row2[i2 - 1] + 1
            row0[i2 + 1] = min(insertion_cost, deletion_cost, substitution_cost, swap_cost)
        # If the minimum cost in the row exceeds the limit, we can stop early
        if min(row0) > limit:
            return float('inf')
    # The Levenshtein distance is the last element of the final row
    return row0[-1]

def list_distances(strings, frac: bool = False, keep: int = 100):
    """
    List pairs of strings and their edit distances, sorted by distance.

    :param strings: list of strings to compare
    :param frac: if True, use fractional distance
    :param keep: maximum number of closest matches to keep
    :return: list of tuples of (distance, string1, string2)
    """
    str_list = sorted(set(strings))
    distances = []
    for i, str1 in enumerate(str_list):
        for str2 in str_list[i + 1:]:
            if len(distances) >= keep:
                dmax = distances[-1][0]
                if frac:
                    dmax *= (len(str1) + len(str2))
                if len(str2) - len(str1) > dmax:
                    break
            dist = str_distance(str1, str2)
            dr = str_distance(str2, str1)
            if dr != dist:
                print(f"Error: asymmetric distance between '{str1}' and '{str2}': {dist} vs {dr}")
            if frac:
                dist /= (len(str1) + len(str2))
            distances.append((dist, str1, str2))
            distances.sort()
            if len(distances) > keep:
                distances.pop()
    if frac:
        print(f"Shortest {len(distances)} fractional distances:")
    else:
        print(f"Shortest {len(distances)} absolute distances:")
    for dist, str1, str2 in distances:
        print(f"{dist:.2f}: '{str1}' vs '{str2}'")
    return distances

def match(string: str, options: set, limit: float = float('inf'), full: bool = False) -> list:
    """
    Find the closest matches to a given string from a set of options

    :param string: the string to match
    :param options: set of valid strings to compare against
    :param limit: maximum distance to consider for matches
    :param full: if True, return all matches within the limit, otherwise only the best matches
    :return: sorted list of tuples of (distance, option)
    """
    # Check if there is an exact match first
    if not full and string in options:
        return [(string, 0)]
    # Compute the edit distance to each option and keep those within the cutoff
    matches = []
    delta = config.edit_distance["delta"]
    ratio = config.edit_distance["ratio"]
    limit = min(limit, config.edit_distance["limit"])
    str_len = len(string)
    for option in options:
        # Limit is the minimum of absolute and fractional limits, but never below delta
        opt_limit = max(delta, min(limit, ratio * (str_len + len(option))))
        dist = str_distance(string, option, opt_limit)
        # Ignore options that are too far away
        if dist > opt_limit:
            continue
        # Record the match and update the cutoff if appropriate
        matches.append((option, dist))
        if not full:
            limit = min(limit, dist + delta)
    # Return matches that are within the margin of the best match
    return sorted((m for m in matches if m[1] <= limit), key=lambda x: x[1])

def match_sorted(string: str, options_by_length: dict, init: str = "", full: bool = False):
    """
    Find the closest matches to a given string from a dictionary of options grouped by length.

    :param string: the string to match
    :param options_by_length: dictionary of options grouped by their length
    :param init: initial match to use for setting the distance limit
    :param full: if True, return all matches within the limit, otherwise only the best matches
    :return: sorted list of tuples of (distance, option)
    """
    # Start with the options that have the same length as the input string
    str_len = len(string)
    delta = config.edit_distance["delta"]
    limit = str_distance(string, init) + delta if init else config.edit_distance["limit"]
    matches = match(string, options_by_length.get(str_len, set()), limit, full)
    if not full and matches:
        if matches[0][1] == 0:
            return matches
        limit = min(limit, matches[0][1] + delta)
    # Check other options in order of increasing length difference
    for dl in count(1):
        # Stop if the length difference alone exceeds the edit distance limit
        if dl > limit:
            break
        # Check options with length difference of dl from the input string
        new_matches = match(string, options_by_length.get(str_len - dl, set()), limit, full)
        new_matches.extend(match(string, options_by_length.get(str_len + dl, set()), limit, full))
        # If we found new matches, update the matches list and distance limit
        if new_matches:
            matches.extend(new_matches)
            matches.sort(key=lambda x: x[1])
            if not full:
                limit = min(limit, matches[0][1] + delta)
    # Return matches that are within the margin of the best match
    return [m for m in matches if m[1] <= limit]

# Initialization

if not KEY_POSITIONS:
    set_keyboard(config.edit_distance["keyboard_layout"])
