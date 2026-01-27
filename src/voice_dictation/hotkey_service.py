"""Windows hotkey service - listens for global hotkey and toggles dictation"""

import os
import platform
import subprocess
import sys
from pathlib import Path

# Platform guard - this module only works on Windows
IS_WINDOWS = platform.system() == "Windows"

if not IS_WINDOWS:
    # Provide stub main function for non-Windows platforms
    def main():
        """Non-Windows stub"""
        print("ERROR: The hotkey service is only supported on Windows.")
        print("On macOS, use 'dictate-hotkey-install' which creates an Automator service.")
        print("On Linux, use 'dictate-hotkey-install' which creates a desktop environment shortcut.")
        sys.exit(1)

    if __name__ == "__main__":
        main()
else:
    # Windows-specific imports and code
    import ctypes
    from ctypes import wintypes

    from .config import (
        get_hotkey, get_vk_code, get_mod_flags,
        LOCK_FILE, get_config_dir, CONFIG_DIR
    )

    WM_HOTKEY = 0x0312
    HOTKEY_ID = 1

    # Signal file for stop toggle (inter-process communication)
    STOP_SIGNAL_FILE = CONFIG_DIR / "stop_signal"
    RECORDING_LOCK_FILE = CONFIG_DIR / "recording.lock"

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # Track the active dictation process directly (no file-based race conditions)
    _active_process = None


    class SingleInstance:
        """Ensure only one instance of the service runs"""

        def __init__(self):
            self.lock_file = None
            self.locked = False

        def acquire(self):
            """Try to acquire the lock"""
            get_config_dir()
            try:
                # Try to create/open lock file exclusively
                self.lock_file = open(LOCK_FILE, 'w')
                # On Windows, use msvcrt for file locking
                import msvcrt
                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                self.lock_file.write(str(os.getpid()))
                self.lock_file.flush()
                self.locked = True
                return True
            except (IOError, OSError, BlockingIOError):
                if self.lock_file:
                    self.lock_file.close()
                return False

        def release(self):
            """Release the lock"""
            if self.lock_file and self.locked:
                try:
                    import msvcrt
                    self.lock_file.seek(0)
                    msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    self.lock_file.close()
                    LOCK_FILE.unlink(missing_ok=True)
                except (IOError, OSError):
                    pass  # Lock may already be released


    def is_dictation_running():
        """Check if a dictation process is still alive"""
        # Primary: check tracked process object (race-free)
        global _active_process
        if _active_process is not None:
            if _active_process.poll() is None:
                return True  # Process still running
            _active_process = None  # Process has exited

        # Fallback: check lock file (covers service restart while process alive)
        if RECORDING_LOCK_FILE.exists():
            try:
                content = RECORDING_LOCK_FILE.read_text().strip()
                if not content:
                    return False
                pid = int(content)
                res = subprocess.run(
                    ['tasklist', '/FI', f'PID eq {pid}', '/NH'],
                    capture_output=True, text=True
                )
                if str(pid) in res.stdout:
                    return True
                # Stale lock file — clean it up
                RECORDING_LOCK_FILE.unlink(missing_ok=True)
            except (ValueError, OSError, Exception):
                pass
        return False


    def signal_stop():
        """Signal the running dictation instance to stop"""
        get_config_dir()
        try:
            STOP_SIGNAL_FILE.write_text(str(os.getpid()))
            return True
        except (IOError, OSError, PermissionError):
            return False


    def get_dictate_command():
        """Get the command to run dictate --one-shot"""
        scripts_dir = Path(sys.executable).parent / "Scripts"
        dictate_exe = scripts_dir / "dictate.exe"
        if dictate_exe.exists():
            return [str(dictate_exe), "--one-shot"]
        return [sys.executable, "-m", "voice_dictation.cli", "--one-shot"]


    def run_dictation():
        """Run dictation in one-shot mode"""
        global _active_process
        cmd = get_dictate_command()
        # Run hidden (no console window)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        _active_process = subprocess.Popen(cmd, startupinfo=startupinfo)


    def toggle_dictation():
        """Toggle dictation - if running, stop it; if not, start it"""
        if is_dictation_running():
            print("Dictation is running, signaling stop...")
            signal_stop()
        else:
            print("Starting dictation...")
            run_dictation()


    def hotkey_listener():
        """Register and listen for global hotkey"""
        # Get configured hotkey
        hotkey = get_hotkey()
        key = hotkey.get("key", "r")
        modifiers = hotkey.get("modifiers", ["ctrl", "shift"])
        display = hotkey.get("display", "Ctrl+Shift+R")

        vk_code = get_vk_code(key)
        mod_flags = get_mod_flags(modifiers)

        if vk_code == 0:
            print(f"ERROR: Unknown key '{key}'")
            return False

        # Register hotkey
        if not user32.RegisterHotKey(None, HOTKEY_ID, mod_flags, vk_code):
            print(f"ERROR: Failed to register hotkey {display}.")
            print("It may be in use by another application.")
            print("Run 'dictate-hotkey-install' to choose a different hotkey.")
            return False

        print(f"Hotkey registered: {display}")
        print(f"Press {display} to toggle STT Prompt.")
        print("The service is running. Close this window to stop.\n")

        try:
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    print("Hotkey pressed! Toggling dictation...")
                    toggle_dictation()
        except KeyboardInterrupt:
            pass
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)
            print("Hotkey unregistered.")

        return True


    def main():
        """Main entry point"""
        import argparse
        parser = argparse.ArgumentParser(description="STT Prompt Hotkey Service")
        parser.add_argument("--background", action="store_true", help="Run in background (no console)")
        args = parser.parse_args()

        # Ensure single instance
        lock = SingleInstance()
        if not lock.acquire():
            print("ERROR: Another instance of the hotkey service is already running.")
            print("Kill it first or run 'dictate-hotkey-uninstall' then 'dictate-hotkey-install'.")
            sys.exit(1)

        try:
            if args.background:
                # Hide console window
                kernel32.FreeConsole()

            hotkey_listener()
        finally:
            lock.release()


    if __name__ == "__main__":
        main()
