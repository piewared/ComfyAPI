"""
Load the file given by the relative path from the project root and return the absolute path.
"""
import os


from pathlib import Path

def get_absolute_path(relative_path: str) -> Path:
    # Get the directory of the current file
    current_dir = Path(__file__).parent
    # Move up to the parent of the 'src' directory
    parent_dir = current_dir.parents[1]
    # Join the parent directory with the relative path
    return parent_dir / relative_path