#!/usr/bin/env bash
set -eEuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &>/dev/null && pwd)"
source "${ROOT_DIR}"/scripts/utils.sh

echo -e "\n\033[1m=== Checking all the requirements ===\033[0m"

verify_required_commands

# Making sure the script is not being run as root
CURRENT_USER_ID="$(id -u)"
CURRENT_GROUP_ID="$(id -g)"
if [ "${CURRENT_USER_ID}" == 0 ] || [ "${CURRENT_GROUP_ID}" == 0 ]; then
  fn_die "Error: This script should not be run as root. Exiting..."
fi

echo -e "\n\033[1mWhat network would you like to setup 'eon' (mainnet) or 'gobi' (testnet): \033[0m"
select network_value in eon gobi; do
  if [ -n "${network_value}" ]; then
    echo -e "\nYou have selected: \033[1m${network_value}\033[0m"
    break
  else
    echo -e "\n\033[1mInvalid selection. Please type 1, or 2.\033[0m\n"
  fi
done

echo -e "\n\033[1m=== Preparing deployment directory ./${network_value} ===\033[0m"
DEPLOYMENT_DIR="${ROOT_DIR}/deployments/${network_value}"
mkdir -p "${DEPLOYMENT_DIR}" || fn_die "Error: could not create deployment directory. Fix it before proceeding any further.  Exiting..."

echo -e "\n\033[1m=== Creating .env file ===\033[0m"
ENV_FILE_TEMPLATE="${ROOT_DIR}/env/env.${network_value}.template"
ENV_FILE="${DEPLOYMENT_DIR}/.env"

if ! [ -f "${ENV_FILE}" ]; then
  cp "${ENV_FILE_TEMPLATE}" "${ENV_FILE}"
  # shellcheck disable=SC1090,SC1091
  source "${ENV_FILE}" || fn_die "Error: could not source ${ENV_FILE} file. Fix it before proceeding any further.  Exiting..."

  # Setting SCNODE_NET_NODENAME and SCNODE_WALLET_SEED dynamically
  if [ -z "${SCNODE_WALLET_SEED}" ]; then
    echo -e "\n\033[1m=== Generating a random throwaway wallet seed phrase. ===\033[0m\n"
    SCNODE_WALLET_SEED="$(pwgen 64 1)" || fn_die "Error: could not set SCNODE_WALLET_SEED variable for some reason. Fix it before proceeding any further.  Exiting..."
    sed -i "s/SCNODE_WALLET_SEED=.*/SCNODE_WALLET_SEED=${SCNODE_WALLET_SEED}/g" "${ENV_FILE}"
  fi
  SCNODE_NET_NODENAME="ext-dump-$((RANDOM % 100000 + 1))" || fn_die "Error: could not set NODE_NAME variable for some reason. Fix it before proceeding any further.  Exiting..."
  sed -i "s/SCNODE_NET_NODENAME=.*/SCNODE_NET_NODENAME=${SCNODE_NET_NODENAME}/g" "${ENV_FILE}"

  # Setting local user and group in docker containers
  echo -e "\n\033[1m=== Setting up the docker containers local user and group ids ===\033[0m\n"
  echo -e "The uid:gid with which to run the processes inside of the container will default to ${CURRENT_USER_ID}:${CURRENT_GROUP_ID}"
  read -rp "Do you want to change the user (please answer 'no' if you're unsure) ? ('yes' or 'no') " user_group_answer
  while [[ ! "${user_group_answer}" =~ ^(yes|no)$ ]]; do
    echo -e "\nError: The only allowed answers are 'yes' or 'no'. Try again...\n"
    read -rp "Do you want to change the user (please answer 'no' if you don't know what you are doing) ? ('yes' or 'no') " user_group_answer
  done
  if [ "${user_group_answer}" = "yes" ]; then
    read -rp "Please type the user id you want to use in your docker containers (0 is an invalid value): " user_id
    while [[ ! "${user_id}" =~ ^[1-9][0-9]*$ ]]; do
      echo -e "\nError: The user id must be a positive integer and not 0. Try again...\n"
      read -rp "Please type the user id you want to use in your docker containers (0 is an invalid value): " user_id
    done
    read -rp "Please type the group id you want to use in your docker containers: " group_id
    while [[ ! "${group_id}" =~ ^[1-9][0-9]*$ ]]; do
      echo -e "\nError: The user id must be a positive integer and not 0. Try again...\n"
      read -rp "Please type the group id you want to use in your docker containers (0 is an invalid value): " group_id
    done
    LOCAL_USER_ID="${user_id}"
    LOCAL_GROUP_ID="${group_id}"
  else
    LOCAL_USER_ID="${CURRENT_USER_ID}"
    LOCAL_GROUP_ID="${CURRENT_GROUP_ID}"
  fi
  sed -i "s/LOCAL_USER_ID=.*/LOCAL_USER_ID=${LOCAL_USER_ID}/g" "${ENV_FILE}"
  sed -i "s/LOCAL_GRP_ID=.*/LOCAL_GRP_ID=${LOCAL_GROUP_ID}/g" "${ENV_FILE}"

  # Setting height targets for mainchain, sidechain height we will detect automatically
  echo -e "\n\033[1m=== Setting up the height targets ===\033[0m\n"
  echo -e "The ${NETWORK} snashopt height defaults to ${ZEND_SNAPSHOT_BLOCK_HEIGHT}."
  read -rp "Would you like to override the default height? ('yes' or 'no') " set_snapshot_height_answer
  while [[ ! "${set_snapshot_height_answer}" =~ ^(yes|no)$ ]]; do
    echo -e "\nError: The only allowed answers are 'yes' or 'no'. Try again...\n"
    read -rp "Would you like to override the default height? ('yes' or 'no') " set_snapshot_height_answer
  done
  if [ "${set_snapshot_height_answer}" = "yes" ]; then
    read -rp "Please type the ZEND ${NETWORK} snapshot block height: " snapshot_height_answer
    while [[ ! "${snapshot_height_answer}" =~ ^[1-9][0-9]*$ ]]; do
      echo -e "\nError: The snapshot block height must be a positive integer and not 0. Try again...\n"
      read -rp "Please type the ZEND ${NETWORK} snapshot block height: " snapshot_height_answer
    done
  ZEND_SNAPSHOT_BLOCK_HEIGHT="${snapshot_height_answer}"
  fi
  sed -i "s/ZEND_SNAPSHOT_BLOCK_HEIGHT=.*/ZEND_SNAPSHOT_BLOCK_HEIGHT=${ZEND_SNAPSHOT_BLOCK_HEIGHT}/g" "${ENV_FILE}"
fi

# shellcheck disable=SC1090,SC1091
source "${ENV_FILE}" || fn_die "Error: could not source ${ENV_FILE} file. Fix it before proceeding any further.  Exiting..."

check_required_variables

echo -e "\n\033[1m=== Setting up required files in deployment directory ===\033[0m"
LINK_SOURCE_PATH=(
  "${ROOT_DIR}/docker-compose.yml"
  "${ROOT_DIR}/container_mounts"
)
LINK_TARGET_PATH=(
  "${DEPLOYMENT_DIR}/docker-compose.yml"
  "${DEPLOYMENT_DIR}/container_mounts"
)

for i in "${!LINK_SOURCE_PATH[@]}"; do
  ln -sf "${LINK_SOURCE_PATH[i]}" "${LINK_TARGET_PATH[i]}"
done

COPY_SOURCE_PATH=(
  "${ROOT_DIR}/orchestrator"
)
COPY_TARGET_PATH=(
  "${DEPLOYMENT_DIR}/orchestrator"
)

for i in "${!COPY_SOURCE_PATH[@]}"; do
  cp -ar "${COPY_SOURCE_PATH[i]}" "${COPY_TARGET_PATH[i]}"
done


echo -e "\n\033[1m=== Initializing and building required docker containers ===\033[0m"
docker compose -f "${DEPLOYMENT_DIR}/docker-compose.yml" --progress=plain create --build --pull always

echo -e "\n\033[1m=== Project has been initialized correctly for ${network_value} ${NETWORK} network ===\033[0m"

echo -e "\n\033[1m=== RUNNING SNAPSHOTTING PROCESS ===\033[0m\n"

echo -e "To start the snapshotting procedure run:"

echo -e "\n\033[1mdocker compose -f ${DEPLOYMENT_DIR}/docker-compose.yml up -d\033[0m"

echo -e "\n\033[1m=== Refer to docs/automated-snapshot.md for details ===\033[0m\n"

exit 0
