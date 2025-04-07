import os
import hashlib
import shutil
import sqlite3
import asyncio
import glob
import tarfile
from io import BytesIO
from pathlib import Path
from loguru import logger

from src.config import get_comfyui_settings
from src.utils.files import calculate_dir_hash

comfyui_settings = get_comfyui_settings()

workspace_meta_dir = comfyui_settings.workspace_path.joinpath('.workspace_meta')
workspace_dirs = ['input', 'output', 'custom_nodes', 'models', 'user']


def calculate_custom_nodes_hash() -> str:
    """Calculate a hash of all requirements.txt files in custom_nodes directories"""
    workspace_path = comfyui_settings.workspace_path
    custom_nodes_path = workspace_path.joinpath("custom_nodes")

    if not os.path.exists(custom_nodes_path):
        return hashlib.md5("".encode()).hexdigest()

    requirements_files = glob.glob(os.path.join(custom_nodes_path, "**", "requirements.txt"), recursive=True)

    if not requirements_files:
        return hashlib.md5("".encode()).hexdigest()

    # Combine all requirements files content
    combined_content = ""
    for req_file in sorted(requirements_files):
        try:
            with open(req_file, 'r') as f:
                combined_content += f.read()
        except Exception as e:
            logger.error(f"Error reading {req_file}: {e}")

    # Generate hash
    return hashlib.md5(combined_content.encode()).hexdigest()


async def _install_workspace_dependencies() -> None:
    # Ensure workspace directory exists
    os.makedirs(workspace_meta_dir, exist_ok=True)

    # Create database if it doesn't exist
    db_path = workspace_meta_dir.joinpath(".dependencies.db")

    # Create db and table if they don't exist
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS dependency_status (
        workspace_hash TEXT PRIMARY KEY,
        installed BOOLEAN NOT NULL
    )
    ''')
    conn.commit()

    # Copy custom nodes if workspace path is different from instance path
    instance_path = comfyui_settings.instance_path
    workspace_path = comfyui_settings.workspace_path

    if instance_path != workspace_path:
        instance_custom_nodes = instance_path.joinpath("custom_nodes")
        workspace_custom_nodes = workspace_path.joinpath("custom_nodes")

        if os.path.exists(instance_custom_nodes) and os.path.isdir(instance_custom_nodes):
            if os.path.exists(instance_custom_nodes.joinpath("comfyapi_nodes")):
                import shutil
                source = instance_custom_nodes.joinpath("comfyapi_nodes")
                destination = workspace_custom_nodes.joinpath("comfyapi_nodes")
                shutil.copytree(source, destination, dirs_exist_ok=True)

    # Calculate current hash
    current_hash = calculate_custom_nodes_hash()

    if not current_hash:
        logger.warning("No requirements.txt files found or custom_nodes directory doesn't exist")
        return

    # Check if hash exists in database and is marked as installed
    cursor.execute("SELECT installed FROM dependency_status WHERE workspace_hash = ?", (current_hash,))
    result = cursor.fetchone()

    needs_install = True
    if result and result[0]:
        logger.info("Dependencies previously installed and custom_nodes unchanged. Skipping installation.")
        needs_install = False
    else:
        logger.info("Custom nodes have changed or dependencies not yet installed. Installing dependencies...")

    if needs_install:
        try:
            # Install dependencies
            from src.comfyui.comfyui_manager import ensure_node_reqs
            await ensure_node_reqs()

            # Update database with success status
            cursor.execute("INSERT OR REPLACE INTO dependency_status (workspace_hash, installed) VALUES (?, ?)",
                           (current_hash, True))
            conn.commit()
            logger.info("Custom node dependencies installation completed.")
        except Exception as e:
            logger.info(f"Error installing dependencies: {e}")
            cursor.execute("INSERT OR REPLACE INTO dependency_status (workspace_hash, installed) VALUES (?, ?)",
                           (current_hash, False))
            conn.commit()

    conn.close()


async def _get_workspace_paths() -> list[Path]:
    """
    Get all files and directories in the specified workspace directories, excluding hidden files and folders.
    """
    workspace_path = comfyui_settings.workspace_path
    workspace_files = []

    # Iterate only over the defined workspace directories
    for dir_name in workspace_dirs:
        dir_path = workspace_path.joinpath(dir_name)

        # Skip if directory doesn't exist
        if not dir_path.exists():
            continue

        # Add the directory itself
        workspace_files.append(dir_path)

        # Walk through this specific directory
        for root, dirs, files in os.walk(dir_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            # Skip hidden files
            files = [f for f in files if not f.startswith('.')]
            # Add files to the list
            for file in files:
                workspace_files.append(Path(root).joinpath(file))
            # Add subdirectories to the list
            for d in dirs:
                workspace_files.append(Path(root).joinpath(d))

    return workspace_files

async def set_workspace_path(new_workspace: Path):
    """Set the workspace path and install dependencies if needed"""

    comfyui_settings.workspace_path = new_workspace
    await _install_workspace_dependencies()

async def delete_workspace() -> None:
    """
    Delete the current workspace and all its contents, except for hidden files/folders.
    """
    # Delete all files in the current workspace by iterating over workspace_dirs
    workspace_paths = await _get_workspace_paths()
    for file_path in workspace_paths:
        if file_path.is_file():
            os.remove(file_path)
        elif file_path.is_dir():
            shutil.rmtree(file_path, ignore_errors=True)

    logger.info("Workspace deleted successfully")


async def backup_workspace() -> Path:
    """
    Make a backup of the current workspace and return the path to the backup file.
    The workspace is left in a clean state.
    """
    # Look for an existing tar file in workspace_meta_dir
    os.makedirs(workspace_meta_dir, exist_ok=True)

    # Start by moving all non-hidden files to a temp directory under workspace_meta_dir
    tmp_backup_dir = workspace_meta_dir.joinpath("tmp_backup")
    # Clean the temporary directory if it exists
    if os.path.exists(tmp_backup_dir):
        shutil.rmtree(tmp_backup_dir, ignore_errors=True)

    # Create the temporary directory
    os.makedirs(tmp_backup_dir, exist_ok=True)

    workspace_paths = await _get_workspace_paths()
    # Move all files to the tmp directory, preserving the directory structure
    for file_path in workspace_paths:
        # Create the target directory structure
        if file_path.is_dir():
            target_dir = tmp_backup_dir.joinpath(file_path.relative_to(comfyui_settings.workspace_path))
            target_file = None
        else:
            target_dir = tmp_backup_dir.joinpath(file_path.parent.relative_to(comfyui_settings.workspace_path))
            target_file = tmp_backup_dir.joinpath(file_path.relative_to(comfyui_settings.workspace_path))

        # If the target file exists, we must have already copied it when moving the directory
        if target_file and target_file.exists():
            #logger.warning(f"File {target_file} already exists in the backup. Skipping.")
            continue

        if file_path.is_dir():
            # Move the directory
            os.makedirs(target_dir, exist_ok=True)

        if target_file:
            # Move the file
            os.makedirs(target_dir, exist_ok=True)
            shutil.copy2(str(file_path), str(target_file))


    # Now calculate the hash of the workspace in the tmp directory
    checksum = calculate_dir_hash(tmp_backup_dir)
    # Create a tar.gz file of the tmp directory and give it the name of the checksum
    backup_path = workspace_meta_dir.joinpath(f"{checksum}.tar.gz")

    # Create the tar.gz file
    with tarfile.open(backup_path, "w:gz") as tar:
        tar.add(tmp_backup_dir, arcname=os.path.basename(tmp_backup_dir))

    # Remove the tmp directory
    shutil.rmtree(tmp_backup_dir, ignore_errors=True)
    logger.info(f"Backup tar created at {backup_path}")

    # Now delete all files in the workspace
    await delete_workspace()

    return backup_path


async def restore_workspace() -> None:
    """
    Make a backup of the current workspace and restore the previous one
    """
    # First back up the current workspace
    current_backup_path = await backup_workspace()
    logger.info(f"Current workspace backed up to {current_backup_path}")

    # Find the most recent backup in workspace_meta_dir (excluding the one we just created)
    backups = list(workspace_meta_dir.glob("*.tar.gz"))
    backups = [b for b in backups if b != current_backup_path]

    if not backups:
        logger.error("No previous workspace backup found to restore")
        return

    # Sort backups by modification time (most recent first)
    backups.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    backup_to_restore = backups[0]

    # Extract the backup checksum from the filename
    backup_checksum = os.path.splitext(os.path.splitext(backup_to_restore.name)[0])[0]
    logger.info(f"Restoring workspace from backup: {backup_to_restore} (checksum: {backup_checksum})")

    # Extract to temporary directory
    temp_extract_dir = workspace_meta_dir.joinpath("temp_restore")

    # Clean the temporary directory if it exists
    if os.path.exists(temp_extract_dir):
        shutil.rmtree(temp_extract_dir, ignore_errors=True)
    os.makedirs(temp_extract_dir, exist_ok=True)

    # Extract the backup
    with tarfile.open(backup_to_restore, "r:gz") as tar:
        tar.extractall(path=temp_extract_dir)

    # Get the directory inside temp_extract_dir (should be tmp_backup)
    extract_contents = os.listdir(temp_extract_dir)
    if not extract_contents:
        logger.error("Extracted backup is empty")
        return

    extracted_dir = temp_extract_dir.joinpath(extract_contents[0])

    # Verify the contents by calculating checksum
    calculated_checksum = calculate_dir_hash(Path(extracted_dir))
    if calculated_checksum != backup_checksum:
        logger.error(f"Checksum verification failed! Expected: {backup_checksum}, Got: {calculated_checksum}")
        return

    logger.info("Checksum verified, restoring workspace...")

    # Clear the workspace (excluding hidden files/folders)
    await delete_workspace()

    # Move contents from extracted dir to workspace
    for item in os.listdir(extracted_dir):
        s = extracted_dir.joinpath(item)
        d = comfyui_settings.workspace_path.joinpath(item)
        if os.path.exists(d):
            if os.path.isdir(d):
                shutil.rmtree(d)
            else:
                os.remove(d)
        shutil.move(s, d)

    # Clean up
    shutil.rmtree(temp_extract_dir, ignore_errors=True)
    os.remove(backup_to_restore)

    logger.info("Workspace restored successfully")

    # Re-install dependencies for the restored workspace
    await _install_workspace_dependencies()


async def set_workspace(new_workspace_tar: bytes | BytesIO) -> None:
    """Set the workspace path and install dependencies if needed"""

    tmp_extract_path = comfyui_settings.workspace_path.joinpath("tmp_extract")

    # Now extract the new workspace tar to the temp directory
    import io
    file_obj = new_workspace_tar if isinstance(new_workspace_tar, BytesIO) else io.BytesIO(new_workspace_tar)
    with tarfile.open(fileobj=file_obj, mode='r:gz') as tar:
        tar.extractall(path=tmp_extract_path)

    # Now make a backup of the current workspace and move the contents of the
    # temp directory to the workspace path
    backup_path = await backup_workspace()

    for item in os.listdir(tmp_extract_path):
        s = tmp_extract_path.joinpath(item)
        d = comfyui_settings.workspace_path.joinpath(item)

        if os.path.exists(d):
            if os.path.isdir(d):
                shutil.rmtree(d)
            else:
                os.remove(d)

        shutil.move(s, d)

    await _install_workspace_dependencies()


async def get_workspace() -> bytes:
    """Get the current workspace as a tar archive, excluding hidden files/folders"""
    # Create a tar.gz file in memory
    import tarfile
    import io

    workspace_files = await _get_workspace_paths()
    if not workspace_files:
        logger.warning("No files found in the workspace directory")
        return b""
    # Create a BytesIO object to hold the tar file
    tar_bytes = io.BytesIO()
    with tarfile.open(fileobj=tar_bytes, mode='w:gz') as tar:
        for file_path in workspace_files:
            tar.add(file_path, arcname=os.path.relpath(file_path, comfyui_settings.workspace_path))

    # Return the tar file as bytes
    return tar_bytes.getvalue()


async def ensure_workspace_initialized() -> None:
    """Initialize the workspace directory structure and check dependencies"""
    workspace_path = comfyui_settings.workspace_path


    # Create workspace directories
    dirs = [workspace_path.joinpath(d) for d in workspace_dirs]

    for directory in dirs:
        os.makedirs(directory, exist_ok=True)

    # Check and install dependencies
    await _install_workspace_dependencies()


if __name__ == "__main__":
    # Example usage
    asyncio.run(ensure_workspace_initialized())
    # asyncio.run(set_workspace(Path("/path/to/new/workspace")))
    # asyncio.run(delete_workspace())
    asyncio.run(backup_workspace())
    asyncio.run(restore_workspace())
