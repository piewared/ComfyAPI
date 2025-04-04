#!/bin/bash
set -e -o pipefail

### Container entrypoint
# Runs the CMD as defined by the Dockerfile or passed to `docker run`
# Can be used to configure the runtime dir
# Bypass by using ENTRYPOINT or `--entrypoint`

### Set INVOKEAI_ROOT pointing to a valid runtime directory
# Otherwise configure the runtime dir first.

### Set the CONTAINER_UID envvar to match your user.
# Ensures files created in the container are owned by you:
# Default UID: 1000 chosen due to popularity on Linux systems. Possibly 501 on MacOS.

USER_ID=${CONTAINER_UID:-1000}
USER=ubuntu
# if the user does not exist, create it. It is expected to be present on ubuntu >=24.x
_=$(id ${USER} 2>&1) || useradd -u ${USER_ID} ${USER}
# ensure the UID is correct
usermod -u ${USER_ID} ${USER} 1>/dev/null

### Set the $PUBLIC_KEY env var to enable SSH access.
# We do not install openssh-server in the image by default to avoid bloat.
# but it is useful to have the full SSH server e.g. on Runpod.
# (use SCP to copy files to/from the image, etc)
if [[ -v "PUBLIC_KEY" ]] && [[ ! -d "${HOME}/.ssh" ]]; then
  apt-get update
  apt-get install -y openssh-server
  pushd "$HOME"
  mkdir -p .ssh
  echo "${PUBLIC_KEY}" >.ssh/authorized_keys
  chmod -R 700 .ssh
  echo "Generating SSH keys..."
  ssh-keygen -A
  popd
  service ssh start
fi

# Create workspace directory if it doesn't exist, along with 'input', 'output', 'custom_nodes', and 'models' subdirectories
mkdir -p "${COMFYUI_WORKSPACE_PATH}"
mkdir -p "${COMFYUI_WORKSPACE_PATH}/input"
mkdir -p "${COMFYUI_WORKSPACE_PATH}/output"
mkdir -p "${COMFYUI_WORKSPACE_PATH}/custom_nodes"
mkdir -p "${COMFYUI_WORKSPACE_PATH}/models"

# if ${COMFYUI_WORKSPACE_PATH} is different from ${COMFYUI_INSTANCE_PATH}, copy custom_nodes from the instance to the workspace
if [[ "${COMFYUI_WORKSPACE_PATH}" != "${COMFYUI_INSTANCE_PATH}" ]]; then
  if [ -d "${COMFYUI_INSTANCE_PATH}/custom_nodes" ]; then
    #ls "${COMFYUI_INSTANCE_PATH}/custom_nodes"
    mv ${COMFYUI_INSTANCE_PATH}/custom_nodes/* ${COMFYUI_WORKSPACE_PATH}/custom_nodes/
  fi
fi


# Run the CMD as the Container User (not root).
#exec gosu ${USER} "$@"
echo "Running as user: $(whoami)"
echo "User ID: $(id -u)"
echo "Group ID: $(id -g)"
echo "Command: $*"
exec "$@"