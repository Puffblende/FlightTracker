#!/bin/bash
cd "$(dirname "$0")"
echo "Installing FlightTracker dependencies..."
echo

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found."
    echo "Install Python 3.9+ from https://www.python.org/downloads/"
    echo
    read -n 1 -s -r -p "Press any key to close..."
    echo
    exit 1
fi

python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

echo
echo "Done! Run FlightTracker by double-clicking run.command"
echo
read -n 1 -s -r -p "Press any key to close..."
echo
