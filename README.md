# MetaCatch
Utilities for catching errors in DUNE metadata

I will be copying over my metadata error checking code from Merge-Utils, and then expanding this to be a more general metadata checking tool.  We might also try to roll in some scripts for generating metadata later.

To begin with, I would like some input on the metadata specification defined in config/keys.yaml.  In particular, I need help with:
  1. Reviewing my preliminary lists of good options, deprecated options, and fixes for invalid options
  2. Adding human-readable descriptions for non-obvious options
  3. Defining the conditions under which various keys are required in the metadata (e.g. "core.file_type == 'mc'")
  4. Adding additional keys that I don't have any rules for yet

In the Merge-Utils error checking any unrecognized keys were treated as valid, but if we can put together a reasonably comprehensive specification I'd like to change it to warn about unknown keys instead.  Presumably the server-side validation would accept things like unknown keys or options I've marked as deprecated, but I think it will be better for this client-side checker to be more strict and give warnings about anything that seems irregular.  Users can always ignore the warnings if they're sure they know better, but that way they'll at least stop and check that they didn't make a typo or something.

Something else to consider is whether we should have cross-checks between different keys.  Steven Timm mentioned comparing core.run_type with the namespace, and there are other combinations that are obviously incorrect such as core.data_tier = raw combined with core.file_format = artroot.  I could see this getting pretty complicated so it won't be in the first version, but it might be something to add down the line.

Copyright © 2025 FERMI NATIONAL ACCELERATOR LABORATORY

This repository, and all software contained within, is licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Copyright is granted to FERMI NATIONAL ACCELERATOR LABORATORY on behalf of the Deep Underground Neutrino Experiment (DUNE). Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.
