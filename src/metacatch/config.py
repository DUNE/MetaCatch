"""Functions to load and keep track of configuration settings"""

import enum
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

error_messages = {}
def set_error_messages(cat: str, settings: dict):
    """Build the error messages dictionary"""
    error_messages[cat] = (messages := {})
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
            messages[sev].append((ValidationError.group(flag), msg))

def error_message(cat: str, severity: "ErrorSeverity", flags: "ValidationError") -> tuple:
    """Return the error message for a given category, severity, and flags"""
    if cat not in error_messages:
        raise ValueError(f"Unknown error category: {cat}")
    messages = error_messages[cat]
    if severity not in messages:
        raise ValueError(f"{cat}_ERRORS unhandled severity: {severity}")
    for flag, msg in messages[severity]:
        if (flags & flag) == flag:
            return severity, msg
    return ErrorSeverity.CRITICAL, messages[None]

class ErrorSeverity(enum.IntEnum):
    """Enum for the severity of a metadata validation error"""
    NONE = 0
    INFO = 1
    WARNING = 2
    FIX = 3
    ERROR = 4
    CRITICAL = 5

class ValidationError(enum.Flag):
    """Enumeration of possible validation error flags"""
    KEY_ILLEGAL     = enum.auto()
    KEY_INVALID     = enum.auto()
    KEY_DEPRECATED  = enum.auto()
    KEY_RETIRED     = enum.auto()
    KEY_UNKNOWN     = enum.auto()
    KEY_REPLACED    = enum.auto()
    KEY_REDUNDANT   = enum.auto()
    KEY_CONFLICT    = enum.auto()
    KEY_REQUIRED    = enum.auto()
    KEY_UNSPECIFIED = enum.auto()
    KEY_DESC        = enum.auto()
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
    USR_DEFAULT     = enum.auto()
    USR_OVERRIDE    = enum.auto()
    USR_DELETED     = enum.auto()
    MRG_CONFLICT    = enum.auto()
    MRG_MISSING     = enum.auto()
    MRG_ORDERED     = enum.auto()
    MRG_DELETED     = enum.auto()
    MRG_SUBSET      = enum.auto()
    MRG_MODIFIED    = enum.auto()

    # Error groups for convenience
    @classmethod
    def group(cls, flags: str) -> "ValidationError":
        """Return a composite error flag for a group of flags"""
        return cls(sum(cls[f].value for f in flags.split("|")))

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

VERBOSITY: ErrorSeverity = ErrorSeverity.INFO
def set_verbosity(queitness: int, debug: bool):
    """Set the verbosity level based on the quietness and debug flags"""
    global VERBOSITY, DEBUG #pylint: disable=global-statement
    DEBUG = debug
    VERBOSITY = ErrorSeverity(min(ErrorSeverity.CRITICAL.value, queitness+1))
    if debug:
        print(f"DEBUG = {DEBUG}, VERBOSITY = {VERBOSITY.name}")

def log(message: str, severity: ErrorSeverity|None = None):
    """Log a message if the severity is above the current verbosity level"""
    if severity is None:
        if DEBUG:
            print(f"DEBUG:    {message}")
    elif severity >= VERBOSITY:
        print(f"{severity.name+':':<9} {message}")

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
    ValidationError.init(settings.pop("error_groups"))
    # Load error messages
    set_error_messages("MRG", settings.pop("mrg_error_messages"))
    set_error_messages("USR", settings.pop("usr_error_messages"))
    set_error_messages("KEY", settings.pop("key_error_messages"))
    set_error_messages("VAL", settings.pop("val_error_messages"))
    # Update key matching settings
    edit_distance.update(settings.pop("edit_distance"))
    set_char_substitutions(settings.pop("allowed_key_characters"))
    # Update other miscellaneous settings
    misc.update(settings.pop("misc"))
    # Warn about any unused settings
    if settings:
        print(f"Warning: unused settings in config file: {settings.keys()}")

load()
