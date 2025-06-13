#!/usr/bin/env bash
set -eEuo pipefail

download_seed() {
  local url="${1}"
  local dest_path="${2}"
  local file_name="${3}"
  echo -e "\n${script_name} - Downloading zend-${NETWORK:-} seed from ${url}.\n"
  mkdir -p "${dest_path}"
  aria2c -c -x16 -s16 -d "${dest_path}" "${url}"
  touch "${dl_status_file}"
  echo -e "${script_name} - Downloading of ${file_name} complete.\n"
}

extract_seed() {
  local file_dir="${1}"
  local file_name="${2}"
  local dest_path="${3}"
  echo -e "${script_name} - Extracting ${file_name} to ${dest_path}\n"
  mkdir -p "${dest_path}"
  rm -rf "${dest_path}/"{blocks,chainstate}
  tar -C "${dest_path}" -xzf "${file_dir}/${file_name}"
  touch "${status_file}"
  echo -e "${script_name} - Extracting complete.\n"
}

script_name="$(basename "${0}")"
netdir=""
[ "${NETWORK:-}" = "testnet" ] && netdir="/testnet3"
datadir="${HOME}/.zen${netdir}"
state_dir="${SNAPSHOT_PATH_CONTAINER:?err_unset}/.state"
mkdir -p "${state_dir}"
dl_status_file="${state_dir}/.zend_reseed_download_complete"
status_file="${state_dir}/.zend_reseed_complete"
seeds_dir="${SNAPSHOT_PATH_CONTAINER}/.seeds"

if [ -n "${ZEN_SEED_TAR_GZ_URL:-}" ]; then
  file_name="$(basename "${ZEN_SEED_TAR_GZ_URL}")"
  if [ ! -f "${dl_status_file}" ]; then
    download_seed "${ZEN_SEED_TAR_GZ_URL}" "${seeds_dir}" "${file_name}"
  fi
  if [ ! -f "${status_file}" ]; then
    extract_seed "${seeds_dir}" "${file_name}" "${datadir}"
  fi
fi
