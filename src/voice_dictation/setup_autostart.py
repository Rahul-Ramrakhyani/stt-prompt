"""Setup STT Prompt hotkey for all platforms - no manual configuration needed"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from .config import (
    get_hotkey, set_hotkey, get_hotkey_display,
    MODIFIERS, KEY_CHOICES, DEFAULT_HOTKEY
)

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

APP_NAME = "stt-prompt"


def parse_gsettings_list(s):
    """Safer alternative to eval() for gsettings @as [] format"""
    s = s.strip()
    if s == "@as []" or s == "[]":
        return []
    if s.startswith("@as "):
        s = s[4:]
    # Basic parsing: remove brackets and quotes, split by comma
    s = s.strip("[]")
    if not s:
        return []
    # Handle single quotes and double quotes
    items = []
    for item in s.split(","):
        item = item.strip()
        if (item.startswith("'") and item.endswith("'")) or (item.startswith('"') and item.endswith('"')):
            items.append(item[1:-1])
        else:
            items.append(item)
    return items


def get_python_executable():
    """Get pythonw.exe (hidden) on Windows, python3 elsewhere"""
    if IS_WINDOWS:
        python_dir = Path(sys.executable).parent
        pythonw = python_dir / "pythonw.exe"
        if pythonw.exists():
            return str(pythonw)
    return sys.executable


def get_dictate_script():
    """Get path to dictate executable"""
    if IS_WINDOWS:
        scripts_dir = Path(sys.executable).parent / "Scripts"
        dictate_exe = scripts_dir / "dictate.exe"
        if dictate_exe.exists():
            return str(dictate_exe)
    else:
        dictate_path = shutil.which("dictate")
        if dictate_path:
            return dictate_path
    return None


def get_one_shot_command():
    """Get the command to run dictate in one-shot mode"""
    dictate_path = get_dictate_script()
    if dictate_path:
        return f'"{dictate_path}" --one-shot'
    else:
        python = get_python_executable()
        return f'"{python}" -m voice_dictation.cli --one-shot'


# ============== WINDOWS ==============

def setup_windows():
    """Setup hotkey on Windows using RegisterHotKey API (reliable, immediate)"""

    # Create startup script that runs the hotkey service
    startup_dir = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    startup_dir.mkdir(parents=True, exist_ok=True)
    vbs_path = startup_dir / "stt-prompt.vbs"

    pythonw = get_python_executable()

    # VBS script to run hotkey service hidden
    vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """{pythonw}"" -m voice_dictation.hotkey_service --background", 0, False
'''

    try:
        vbs_path.write_text(vbs_content)
        print(f"Created startup script: {vbs_path}")
        print("Hotkey service will start automatically on login.")
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


def start_hotkey_service():
    """Start the hotkey service now (in background)"""
    pythonw = get_python_executable()
    subprocess.Popen(
        [pythonw, "-m", "voice_dictation.hotkey_service", "--background"],
        creationflags=0x08000000  # CREATE_NO_WINDOW
    )
    print("Hotkey service started!")


def stop_hotkey_service():
    """Stop running hotkey service"""
    try:
        # Use PowerShell to find and kill processes running hotkey_service (Windows)
        subprocess.run(
            ['powershell', '-Command', "Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*hotkey_service*' } | Stop-Process -Force"],
            capture_output=True
        )
    except (subprocess.SubprocessError, OSError):
        pass  # Service may not be running or PowerShell failed


def remove_windows():
    """Remove Windows setup"""
    removed = False

    # Stop running hotkey service (targeted, not all pythonw)
    stop_hotkey_service()

    # Remove Start Menu shortcut
    start_menu = Path(os.environ.get('APPDATA', '')) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    shortcut_path = start_menu / "STT Prompt.lnk"
    if shortcut_path.exists():
        shortcut_path.unlink()
        print(f"Removed: {shortcut_path}")
        removed = True

    # Remove startup VBS
    startup_dir = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    vbs_path = startup_dir / "stt-prompt.vbs"
    if vbs_path.exists():
        vbs_path.unlink()
        print(f"Removed: {vbs_path}")
        removed = True

    if not removed:
        print("Nothing to remove")
    return True


# ============== MACOS ==============
# Creates Automator Quick Action + assigns keyboard shortcut

def setup_macos():
    """Setup hotkey on macOS using Automator service"""

    # Create the Automator workflow directory
    services_dir = Path.home() / "Library" / "Services"
    services_dir.mkdir(parents=True, exist_ok=True)

    workflow_dir = services_dir / "STT Prompt.workflow"
    contents_dir = workflow_dir / "Contents"
    contents_dir.mkdir(parents=True, exist_ok=True)

    dictate_cmd = get_one_shot_command()

    # Create Info.plist
    info_plist = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>NSServices</key>
    <array>
        <dict>
            <key>NSMenuItem</key>
            <dict>
                <key>default</key>
                <string>STT Prompt</string>
            </dict>
            <key>NSMessage</key>
            <string>runWorkflowAsService</string>
            <key>NSRequiredContext</key>
            <dict/>
            <key>NSSendTypes</key>
            <array/>
            <key>NSReturnTypes</key>
            <array/>
        </dict>
    </array>
</dict>
</plist>
'''
    (contents_dir / "Info.plist").write_text(info_plist)

    # Create document.wflow (the actual workflow)
    document_wflow = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>AMApplicationBuild</key>
    <string>523</string>
    <key>AMApplicationVersion</key>
    <string>2.10</string>
    <key>AMDocumentVersion</key>
    <string>2</string>
    <key>actions</key>
    <array>
        <dict>
            <key>action</key>
            <dict>
                <key>AMAccepts</key>
                <dict>
                    <key>Container</key>
                    <string>List</string>
                    <key>Optional</key>
                    <true/>
                    <key>Types</key>
                    <array>
                        <string>com.apple.cocoa.string</string>
                    </array>
                </dict>
                <key>AMActionVersion</key>
                <string>2.0.3</string>
                <key>AMApplication</key>
                <array>
                    <string>Automator</string>
                </array>
                <key>AMCategory</key>
                <string>AMCategoryUtilities</string>
                <key>AMIconName</key>
                <string>Run Shell Script</string>
                <key>AMName</key>
                <string>Run Shell Script</string>
                <key>AMProvides</key>
                <dict>
                    <key>Container</key>
                    <string>List</string>
                    <key>Types</key>
                    <array>
                        <string>com.apple.cocoa.string</string>
                    </array>
                </dict>
                <key>AMRequiredResources</key>
                <array/>
                <key>ActionBundlePath</key>
                <string>/System/Library/Automator/Run Shell Script.action</string>
                <key>ActionName</key>
                <string>Run Shell Script</string>
                <key>ActionParameters</key>
                <dict>
                    <key>COMMAND_STRING</key>
                    <string>{dictate_cmd}</string>
                    <key>CheckedForUserDefaultShell</key>
                    <true/>
                    <key>inputMethod</key>
                    <integer>1</integer>
                    <key>shell</key>
                    <string>/bin/zsh</string>
                    <key>source</key>
                    <string></string>
                </dict>
                <key>BundleIdentifier</key>
                <string>com.apple.RunShellScript</string>
                <key>CFBundleVersion</key>
                <string>2.0.3</string>
                <key>CanShowSelectedItemsWhenRun</key>
                <false/>
                <key>CanShowWhenRun</key>
                <true/>
                <key>Category</key>
                <array>
                    <string>AMCategoryUtilities</string>
                </array>
                <key>Class Name</key>
                <string>RunShellScriptAction</string>
                <key>InputUUID</key>
                <string>0A0D52E3-B72D-4902-9C27-C4D750C3A8F3</string>
                <key>Keywords</key>
                <array>
                    <string>Shell</string>
                    <string>Script</string>
                    <string>Command</string>
                    <string>Run</string>
                    <string>Unix</string>
                </array>
                <key>OutputUUID</key>
                <string>7B0E847D-6F47-4C40-9F95-7C9F7C9D8F89</string>
                <key>UUID</key>
                <string>E1A60B89-5D46-4B2D-9C1C-3E7D7E8E9F0A</string>
                <key>UnlocalizedApplications</key>
                <array>
                    <string>Automator</string>
                </array>
                <key>arguments</key>
                <dict>
                    <key>0</key>
                    <dict>
                        <key>default value</key>
                        <integer>1</integer>
                        <key>name</key>
                        <string>inputMethod</string>
                        <key>required</key>
                        <string>0</string>
                        <key>type</key>
                        <string>0</string>
                        <key>uuid</key>
                        <string>0</string>
                    </dict>
                    <key>1</key>
                    <dict>
                        <key>default value</key>
                        <string></string>
                        <key>name</key>
                        <string>source</string>
                        <key>required</key>
                        <string>0</string>
                        <key>type</key>
                        <string>0</string>
                        <key>uuid</key>
                        <string>1</string>
                    </dict>
                    <key>2</key>
                    <dict>
                        <key>default value</key>
                        <false/>
                        <key>name</key>
                        <string>CheckedForUserDefaultShell</string>
                        <key>required</key>
                        <string>0</string>
                        <key>type</key>
                        <string>0</string>
                        <key>uuid</key>
                        <string>2</string>
                    </dict>
                    <key>3</key>
                    <dict>
                        <key>default value</key>
                        <string></string>
                        <key>name</key>
                        <string>COMMAND_STRING</string>
                        <key>required</key>
                        <string>0</string>
                        <key>type</key>
                        <string>0</string>
                        <key>uuid</key>
                        <string>3</string>
                    </dict>
                    <key>4</key>
                    <dict>
                        <key>default value</key>
                        <string>/bin/sh</string>
                        <key>name</key>
                        <string>shell</string>
                        <key>required</key>
                        <string>0</string>
                        <key>type</key>
                        <string>0</string>
                        <key>uuid</key>
                        <string>4</string>
                    </dict>
                </dict>
                <key>isViewVisible</key>
                <integer>1</integer>
                <key>location</key>
                <string>309.000000:253.000000</string>
                <key>nibPath</key>
                <string>/System/Library/Automator/Run Shell Script.action/Contents/Resources/Base.lproj/main.nib</string>
            </dict>
            <key>isViewVisible</key>
            <integer>1</integer>
        </dict>
    </array>
    <key>connectors</key>
    <dict/>
    <key>workflowMetaData</key>
    <dict>
        <key>workflowTypeIdentifier</key>
        <string>com.apple.Automator.servicesMenu</string>
    </dict>
</dict>
</plist>
'''
    (contents_dir / "document.wflow").write_text(document_wflow)

    print(f"Created Automator service: {workflow_dir}")

    # Now set the keyboard shortcut using defaults
    # The shortcut is ^$r (Ctrl+Shift+R)
    # ^ = Ctrl, $ = Shift, @ = Cmd, ~ = Option
    try:
        # Set the keyboard shortcut for the service
        subprocess.run([
            "defaults", "write", "pbs", "NSServicesStatus",
            "-dict-add", "(null) - STT Prompt - runWorkflowAsService",
            '{"enabled_context_menu" = 0; "enabled_services_menu" = 1; "key_equivalent" = "^$r";}'
        ], check=True, capture_output=True)

        # Refresh services
        subprocess.run(["/System/Library/CoreServices/pbs", "-update"], capture_output=True)

        print(f"Keyboard shortcut set: {get_hotkey_display()}")
        print("\nIMPORTANT: You may need to:")
        print("1. Go to System Settings > Keyboard > Keyboard Shortcuts > Services")
        print("2. Find 'STT Prompt' under 'General'")
        print(f"3. Enable it and verify the shortcut is {get_hotkey_display()}")

    except Exception as e:
        print(f"Note: Could not auto-set keyboard shortcut: {e}")
        print("\nManual step required:")
        print("1. Go to System Settings > Keyboard > Keyboard Shortcuts > Services")
        print("2. Find 'STT Prompt' under 'General'")
        print(f"3. Click to add shortcut: {get_hotkey_display()}")

    return True


def remove_macos():
    """Remove macOS setup"""
    workflow_dir = Path.home() / "Library" / "Services" / "STT Prompt.workflow"

    if workflow_dir.exists():
        shutil.rmtree(workflow_dir)
        print(f"Removed: {workflow_dir}")
        subprocess.run(["/System/Library/CoreServices/pbs", "-update"], capture_output=True)
        return True
    else:
        print("Nothing to remove")
        return True


# ============== LINUX ==============
# Uses gsettings for GNOME, KDE settings for KDE, or xbindkeys fallback

def detect_linux_desktop():
    """Detect Linux desktop environment"""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    session = os.environ.get("DESKTOP_SESSION", "").lower()

    if "gnome" in desktop or "gnome" in session or "ubuntu" in desktop:
        return "gnome"
    elif "kde" in desktop or "plasma" in desktop or "kde" in session:
        return "kde"
    elif "xfce" in desktop or "xfce" in session:
        return "xfce"
    else:
        return "other"


def setup_linux_gnome():
    """Setup hotkey on GNOME using gsettings"""
    dictate_cmd = get_one_shot_command()

    # Get current custom keybindings
    current = "[]"
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"],
            capture_output=True, text=True, check=True
        )
        current = result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass

    bindings = parse_gsettings_list(current)

    # Add our binding path
    our_path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/stt-prompt/"
    if our_path not in bindings:
        bindings.append(our_path)

    # Update the list
    bindings_str = str(bindings)
    subprocess.run([
        "gsettings", "set", "org.gnome.settings-daemon.plugins.media-keys",
        "custom-keybindings", bindings_str
    ], check=True)

    # Set the keybinding properties
    base = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
    path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/stt-prompt/"

    subprocess.run(["gsettings", "set", f"{base}:{path}", "name", "STT Prompt"], check=True)
    subprocess.run(["gsettings", "set", f"{base}:{path}", "command", dictate_cmd], check=True)
    subprocess.run(["gsettings", "set", f"{base}:{path}", "binding", "<Primary><Shift>r"], check=True)

    print(f"GNOME keyboard shortcut configured: {get_hotkey_display()}")
    return True


def setup_linux_kde():
    """Setup hotkey on KDE using kwriteconfig"""
    dictate_cmd = get_one_shot_command()

    try:
        # Create a .desktop file for the action
        apps_dir = Path.home() / ".local" / "share" / "applications"
        apps_dir.mkdir(parents=True, exist_ok=True)

        desktop_file = apps_dir / "stt-prompt.desktop"
        desktop_content = f"""[Desktop Entry]
Type=Application
Name=STT Prompt
Exec={dictate_cmd}
Icon=audio-input-microphone
Terminal=false
Categories=Utility;
"""
        desktop_file.write_text(desktop_content)

        # Use kwriteconfig6 or kwriteconfig5 to set the shortcut
        kwriteconfig = shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5")
        if not kwriteconfig:
            raise RuntimeError("kwriteconfig (5 or 6) not found")

        subprocess.run([
            kwriteconfig, "--file", "kglobalshortcutsrc",
            "--group", "stt-prompt.desktop",
            "--key", "_launch", "Ctrl+Shift+R,none,STT Prompt"
        ], check=True)

        # Reload KDE shortcuts
        subprocess.run(["qdbus", "org.kde.kglobalaccel", "/kglobalaccel", "reloadConfig"], capture_output=True)

        print(f"KDE keyboard shortcut configured: {get_hotkey_display()}")
        return True
    except Exception as e:
        print(f"KDE setup error: {e}")
        return setup_linux_xbindkeys()


def setup_linux_xfce():
    """Setup hotkey on XFCE"""
    dictate_cmd = get_one_shot_command()

    try:
        subprocess.run([
            "xfconf-query", "-c", "xfce4-keyboard-shortcuts",
            "-p", "/commands/custom/<Primary><Shift>r",
            "-n", "-t", "string", "-s", dictate_cmd
        ], check=True)
        print(f"XFCE keyboard shortcut configured: {get_hotkey_display()}")
        return True
    except Exception as e:
        print(f"XFCE setup error: {e}")
        return setup_linux_xbindkeys()


def setup_linux_xbindkeys():
    """Fallback: Setup using xbindkeys"""
    dictate_cmd = get_one_shot_command()

    xbindkeys_config = Path.home() / ".xbindkeysrc"

    # Read existing config
    if xbindkeys_config.exists():
        content = xbindkeys_config.read_text()
    else:
        content = ""

    # Add our binding if not present
    our_binding = f'''
# STT Prompt
"{dictate_cmd}"
    control+shift + r
'''

    if "STT Prompt" not in content:
        content += our_binding
        xbindkeys_config.write_text(content)

    print(f"Created xbindkeys config: {xbindkeys_config}")
    print("\nTo activate, run: xbindkeys")
    print("To auto-start xbindkeys, add it to your session startup.")

    # Try to restart xbindkeys
    subprocess.run(["pkill", "xbindkeys"], capture_output=True)
    subprocess.Popen(["xbindkeys"], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return True


def setup_linux():
    """Setup hotkey on Linux based on desktop environment"""
    desktop = detect_linux_desktop()
    print(f"Detected desktop environment: {desktop}")

    if desktop == "gnome":
        return setup_linux_gnome()
    elif desktop == "kde":
        return setup_linux_kde()
    elif desktop == "xfce":
        return setup_linux_xfce()
    else:
        print("Unknown desktop environment, using xbindkeys...")
        return setup_linux_xbindkeys()


def remove_linux():
    """Remove Linux setup"""
    removed = False
    desktop = detect_linux_desktop()

    # Remove GNOME shortcut
    if desktop == "gnome":
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"],
                capture_output=True, text=True
            )
            current = result.stdout.strip()
            if "stt-prompt" in current:
                bindings = parse_gsettings_list(current)
                bindings = [b for b in bindings if "stt-prompt" not in b]
                subprocess.run([
                    "gsettings", "set", "org.gnome.settings-daemon.plugins.media-keys",
                    "custom-keybindings", str(bindings)
                ])
                print("Removed GNOME keyboard shortcut")
                removed = True
        except (subprocess.CalledProcessError, SyntaxError, ValueError, OSError):
            pass  # GNOME shortcut may not exist

    # Remove KDE shortcut
    kde_desktop = Path.home() / ".local" / "share" / "applications" / "stt-prompt.desktop"
    if kde_desktop.exists():
        kde_desktop.unlink()
        print(f"Removed: {kde_desktop}")
        removed = True

    # Remove xbindkeys config
    xbindkeys_config = Path.home() / ".xbindkeysrc"
    if xbindkeys_config.exists():
        content = xbindkeys_config.read_text()
        if "STT Prompt" in content:
            lines = content.split('\n')
            new_lines = []
            skip_next = 0
            for line in lines:
                if skip_next > 0:
                    skip_next -= 1
                    continue
                if "STT Prompt" in line:
                    skip_next = 2  # Skip the comment and the next 2 lines
                    continue
                new_lines.append(line)
            xbindkeys_config.write_text('\n'.join(new_lines))
            print("Removed xbindkeys configuration")
            removed = True

    if not removed:
        print("Nothing to remove")
    return True


# ============== HOTKEY CONFIGURATION ==============

def configure_hotkey():
    """Interactive hotkey configuration"""
    print("\n" + "="*50)
    print("HOTKEY CONFIGURATION")
    print("="*50)

    current = get_hotkey()
    print(f"\nCurrent hotkey: {current.get('display', 'Ctrl+Shift+`')}")
    print("\nWould you like to configure a custom hotkey?")
    response = input("Configure custom hotkey? (y/N): ").strip().lower()

    if response != 'y':
        print(f"Keeping current hotkey: {current.get('display')}")
        return current

    # Select modifiers
    print("\n--- SELECT MODIFIERS ---")
    print("Choose modifiers (you can combine multiple):")
    for i, mod in enumerate(MODIFIERS, 1):
        print(f"  {i}. {mod.upper()}")

    print("\nEnter numbers separated by space (e.g., '1 2' for Ctrl+Alt)")
    print("Default: 1 3 (Ctrl+Shift)")
    mod_input = input("Modifiers: ").strip()

    if not mod_input:
        selected_mods = ["ctrl", "shift"]
    else:
        try:
            indices = [int(x) - 1 for x in mod_input.split()]
            selected_mods = [MODIFIERS[i] for i in indices if 0 <= i < len(MODIFIERS)]
            if not selected_mods:
                selected_mods = ["ctrl", "shift"]
        except (ValueError, IndexError):
            print("Invalid input, using default: Ctrl+Shift")
            selected_mods = ["ctrl", "shift"]

    # Select key
    print("\n--- SELECT KEY ---")
    print("Choose a key:")
    for i, (key, desc) in enumerate(KEY_CHOICES, 1):
        print(f"  {i}. {desc}")
    print(f"  {len(KEY_CHOICES) + 1}. Other (type custom key)")

    print(f"\nDefault: 1 (` Backtick)")
    key_input = input("Key: ").strip()

    if not key_input:
        selected_key = "`"
    else:
        try:
            idx = int(key_input) - 1
            if idx == len(KEY_CHOICES):
                custom_key = input("Enter custom key (single character or f1-f12): ").strip().lower()
                selected_key = custom_key if custom_key else "`"
            elif 0 <= idx < len(KEY_CHOICES):
                selected_key = KEY_CHOICES[idx][0]
            else:
                selected_key = "`"
        except ValueError:
            # Maybe they typed the key directly
            selected_key = key_input.lower() if key_input else "`"

    # Save and confirm
    hotkey = set_hotkey(selected_mods, selected_key)
    print(f"\nHotkey configured: {hotkey['display']}")
    return hotkey


# ============== MAIN ==============

def setup():
    """Setup hotkey for current platform"""
    print(f"Setting up STT Prompt hotkey for {platform.system()}...")

    # Configure hotkey first
    hotkey = configure_hotkey()
    hotkey_display = hotkey.get('display', 'Ctrl+Shift+`')

    print(f"\nUsing hotkey: {hotkey_display}")
    print()

    if IS_WINDOWS:
        return setup_windows()
    elif IS_MACOS:
        return setup_macos()
    elif IS_LINUX:
        return setup_linux()
    else:
        print(f"Unsupported platform: {platform.system()}")
        return False


def remove():
    """Remove hotkey setup for current platform"""
    print(f"Removing STT Prompt hotkey for {platform.system()}...")

    if IS_WINDOWS:
        return remove_windows()
    elif IS_MACOS:
        return remove_macos()
    elif IS_LINUX:
        return remove_linux()
    else:
        print(f"Unsupported platform: {platform.system()}")
        return False


def status():
    """Check if hotkey is configured"""
    if IS_WINDOWS:
        start_menu = Path(os.environ.get('APPDATA', '')) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        shortcut_path = start_menu / "STT Prompt.lnk"
        startup_vbs = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "stt-prompt.vbs"
        return shortcut_path.exists() or startup_vbs.exists()
    elif IS_MACOS:
        workflow_dir = Path.home() / "Library" / "Services" / "STT Prompt.workflow"
        return workflow_dir.exists()
    elif IS_LINUX:
        # Check various configs
        xbindkeys = Path.home() / ".xbindkeysrc"
        if xbindkeys.exists() and "STT Prompt" in xbindkeys.read_text():
            return True
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"],
                capture_output=True, text=True
            )
            if "stt-prompt" in result.stdout:
                return True
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            pass
        return False
    return False


def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        prog="dictate-setup",
        description="Setup STT Prompt hotkey - configure your preferred shortcut"
    )
    parser.add_argument(
        "action",
        choices=["install", "uninstall", "status"],
        nargs="?",
        default="install",
        help="Action to perform (default: install)"
    )

    args = parser.parse_args()

    if args.action == "install":
        if status():
            print("STT Prompt hotkey is already configured.")
            response = input("Reinstall? (y/N): ").strip().lower()
            if response != 'y':
                return
            remove()
            print()

        if setup():
            print("\n" + "="*50)
            print("SUCCESS!")
            print("="*50)
            print(f"\nPress {get_hotkey_display()} anytime to start STT Prompt.")

            # Start the hotkey service immediately on Windows
            if IS_WINDOWS:
                print("\nStarting hotkey service...")
                start_hotkey_service()
                print(f"\nHotkey is now active! Press {get_hotkey_display()} to test.")
        else:
            print("\nSetup failed")
            sys.exit(1)

    elif args.action == "uninstall":
        if remove():
            print("\nSTT Prompt hotkey removed")
        else:
            sys.exit(1)

    elif args.action == "status":
        if status():
            print(f"STT Prompt hotkey is configured: {get_hotkey_display()}")
        else:
            print("STT Prompt hotkey is not configured")
            print("Run 'dictate-hotkey-install' to enable")


def install_cmd():
    """CLI entry point for dictate-hotkey-install"""
    if status():
        print("STT Prompt hotkey is already configured.")
        response = input("Reinstall? (y/N): ").strip().lower()
        if response != 'y':
            return
        remove()
        print()

    if setup():
        print("\n" + "="*50)
        print("SUCCESS!")
        print("="*50)
        print(f"\nPress {get_hotkey_display()} anytime to start STT Prompt.")

        if IS_WINDOWS:
            print("\nStarting hotkey service...")
            start_hotkey_service()
            print(f"\nHotkey is now active! Press {get_hotkey_display()} to test.")
    else:
        print("\nSetup failed")
        sys.exit(1)


def status_cmd():
    """CLI entry point for dictate-hotkey-status"""
    if status():
        print(f"STT Prompt hotkey is configured: {get_hotkey_display()}")
    else:
        print("STT Prompt hotkey is not configured")
        print("Run 'dictate-hotkey-install' to enable")


def uninstall_cmd():
    """CLI entry point for dictate-hotkey-uninstall"""
    if remove():
        print("\nSTT Prompt hotkey removed")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
