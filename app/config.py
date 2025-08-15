import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()


def load_config():
    """Load configuration from YAML file with environment variable overrides."""

    # Get the project root directory
    project_root = Path(__file__).parent.parent
    config_path = project_root / "config.yaml"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found at {config_path}. "
            f"Please copy config.example.yaml to config.yaml and configure it."
        )

    with open(config_path, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    return config


# Load configuration
_config = load_config()

# Telegram Bot Configuration
TELEGRAM_API_TOKEN = os.getenv("TELEGRAM_API_TOKEN") or _config["telegram"]["api_token"]
PEER_ID = os.getenv("PEER_ID") or _config["telegram"]["peer_id"]
REPORT_CHAT_ID = os.getenv("REPORT_CHAT_ID") or _config["telegram"].get(
    "report_chat_id", PEER_ID
)

# Trello Configuration
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY") or _config["trello"]["api_key"]
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN") or _config["trello"]["token"]

# Board IDs to monitor
board_ids = _config["trello"]["board_ids"]

# Mapping Trello usernames to Telegram usernames
trello_to_telegram_users = _config["user_mapping"]["trello_to_telegram"]

# Lists that represent "done" status
done_list_names = _config["lists"]["done_status"]

# Lists that represent "in progress" status
in_progress_list_names = _config["lists"]["in_progress_status"]

# General settings
SET_LOGGING = _config["settings"].get("enable_logging", True)
DELAY = _config["settings"].get("check_delay", 30)  # seconds between checks


# Validation
def validate_config():
    """Validate that all required configuration values are present."""
    required_vars = {
        "TELEGRAM_API_TOKEN": TELEGRAM_API_TOKEN,
        "PEER_ID": PEER_ID,
        "TRELLO_API_KEY": TRELLO_API_KEY,
        "TRELLO_TOKEN": TRELLO_TOKEN,
    }

    missing_vars = [
        name
        for name, value in required_vars.items()
        if not value or value.startswith("YOUR_") or value == "YOUR_CHAT_ID_HERE"
    ]

    if missing_vars:
        raise ValueError(
            f"Missing or invalid configuration values: {', '.join(missing_vars)}. "
            f"Please check your config.yaml file or environment variables."
        )

    if not board_ids:
        raise ValueError(
            "No board IDs configured. Please add at least one board ID to monitor."
        )


# Validate configuration on import
validate_config()
