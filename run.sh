#!/bin/bash
# ============================================
# AI Usage Dashboard — Quick Start Script
# ============================================
# This script sets up a Python virtual environment,
# installs dependencies, and starts the dashboard.
#
# Usage:
#   chmod +x run.sh
#   ./run.sh

set -e

# Navigate to the script's directory
cd "$(dirname "$0")"

echo "=== AI Usage Dashboard ==="
echo ""

# Check for Python 3
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "Error: Python 3 is required but not found."
    echo "Install it from https://python.org or via your package manager."
    exit 1
fi

echo "Using: $($PYTHON --version)"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/update dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt

# Check for .env file
if [ ! -f ".env" ]; then
    echo ""
    echo "No .env file found. Creating one from .env.example..."
    cp .env.example .env
    echo ""
    echo ">>> IMPORTANT: Edit .env and add your API keys before continuing."
    echo ">>> Open .env in your editor, then run this script again."
    echo ""
    exit 0
fi

# Start the dashboard
echo ""
echo "Starting dashboard..."
echo ""
python app.py
