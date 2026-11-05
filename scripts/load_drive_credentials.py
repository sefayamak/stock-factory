#!/usr/bin/env python3
"""Load Drive OAuth credentials from macOS Keychain and export as env vars.

Usage:
    eval "$(python3 scripts/load_drive_credentials.py)"

This loads credentials securely from Keychain without printing them.
"""
import sys
import subprocess
import json

KEYCHAIN_SERVICE = 'stock-factory'
CRED_KEYS = {
    'GOOGLE_OAUTH_CLIENT_ID': 'GOOGLE_OAUTH_CLIENT_ID',
    'GOOGLE_OAUTH_CLIENT_SECRET': 'GOOGLE_OAUTH_CLIENT_SECRET',
    'GOOGLE_OAUTH_REFRESH_TOKEN': 'GOOGLE_OAUTH_REFRESH_TOKEN',
}

def get_from_keychain(key: str) -> str | None:
    """Retrieve value from Keychain."""
    try:
        cmd = f'security find-generic-password -s "{KEYCHAIN_SERVICE}" -a "{key}" -w 2>/dev/null'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None

def main() -> int:
    missing = []
    exports = []

    for keychain_key, env_var in CRED_KEYS.items():
        value = get_from_keychain(keychain_key)
        if not value:
            missing.append(keychain_key)
        else:
            # Export as environment variable (shell-safe)
            escaped = value.replace('"', '\\"')
            exports.append(f'export {env_var}="{escaped}"')

    if missing:
        print(f"# Missing credentials in Keychain: {', '.join(missing)}", file=sys.stderr)
        print("# Run: python3 scripts/setup_drive_oauth_secure.py", file=sys.stderr)
        return 1

    # Also set the folder IDs (same folder used for both queues in Phase 2 setup)
    exports.append(f'export DRIVE_MAGNIFIC_FOLDER_ID="1OUL8cY9_Yd1qSy5zmcno0ilom0DpBsUA"')
    exports.append(f'export DRIVE_ADOBE_FOLDER_ID="1OUL8cY9_Yd1qSy5zmcno0ilom0DpBsUA"')

    # Output as shell commands (can be eval'd)
    for export in exports:
        print(export)

    return 0

if __name__ == '__main__':
    sys.exit(main())
