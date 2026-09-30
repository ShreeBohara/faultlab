#!/usr/bin/env bash
# Verifier-2: record the saved stores' state without writing them. control-capability files are credentials-like:
# only size and mtime are recorded (never opened). Every other file: sha256.
# Usage: saved_stores_state.sh <label>
set -u
V=/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-diagnosis-rules-2026-09-30/verify-2
find /Users/shree/FaultLab_Runs -type f ! -name 'control-capability' ! -name '.env' ! -name '.env.*' -print0 | sort -z | xargs -0 shasum -a 256 > "$V/saved-stores-sha256-$1.txt"
find /Users/shree/FaultLab_Runs -type f -name 'control-capability' -print0 | sort -z | xargs -0 stat -f '%z %Sm %N' > "$V/saved-stores-capability-files-not-opened-$1.txt"
find /Users/shree/FaultLab_Runs -type f \( -name '.env' -o -name '.env.*' \) | wc -l | tr -d ' ' | sed 's/^/env-like files present (not opened): /' >> "$V/saved-stores-capability-files-not-opened-$1.txt"
echo "$(wc -l < "$V/saved-stores-sha256-$1.txt" | tr -d ' ') files hashed"
