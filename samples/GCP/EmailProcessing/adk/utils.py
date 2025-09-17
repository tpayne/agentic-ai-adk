from jproperties import Properties
import re

_config = Properties()
_is_initialized = False

# Application property cache for key value pairs
def load_properties(propFile) -> bool:
    """Loads properties from a file into the global config object."""
    global _config
    try:
        with open(propFile, "rb") as config_file:
            _config.load(config_file, "utf-8")
            print("Properties loaded successfully.")
            return True
    except Exception as err:
        print(f"Error loading properties: {err}")
        return False

def dump_config_contents():
    """Prints all key-value pairs from the global config object."""
    print("--- DUMPING CONFIG CONTENTS ---")
    for key, value in _config.items():
        print(f"{key}: {value.data}")
    print("------------------------------")

# Get getValue
def getValue(
        keyString
) -> str | None:
    """Retrieves a value from the global config object."""
    global _is_initialized
    if not _is_initialized:
        _is_initialized = load_properties("resources/app.properties")
    key = getKey(keyString)
    # Check if the key exists before trying to get data

    value = _config.get(key)
    if value:
        return value.data
    return None

# Get key
def getKey(
        keyString
) -> str:
    """Normalizes a key string."""
    key = re.sub(r'\W+', '', keyString)
    return key