import importlib
import sys
from pathlib import Path

# Initialize empty dictionaries to hold all node mappings
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

# Get the directory of this file
current_dir = Path(__file__).parent

# Iterate through all .py files in the package
for file_path in current_dir.glob("*.py"):
    # Skip the __init__.py file itself
    if file_path.name == "__init__.py":
        continue

    # Import the module
    module_name = file_path.stem
    try:
        # Create a proper module path for import
        module_path = f"{__name__}.{module_name}"
        module = importlib.import_module(module_path)

        # Look for node mappings and update the dictionaries
        if hasattr(module, "NODE_CLASS_MAPPINGS"):
            NODE_CLASS_MAPPINGS.update(module.NODE_CLASS_MAPPINGS)

        if hasattr(module, "NODE_DISPLAY_NAME_MAPPINGS"):
            NODE_DISPLAY_NAME_MAPPINGS.update(module.NODE_DISPLAY_NAME_MAPPINGS)

    except Exception as e:
        print(f"Error importing module {module_name}: {e}", file=sys.stderr)

# Print a summary of loaded nodes
if NODE_CLASS_MAPPINGS:
    print(f"ComfyAPI Nodes: Loaded {len(NODE_CLASS_MAPPINGS)} node types")
