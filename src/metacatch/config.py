"""Functions to load and keep track of configuration settings"""

import re
import copy
import enum
import shutil
from importlib import resources
import yaml # type: ignore pylint: disable=import-error

DEBUG = False
INITIALIZED = False

edit_distance = {}
misc = {}

char_substitutions = {}
def set_char_substitutions(subs: dict):
    """Build the character substitutions dictionary"""
    char_substitutions.clear()
    for key, options in subs.items():
        char_substitutions.update({opt: key for opt in options})

class Color(enum.StrEnum):
    """Enumeration of ANSI color codes for formatting output"""
    # Colors
    BLACK =     "\033[30m"
    RED =       "\033[31m"
    GREEN =     "\033[32m"
    YELLOW =    "\033[33m"
    BLUE =      "\033[34m"
    MAGENTA =   "\033[35m"
    CYAN =      "\033[36m"
    WHITE =     "\033[37m"
    # Styles
    BOLD =      "\033[1m"
    DIM =       "\033[2m"
    ITALIC =    "\033[3m"
    UNDERLINE = "\033[4m"
    STRIKE =    "\033[9m"
    # Reset
    RESET =     "\033[0m"

class ErrorSeverity(enum.IntEnum):
    """Enumeration of possible validation error severities"""
    NONE = 0
    INFO = 1
    WARNING = 2
    FIX = 3
    ERROR = 4
    CRITICAL = 5

    @property
    def color(self) -> str:
        """Return the color code for the severity"""
        return self._colors.get(self, "")

    @classmethod
    def init(cls, settings: dict):
        """Initialize the color codes for each severity from the config"""
        cls._colors = {}
        for sev in cls:
            color_name = settings.pop(sev.name, None)
            if color_name is None:
                cls._colors[sev] = Color.BOLD
                continue
            try:
                color = Color[color_name]
            except KeyError as e:
                raise ValueError(f"Unknown color '{color_name}' for severity {sev.name}") from e
            cls._colors[sev] = Color.BOLD + color
        # Warn about any unused config keys
        if settings:
            raise ValueError(f"Unknown error severity color(s) in config: {settings.keys()}")

ES = ErrorSeverity

class ErrorFlag(enum.Flag):
    """Enumeration of possible validation error flags"""
    NONE            = 0
    # Merging Flags
    MRG_CONFLICT    = enum.auto()
    MRG_MISSING     = enum.auto()
    MRG_DELETED     = enum.auto()
    MRG_SUBSET      = enum.auto()
    MRG_ORDERED     = enum.auto()
    MRG_MODIFIED    = enum.auto()
    # User Flags
    USR_DEFAULT     = enum.auto()
    USR_OVERRIDE    = enum.auto()
    USR_DELETED     = enum.auto()
    # Key Flags
    KEY_ILLEGAL     = enum.auto()
    KEY_INVALID     = enum.auto()
    KEY_DEPRECATED  = enum.auto()
    KEY_RETIRED     = enum.auto()
    KEY_UNKNOWN     = enum.auto()
    KEY_REPLACED    = enum.auto()
    KEY_REDUNDANT   = enum.auto()
    KEY_CONFLICT    = enum.auto()
    KEY_REQUIRED    = enum.auto()
    KEY_SPEC        = enum.auto()
    KEY_DESC        = enum.auto()
    # Value Flags
    VAL_TYPE        = enum.auto()
    VAL_INVALID     = enum.auto()
    VAL_DEPRECATED  = enum.auto()
    VAL_RETIRED     = enum.auto()
    VAL_REPLACED    = enum.auto()
    VAL_CONVERTED   = enum.auto()
    VAL_MIN         = enum.auto()
    VAL_MAX         = enum.auto()
    VAL_PATTERN     = enum.auto()
    VAL_DESC        = enum.auto()

    # Error groups for convenience
    @classmethod
    def group(cls, flags: str|set) -> "ErrorFlag":
        """Return a composite error flag for a group of flags"""
        if not flags:
            return cls(0)
        # String of flags separated by |, e.g. "KEY_ILLEGAL|VAL_INVALID"
        if isinstance(flags, str):
            flags = set(flags.split("|"))
        # Set of flags
        return cls(sum((f if isinstance(f, cls) else cls[f]).value for f in flags))

    @classmethod
    def init(cls, config: dict):
        """Build composit error flags for common error groups"""
        # Group creation helper functions
        def prefix_group(prefix: str):
            """Create a composite error flag for a group of flags with a common prefix"""
            return cls(sum(f.value for f in cls if (n := f.name) and n.startswith(prefix + '_')))
        def config_group(name: str):
            """Create a composite error flag for a group of flags defined in the config"""
            return cls(sum(cls[f].value for f in config.pop(name, [])))
        # Create prefix groups for key, value, user, and merge errors
        cls.KEY_ERRORS  = prefix_group("KEY")
        cls.VAL_ERRORS  = prefix_group("VAL")
        cls.USR_ERRORS  = prefix_group("USR")
        cls.MRG_ERRORS  = prefix_group("MRG")
        # Create composite groups from the config
        cls.CRITICAL    = config_group("CRITICAL")
        cls.WARNING     = config_group("WARNING")
        cls.INFO        = config_group("INFO")
        cls.ERROR       = ~(cls.CRITICAL | cls.WARNING | cls.INFO) # default
        cls.DELETED     = config_group("DELETED")
        cls.UNFIXABLE   = config_group("UNFIXABLE")
        cls.UNAMBIGUOUS = config_group("UNAMBIGUOUS")
        # Warn about any unused config keys
        if config:
            raise ValueError(f"Unknown error group(s) in config: {config.keys()}")
EF = ErrorFlag

class Formatter:
    """Class to format output messages for a metadata key"""

    default_width = 40
    min_element_count = 1
    min_string_width = 5
    colors = {}
    color_substitutions = {
        ("@(", ")@"): ("{files}", "{reset}"),   # File names
        ("<<", ">>"): ("{keys}<", ">{reset}"),  # Key names
        ("#(", ")#"): ("{values}", "{reset}"),  # Values
    }

    @classmethod
    def set_widths(cls, settings: dict):
        """Initialize the formatter width settings from the config"""
        cls.default_width = settings.pop("default_width", cls.default_width)
        cls.min_element_count = settings.pop("min_element_count", cls.min_element_count)
        cls.min_string_width = settings.pop("min_string_width", cls.min_string_width)
        # Warn about any unused config keys
        if settings:
            raise ValueError(f"Unknown width setting(s) in config: {settings.keys()}")

    @classmethod
    def set_colors(cls, settings: dict|None = None):
        """Initialize the formatter color settings from the config"""
        cls.colors = {}
        if not settings:
            return
        for name in ("files", "keys", "values"):
            color_name = settings.pop(name, None)
            if color_name is None:
                cls.colors[name] = ""
                continue
            try:
                color = Color[color_name]
            except KeyError as e:
                raise ValueError(f"Unknown color '{color_name}' for field {name}") from e
            cls.colors[name] = color
        cls.colors["reset"] = Color.RESET

    def __init__(self, keys: list[str]|None = None, vals: list[str]|None = None, **kwargs):
        self.keys = keys or []
        self.vals = vals or []
        self.map = kwargs
        self.field = None
        self.index = None
        self.width_target = None

    @classmethod
    def colorize(cls, string: str, disable = False) -> str:
        """Replace color substitution markers in a string with ANSI codes"""
        disable = disable or not cls.colors
        for (start, end), (start_code, end_code) in cls.color_substitutions.items():
            count_start = string.count(start)
            count_end = string.count(end)
            if count_start != count_end:
                raise ValueError(f"Unmatched format markers: {start} {end} in {string}")
            if count_start == 0:
                continue
            if disable:
                start_sub = start_code.format(files="", keys="", values="", reset="")
                end_sub = end_code.format(files="", keys="", values="", reset="")
            else:
                start_sub = start_code.format_map(cls.colors)
                end_sub = end_code.format_map(cls.colors)
            string = string.replace(start, start_sub).replace(end, end_sub)
        return string

    @classmethod
    def width(cls, width: int|None, offset: int = 0, factor: float = 1.0) -> int:
        """
        Return a valid width for formatting
          - widths >= 0     used as-is
          - widths < 0      subtract from terminal width
          - width == None   uses the default width
        Can also apply an offset and scaling factor to the width, staying >= 0
        """
        if width is None:
            width = cls.default_width
        elif width < 0:
            term_width, _ = shutil.get_terminal_size(fallback=(80, 20))
            width = max(term_width + width + 1, 0)
        return max(int((width + offset) * factor), 0)

    @classmethod
    def str_width(cls, string: str) -> int:
        """Return the width of a string, with modifiers"""
        return len(cls.colorize(string, disable=True))

    @classmethod
    def pad(cls, string: str, width: int) -> str:
        """Pad a string to a given width, accounting for modifiers"""
        return string + " " * max(width - cls.str_width(string), 0)

    @classmethod
    def truncate(cls, vals: list[str], width: int|None = None, min_count: int|None = None) -> str:
        """Truncate a list of strings to fit within a given width, but keep min_count"""
        # Set default values for width and min_count if not provided
        width = cls.width(width)
        min_count = min_count if min_count is not None else cls.min_element_count
        # Get the widths of all the input strings
        widths = [cls.str_width(s) for s in vals]
        # Pop elements until '[' + ', '.join(strings) + ']' fits within the width
        tail = ""
        dropped = 0
        while len(vals) > min_count and sum(widths) + 2*len(vals) + len(tail) > width:
            vals.pop()
            widths.pop()
            dropped += 1
            tail = f", ... (+{dropped})"
        return ", ".join(vals) + tail

    @classmethod
    def filename(cls, filename: str, width: int|None = None) -> str:
        """Format a filename for display"""
        return f"@({cls.fit(filename, cls.width(width, 2))[1:-1]})@"

    @classmethod
    def keyname(cls, key: str) -> str:
        """Format a key name for display"""
        return f"<<{key}>>"

    @classmethod
    def value(cls, val, width: int|None = None) -> str:
        """Format a value for display"""
        return f"#({cls.fit(val, width)})#"

    @classmethod
    def fit(cls, val, width: int|None = None) -> str:
        """Adjust the representation of a value to fit within a given width"""
        width = cls.width(width)
        # For sets & dicts, convert to list and just replace brackets with braces
        if isinstance(val, (set, dict)):
            out = f"#({{{cls.fit(sorted(val), width)[1:-1]}}})#"
        # For tuples, convert to list and just replace brackets with parentheses
        elif isinstance(val, tuple):
            # Pairs are probably k-v pairs, format as "k: v" and truncate the value
            if len(val) == 2:
                el_width = cls.width(width, -2, 0.5) # -2 for ': '
                out = f"{repr(val[0])}: {cls.fit(val[1], el_width)}"
            else:
                out = f"({cls.fit(list(val), width)[1:-1]})"
        # For lists, truncate the list if it exceeds the width
        elif isinstance(val, list):
            # Try to give elements equal fractions of the width, -2 for ', ' and '[]'
            el_width = cls.width(width, -2*len(val), 1/len(val)) if val else width
            strings = [cls.fit(v, el_width) for v in val]
            out = f"[{cls.truncate(strings, width, cls.min_element_count)}]"
        # For strings, cut out the middle but leave min_string_width on each side
        elif isinstance(val, str):
            # If the string is already quoted, trim them so we don't double-quote it
            if val.startswith("'") and val.endswith("'"):
                val = val[1:-1]
            width = max(width, 2*cls.min_string_width + 5) # + 5 for "'...'"
            if cls.str_width(val) > width:
                width = cls.width(width, -5, 0.5) # - 5 for "'...'"
                out = f"'{val[:width]}...{val[-width:]}'"
            else:
                out = repr(val)
        # For other types, just use repr()
        else:
            out = repr(val)
        return out

    @classmethod
    def options(cls, opts: list, width: int|None = None) -> str:
        """Return a string representation of a list of options"""
        if not opts:
            return "no valid matches found!"
        if len(opts) == 1:
            return f"did you mean {repr(opts[0])}?"
        width = cls.width(width, -22) # -22 for "did you mean one of: ?"
        return f"did you mean one of: {cls.truncate(opts, width)}?"

    def format(self, message: str, width: int|None = None) -> str:
        """Format a message by substituting the key information"""
        # If we don't have a width target, just format and return the message
        if width is None:
            return message.format_map(self)
        # First try formatting with the full width, and see if it fits
        width = self.width(width)
        self.width_target = width
        max_out = message.format_map(self)
        max_len = self.str_width(max_out)
        if max_len <= width:
            return self.pad(max_out, width) # Pad to the width if necessary
        # Next, set the width limit to 0 to see if it is even possible to fit
        self.width_target = 0
        min_out = message.format_map(self)
        min_len = self.str_width(min_out)
        if min_len >= width:
            return min_out
        # Otherwise, we have some flexibility to interpolate between these two limits
        max_lim, min_lim = width, 0
        def next_limit() -> int:
            """Interpolate between the min and max limits to get a new width target"""
            lim = (width-min_len) / (max_len-min_len) * (max_lim-min_lim) + min_lim
            return max(min(int(lim), max_lim-1), min_lim+1)
        # Iteratively adjust the width limit to get the best fit
        while True:
            self.width_target = next_limit()
            out = message.format_map(self)
            out_len = self.str_width(out)
            # If we hit the target width exactly, return it
            if out_len == width:
                return out
            # Update the min/max limits as appropriate
            if out_len > width:
                max_lim = self.width_target
                max_len = out_len
                max_out = out
            else:
                min_lim = self.width_target
                min_len = out_len
                min_out = out
            # If the limits are too close together, the shorter output is the best fit
            if max_len - min_len <= 1:
                return self.pad(min_out, width) # Pad to the width if necessary

    def _check_field(self, field: str):
        """Check if the field is valid for this formatter"""
        if field not in ("keys", "vals") and field not in self.map:
            raise KeyError(f"Unknown field {field}")

    def _check_index(self, index: str) -> int:
        """Check if the index is valid for the current field"""
        if self.field not in ("keys", "vals"):
            raise IndexError(f"Field {self.field} cannot take an index")
        return int(index)

    def __getitem__(self, field):
        """Make the ErrorFormatter act like a dict for formatting"""
        # If we don't have a field yet, return a new formatter for the field
        if self.field is None:
            self._check_field(field)
            out = copy.deepcopy(self)
            out.field = field
            return out
        # If we already have a field, try to set the index
        if self.index is None:
            self.index = self._check_index(field)
            return self
        raise IndexError(f"Field {self.field}[{self.index}] cannot take an additional index")

    def __format__(self, fmt: str) -> str:
        """Format the error message for the key"""
        if self.field is None:
            raise KeyError("No field specified!")
        if self.field == "keys":
            return format(self.keyname(self.keys[self.index or 0]), fmt)
        if self.field == "vals":
            width = self.width(self.width_target)
            return format(self.value(self.vals[self.index or 0], width), fmt)
        if self.field in self.map:
            return format(self.map[self.field], fmt)
        return ""

class ErrorMessage:
    """Class to represent an error message with severity and flags"""

    standard_messages = {}

    def __init__(self, sev: ES, flags: EF = EF.NONE, msg: str = "", fmt: Formatter|None = None):
        """Initialize the error message with severity, flags, and message"""
        self.severity = sev
        self.flags = flags
        self.raw = self.raw = re.split(r" {2,}", msg.strip())
        self.out = []
        self.formatter = fmt if fmt is not None else Formatter()

    @classmethod
    def set_messages(cls, cat: str, settings: dict):
        """Build the standard error messages dictionary from the config"""
        cls.standard_messages[cat] = (messages := {})
        if (default := settings.pop(None, None)) is None:
            raise ValueError("Missing default error message in settings")
        messages[None] = default
        for sev, msgs in settings.items():
            sev = ErrorSeverity[sev]
            messages[sev] = []
            for item in msgs:
                if not isinstance(item, dict) or len(item) != 1:
                    raise ValueError("Error messages must be of the form 'FLAG: message'")
                flag, msg = next(iter(item.items()))
                flags = {f if '_' in f else f"{cat}_{f}" for f in flag.split("|")}
                messages[sev].append((EF.group(flags), msg))

    @classmethod
    def get(cls, cat: str, sev: ES, flags: EF, fmt: Formatter|None = None) -> "ErrorMessage":
        """Return the error message for a given category, severity, and flags"""
        messages = cls.standard_messages.get(cat)
        if not messages:
            raise ValueError(f"Unknown error category: {cat}")
        if sev not in messages:
            raise ValueError(f"{cat}_ERRORS unhandled severity: {sev.name}")
        for flag, msg in messages[sev]:
            if (flags & flag) == flag:
                return cls(sev, flags, msg, fmt)
        return cls(ES.CRITICAL, flags, messages[None], fmt)

    @property
    def raw_str(self) -> str:
        """Return the raw message as a single string, joined by double spaces"""
        return "  ".join(self.raw)

    @property
    def remaining(self) -> int:
        """Return the number of unformatted segments remaining"""
        return len(self.raw) - len(self.out)

    def __bool__(self) -> bool:
        """Return True if the error message has a non-zero severity"""
        return self.severity > ES.NONE

    def __str__(self) -> str:
        """Return the formatted error message"""
        if self.out:
            return " ".join(self.out)
        return " ".join(self.formatter.format(segment) for segment in self.raw)

    def __gt__(self, other: "ErrorMessage|ES") -> bool:
        """Compare two error messages by severity and flags"""
        if isinstance(other, ES):
            return self.severity > other
        if not isinstance(other, ErrorMessage):
            return NotImplemented
        # Higher severity beats lower severity
        if self.severity != other.severity:
            return self.severity > other.severity
        # Lower error flags beat higher error flags (so similar messages are grouped together)
        if self.flags != other.flags:
            return self.flags.value < other.flags.value
        # Formatted messages beat unformatted messages
        if (self_rem := self.remaining) != (other_rem := other.remaining):
            return self_rem < other_rem
        # Finally, return strings in alphabetical order
        return str(self) < str(other)

    def __lt__(self, other: "ErrorMessage|ES") -> bool:
        """Compare two error messages by severity and flags"""
        if isinstance(other, ES):
            return self.severity < other
        if not isinstance(other, ErrorMessage):
            return NotImplemented
        # Higher severity beats lower severity
        if self.severity != other.severity:
            return self.severity < other.severity
        # Lower error flags beat higher error flags (so similar messages are grouped together)
        if self.flags != other.flags:
            return self.flags.value > other.flags.value
        # Formatted messages beat unformatted messages
        if (self_rem := self.remaining) != (other_rem := other.remaining):
            return self_rem > other_rem
        # Finally, return strings in reverse alphabetical order
        return str(self) > str(other)

    def format(self, width: int|None = None) -> int:
        """Format the last chunk with the width, and return the length of the next"""
        if len(self.out) == len(self.raw):
            return -1
        idx = len(self.out)
        # Format the last chunk with the given width, if applicable
        if idx > 0:
            self.out[-1] = self.formatter.format(self.raw[idx-1], width)
        # If this isn't the last chunk, just get the default length and adjust later
        if idx < len(self.raw) - 1:
            self.out.append(self.formatter.format(self.raw[idx]))
            return len(self.out[-1])
        # The last chunk should fill the rest of the line, and return -1
        # Current indent is severity(9) + chunk lengths + 1 space per chunk
        indent = 10 + sum(self.formatter.str_width(s) for s in self.out) + len(self.out)
        width = Formatter.width(-indent)
        self.out.append(self.formatter.format(self.raw[-1], width).rstrip())
        return -1

    def reset(self):
        """Reset the formatted message to its original state"""
        self.out.clear()

    def insert_label(self, label: str):
        """Insert a label at the beginning of the second chunk"""
        if len(self.raw) < 2:
            self.raw.append(label)
        else:
            self.raw[1] = f"{label} {self.raw[1][0].lower()}{self.raw[1][1:]}"
        self.reset()

    def log(self):
        """Log the error message"""
        # Make sure the message is formatted
        while self.format() >= 0:
            pass
        log(str(self), self.severity)
EM = ErrorMessage

class ErrorReport:
    """Class to represent a collection of error messages"""
    def __init__(self, name: str = "", merged: bool = False):
        self.name = name
        self.merged = merged
        self.messages: list[EM] = []

    def extend(self, report):
        """Add another report or a raw list of error messages"""
        # If the input is an ErrorReport, just extend the messages list
        if isinstance(report, ErrorReport):
            self.messages.extend(report.messages)
        # If the input is a list of ErrorMessages, add and process them individually
        else:
            for message in report:
                self.add(message)
        # Re-sort the messages
        self.messages.sort(reverse=True)

    def add(self, message: EM):
        """Add an error message to the report, splitting multi-line messages"""
        if not message: # Skip messages with severity NONE
            return
        raw = message.raw_str
        if '\n' in raw:
            sev = message.severity
            flags = message.flags
            fmt = message.formatter
            self.messages.extend(EM(sev, flags, s, fmt) for s in raw.splitlines())
        else:
            self.messages.append(message)

    @property
    def severity(self) -> ES:
        """Return the highest severity of any message in the report"""
        # If there are no messages, return NONE
        if not self.messages:
            return ES.NONE
        # Sort the messages by severity and return the highest severity
        self.messages.sort(reverse=True)
        return self.messages[0].severity

    def format(self):
        """Format all error messages in the report"""
        # Sort the messages and reset their formatting
        self.messages.sort(reverse=True)
        for msg in self.messages:
            msg.reset()
        # Format the messages in chunks, so that they can be aligned
        width = None
        while True:
            width = max(m.format(width) for m in self.messages if m.severity >= VERBOSITY)
            if width < 0:
                break
        # Sort the messages again in case the formatting changed their order
        self.messages.sort(reverse=True)

    def __len__(self) -> int:
        """Return the number of error messages in the report"""
        return len(self.messages)

    def __iter__(self):
        """Return an iterator over the error messages in the report"""
        return iter(self.messages)

    def log(self):
        """Log all error messages in the report"""
        status_messages = {
            ES.NONE:        "passed validation",
            ES.INFO:        "passed validation",
            ES.WARNING:     "passed validation with warnings",
            ES.FIX:         "passed validation after fixes",
            ES.ERROR:       "had non-critical validation errors",
            ES.CRITICAL:    "failed validation with crital errors",
        }
        sev = self.severity
        head = "Merged file " if self.merged else "Input file "
        tail = f" {status_messages[sev]}{'!' if sev < VERBOSITY else ':'}"
        body = Formatter.colorize(Formatter.filename(self.name, -len(head)-len(tail)))
        print(f"{head}{body}{tail}")
        if sev < VERBOSITY:
            return
        self.format()
        for msg in self.messages:
            if msg.severity < VERBOSITY:
                break
            msg.log()
ER = ErrorReport

VERBOSITY: ES = ES.INFO
def set_verbosity(queitness: int, debug: bool, boring: bool):
    """Set the verbosity level based on the quietness and debug flags"""
    global VERBOSITY, DEBUG #pylint: disable=global-statement
    DEBUG = debug
    VERBOSITY = ES(min(ES.CRITICAL.value, queitness+1))
    if debug:
        print(f"{Color.DIM}DEBUG = {DEBUG}, VERBOSITY = {VERBOSITY.name}{Color.RESET}")
    if boring:
        Formatter.set_colors({})
        ES.init({})

def log(message: str, severity: ES = ES.NONE):
    """Log a message if the severity is above the current verbosity level"""
    colorized = Formatter.colorize(message)
    if severity == ES.NONE:
        if DEBUG:
            colorized = message.replace(Color.RESET, Color.RESET + Color.DIM)
            print(f"{Color.DIM}DEBUG:    {colorized}{Color.RESET}")
    elif severity >= VERBOSITY:
        print(f"{severity.color}{severity.name+':':<9}{Color.RESET} {colorized}")

def read(path: str) -> dict:
    """Read a configuration file from the package"""
    pkg_name = __package__
    log(f"Reading configuration file {path} from package {pkg_name}")
    if pkg_name is None:
        raise RuntimeError("Package name is not set!")
    resource = resources.files(pkg_name).joinpath("config", path)
    if not resource.is_file():
        raise FileNotFoundError(f"Resource {path} not found in package {pkg_name}")
    with resource.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

colors = {}
def configure_colors(settings: dict):
    """Configure the color codes for error severities"""
    enabled = settings.pop("enabled", False)
    error_colors = settings.pop("error_severities", {})
    ES.init(error_colors if enabled else {})
    field_colors = settings.pop("fields", {})
    Formatter.set_colors(field_colors if enabled else {})
    # Warn about any unused config keys
    if settings:
        raise ValueError(f"Unknown colorization setting(s) in config: {settings.keys()}")

def load():
    """Load the settings from the config file"""
    # Use a global variable to ensure that the settings are only loaded once
    global INITIALIZED #pylint: disable=global-statement
    if INITIALIZED:
        return
    INITIALIZED = True
    # Read the settings from the yaml file
    settings = read("settings.yaml")
    # Create the error groups from the settings
    EF.init(settings.pop("error_groups"))
    # Load error messages
    EM.set_messages("MRG", settings.pop("mrg_error_messages"))
    EM.set_messages("USR", settings.pop("usr_error_messages"))
    EM.set_messages("KEY", settings.pop("key_error_messages"))
    EM.set_messages("VAL", settings.pop("val_error_messages"))
    # Load formatter settings
    Formatter.set_widths(settings.pop("field_widths"))
    configure_colors(settings.pop("colorization"))
    # Update key matching settings
    edit_distance.update(settings.pop("edit_distance"))
    set_char_substitutions(settings.pop("allowed_key_characters"))
    # Update other miscellaneous settings
    misc.update(settings.pop("misc"))
    # Warn about any unused settings
    if settings:
        print(f"Warning: unused settings in config file: {settings.keys()}")

load()
