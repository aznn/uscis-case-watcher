#!/bin/bash
# USCIS Case Watcher - Run Script
# Add to your shell config: alias uscis-watch='/path/to/run.sh'

cd "$(dirname "$0")"
uv run uscis_watcher.py "$@"
