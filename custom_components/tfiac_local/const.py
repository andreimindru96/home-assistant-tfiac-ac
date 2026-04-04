"""Constants for the local TFIAC integration."""

DOMAIN = "tfiac_local"
DEFAULT_NAME = "TFIAC AC"
DEFAULT_PORT = 7777
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_DISPLAY_UNIT = "C"
DEFAULT_PROTOCOL_UNIT = "F"
DEFAULT_TIMEOUT = 5.0

CONF_DISPLAY_UNIT = "temperature_unit"
CONF_PROTOCOL_UNIT = "protocol_temperature_unit"
CONF_TIMEOUT = "timeout"

PROTOCOL_TO_HVAC_STR = {
    "cool": "cool",
    "heat": "heat",
    "dehumi": "dry",
    "fan": "fan_only",
    "selfFeel": "auto",
}

HVAC_STR_TO_PROTOCOL = {value: key for key, value in PROTOCOL_TO_HVAC_STR.items()}

FAN_MODES = ["Auto", "Low", "Middle", "High"]
SWING_MODES = ["Off", "Vertical", "Horizontal", "Both"]
