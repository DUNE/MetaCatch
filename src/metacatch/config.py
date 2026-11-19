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
    VAL_CHECK       = enum.auto()
    VAL_DESC        = enum.auto()
    USR_DEFAULT     = enum.auto()
    USR_OVERRIDE    = enum.auto()
    USR_DELETED     = enum.auto()
    MRG_CONFLICT    = enum.auto()
    MRG_MISSING     = enum.auto()
    MRG_ORDERED     = enum.auto()
    MRG_DELETED     = enum.auto()
    MRG_SUBSET      = enum.auto()

    # Error groups for convenience
    @classmethod
    def init(cls):
        """Build composit error flags for common error groups"""
        cls.CRITICAL =  cls.MRG_CONFLICT
        cls.WARNING =   cls.KEY_DEPRECATED | cls.VAL_DEPRECATED | cls.MRG_ORDERED
        cls.INFO =      cls.KEY_DESC | cls.VAL_DESC | cls.VAL_CONVERTED
        cls.ERROR =     ~(cls.CRITICAL | cls.WARNING | cls.INFO)
        cls.DELETED =   cls.KEY_RETIRED | cls.USR_DELETED | cls.MRG_DELETED
        cls.UNFIXABLE = cls.KEY_UNKNOWN | cls.VAL_CHECK
        cls.KEY_ERRORS = cls(sum(f.value for f in cls if (n := f.name) and n.startswith("KEY_")))
        cls.VAL_ERRORS = cls(sum(f.value for f in cls if (n := f.name) and n.startswith("VAL_")))
        cls.USR_ERRORS = cls(sum(f.value for f in cls if (n := f.name) and n.startswith("USR_")))
        cls.MRG_ERRORS = cls(sum(f.value for f in cls if (n := f.name) and n.startswith("MRG_")))

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
    # Run the validation error test
    ValidationError.init()
    # Read the settings from the yaml file
    settings = read("settings.yaml")
    # Update the settings
    edit_distance.update(settings.pop("edit_distance"))
    set_char_substitutions(settings.pop("allowed_key_characters"))
    misc.update(settings.pop("misc"))
    # Warn about any unused settings
    if settings:
        print(f"Warning: unused settings in config file: {settings.keys()}")

load()
