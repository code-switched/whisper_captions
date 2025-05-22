#!/bin/bash
# This script launches the whisper server with necessary CUDA/CUDNN environment variables

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found. Please run the installation steps first."
    exit 1
fi

# Get site-packages directory using venv Python without activating
SITE_PACKAGES=$(./venv/bin/python -c "import site; print(site.getsitepackages()[0])")

# Set environment variables
export LD_LIBRARY_PATH="$SITE_PACKAGES/nvidia/cudnn/lib:$LD_LIBRARY_PATH"

# Run the application using the venv's Python directly
./venv/bin/python whisper_online_server.py