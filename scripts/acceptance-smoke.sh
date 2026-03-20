#!/usr/bin/env bash
set -euo pipefail

echo "[smoke] starting acceptance checks"

if ! command -v switcher >/dev/null 2>&1; then
  echo "[smoke] switcher binary not found in PATH"
  echo "[smoke] install first (for example: pip install -e .)"
  exit 1
fi

run_and_check() {
  local title="$1"
  local expected="$2"
  shift 2

  echo "[smoke] $title"
  local output
  output="$("$@" 2>&1)"
  echo "$output"
  if [[ -n "$expected" ]] && [[ "$output" != *"$expected"* ]]; then
    echo "[smoke] expected output to contain: $expected"
    exit 1
  fi
}

# Existing-login adoption path.
run_and_check \
  "discover existing credentials" \
  "Scanning for existing Gemini/Codex credentials" \
  switcher discover

# Fresh setup guidance path.
run_and_check \
  "fresh setup guidance" \
  "Fresh setup mode selected" \
  switcher setup --fresh --no-install

# Remediation path.
run_and_check "doctor diagnostics" "" switcher doctor
run_and_check "fix remediation" "" switcher fix

echo "[smoke] all checks passed"
