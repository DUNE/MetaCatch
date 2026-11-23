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
