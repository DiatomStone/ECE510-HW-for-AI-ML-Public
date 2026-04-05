import torch
import os
import sys

import glob


# Print the path to the torch package
print(f"PyTorch Location: {torch.__file__}")

# Print the root of the current Python environment
print(f"Virtual Env Root: {sys.prefix}")

# Check if CUDA (GPU support) is available in this env
print(f"CUDA Available: {torch.cuda.is_available()}")

# Searches home directory for folders with "env" in the name
search_path = os.path.join(os.path.expanduser("~"), "**/*env*")
potential_venvs = glob.glob(search_path, recursive=True)

for path in potential_venvs:
    # Check for the 'activate' script to confirm it is a venv
    if os.path.isdir(path) and (os.path.exists(os.path.join(path, "bin", "activate")) or 
                                os.path.exists(os.path.join(path, "Scripts", "activate"))):
        print(f"Found venv: {path}")
