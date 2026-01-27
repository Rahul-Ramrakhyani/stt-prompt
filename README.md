# STT Prompt

[![PyPI version](https://img.shields.io/pypi/v/stt-prompt)](https://pypi.org/project/stt-prompt/)
[![Python versions](https://img.shields.io/pypi/pyversions/stt-prompt)](https://pypi.org/project/stt-prompt/)
[![License: MIT](https://img.shields.io/pypi/l/stt-prompt)](https://pypi.org/project/stt-prompt/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue)](https://github.com/zunmax/stt-prompt)

**Speak instead of typing!** This tool converts your voice to text and types it wherever your cursor is.

## What Is This?

STT Prompt (Speech-to-Text Prompt) is a simple tool that lets you **use your voice to type text anywhere on your computer**. Just press a hotkey, speak, and your words appear as text.

### Use Cases

- **AI Chatbots** - Dictate prompts to ChatGPT, Claude, Gemini, or any AI assistant
- **Messaging Apps** - Send voice-to-text messages on WhatsApp, Telegram, Discord, Slack
- **Social Media** - Compose posts on X (Twitter), Facebook, LinkedIn
- **Emails** - Write emails in Gmail, Outlook, or any email client
- **Documents** - Dictate into Word, Google Docs, Notion, or any text editor
- **Anywhere** - Works in any app where you can type text

### How It Works

1. Place your cursor in any text input field (chat box, search bar, document, etc.)
2. Press **Ctrl+Shift+R** to start recording
3. Speak naturally
4. Press **Ctrl+Shift+R** again to stop
5. Your speech is converted to text and typed automatically at the cursor

That's it! No copy-pasting needed - text appears right where you're typing.

## Features

- **Works Everywhere** - Any app, any text field, just place your cursor and speak
- **Simple Toggle** - Same hotkey (Ctrl+Shift+R) to start and stop recording
- **Cross-Platform** - Windows, macOS, and Linux (GNOME, KDE, XFCE)
- **Background Service** - Runs silently, always ready when you need it
- **Fast & Accurate** - Uses ChatGPT's Whisper speech recognition

---

## Requirements

- **Python 3.9+** installed on your computer
- **ChatGPT account** (free or paid) - for speech recognition
- **Microphone** - built-in or external

---

## Quick Start (3 Steps)

### Step 1: Install

**Windows:**
```bash
pip install stt-prompt
```

**macOS:**
```bash
pip3 install stt-prompt
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install python3 python3-pip libportaudio2 xclip
pip3 install stt-prompt
```

<details>
<summary>Other Linux distributions</summary>

**Fedora:**
```bash
sudo dnf install python3 python3-pip portaudio xclip
pip3 install stt-prompt
```

**Arch:**
```bash
sudo pacman -S python python-pip portaudio xclip
pip3 install stt-prompt
```
</details>

### Step 2: Authorize with ChatGPT (One-Time)

```bash
chatgpt-auth
```

This opens ChatGPT in your browser. Follow the on-screen instructions to copy your access token.

> **Note:** Tokens expire after ~10 days. Run `chatgpt-auth` again when needed.

### Step 3: Setup Hotkey

```bash
dictate-hotkey-install
```

Done! Now press **Ctrl+Shift+R** anywhere to start STT Prompt.

---

## Platform Notes

### Windows
- Hotkey service runs in background and starts automatically on login
- No additional setup needed

### macOS
- Creates an Automator Quick Action
- **Grant these permissions when prompted:**
  - System Settings > Privacy & Security > Accessibility
  - System Settings > Privacy & Security > Microphone

### Linux
- Auto-detects your desktop environment (GNOME, KDE, XFCE)
- **X11 only** - Hotkey detection (`pynput`) does not work on Wayland. Use X11 or XWayland.
- **System tray** may require extra packages:
  ```bash
  sudo apt install python3-gi gir1.2-appindicator3-0.1  # Ubuntu/Debian
  ```
- **Other desktops:** Falls back to xbindkeys (install: `apt install xbindkeys`)

---

## Authorization Details

The tool uses ChatGPT's speech-to-text service. You need to provide your ChatGPT access token (one-time setup).

**How to get your token:**

1. Run `chatgpt-auth` - it opens https://chatgpt.com
2. Make sure you're **logged in** to ChatGPT
3. Press `F12` to open Developer Tools
4. Click the **Console** tab
5. Paste this code and press Enter:
   ```javascript
   fetch('https://chatgpt.com/api/auth/session').then(r=>r.json()).then(d=>console.log(JSON.stringify({accessToken:d.accessToken,email:d.user?.email,expires:d.expires})))
   ```
6. Copy the JSON output that appears
7. Paste it in the terminal where `chatgpt-auth` is waiting

**Token expires after ~10 days.** When you see "Token expired" error, just run `chatgpt-auth` again.

---

## Commands

| Command | Description |
|---------|-------------|
| `dictate-hotkey-install` | Setup hotkey service |
| `dictate-hotkey-uninstall` | Remove hotkey service |
| `dictate-hotkey-status` | Check if hotkey is configured |
| `chatgpt-auth` | Authorize with ChatGPT |
| `chatgpt-auth-status` | Check authorization status |
| `chatgpt-auth-delete` | Delete authorization / logout |

---

## Troubleshooting

### "Command not found" after installation

If `dictate` or `chatgpt-auth` commands are not found, pip installed them to a directory not in your PATH.

**Quick Fix - Use python -m instead:**
```bash
python -m voice_dictation.cli              # instead of: dictate
python -m voice_dictation.cli --one-shot   # one-shot mode
```

**Permanent Fix - Add to PATH:**

<details>
<summary>Linux/macOS</summary>

Add this line to your `~/.bashrc` or `~/.zshrc`:
```bash
export PATH="$HOME/.local/bin:$PATH"
```
Then reload: `source ~/.bashrc` (or restart terminal)
</details>

<details>
<summary>Windows</summary>

1. Find where pip installed scripts:
   ```powershell
   python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
   ```
2. Add that path to your system PATH environment variable
</details>

---

### Common Issues

| Problem | Solution |
|---------|----------|
| **Hotkey not working (Windows)** | Re-run `dictate-hotkey-install` |
| **Hotkey not working (macOS)** | Grant Accessibility permission in System Settings |
| **Hotkey not working (Linux)** | Run `sudo usermod -aG input $USER`, then log out and back in |
| **Text not pasting (Linux)** | Install clipboard tool: `sudo apt install xclip` |
| **Text not pasting (Wayland)** | Install: `sudo apt install wl-clipboard` |
| **Hotkey not detected (Wayland)** | `pynput` requires X11. Switch to X11 session or use XWayland |
| **No system tray icon (Linux)** | Install: `sudo apt install python3-gi gir1.2-appindicator3-0.1` |
| **"Authorization required"** | Run `chatgpt-auth` to set up your token |
| **"Token expired"** | Run `chatgpt-auth` again (tokens last ~10 days) |
| **Microphone not working** | Check your system microphone permissions |

---

## Uninstall

```bash
dictate-hotkey-uninstall  # Remove hotkey service
chatgpt-auth-delete       # Remove authorization (optional)
pip uninstall stt-prompt
```

---

## License

MIT

---

<details>
<summary>For Developers</summary>

### Local Development Setup

```bash
git clone https://github.com/zunmax/stt-prompt.git
cd stt-prompt
pip install -e ".[dev]"
```

### Project Structure

```
stt-prompt/
├── pyproject.toml          # Package configuration
├── requirements.txt        # Dependencies
└── src/voice_dictation/
    ├── cli.py              # CLI entry points
    ├── core.py             # Dictation logic (recording, transcription)
    ├── config.py           # Configuration management
    ├── hotkey_service.py   # Windows hotkey listener
    └── setup_autostart.py  # Platform-specific setup
```

### Building & Publishing

```bash
python -m build
twine check dist/*
twine upload dist/*
```

</details>
