#!/bin/sh
set -e
cd "$(dirname "$0")/.."
chmod +x .githooks/prepare-commit-msg
git config core.hooksPath .githooks
echo "Git hooks installed (core.hooksPath=.githooks)"
