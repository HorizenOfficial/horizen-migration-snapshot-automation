#!/usr/bin/env bash
set -eEuo pipefail

exit_handler() {
  retcode=$?
  stop_zend || true
  { [ -n "${zend_pid:-}" ] && kill -0 "${zend_pid}" &> /dev/null; } && kill -9 "${zend_pid}"
  exit "${retcode}"
}

revert_until_num_confirmations() {
  local hash="${1}"
  local expected_height="${2}"
  local num_confirmations="${3}"
  local blockheader_at_hash height_at_hash confirmations_at_hash cur_block_header cur_block_hash cur_block_height prev_block_hash revert_until
  blockheader_at_hash="$(zen-cli ${cli_network} getblockheader "${hash}" 2>/dev/null || true)"
  height_at_hash="$(jq -rc '.height' <<< "${blockheader_at_hash}" 2>/dev/null || true)"
  confirmations_at_hash="$(jq -rc '.confirmations' <<< "${blockheader_at_hash}" 2>/dev/null || true)"
  # Sanity check
  if [ -z "${blockheader_at_hash}" ] || [ "${expected_height}" -ne "${height_at_hash}" ] || [ "${confirmations_at_hash}" -eq "-1" ]; then
    echo -e "${script_name} - ERROR: Snapshot block hash ${hash} not found in canonical chain or not of expected height.\n"
    return 1
  fi
  cur_block_header="$(zen-cli ${cli_network} getblockheader "$(zen-cli ${cli_network} getbestblockhash)")"
  cur_block_hash="$(jq -rc '.hash' <<< "${cur_block_header}")"
  cur_block_height="$(jq -rc '.height' <<< "${cur_block_header}")"
  prev_block_hash="$(jq -rc '.previousblockhash' <<< "${cur_block_header}")"
  revert_until="$(( height_at_hash + num_confirmations ))"
  while [ "${cur_block_height}" -gt "${revert_until}" ]; do
    echo -e "${script_name} - reverting block ${cur_block_height} with hash ${cur_block_hash}"
    zen-cli ${cli_network} invalidateblock "${cur_block_hash}"
    echo "${cur_block_hash}" >> "${reverted_blocks_file}"
    cur_block_header="$(zen-cli ${cli_network} getblockheader "${prev_block_hash}")"
    cur_block_hash="$(jq -rc '.hash' <<< "${cur_block_header}")"
    cur_block_height="$(jq -rc '.height' <<< "${cur_block_header}")"
    prev_block_hash="$(jq -rc '.previousblockhash' <<< "${cur_block_header}")"
  done
  cur_block_height="$(zen-cli ${cli_network} getblockcount)"
  if [ "${cur_block_height}" -gt "${revert_until}" ]; then
    echo -e "${script_name} - ERROR: Failed to revert blocks to snapshot height + ${num_confirmations}.\n"
    return 1
  fi
  touch "${revert_complete_file}"
  echo -e "\n${script_name} - successfully reverted to block height ${cur_block_height}. Ready for snapshot.\n"
}

reconsider_reverted_blocks() {
  echo -e "${script_name} - reconsidering reverted blocks.\n"
  while read -r block_hash; do
    echo -e "${script_name} - reconsidering block with hash ${block_hash}"
    zen-cli ${cli_network} reconsiderblock "${block_hash}"
  done < <(tac "${reverted_blocks_file}")
  rm -f "${reverted_blocks_file}" "${revert_complete_file}"
  echo -e "\n${script_name} - reverted blocks reconsidered successfully.\n"
}

start_zend() {
  echo -e "${script_name} - starting ZEND.\n"
  # start zend without connecting to any nodes
  OPTS+=" -connect=127.0.0.1:54321 -listen=0"
  # shellcheck disable=SC2086
  zend ${OPTS} &
  zend_pid=$!
  local i=0
  while [ "${i}" -lt 1800 ] && ! zen-cli ${cli_network} -rpcclienttimeout=1 getblockcount &> /dev/null ; do
    i="$((i+1))"
    sleep 0.1
  done
  if [ "${i}" -eq 1800 ]; then
    echo -e "${script_name} - ERROR: Zend did not start within 180 seconds.\n"
    return 1
  fi
  echo -e "${script_name} - ZEND started successfully.\n"
}

stop_zend() {
  if [ -n "${zend_pid:-}" ] && kill -0 "${zend_pid}" &> /dev/null; then
    zen-cli ${cli_network} stop
    local i=0
    while kill -0 "${zend_pid}" &> /dev/null && [ "${i}" -lt 600 ]; do
      i="$((i+1))"
      sleep 0.1
    done
    if kill -0 "${zend_pid}" &> /dev/null; then
      echo -e "\n${script_name} - failed to stop ZEND cleanly.\n"
      return 1
    fi
    echo -e "\n${script_name} - successfully stopped ZEND.\n"
    # ensure leveldb is written to disk
    sync
  fi
}

dump() {
  local height="${1}"
  local path="${2}"
  local outfile="${3}"
  echo -e "${script_name} - Taking UTXO snapshot at height ${height}.\n"
  mkdir -p "${path}"
  dumper ${dumper_network} --height "${height}" > "${path}/${outfile}"
  touch "${snapshot_complete_file}"
  echo -e "\n${script_name} - UTXO snapshot written to ${SNAPSHOT_PATH_CONTAINER}/${outfile} successfully.\n"
  echo -e "\n${script_name} - snapshot completed.\n"
  sync
}

script_name="$(basename "${0}")"
snapshot_height="${ZEND_SNAPSHOT_BLOCK_HEIGHT:?err_unset}"
utxo_dir="${SNAPSHOT_PATH_CONTAINER:?err_unset}/zend"
utxo_file="${ZEND_SNAPSHOT_FILE:?err_unset}"
state_dir="${SNAPSHOT_PATH_CONTAINER}/.state"
mkdir -p "${state_dir}"
ready_to_snapshot_file="${state_dir}/.zend_snapshot_block_hash"
revert_complete_file="${state_dir}/.zend_revert_complete"
snapshot_complete_file="${state_dir}/.zend_snapshot_complete"
reverted_blocks_file="${state_dir}/.zend_revered_blocks"
expected_hash=""
max_confirmations=99
cli_network=""
dumper_network=""
if [ "${NETWORK:-}" = "testnet" ]; then
  cli_network="-testnet"
  dumper_network="--testnet"
fi
zend_pid=""
if [ -s "${ready_to_snapshot_file}" ]; then
  trap 'exit_handler' ERR EXIT
  expected_hash="$(<"${ready_to_snapshot_file}")"
  if [ ! -f "${revert_complete_file}" ] && [ ! -f "${snapshot_complete_file}" ]; then
    echo
    start_zend
    revert_until_num_confirmations "${expected_hash}" "${snapshot_height}" "${max_confirmations}"
    stop_zend
  fi
  if [ -f "${snapshot_complete_file}" ]; then
    echo -e "\n${script_name} - snapshot already completed, nothing to be done.\n"
  else
    dump "${snapshot_height}" "${utxo_dir}" "${utxo_file}"
  fi
  if [ -s "${reverted_blocks_file}" ]; then
    start_zend
    reconsider_reverted_blocks
    stop_zend
  fi
fi
