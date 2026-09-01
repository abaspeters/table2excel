#!/usr/bin/env bash
# Build a folder that installs with NO internet on the target machine.
# Run this once on a machine that HAS internet, then copy the whole folder.
#
# Wheels are platform-specific, so you must download the Windows ones
# explicitly even when running this on Linux or macOS.
set -e
cd "$(dirname "$0")"
rm -rf wheels && mkdir wheels
pip download -r requirements-offline.txt -d wheels \
    --platform win_amd64 --python-version 3.12 --only-binary=:all:
echo
echo "Done. Copy this whole folder (including wheels/) to the Windows machine."
echo "Also copy the Tesseract installer alongside it — that is a separate download."
