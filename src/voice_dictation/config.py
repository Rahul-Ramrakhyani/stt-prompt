"""Configuration management for STT Prompt"""

import json
import platform
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

# Config directory
if IS_WINDOWS:
    CONFIG_DIR = Path.home() / "AppData" / "Local" / "stt-prompt"
elif IS_MACOS:
    CONFIG_DIR = Path.home() / "Library" / "Application Support" / "stt-prompt"
else:
    CONFIG_DIR = Path.home() / ".config" / "stt-prompt"

CONFIG_FILE = CONFIG_DIR / "config.json"
LOCK_FILE = CONFIG_DIR / "service.lock"

# Default hotkey
DEFAULT_HOTKEY = {
    "modifiers": ["ctrl", "shift"],
    "key": "r",  # R for Record
    "display": "Ctrl+Shift+R"
}

# Available modifier keys
MODIFIERS = ["ctrl", "alt", "shift", "win"]

# Common key choices for users
KEY_CHOICES = [
    ("`", "` (Backtick - above Tab)"),
    ("f9", "F9"),
    ("f10", "F10"),
    ("f11", "F11"),
    ("f12", "F12"),
    ("/", "/ (Slash)"),
    ("\\", "\\ (Backslash)"),
    (";", "; (Semicolon)"),
    ("'", "' (Quote)"),
]


def get_config_dir():
    """Get/create config directory"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Restrict directory permissions on Unix (owner-only access)
    if not IS_WINDOWS:
        try:
            CONFIG_DIR.chmod(0o700)
        except OSError:
            pass
    return CONFIG_DIR


def load_config():
    """Load configuration from file"""
    get_config_dir()
    if CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError, OSError):
            pass  # Return empty config on any read error
    return {}


def save_config(config):
    """Save configuration to file"""
    get_config_dir()
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(config, indent=2, fp=f)


def get_hotkey():
    """Get configured hotkey or default"""
    config = load_config()
    return config.get("hotkey", DEFAULT_HOTKEY)


def set_hotkey(modifiers, key):
    """Set hotkey configuration"""
    display = "+".join([m.capitalize() for m in modifiers] + [key.upper() if len(key) > 1 else key])
    hotkey = {
        "modifiers": modifiers,
        "key": key,
        "display": display
    }
    config = load_config()
    config["hotkey"] = hotkey
    save_config(config)
    return hotkey


def get_hotkey_display():
    """Get human-readable hotkey string"""
    return get_hotkey().get("display", DEFAULT_HOTKEY["display"])


# Windows virtual key codes
VK_CODES = {
    "`": 0xC0, "~": 0xC0,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "/": 0xBF, "\\": 0xDC, ";": 0xBA, "'": 0xDE,
    "[": 0xDB, "]": 0xDD, ",": 0xBC, ".": 0xBE,
    "-": 0xBD, "=": 0xBB,
}

# Add letter keys
for i, c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    VK_CODES[c] = 0x41 + i

# Add number keys
for i in range(10):
    VK_CODES[str(i)] = 0x30 + i


def get_vk_code(key):
    """Get Windows virtual key code for a key"""
    return VK_CODES.get(key.lower(), 0)


# Windows modifier flags
MOD_FLAGS = {
    "alt": 0x0001,
    "ctrl": 0x0002,
    "shift": 0x0004,
    "win": 0x0008,
}


def get_mod_flags(modifiers):
    """Get Windows modifier flags for a list of modifiers"""
    flags = 0x4000  # MOD_NOREPEAT
    for mod in modifiers:
        flags |= MOD_FLAGS.get(mod.lower(), 0)
    return flags
