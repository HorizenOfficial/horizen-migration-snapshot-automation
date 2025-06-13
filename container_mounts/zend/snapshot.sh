#!/usr/bin/env bash
set -eEuo pipefail

script_name="$(basename "${0}")"

check_requirements() {
  local to_install=""
  command -v jq &> /dev/null || to_install+="jq"
  if [ -n "${to_install}" ]; then
    echo -e "\n${script_name} - Installing requirements: ${to_install}\n"
    DEBIAN_FRONTEND=noninteractive apt-get -qq update
    # shellcheck disable=SC2086
    DEBIAN_FRONTEND=noninteractive apt-get -yqq install --no-install-recommends ${to_install}
  fi
}

check_requirements
# set ownership of migration-artifacts dir
CURRENT_UID="$(id -u "${USERNAME}")"
CURRENT_GID="$(id -g "${USERNAME}")"
find "${SNAPSHOT_PATH_CONTAINER:?err_unset}" -writable -print0 | xargs -0 -I{} -P64 -n1 chown -f "${CURRENT_UID}":"${CURRENT_GID}" "{}"

# use gosu if not running as root
gosu_cmd=""
[ "${CURRENT_UID}" -ne 0 ] && gosu_cmd="/usr/local/bin/gosu ${USERNAME}"

# reseed the node if needed
$gosu_cmd bash -c /mnt/scripts/reseed.sh

# dump utxo state if ready for snapshot
$gosu_cmd bash -c /mnt/scripts/dump.sh
