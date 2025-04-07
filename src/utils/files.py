import hashlib
import os
import tarfile
from pathlib import Path
from loguru import logger


def calculate_dir_hash(in_dir: Path, ignore_hidden_files: bool = True) -> str:
    """Calculate an efficient hash of all files in the directory"""

    if not os.path.exists(in_dir):
        return hashlib.md5("".encode()).hexdigest()

    # Get all files in the workspace directory recursively
    all_files = []
    for root, _, files in os.walk(in_dir):
        for file in files:
            # Skip hidden files and the dependencies database
            if ignore_hidden_files and file.startswith('.'):
                continue

            all_files.append(os.path.join(root, file))

    if not all_files:
        return hashlib.md5("".encode()).hexdigest()

    # Sort files for consistent hash
    all_files.sort()

    # Combine modification times and file sizes for a hash that's faster than reading content
    combined_data = ""
    for file_path in all_files:
        stat_info = os.stat(file_path)
        combined_data += f"{Path(file_path).name}:{stat_info.st_mtime}:{stat_info.st_size};"

    # Generate hash
    return hashlib.md5(combined_data.encode()).hexdigest()

def extract_tar_gz(tar_file: bytes, temp_extract_dir: str):
    def is_safe_path(path, base_dir):
        return os.path.abspath(os.path.join(base_dir, path)).startswith(base_dir)

    with tarfile.open(tar_file, "r:gz") as tar:
        for member in tar.getmembers():
            if not is_safe_path(member.name, temp_extract_dir):
                raise ValueError(f"Potentially unsafe path in archive: {member.name}")
        tar.extractall(path=temp_extract_dir)