"""Core dictation functionality"""

import io
import json
import logging
import os
import platform
import sys
import threading
import time
import wave
from datetime import datetime
import shutil
from pathlib import Path

import numpy as np
import pyperclip
import pystray
import sounddevice as sd
from curl_cffi import CurlMime, requests
from PIL import Image, ImageDraw
from pynput import keyboard

# Platform detection
IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

# Config directory (cross-platform)
if IS_WINDOWS:
    CONFIG_DIR = Path.home() / "AppData" / "Local" / "stt-prompt"
elif IS_MACOS:
    CONFIG_DIR = Path.home() / "Library" / "Application Support" / "stt-prompt"
else:
    CONFIG_DIR = Path.home() / ".config" / "stt-prompt"

AUTH_FILE = CONFIG_DIR / "auth.json"

# Signal files for toggle (inter-process communication)
STOP_SIGNAL_FILE = CONFIG_DIR / "stop_signal"
RECORDING_LOCK_FILE = CONFIG_DIR / "recording.lock"

TRANSCRIBE_URL = "https://chatgpt.com/backend-api/transcribe"

AUDIO_RATE = 16000
AUDIO_CHANNELS = 1
TRANSCRIBE_TIMEOUT = 60

# Hotkey: Ctrl+Shift+R (toggle) - R for Record
HOTKEY_MODIFIERS = {keyboard.Key.ctrl, keyboard.Key.shift}
HOTKEY_KEY = keyboard.KeyCode.from_char('r')

STATUS_READY = "[Ready]"
STATUS_RECORDING = "[Recording...]"
STATUS_TRANSCRIBING = "[Transcribing...]"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("dictation")


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


def load_auth():
    """Load authentication from config file"""
    # Check multiple locations for backward compatibility
    auth_locations = [
        AUTH_FILE,
        Path(__file__).parent.parent.parent / "auth" / "chatgpt.json",  # Old location (source dir)
    ]

    auth_file = None
    for loc in auth_locations:
        if loc.exists():
            auth_file = loc
            break

    if auth_file is None:
        return None

    try:
        with auth_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        log.error("Failed to read auth file: %s", exc)
        return None

    expires_at = data.get("expiresAt") or data.get("expires")
    if expires_at:
        try:
            if isinstance(expires_at, str):
                expires_at = expires_at.replace("Z", "+00:00")
            exp_dt = datetime.fromisoformat(expires_at)
            # Handle timezone-naive comparison
            now = datetime.now()
            if exp_dt.tzinfo is not None:
                from datetime import timezone
                now = datetime.now(timezone.utc)
            if exp_dt <= now:
                log.error("Token expired (expiresAt=%s).", expires_at)
                return None
        except (ValueError, TypeError):
            log.warning("Invalid expiresAt value; ignoring expiry check.")
    return data


def save_auth(data):
    """Save authentication to config file"""
    get_config_dir()
    with AUTH_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, indent=2, fp=f)
    # Restrict file permissions on Unix (owner read/write only)
    if not IS_WINDOWS:
        try:
            AUTH_FILE.chmod(0o600)
        except OSError:
            pass
    return AUTH_FILE


def create_icon(recording=False):
    """Create system tray icon"""
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = "#e63946" if recording else "#00d4ff"
    draw.ellipse([4, 4, 60, 60], fill=color)
    draw.rectangle([24, 16, 40, 40], fill="white")
    draw.ellipse([20, 12, 44, 28], fill="white")
    if not recording:
        draw.rectangle([30, 42, 34, 52], fill="white")
        draw.rectangle([22, 50, 42, 54], fill="white")
    return img


def transcribe(audio_data, token):
    """Send audio to ChatGPT for transcription"""
    mp = CurlMime()
    mp.addpart(name="file", content_type="audio/wav", filename="audio.wav", data=audio_data)
    mp.addpart(name="model", data=b"whisper-1")

    r = requests.post(
        TRANSCRIBE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Origin": "https://chatgpt.com",
            "Referer": "https://chatgpt.com/",
        },
        multipart=mp,
        timeout=TRANSCRIBE_TIMEOUT,
        impersonate="chrome",
    )

    if not r.ok:
        snippet = (r.text or "").strip()
        if len(snippet) > 200:
            snippet = snippet[:200] + "..."
        raise RuntimeError(f"Transcribe failed ({r.status_code}). {snippet}".strip())
    try:
        payload = r.json()
    except Exception as exc:
        raise RuntimeError(f"Invalid response ({exc})") from exc
    return payload.get("text", "")


class Dictation:
    """Main dictation application"""

    def __init__(self, one_shot=False):
        self.auth = load_auth()
        self.one_shot = one_shot
        self.recording = False
        self.transcribing = False
        self.frames = []
        self.stream = None
        self.icon = None
        self.keyboard_listener = None
        self.current_status = ""
        self.type_lock = threading.RLock()
        self.state_lock = threading.Lock()
        self.frames_lock = threading.Lock()
        self.transcription_done = threading.Event()
        self.stop_requested = threading.Event()
        self.running = True

        # Track pressed modifier keys
        self.pressed_modifiers = set()
        self.last_toggle_time = 0

        if not self.auth or not self.auth.get('accessToken'):
            print("Authorization required. Run: chatgpt-auth")
            raise SystemExit(1)

        if IS_LINUX:
            self._check_linux_dependencies()

        # Check if another instance is already recording
        if self._is_another_instance_running():
            log.warning("Another dictation instance is already recording. Exiting.")
            sys.exit(0)

        # Clean up stale signal files from previous runs
        self._cleanup_signal_files()

    def _is_another_instance_running(self):
        """Check if another recording/transcribing instance is alive"""
        if not RECORDING_LOCK_FILE.exists():
            return False
        try:
            pid = int(RECORDING_LOCK_FILE.read_text().strip())
            if pid == os.getpid():
                return False

            # Check if process exists
            if IS_WINDOWS:
                import subprocess
                res = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'], capture_output=True, text=True)
                return str(pid) in res.stdout
            else:
                os.kill(pid, 0)
                return True
        except (ValueError, OSError, Exception):
            return False

    def _check_linux_dependencies(self):
        """Check for missing system dependencies on Linux"""
        missing = []
        
        # Check for clipboard tool
        has_xclip = shutil.which("xclip")
        has_wlcopy = shutil.which("wl-copy")
        if not has_xclip and not has_wlcopy:
            missing.append("xclip or wl-clipboard (for text input)")
            
        # Check for portaudio (sounddevice dependency)
        # We can try to load sounddevice and see if it fails
        try:
            import sounddevice as sd
            # If we reached here, it's likely okay, but let's be sure
            _ = sd.query_devices()
        except Exception:
            missing.append("libportaudio2 (for microphone access)")
            
        if missing:
            print("\n" + "!" * 50)
            print("MISSING LINUX DEPENDENCIES")
            print("!" * 50)
            print("The following system tools are missing:")
            for item in missing:
                print(f"  - {item}")
            print("\nPlease install them using your package manager, e.g.:")
            print("  sudo apt install libportaudio2 xclip")
            if not has_wlcopy:
                print("  sudo apt install wl-clipboard  # if using Wayland")
            print("!" * 50 + "\n")

    def _type_text_platform(self, text):
        """Platform-specific text input"""
        from pynput.keyboard import Controller, Key
        kb = Controller()

        try:
            # Try clipboard method first (most reliable)
            old_clipboard = None
            try:
                old_clipboard = pyperclip.paste()
            except Exception:
                pass

            pyperclip.copy(text)
            time.sleep(0.05)

            # Platform-specific paste
            if IS_MACOS:
                kb.press(Key.cmd)
                kb.press('v')
                kb.release('v')
                kb.release(Key.cmd)
            elif IS_LINUX:
                # Linux terminals require Ctrl+Shift+V, GUI apps accept both
                kb.press(Key.ctrl)
                kb.press(Key.shift)
                kb.press('v')
                kb.release('v')
                kb.release(Key.shift)
                kb.release(Key.ctrl)
            else:
                # Windows
                kb.press(Key.ctrl)
                kb.press('v')
                kb.release('v')
                kb.release(Key.ctrl)

            time.sleep(0.05)

            # Restore clipboard
            if old_clipboard is not None:
                try:
                    pyperclip.copy(old_clipboard)
                except Exception:
                    pass

        except Exception:
            # Fallback: type character by character
            for char in text:
                try:
                    kb.type(char)
                except Exception:
                    pass

    def type_text(self, text, track_status=True):
        """Type text at cursor position"""
        if not text:
            return
        with self.type_lock:
            try:
                self._type_text_platform(text)
                if track_status:
                    self.current_status = text
            except Exception as exc:
                log.error("Failed to type text: %s", exc)

    def clear_status(self):
        """Delete current status text"""
        with self.type_lock:
            if self.current_status:
                from pynput.keyboard import Controller, Key
                kb = Controller()
                for _ in range(len(self.current_status)):
                    try:
                        kb.press(Key.backspace)
                        kb.release(Key.backspace)
                        time.sleep(0.01)
                    except Exception as exc:
                        log.error("Failed to clear status: %s", exc)
                        break
                time.sleep(0.05)
                self.current_status = ""

    def set_status(self, text):
        """Replace current status text"""
        self.clear_status()
        self.type_text(text, track_status=True)

    def toggle(self):
        """Toggle recording on/off"""
        # Debounce
        now = time.monotonic()
        if now - self.last_toggle_time < 0.3:
            return
        self.last_toggle_time = now

        with self.state_lock:
            if self.recording:
                self.stop()
            else:
                self.start()

    def start(self):
        """Start recording"""
        if self.recording:
            return
        if self.transcribing:
            log.info("Transcription in progress. Please wait.")
            return

        self.recording = True
        with self.frames_lock:
            self.frames = []
        self.stop_requested.clear()
        self.transcription_done.clear()

        if self.icon:
            self.icon.icon = create_icon(True)

        # Create recording lock file to signal we're recording
        try:
            get_config_dir()
            RECORDING_LOCK_FILE.write_text(str(os.getpid()))
        except (IOError, OSError, PermissionError):
            pass  # Non-critical: recording lock file

        try:
            def audio_callback(indata, frames, time_info, status):
                if status:
                    log.warning("Audio status: %s", status)
                if self.recording:
                    with self.frames_lock:
                        self.frames.append(indata.copy())

            self.stream = sd.InputStream(
                samplerate=AUDIO_RATE,
                channels=AUDIO_CHANNELS,
                dtype=np.int16,
                callback=audio_callback,
            )
            self.stream.start()
        except Exception as exc:
            self.recording = False
            if self.icon:
                self.icon.icon = create_icon(False)
            log.error("Failed to access microphone: %s", exc)
            return

        self.set_status(STATUS_RECORDING)

    def _stop_recording(self):
        """Internal: stop the audio stream"""
        if not self.recording:
            return
        self.recording = False
        if self.icon:
            self.icon.icon = create_icon(False)
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as exc:
                log.error("Failed to close audio stream: %s", exc)
            finally:
                self.stream = None

        # In one-shot mode, keep the lock file until quit() so the hotkey
        # service won't launch a duplicate during transcription.
        if not self.one_shot:
            try:
                RECORDING_LOCK_FILE.unlink(missing_ok=True)
            except (IOError, OSError, PermissionError):
                pass

    def stop(self, do_transcribe=True):
        """Stop recording and optionally transcribe"""
        if not self.recording:
            return
        self._stop_recording()

        if self.one_shot:
            self.stop_requested.set()

        if not do_transcribe:
            with self.frames_lock:
                self.frames = []
            self.transcription_done.set()
            return

        self.set_status(STATUS_TRANSCRIBING)

        # Convert frames to bytes
        with self.frames_lock:
            if self.frames:
                audio_array = np.concatenate(self.frames, axis=0)
                frames_bytes = audio_array.tobytes()
            else:
                frames_bytes = b""
            self.frames = []
        self.transcribing = True

        def process(audio_bytes):
            try:
                if not self.running:
                    return
                if not audio_bytes:
                    raise RuntimeError("No audio captured")

                # Create WAV file in memory
                buf = io.BytesIO()
                with wave.open(buf, "wb") as wf:
                    wf.setnchannels(AUDIO_CHANNELS)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(AUDIO_RATE)
                    wf.writeframes(audio_bytes)

                text = transcribe(buf.getvalue(), self.auth["accessToken"])
                if not self.running:
                    return
                self.clear_status()
                if text:
                    self.type_text(text, track_status=False)
                else:
                    self.type_text("(no speech detected)", track_status=False)
            except Exception as exc:
                self.clear_status()
                self.type_text(f"Error: {exc}", track_status=False)
                log.error("Transcription error: %s", exc)
            finally:
                self.current_status = ""
                self.transcribing = False
                log.info("Transcription completed.")
                self.transcription_done.set()

        threading.Thread(target=process, args=(frames_bytes,), daemon=True).start()

    def quit(self):
        """Exit the application"""
        self.running = False
        if self.recording:
            self.stop(do_transcribe=False)
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        if self.icon:
            self.icon.stop()
        # Clean up signal files - FORCE removal of our own lock file
        self._cleanup_signal_files(force_lock=True)

    def _cleanup_signal_files(self, force_lock=False):
        """Clean up signal files"""
        try:
            STOP_SIGNAL_FILE.unlink(missing_ok=True)
        except (IOError, OSError, PermissionError):
            pass
            
        if RECORDING_LOCK_FILE.exists():
            try:
                # Check if the process is actually running
                pid = int(RECORDING_LOCK_FILE.read_text().strip())
                
                # If we are forcing (on exit), or if it's NOT our own lock, we check if it's stale
                if not force_lock and pid == os.getpid():
                    return # Keep it while we are running
                
                # If we are NOT forcing, and it's another process, only delete if it's gone
                if not force_lock:
                    import subprocess
                    if IS_WINDOWS:
                        res = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'], capture_output=True, text=True)
                        if str(pid) in res.stdout:
                            return # Still running
                    else:
                        os.kill(pid, 0)
                        return # Still running
            except (ValueError, OSError, Exception):
                pass

            try:
                RECORDING_LOCK_FILE.unlink(missing_ok=True)
            except (IOError, OSError, PermissionError):
                pass

    def _on_press(self, key):
        """Handle key press"""
        if key in HOTKEY_MODIFIERS:
            self.pressed_modifiers.add(key)
        # Handle left/right variants
        if hasattr(key, 'name'):
            if 'ctrl' in key.name:
                self.pressed_modifiers.add(keyboard.Key.ctrl)
            if 'alt' in key.name:
                self.pressed_modifiers.add(keyboard.Key.alt)
            if 'shift' in key.name:
                self.pressed_modifiers.add(keyboard.Key.shift)

    def _on_release(self, key):
        """Handle key release"""
        # Check if hotkey combo was pressed (Ctrl+Shift+R)
        key_match = False
        if hasattr(key, 'char') and key.char:
            # When Shift is held, 'r' becomes 'R', so check both
            key_match = key.char.lower() == 'r'
        # Also check vk code for 'R' key (0x52) as fallback
        elif hasattr(key, 'vk') and key.vk == 0x52:
            key_match = True

        if key_match and HOTKEY_MODIFIERS.issubset(self.pressed_modifiers):
            self.toggle()

        # Clear modifiers on release - only clear the specific key that was released
        if hasattr(key, 'name'):
            if 'ctrl' in key.name:
                self.pressed_modifiers.discard(keyboard.Key.ctrl)
            if 'shift' in key.name:
                self.pressed_modifiers.discard(keyboard.Key.shift)
            if 'alt' in key.name:
                self.pressed_modifiers.discard(keyboard.Key.alt)
        self.pressed_modifiers.discard(key)

    def _setup_runtime(self):
        """Setup tray icon and keyboard listener"""
        # System tray
        self.icon = pystray.Icon(
            "dictation",
            create_icon(),
            "Dictation (Ctrl+Shift+R)",
            pystray.Menu(
                pystray.MenuItem("Toggle Recording (Ctrl+Shift+R)", lambda: self.toggle(), default=True),
                pystray.MenuItem("Quit", lambda: self.quit()),
            ),
        )

        # Start tray in background
        tray_thread = threading.Thread(target=self.icon.run, daemon=True)
        tray_thread.start()

        print("STT Prompt running")
        print("  Ctrl+Shift+R = Toggle recording")
        print("  System tray icon = Right-click for menu")
        print()

        # Setup keyboard listener - ONLY if NOT in one-shot mode
        # In one-shot mode, the hotkey service handles the hotkey globally.
        # If we run another listener here, we get double-triggering.
        if self.one_shot:
            return True

        try:
            self.keyboard_listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
            )
            self.keyboard_listener.start()
        except Exception as exc:
            log.error("Failed to setup keyboard listener: %s", exc)
            self.quit()
            return False
        return True

    def run(self):
        """Run the main loop (background mode - no status text)"""
        if not self._setup_runtime():
            return
        # Don't type [Ready] in background mode - just wait silently

        while self.running:
            time.sleep(0.1)

    def run_one_shot(self):
        """Run in one-shot mode"""
        if not self._setup_runtime():
            return
        self.set_status(STATUS_READY)
        time.sleep(0.1)
        self.start()

        while self.running and not self.stop_requested.is_set():
            # Check for external stop signal (from hotkey service toggle)
            if STOP_SIGNAL_FILE.exists():
                try:
                    STOP_SIGNAL_FILE.unlink(missing_ok=True)
                except (IOError, OSError, PermissionError):
                    pass  # Non-critical: signal file cleanup
                self.stop_requested.set()
                self.stop()
                break
            time.sleep(0.05)

        if not self.running:
            return

        self.transcription_done.wait()
        self.quit()
