#!/usr/bin/env bash

# Functions
fn_die() {
  echo -e "\n\033[1;31m${1}\033[0m\n" >&2
  exit "${2:-1}"
}

verify_required_commands() {

  command -v pwgen &>/dev/null || fn_die "${FUNCNAME[0]} Error: 'pwgen' is required to run this script, install with 'sudo apt-get install pwgen' or 'brew install pwgen'."

  command -v jq &>/dev/null || fn_die "${FUNCNAME[0]} Error: 'jq' is required to run this script, see installation instructions at 'https://jqlang.github.io/jq/download/'."

  command -v docker &>/dev/null || fn_die "${FUNCNAME[0]} Error: 'docker' is required to run this script, see installation instructions at 'https://docs.docker.com/engine/install/'."

  (docker compose version 2>&1 | grep -q v2) || fn_die "${FUNCNAME[0]} Error: 'docker compose' v2 is required to run this script, see installation instructions at 'https://docs.docker.com/compose/install/'."

  if [ "$(uname)" = "Darwin" ]; then
    command -v gsed &>/dev/null || fn_die "${FUNCNAME[0]} Error: 'gnu-sed' is required to run this script in MacOS environment, see installation instructions at 'https://formulae.brew.sh/formula/gnu-sed'. Make sure to add it to your PATH."
  fi
}

check_env_var() {
  local usage="Check if required environmental variable is empty and produce an error - usage: ${FUNCNAME[0]} {env_var_name}"
  [ "${1:-}" = "usage" ] && echo "${usage}" && return
  [ "$#" -ne 1 ] && {
    fn_die "${FUNCNAME[0]} error: function requires exactly one argument.\n\n${usage}"
  }

  local var="${1}"
  if [ -z "${!var:-}" ]; then
    fn_die "Error: Environment variable ${var} is required. Exiting ..."
  fi
}

check_required_variables() {
  TO_CHECK=(
    "ARG_MIGRATION_COMMITTISH"
    "COMPOSE_PROJECT_NAME"
    "EVMAPP_CONTAINER_NAME_PREFIX"
    "EVMAPP_SNAPSHOT_FILE"
    "EVMAPP_STAKES_FILE"
    "EVMAPP_TAG"
    "LOCAL_GRP_ID"
    "LOCAL_USER_ID"
    "NETWORK"
    "SCNODE_ALLOWED_FORGERS"
    "SCNODE_CERT_MASTERS_PUBKEYS"
    "SCNODE_CERT_SIGNERS_MAXPKS"
    "SCNODE_CERT_SIGNERS_PUBKEYS"
    "SCNODE_CERT_SIGNERS_THRESHOLD"
    "SCNODE_CERT_SIGNING_ENABLED"
    "SCNODE_CERT_SUBMITTER_ENABLED"
    "SCNODE_EVM_STATE_DUMP_ENABLED"
    "SCNODE_FORGER_ENABLED"
    "SCNODE_FORGER_MAXCONNECTIONS"
    "SCNODE_FORGER_RESTRICT"
    "SCNODE_GENESIS_BLOCKHEX"
    "SCNODE_GENESIS_COMMTREEHASH"
    "SCNODE_GENESIS_ISNONCEASING"
    "SCNODE_GENESIS_MCBLOCKHEIGHT"
    "SCNODE_GENESIS_MCNETWORK"
    "SCNODE_GENESIS_POWDATA"
    "SCNODE_GENESIS_SCID"
    "SCNODE_GENESIS_WITHDRAWALEPOCHLENGTH"
    "SCNODE_LOG_CONSOLE_LEVEL"
    "SCNODE_LOG_FILE_LEVEL"
    "SCNODE_NET_API_LIMITER_ENABLED"
    "SCNODE_NET_HANDLING_TXS"
    "SCNODE_NET_KNOWNPEERS"
    "SCNODE_NET_MAGICBYTES"
    "SCNODE_NET_MAX_IN_CONNECTIONS"
    "SCNODE_NET_MAX_OUT_CONNECTIONS"
    "SCNODE_NET_NODENAME"
    "SCNODE_NET_P2P_PORT"
    "SCNODE_NET_REBROADCAST_TXS"
    "SCNODE_NET_SLOW_MODE"
    "SCNODE_REST_PORT"
    "SCNODE_SEED_TAR_GZ_URL"
    "SCNODE_WALLET_MAXTX_FEE"
    "SCNODE_WALLET_SEED"
    "SCNODE_WS_CLIENT_ENABLED"
    "SCNODE_WS_SERVER_ENABLED"
    "SCNODE_WS_SERVER_PORT"
    "SNAPSHOT_PATH_CONTAINER"
    "SNAPSHOT_PATH_LOCAL"
    "ZEN_CUSTOM_SCRIPT"
    "ZEND_CONTAINER_NAME_PREFIX"
    "ZEND_SNAPSHOT_BLOCK_HEIGHT"
    "ZEND_SNAPSHOT_BLOCK_HEIGHT_MIN_CONF"
    "ZEND_SNAPSHOT_FILE"
    "ZEND_TAG"
    "ZEN_EXTERNAL_IP"
    "ZEN_LOG"
    "ZEN_OPTS"
    "ZEN_PORT"
    "ZEN_RPC_ALLOWIP_PRESET"
    "ZEN_RPC_PASSWORD"
    "ZEN_RPC_PORT"
    "ZEN_RPC_USER"
    "ZEN_SEED_TAR_GZ_URL"
  )

  for var in "${TO_CHECK[@]}"; do
    check_env_var "${var}"
  done
}
