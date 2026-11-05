#!/bin/bash
# Start Chrome with Stock Factory dedicated profile and CDP debugging
# Binds only to localhost (127.0.0.1:9222)
# Profile data: /tmp/stock-factory-chrome-profile

set -e

PROFILE_DIR="/tmp/stock-factory-chrome-profile"
CHROME_APP="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Verify Chrome exists
if [ ! -x "$CHROME_APP" ]; then
    echo "ERROR: Google Chrome not found at $CHROME_APP"
    exit 1
fi

# Create dedicated profile directory if needed
mkdir -p "$PROFILE_DIR"

echo "=========================================="
echo "Starting Chrome for Stock Factory Pilot"
echo "=========================================="
echo ""
echo "Profile: $PROFILE_DIR"
echo "CDP Debug: http://127.0.0.1:9222 (localhost only)"
echo ""
echo "When Chrome opens:"
echo "  1. Sign into Google if prompted"
echo "  2. Navigate to: https://flow.google.com"
echo "  3. Authenticate to Google Flow"
echo "  4. Keep this window open during pilot"
echo ""
echo "Press Ctrl+C to stop Chrome"
echo "=========================================="
echo ""

# Start Chrome with:
# - Remote debugging on localhost only
# - Dedicated profile directory
# - No personal data mixed in
"$CHROME_APP" \
  --remote-debugging-port=9222 \
  --remote-debugging-address=127.0.0.1 \
  --user-data-dir="$PROFILE_DIR" \
  https://flow.google.com

echo ""
echo "Chrome closed. Pilot complete."
