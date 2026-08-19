#!/usr/bin/env bash
# Store the Gmail APP PASSWORD for sync reports in the macOS Keychain.
#
# This is NOT your Google account password. It is a 16-letter string Google
# generates at https://myaccount.google.com/apppasswords (needs 2-Step
# Verification on the account first). Gmail always rejects the account
# password over SMTP.
#
# Validates the shape before storing, so a wrong value fails here instead of
# surfacing later as SMTPAuthenticationError.
set -uo pipefail

ACCOUNT="${1:-nebula.markdown@gmail.com}"
SERVICE="claude-toolkit-smtp"

echo "Storing app password for: $ACCOUNT"
echo "Get one at: https://myaccount.google.com/apppasswords"
echo "It looks like:  abcd efgh ijkl mnop   (16 letters, spaces optional)"
echo

printf 'Paste or type the app password (input hidden): '
stty -echo 2>/dev/null; IFS= read -r RAW; stty echo 2>/dev/null; echo

# Strip spaces, non-breaking spaces, and stray quotes some browsers add.
PW="$(printf '%s' "$RAW" | tr -d '[:space:]' | tr -d "\"'")"

if [ -z "$PW" ]; then
  echo "Nothing entered. Aborted." >&2; exit 1
fi

LEN=${#PW}
if [ "$LEN" -ne 16 ]; then
  echo >&2
  echo "REJECTED: got $LEN characters, expected exactly 16." >&2
  if [ "$LEN" -gt 20 ]; then
    echo "That length looks like your ACCOUNT password. Gmail always refuses" >&2
    echo "that over SMTP. Generate an app password instead:" >&2
    echo "  https://myaccount.google.com/apppasswords" >&2
  fi
  echo "Nothing was stored." >&2
  exit 1
fi

if ! printf '%s' "$PW" | grep -qE '^[a-z]{16}$'; then
  echo >&2
  echo "REJECTED: 16 characters, but not all lowercase letters." >&2
  echo "Google app passwords are 16 lowercase a-z. Check for a typo." >&2
  echo "Nothing was stored." >&2
  exit 1
fi

security delete-generic-password -s "$SERVICE" >/dev/null 2>&1
if printf '%s' "$PW" | xargs -0 security add-generic-password \
     -a "$ACCOUNT" -s "$SERVICE" -w 2>/dev/null; then
  :
else
  security add-generic-password -a "$ACCOUNT" -s "$SERVICE" -w "$PW" || {
    echo "Failed to write to Keychain." >&2; exit 1; }
fi

echo "Stored 16-character app password for $ACCOUNT."
echo
echo "Testing send..."
exec /usr/bin/python3 "$(dirname "$0")/nik_mail_report.py" --test
