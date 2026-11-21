"""Command line interface for MetaCatch."""

import os
import sys
import json
import re
import argparse
import metacat.webapi as metacat #pylint: disable=import-error
from metacatch import config, validation
from metacatch.config import ErrorSeverity as ES

PATH_REGEX = r'[A-Za-z0-9_/\-]*\.[A-Za-z0-9]*'
DID_REGEX = r'[A-Za-z0-9_.\-]*:[A-Za-z0-9_.\-]*\.[A-Za-z0-9]*'

VALIDATION_STATUS = {
    ES.NONE:        "passed validation",
    ES.INFO:        "passed validation",
    ES.WARNING:     "passed validation with warnings",
    ES.FIX:         "passed validation after fixes",
    ES.ERROR:       "had non-critical errors in validation",
    ES.CRITICAL:    "failed validation with crital errors",
}

def get_parser() -> argparse.ArgumentParser:
    """Set up the command line argument parser."""
    parser = argparse.ArgumentParser(
        description="MetaCatch: Utility for catching errors in DUNE file metadata",
        usage="%(prog)s [options] <input> [<input> ...]"
    )
    parser.add_argument('-d', '--default', type=str, metavar='<file|json>',
                        help='defaults for missing metadata keys, as JSON file or inline JSON')
    parser.add_argument('-o', '--override', type=str, metavar='<file|json>',
                        help='overrides for existing metadata keys, as JSON file or inline JSON')
    parser.add_argument('-f', '--fix', type=str, metavar='pattern',
                        nargs='?', const='{dir}/{name}.fixed', default=None,
                        help='output fixed metadata, default = "{dir}/{name}.fixed"')
    parser.add_argument('-m', '--merge', type=str, metavar='<file>',
                        help='merge input metadata and write output to JSON file')
    parser.add_argument('--force', action='store_true',
                        help='overwrite existing output files without prompting')
    parser.add_argument('-q', '--quiet', action='count', default=0,
                        help='suppress output (info -> warnings -> fixes -> non-critical errors)')
    parser.add_argument('--debug', action='store_true', help='print extra debug information')
    #parser.add_argument('inputs', nargs=argparse.REMAINDER, help='remaining command line inputs')
    parser.add_argument('input', nargs='*', type=str,
                        help='file(s) to validate, as JSON file, DID, or TXT file listing inputs')
    return parser

def load_json(path: str) -> dict|None:
    """Load a JSON file and return the parsed dictionary."""
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return None

def read_json(arg: str) -> dict:
    """Read a JSON file or inline JSON string and return the parsed dictionary."""
    # If the argument wasn't provided, return an empty dictionary
    if not arg:
        return {}
    # If the argument is a file path, read the JSON from the file
    if os.path.isfile(arg):
        contents = load_json(arg)
        if contents is None:
            print(f"Invalid JSON file: {arg}")
            sys.exit(1)
        return contents
    # If the argument is not a file, try to parse it as inline JSON
    try:
        return json.loads(arg)
    except json.JSONDecodeError:
        # Try to figure out if the argument looks like a filename or inline JSON
        if any(c in arg for c in '{}[],: '):
            print(f"Invalid inline JSON: {arg}")
        elif re.fullmatch(PATH_REGEX, arg):
            print(f"File not found: {arg}")
        else:
            print(f"Invalid inline JSON: {arg}")
        sys.exit(1)

def expand_inputs(args: list) -> list:
    """Expand a list of input files, DIDs, or TXT files containing inputs."""
    expanded = []
    for arg in args:
        # If the argument is a TXT file, read the lines as inputs
        if os.path.isfile(arg) and arg.lower().endswith('.txt'):
            with open(arg, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip()]
                expanded.extend(lines)
        else:
            expanded.append(arg)
    # Check for empty inputs
    if not expanded:
        print("Please provide at least one input!")
        sys.exit(1)
    # Check for duplicates
    if len(set(expanded)) < len(expanded):
        for dup in (x for x in expanded if expanded.count(x) > 1):
            print(f"Duplicate input: {dup}")
        sys.exit(1)
    return expanded

def read_inputs(args: list) -> dict:
    """Read a list of input files, DIDs, or TXT files containing inputs."""
    error = False
    inputs = {}
    dids = set()
    query = set()
    for arg in expand_inputs(args):
        # If the argument is an existing file path, try to read it
        if os.path.isfile(arg):
            metadata = load_json(arg)
            if metadata is None:
                print(f"Invalid input JSON file: {arg}")
                error = True
                continue
            did = metadata['namespace'] + ':' + metadata['name']
            if did in dids:
                print(f"Duplicate input DID: {did}")
                error = True
                continue
            dids.add(did)
            inputs[arg] = metadata
            continue
        # If the argument looks like a DID, add it to the list of DIDs
        if re.fullmatch(DID_REGEX, arg):
            if arg in dids:
                print(f"Duplicate input DID: {arg}")
                error = True
                continue
            dids.add(arg)
            query.add(arg)
            continue
        # If the argument looks like a filename but doesn't exist, report an error
        if re.fullmatch(PATH_REGEX, arg):
            print(f"Input file not found: {arg}")
            error = True
            continue
        # Otherwise, give a generic error
        print(f"Invalid input: {arg}")
        error = True
    # Quit if there were any errors reading the inputs
    if error:
        sys.exit(1)
    if inputs:
        config.log(f"Read {len(inputs)} input JSON file(s) with metadata.")
    # Fetch metadata for any input DIDs from the MetaCat database
    if query:
        client = metacat.MetaCatClient()
        config.log(f"Fetching metadata for {len(query)} input DIDs from MetaCat database...")
        res = client.get_files([{'did': q} for q in query],
                               with_metadata = True, with_provenance = True)
        for f in res:
            did = f['namespace'] + ':' + f['name']
            inputs[did] = f
            query.remove(did)
        if query:
            for q in query:
                print(f"Input DID not found in MetaCat database: {q}")
            sys.exit(1)
    return inputs

def format_outputs(pattern: str, inputs: dict) -> dict:
    """Format output file paths based on the given pattern and input metadata."""
    if pattern is None:
        return {}
    config.log(f"Formatting output pattern '{pattern}'")
    # Check output pattern for basic validity
    if len(inputs) > 1 and '{name}' not in pattern:
        print(f"Output pattern '{pattern}' must include '{{name}}' when fixing multiple inputs.")
        sys.exit(1)
    if not pattern.lower().endswith('.json'):
        pattern += '.json'
    try:
        pattern.format(dir='d', name='n', namespace='ns')
    except KeyError as e:
        key = str(e).strip("'")
        print(f"Output pattern '{pattern}' contains unknown substitution '{{{key}}}'")
        sys.exit(1)
    outputs = {}
    paths = set()
    namespaces = set()
    directories = set()
    cwd = os.getcwd()
    for source, data in inputs.items():
        # Format the output path using the pattern and metadata
        name = data['name']
        namespace = data['namespace']
        is_file = os.path.isfile(source)
        directory = os.path.dirname(source) if is_file else cwd
        namespaces.add(namespace)
        directories.add(directory)
        output = pattern.format(dir=directory, name=name, namespace=namespace)
        # Check for collisions
        if output in paths:
            reqs = []
            if len(namespaces) > 1 and '{namespace}' not in pattern:
                reqs.append('{namespace}')
            if len(directories) > 1 and '{dir}' not in pattern:
                reqs.append('{dir}')
            req_str = " or ".join(reqs)
            print(f"Output pattern '{pattern}' should contain {req_str} to avoid collisions")
            sys.exit(1)
        # Add output to the dictionary and mark the path and DID as used
        outputs[source] = output
        paths.add(output)
    return outputs

def diff(old: dict|None, new: dict) -> dict:
    """Compare two dictionaries and return the differences."""
    if old is None:
        return {k: (None, v) for k, v in new.items()}
    changes = {}
    for key, value in new.items():
        if key not in old:
            changes[key] = (None, value)
        elif isinstance(value, dict):
            sub_changes = diff(old[key], value)
            if sub_changes:
                changes[key] = sub_changes
        elif old[key] != value:
            changes[key] = (old[key], value)
    for key, value in old.items():
        if key not in new:
            changes[key] = (value, None)
    return changes

def write(destination: str, data: dict, force: bool = False):
    """Write metadata to a JSON file."""
    # Get JSON-serializable output with no null values
    output = {k: v for k, v in data.items() if k != 'metadata'}
    output['metadata'] = data['metadata'].output
    # Check if the output file already exists
    if os.path.exists(destination):
        # If the existing file is identical to the new output, skip writing
        if diffs := diff(load_json(destination), output):
            diff_str = json.dumps(diffs, indent=2)
            config.log(f"Output {destination} already exists, but differs: {diff_str}")
        else:
            print(f"Output {destination} already exists and is identical, skipping write")
            return
        # If force is false, prompt the user to confirm overwriting the existing file
        if not force:
            go = input(f"Output {destination} already exists, overwrite? (yes/no): ")
            if go.lower() not in ("yes", "y"):
                print("Skipping write")
                return
        print(f"Overwriting existing file {destination}")
    else:
        # Create the output directory if it doesn't exist
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        print(f"Writing fixed metadata to {destination}")
    with open(destination, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)

def main():
    """Main function to run the MetaCatch utility."""
    parser = get_parser()
    args = parser.parse_args()
    config.set_verbosity(args.quiet, args.debug)
    config.log(f"Command line arguments: {args}")
    # Process user defaults and overrides
    defaults = read_json(args.default)
    overrides = read_json(args.override)
    if defaults:
        config.log(f"Defaults: {json.dumps(defaults, indent=2)}")
    if overrides:
        config.log(f"Overrides: {json.dumps(overrides, indent=2)}")
    if errors := validation.validate_defaults(defaults, overrides):
        severity = errors[0][0]
        config.log("Errors found in user defaults and overrides:", severity)
        for sev, message in errors:
            config.log(message, sev)
        if severity >= config.VERBOSITY:
            sys.exit(1)
    # Get inputs and outputs
    inputs = read_inputs(args.input)
    outputs = format_outputs(args.fix, inputs)
    merge = args.merge
    fix = bool(outputs) or bool(merge)

    # Process input files
    max_severity = ES.NONE
    for name, data in inputs.items():
        config.log(f"Procesing input {name}:")
        errors = validation.validate_file(data, fix, defaults=defaults, overrides=overrides)
        severity = errors[0][0] if errors else ES.NONE
        max_severity = max(max_severity, severity)
        # If we are merging then skip individual reports unless there are critical errors
        if severity != ES.CRITICAL and merge and not outputs:
            continue
        # Print validation errors
        msg = VALIDATION_STATUS[severity]
        if severity < config.VERBOSITY:
            print(f"File {name} {msg}!")
        else:
            print(f"File {name} {msg}:")
            for sev, message in errors:
                if sev < config.VERBOSITY:
                    break
                config.log(message, sev)
        # Save fixed metadata
        if outputs and severity != ES.CRITICAL:
            write(outputs[name], data, force=args.force)

    # Merge metadata if requested
    if merge:
        if max_severity == ES.CRITICAL:
            config.log("Skipping merge due to critical errors in input files!", ES.CRITICAL)
            sys.exit(1)
        if not merge.lower().endswith('.json'):
            merge += '.json'
        basename = os.path.basename(merge)[:-5]
        if not basename:
            config.log(f"Invalid merge output base name: {basename}", ES.CRITICAL)
            sys.exit(1)
        config.log(f"Merging metadata from {len(inputs)} input files into {basename}")
        ordered_inputs = sorted(inputs.values(), key=lambda d: d['name'])
        # Do the merge and report any errors
        merged_file, errors = validation.merge_files(ordered_inputs, basename)
        severity = errors[0][0] if errors else ES.NONE
        msg = VALIDATION_STATUS[severity]
        if severity < config.VERBOSITY:
            print(f"Merged file {merge} {msg}!")
        else:
            print(f"File {merge} {msg}:")
            for sev, message in errors:
                if sev < config.VERBOSITY:
                    break
                config.log(message, sev)
        # Save fixed metadata
        if severity != ES.CRITICAL:
            write(merge, merged_file, force=args.force)
