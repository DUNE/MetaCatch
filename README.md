# MetaCatch
Utility for catching errors in DUNE file metadata

## MetaData Specification

MetaCatch includes a fairly comprehensive metadata specification, defined here:
[config/specification.yaml](https://github.com/DUNE/MetaCatch/blob/main/src/metacatch/config/specification.yaml)

However, the specification is far from complete, and we could use help fleshing it out by:
  - Adding definitions for keys that are currently missing them
  - Adding human-readable descriptions for keys and options
  - Flagging deprecated and retired keys and mapping them to appropriate replacements (if any)
  - Reviewing the preliminary categorization of valid, deprecated, and retired options for various keys
  - Reviewing add adding to the system for conditional key requirements and value cross-checks

## Client-Side MetaData Validation

The "metacatch" command will run client-side validation on a list of inputs.  Inputs may be provided as either JSON file paths or existing DIDs to fetch from the MetaCat database.  Text files containing lists of additional inputs may also be provided and will be expanded automatically.

MetaCatch may run in three different modes:
  - By default, MetaCatch will simply report any errors or warnings, and suggest potential fixes if possible.
  - The "--fix [\<pattern\>]" argument will make MetaCatch attempt to automatically fix any problems it detects, outputting the result to JSON files.  The provided pattern will be used to generate appropriate output filenames, and can use {path} to get the path of local input files or {namespace} and {name} to refer to the corresponding field in the file dictionaries.  This may fail for inputs with critical validation errors.
  - The "--merge \<file\> argument will make MetaCatch attempt to merge the metadata from all the input files, applying any fixes in the process.  The output will be written to the specified file, which should be of the form "directory/filename.ext.json" where "filename.ext" is the name of the merged data file.  Again, this may fail if any input files have critical validation errors.

The user may also provide "default" and "override" metadata values, as either JSON files or inline JSON.  The default values will be used to populate any missing metadata keys, while the override values will be set whether or not the key exists in the input.  Overriding a key to null is interpreted as deleting the key.

```
usage: metacatch [options] <input> [<input> ...]

MetaCatch: Utility for catching errors in DUNE file metadata

positional arguments:
  input                 file(s) to validate, as JSON file, DID, or TXT file listing inputs

options:
  -h, --help            show this help message and exit
  -d <file|json>, --default <file|json>
                        defaults for missing metadata keys, as JSON file or inline JSON
  -o <file|json>, --override <file|json>
                        overrides for existing metadata keys, as JSON file or inline JSON
  -f [pattern], --fix [pattern]
                        output fixed metadata, default = "{dir}/{name}.fixed"
  -m <file>, --merge <file>
                        merge input metadata and write output to JSON file
  --force               overwrite existing output files without prompting
  -q, --quiet           suppress output (info -> warnings -> fixes -> non-critical errors)
  --debug               print extra debug information
  --boring              disable colorized output
```

## Server-Side MetaData Validation

The MetaCat server-side validation does not use the MetaCatch metadata specification directly, instead it uses a separate set of validation rules stored in the database.  This means that any updates to the specification need to be manually uploaded to the server to take effect.  

MetaCatch therefore also includes a "metacatch-sync" command, which will check for differences between the client-side and server-side specs and optionally upload any changes to the server.  It can currently run in three different modes:
  - minimal: Only includes required keys, all categories set to unrestricted
  - basic:   Only includes keys with full definitions, all categories set to unrestricted
  - full:    Includes all known keys, categories set to restricted by default

```
usage: metacatch-sync [-h] {minimal,basic,full}

Synchronize the MetaCatch specification with the online MetaCat database

positional arguments:
  {minimal,basic,full}  Synchronization mode (default: minimal)

options:
  -h, --help            show this help message and exit
```

## Legal

Copyright © 2025 FERMI NATIONAL ACCELERATOR LABORATORY

This repository, and all software contained within, is licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Copyright is granted to FERMI NATIONAL ACCELERATOR LABORATORY on behalf of the Deep Underground Neutrino Experiment (DUNE). Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.
