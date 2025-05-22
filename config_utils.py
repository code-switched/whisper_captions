import yaml
import os

CONFIG_FILE_NAME = "config.yaml"

DEFAULT_CONFIG = {
    "version": "1.0",
    "server": {
        "model": None,
        "backend": None,
        "host": "0.0.0.0",
        "port": 43007,
        "warmup_file": "./jfk.wav",
        "language": "en",
        "vac_enabled": True,
        "vad_enabled": True,
        "min_chunk_size": 0.25,
        "log_level": "INFO"
    },
    "client": {
        "host": "localhost",
        "port": 43007,
        "device_index": None,
        "device_name": None,
        "transcript_filename_base": None
    }
}


def create_default_config():
    """Creates the default config file."""
    print(f"Creating default configuration file: {CONFIG_FILE_NAME}")
    try:
        with open(CONFIG_FILE_NAME, 'w') as f:
            yaml.dump(DEFAULT_CONFIG, f, sort_keys=False)
        print("Default configuration file created successfully.")
    except IOError as e:
        print(f"Error creating default configuration file: {e}")


def save_config(config_data):
    """Saves the given config_data dictionary to the YAML file specified by CONFIG_FILE_NAME.

    Note: In the context of `whisper_online_server.py` and `client_connect.py` 
    (as of their current design), this function is primarily for initial default 
    config creation or for potential external tools. These scripts treat 
    `config.yaml` as read-only during runtime after initial creation.
    """
    try:
        with open(CONFIG_FILE_NAME, 'w') as f:
            yaml.dump(config_data, f, sort_keys=False)
    except IOError as e:
        print(f"Error saving configuration file: {e}")
    except yaml.YAMLError as e:
        print(f"Error while saving YAML configuration: {e}")


def load_config():
    """Loads the configuration from CONFIG_FILE_NAME.

    If the file doesn't exist, it creates a default config file and returns
    DEFAULT_CONFIG.
    Includes error handling for invalid YAML files.
    """
    if not os.path.exists(CONFIG_FILE_NAME):
        print(f"Configuration file {CONFIG_FILE_NAME} not found.")
        create_default_config()
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE_NAME, 'r') as f:
            config_data = yaml.safe_load(f)
            if config_data is None: # Handle empty or invalid YAML
                print(f"Warning: Configuration file {CONFIG_FILE_NAME} is empty or invalid. Using default configuration.")
                return DEFAULT_CONFIG
            return config_data
    except yaml.YAMLError as e:
        print(f"Error parsing YAML configuration file: {e}. Using default configuration.")
        return DEFAULT_CONFIG
    except IOError as e:
        print(f"Error reading configuration file: {e}. Using default configuration.")
        return DEFAULT_CONFIG


def get_config_value(key_path, default_value=None):
    """Retrieves a value from the configuration using a key path.

    Args:
        key_path: A string representing the path to the key (e.g., "server.model").
        default_value: The value to return if the key is not found.

    Returns:
        The value from the configuration or default_value.
    """
    config = load_config()
    keys = key_path.split('.')
    current_level = config
    for key in keys:
        if isinstance(current_level, dict) and key in current_level:
            current_level = current_level[key]
        else:
            return default_value
    return current_level


def update_config_value(key_path, value):
    """Loads the current configuration, updates a specific key, and saves the entire configuration back.

    This function modifies the configuration file by setting the given `value` at
    the specified `key_path`. If intermediate keys in the path do not exist,
    they will be created as dictionaries.

    Args:
        key_path: A string representing the path to the key (e.g., "server.model").
        value: The new value to set for the specified key.

    Note: In the context of `whisper_online_server.py` and `client_connect.py` 
    (as of their current design), this function is not used at runtime to avoid 
    altering `config.yaml` based on interactive session inputs. It's available 
    for other tools or manual scripting.
    """
    config = load_config()
    keys = key_path.split('.')
    current_level = config
    for i, key in enumerate(keys):
        if i == len(keys) - 1:  # Last key in the path
            current_level[key] = value
        else:
            if key not in current_level or not isinstance(current_level[key], dict):
                current_level[key] = {}  # Create intermediate dict if it doesn't exist
            current_level = current_level[key]
    save_config(config)
