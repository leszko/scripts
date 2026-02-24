#!/usr/bin/env bash
# Wrapper for cron: run check_messages.py every 30 min.
# Cron has a minimal PATH; ensure uv and the project dir are set.
set -e
export PATH="${HOME}/.local/bin:${PATH}"
cd "$(dirname "$0")"
exec uv run python check_messages.py
