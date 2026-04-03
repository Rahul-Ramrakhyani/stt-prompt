"""Command-line interface for STT Prompt"""

import argparse
import json
import sys
import webbrowser
from datetime import datetime

from .core import Dictation, save_auth, AUTH_FILE


def main():
    """Main entry point for dictation"""
    parser = argparse.ArgumentParser(
        prog="dictate",
        description="Voice-to-text dictation using ChatGPT transcription",
    )
    parser.add_argument(
        "--one-shot",
        action="store_true",
        help="Start recording immediately, stop with Ctrl+Shift+R, transcribe, then exit",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )
    args = parser.parse_args()

    try:
        # On Linux/macOS, check if another instance is recording and signal it to stop
        # This enables toggle behavior similar to the Windows hotkey service
        if args.one_shot:
            from .core import RECORDING_LOCK_FILE, STOP_SIGNAL_FILE, get_config_dir
            import os

            if RECORDING_LOCK_FILE.exists():
                try:
                    pid = int(RECORDING_LOCK_FILE.read_text().strip())
                    # Check if process is still running
                    try:
                        os.kill(pid, 0)
                        # Process exists - signal it to stop
                        get_config_dir()
                        STOP_SIGNAL_FILE.write_text(str(os.getpid()))
                        print("Signaled recording to stop...")
                        return
                    except OSError:
                        # Stale lock file - clean it up
                        RECORDING_LOCK_FILE.unlink(missing_ok=True)
                except (ValueError, OSError, PermissionError):
                    pass

        app = Dictation(one_shot=args.one_shot)
        if args.one_shot:
            app.run_one_shot()
        else:
            app.run()
    except KeyboardInterrupt:
        print("\nExiting...")
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def auth():
    """Authorization entry point"""
    print("""
=== STT Prompt - Authorization ===

This tool uses ChatGPT's transcription service.
You need to extract your access token from ChatGPT.

Steps:
1. Open https://chatgpt.com and LOGIN
2. Press F12 to open Developer Tools
3. Go to Console tab
4. Paste this code and press Enter:

fetch('https://chatgpt.com/api/auth/session').then(r=>r.json()).then(d=>console.log(JSON.stringify({accessToken:d.accessToken,email:d.user?.email,expires:d.expires})))

5. Copy the JSON output that appears
""")

    # Ask to open browser
    response = input("Open ChatGPT in browser? (Y/n): ").strip().lower()
    if response != 'n':
        webbrowser.open('https://chatgpt.com')

    # Get token input
    print("\nPaste the JSON output here (or just the token):")
    token_input = input("> ").strip()

    if not token_input:
        print("Error: No input provided", file=sys.stderr)
        sys.exit(1)

    try:
        # Try to parse as JSON first
        if token_input.startswith("{"):
            data = json.loads(token_input)
        else:
            # Treat as raw token
            data = {"accessToken": token_input}

        token = data.get("accessToken") or data.get("token")
        if not token:
            print("Error: No access token found in input", file=sys.stderr)
            sys.exit(1)

        # Save to config
        payload = {
            "accessToken": token,
            "email": data.get("email"),
            "expiresAt": data.get("expires") or data.get("expiresAt"),
            "createdAt": datetime.now().isoformat(),
        }

        saved_path = save_auth(payload)

        print(f"\nAuthorization saved!")
        print(f"  Location: {saved_path}")
        if data.get("email"):
            print(f"  Account: {data.get('email')}")
        print(f"\nRun 'dictate' to start STT Prompt")

    except json.JSONDecodeError:
        print("Error: Invalid JSON format", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def auth_status():
    """Check authorization status"""
    from .core import load_auth, AUTH_FILE
    
    print("=== STT Prompt - Authorization Status ===\n")
    
    if not AUTH_FILE.exists():
        print("❌ NOT AUTHORIZED")
        print(f"   No auth file found at: {AUTH_FILE}")
        print("\n   Run 'chatgpt-auth' to authorize.")
        sys.exit(1)
    
    auth = load_auth()
    
    if not auth:
        print("❌ NOT AUTHORIZED (token expired or invalid)")
        print(f"   Auth file: {AUTH_FILE}")
        print("\n   Run 'chatgpt-auth' to re-authorize.")
        sys.exit(1)
    
    if not auth.get('accessToken'):
        print("❌ NOT AUTHORIZED (no access token found)")
        print("\n   Run 'chatgpt-auth' to authorize.")
        sys.exit(1)
    
    # Token is valid
    print("✅ AUTHORIZED")
    print(f"   Auth file: {AUTH_FILE}")
    
    if auth.get('email'):
        print(f"   Account: {auth.get('email')}")
    
    if auth.get('expiresAt'):
        try:
            expires = auth.get('expiresAt')
            if isinstance(expires, str):
                expires = expires.replace("Z", "+00:00")
            from datetime import datetime, timezone
            exp_dt = datetime.fromisoformat(expires)
            now = datetime.now(timezone.utc) if exp_dt.tzinfo else datetime.now()
            
            if exp_dt > now:
                days_left = (exp_dt - now).days
                print(f"   Expires: {expires[:10]} ({days_left} days remaining)")
            else:
                print(f"   ⚠️  Token expired: {expires[:10]}")
                print("\n   Run 'chatgpt-auth' to re-authorize.")
        except (ValueError, TypeError, AttributeError):
            print(f"   Expires: {auth.get('expiresAt')}")
    
    if auth.get('createdAt'):
        print(f"   Created: {auth.get('createdAt')[:10]}")
    
    print("\n   Ready to use! Press Ctrl+Shift+R to dictate.")


def auth_delete():
    """Delete authorization / logout"""
    from .core import AUTH_FILE
    
    print("=== STT Prompt - Delete Authorization ===\n")
    
    if not AUTH_FILE.exists():
        print("No authorization found. Nothing to delete.")
        return
    
    # Confirm deletion
    response = input("Are you sure you want to delete your authorization? (y/N): ").strip().lower()
    if response != 'y':
        print("Cancelled.")
        return
    
    try:
        AUTH_FILE.unlink()
        print("✅ Authorization deleted successfully.")
        print(f"   Removed: {AUTH_FILE}")
        print("\n   Run 'chatgpt-auth' to re-authorize.")
    except Exception as exc:
        print(f"❌ Failed to delete: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
