#!/usr/bin/env bash
set -eEuo pipefail

download_seed() {
 local url="${1}"
 local dest_path="${2}"
 local file_name="${3}"
 echo -e "\n${script_name} - Downloading $(hostname) seed from ${url}.\n"
 mkdir -p "${seeds_dir}"
 aria2c -c -x16 -s16 -d "${dest_path}" "${url}"
 touch "${dl_status_file}"
 chown -f "${LOCAL_USER_ID}":"${LOCAL_GRP_ID}" "${dest_path}/${file_name}" "${dl_status_file}"
 echo -e "${script_name} - Downloading of ${file_name} complete.\n"
}

extract_seed() {
  local file_dir="${1}"
  local file_name="${2}"
  local dest_path="${3}"
  echo -e "${script_name} - Extracting ${file_name} to ${dest_path}\n"
  mkdir -p "${dest_path}"
  rm -rf "${dest_path}/"{consensusData,evm-state,history,state}
  tar -C "${dest_path}" -xzf "${file_dir}/${file_name}"
  touch "${status_file}"
  chown -f "${LOCAL_USER_ID}":"${LOCAL_GRP_ID}" "${status_file}"
  echo -e "${script_name} - Extracting complete.\n"
}

check_requirements() {
  local to_install=""
  command -v aria2c &> /dev/null || to_install+="aria2"
  if [ -n "${to_install}" ]; then
    echo -e "${script_name} - Installing requirements: ${to_install}\n"
    DEBIAN_FRONTEND=noninteractive apt-get -qq update
    # shellcheck disable=SC2086
    DEBIAN_FRONTEND=noninteractive apt-get -yqq install --no-install-recommends ${to_install}
  fi
}

script_name="$(basename "${0}")"
datadir="/sidechain/datadir"
state_dir="${SNAPSHOT_PATH_CONTAINER:?err_unset}/.state"
mkdir -p "${state_dir}"
dl_status_file="${state_dir}/.evmapp_reseed_download_complete"
status_file="${state_dir}/.evmapp_reseed_complete"
seeds_dir="${SNAPSHOT_PATH_CONTAINER}/.seeds"

if [ -n "${SCNODE_SEED_TAR_GZ_URL:-}" ]; then
  file_name="$(basename "${SCNODE_SEED_TAR_GZ_URL}")"
  if [ ! -f "${dl_status_file}" ]; then
    check_requirements
    download_seed "${SCNODE_SEED_TAR_GZ_URL}" "${seeds_dir}" "${file_name}"
  fi
  if [ ! -f "${status_file}" ]; then
    extract_seed "${seeds_dir}" "${file_name}" "${datadir}"
  fi
fi

exec entrypoint.sh "$@"
