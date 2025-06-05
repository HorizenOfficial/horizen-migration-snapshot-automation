#!/usr/bin/env python
import sys
import signal
import time
import os
import docker
import requests
import simplejson as json
import subprocess
from decimal import Decimal
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
from typing import Optional

# ------------------------------------------------------------------------------------------------
# script variables

# environment
mandatory_env_vars = [
    "EVMAPP_CONTAINER_NAME_PREFIX",
    "EVMAPP_SNAPSHOT_FILE",
    "EVMAPP_STAKES_FILE",
    "NETWORK",
    "SCNODE_GENESIS_SCID",
    "SCNODE_REST_PORT",
    "SNAPSHOT_PATH_CONTAINER",
    "ZEND_CONTAINER_NAME_PREFIX",
    "ZEND_SNAPSHOT_BLOCK_HEIGHT",
    "ZEND_SNAPSHOT_BLOCK_HEIGHT_MIN_CONF",
    "ZEND_SNAPSHOT_FILE",
    "ZEN_RPC_PASSWORD",
    "ZEN_RPC_PORT",
    "ZEN_RPC_USER"
]

for var in mandatory_env_vars:
    if var not in os.environ or not os.getenv(var):
        raise ValueError(f"Mandatory environment variable '{var}' is not set or empty.")

NETWORK = os.getenv("NETWORK")
SNAPSHOT_PATH_CONTAINER = os.getenv("SNAPSHOT_PATH_CONTAINER")
ZEND_SNAPSHOT_BLOCK_HEIGHT = int(os.getenv("ZEND_SNAPSHOT_BLOCK_HEIGHT"))
ZEND_SNAPSHOT_BLOCK_HEIGHT_MIN_CONF = int(os.getenv("ZEND_SNAPSHOT_BLOCK_HEIGHT_MIN_CONF"))
ZEN_RPC_USER = os.getenv("ZEN_RPC_USER")
ZEN_RPC_PASSWORD = os.getenv("ZEN_RPC_PASSWORD")
ZEN_RPC_PORT = int(os.getenv("ZEN_RPC_PORT"))
SCNODE_GENESIS_SCID = os.getenv("SCNODE_GENESIS_SCID")
SCNODE_REST_PORT = int(os.getenv("SCNODE_REST_PORT"))
ZEND_CONTAINER_NAME_PREFIX = os.getenv("ZEND_CONTAINER_NAME_PREFIX")
ZEND_SNAPSHOT_FILE = os.getenv("ZEND_SNAPSHOT_FILE")
EVMAPP_CONTAINER_NAME_PREFIX = os.getenv("EVMAPP_CONTAINER_NAME_PREFIX")
EVMAPP_SNAPSHOT_FILE = os.getenv("EVMAPP_SNAPSHOT_FILE")
EVMAPP_STAKES_FILE = os.getenv("EVMAPP_STAKES_FILE")
DEBUG = os.getenv("DEBUG", "False") == "True"
FORCE_NEW_SNAPSHOT = os.getenv("FORCE_NEW_SNAPSHOT", "False") == "True" and DEBUG
FORCE_RESEED = os.getenv("FORCE_RESEED", "False") == "True" and DEBUG
PREGOBI_SCID = os.getenv("PREGOBI_SCID")
SKIP_CHECK_TOTAL_BALANCE_FROM_ZEND = os.getenv("SKIP_CHECK_TOTAL_BALANCE_FROM_ZEND", "False") == "True" and DEBUG
if NETWORK == "testnet" and not PREGOBI_SCID:
   raise ValueError("Mandatory environment variable 'PREGOBI_SCID' is not set or empty.")

# global constants
state_dir = f"{SNAPSHOT_PATH_CONTAINER}/.state"
zend_container_name = f"{ZEND_CONTAINER_NAME_PREFIX}-{NETWORK}"
zend_snapshot_path = f"{SNAPSHOT_PATH_CONTAINER}/zend"
zend_snapshot_file = f"{zend_snapshot_path}/{ZEND_SNAPSHOT_FILE}"
zend_reseed_status_file = f"{state_dir}/.zend_reseed_complete"
zend_ready_to_snapshot_file = f"{state_dir}/.zend_snapshot_block_hash"
zend_snapshot_complete_file = f"{state_dir}/.zend_snapshot_complete"
zend_snapshot_scid_balance_file = f"{state_dir}/.zend_snapshot_scid_balance"
evmapp_container_name = f"{EVMAPP_CONTAINER_NAME_PREFIX}-{NETWORK}"
evmapp_reseed_status_file = f"{state_dir}/.evmapp_reseed_complete"
evmapp_snapshot_complete_file = f"{state_dir}/.evmapp_snapshot_complete"
evmapp_network = "gobi" if NETWORK == "testnet" else "eon"
evmapp_mc_ref_delay = 6
evmapp_snapshot_path = f"{SNAPSHOT_PATH_CONTAINER}/evmapp"
evmapp_snapshot_file = f"{evmapp_snapshot_path}/{EVMAPP_SNAPSHOT_FILE}"
evmapp_stakes_file = f"{evmapp_snapshot_path}/{EVMAPP_STAKES_FILE}"
evmapp_stakes_complete_file = f"{state_dir}/.evmapp_stakes_complete"
orchestator_zend_snapshot_hash_file = f"{state_dir}/.orchestrator_zend_snapshot_hash"
automappings_file = f"/app/horizen-migration/dump-scripts/automappings/{NETWORK}.json"
zend_to_horizen_complete_file = f"{state_dir}/.zend_to_horizen_complete"
zend_vault_file = f"{zend_snapshot_path}.json"
evmapp_vault_file = f"{zend_snapshot_path}/_automaps.json"
evmapp_accounts_file = f"{SNAPSHOT_PATH_CONTAINER}/{EVMAPP_SNAPSHOT_FILE}"
setup_eon2_json_complete_file = f"{state_dir}/.setup_eon2_json_complete"
check_addresses_balance_from_eon_complete_file = f"{state_dir}/.check_addresses_balance_from_eon_complete"
check_addresses_balance_from_zend_complete_file = f"{state_dir}/.check_addresses_balance_from_zend_complete"
check_total_balance_from_zend_complete_file = f"{state_dir}/.check_total_balance_from_zend_complete"
migrationhash_zend_complete_file = f"{state_dir}/.migrationhash_zend_complete"
migrationhash_evmapp_complete_file = f"{state_dir}/.migrationhash_evmapp_complete"
migrationhash_zend_file = f"{zend_vault_file}.migrationhash"
migrationhash_evmapp_file = f"{evmapp_accounts_file}.migrationhash"
target_height = ZEND_SNAPSHOT_BLOCK_HEIGHT + ZEND_SNAPSHOT_BLOCK_HEIGHT_MIN_CONF
target_mc_ref_height = target_height - evmapp_mc_ref_delay

# check confirmation inputs
assertion_msg = (f"ORCHESTRATOR -  Error: ZEND_SNAPSHOT_BLOCK_HEIGHT_MIN_CONF minimum allowed value is {evmapp_mc_ref_delay}, current value: {ZEND_SNAPSHOT_BLOCK_HEIGHT_MIN_CONF}")
assert ZEND_SNAPSHOT_BLOCK_HEIGHT_MIN_CONF - evmapp_mc_ref_delay >= 0, assertion_msg

# ------------------------------------------------------------------------------------------------
# signal handling

def signal_handler(signum, frame):
    print(f"Gracefully shutting down after receiving signal {signum}")
    sys.exit(0)


# ------------------------------------------------------------------------------------------------
# utility methods

def path_exists(path: str):
    return os.path.exists(path)

def read_str_file(path: str):
    with open(path, "r") as f:
        return f.read().rstrip()

def write_str_file(path: str, content: Optional[str]=""):
    with open(path, "w") as f:
      f.write(content)

def execute_external_command(executable: str, *args):
    try:
        command = [executable] + list(args)
        print(f"Running external command: {executable} with arguments: {args}")
        result = subprocess.run(command, check=True, text=True, stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
        print(f"External command '{executable}' executed successfully with output:\n{result.stdout}")
        return result.stdout

    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to execute '{executable}'.")
        print(f"Command Output:\n{e.output}")
        raise

    except Exception as e:
        print(f"Unexpected error while calling external script: {e}")
        raise


# ------------------------------------------------------------------------------------------------
# docker container handling

def get_container_status(container_name: str):
    client = docker.from_env()

    try:
        # Check if the container is running
        container = client.containers.get(container_name)
        if container and container.status:
            return container.status

    except docker.errors.NotFound:
        print(f"Container '{container_name}' not found. Run 'docker compose create' first. Exiting ...")
        raise docker.errors.NotFound

    except Exception as e:
        print(f"An error occurred while managing the container '{container_name}': {e}")

    client.close()

def start_container(container_name: str):
    client = docker.from_env()

    try:
        # Check if the container is running
        container = client.containers.get(container_name)
        if container and container.status == "running":
            print(f"Container '{container_name}' is already running.")
            return
        else:
            print(f"Container '{container_name}' found but not running. Starting...")
            container.start()

    except docker.errors.NotFound:
        print(f"Container '{container_name}' not found. Run 'docker compose create' first. Exiting ...")
        raise docker.errors.NotFound

    except Exception as e:
        print(f"An error occurred while managing the container '{container_name}': {e}")

    client.close()

def stop_container_if_running(container_name: str):
    client = docker.from_env()

    try:
        # Check if the container is running
        container = client.containers.get(container_name)
        if container and container.status == "running":
            print(f"Container '{container_name}' is running. Stopping it...")
            container.stop()
            # Honor the container's Stop Timeout
            stop_time = time.time()
            grace_period = 60
            if "StopTimeout" in container.attrs["Config"]:
                grace_period = container.attrs["Config"]["StopTimeout"]
            end_time = stop_time + grace_period
            # Wait for the container to stop
            while time.time() < end_time:
                container.reload()
                if container.status == "exited":
                    print(f"Container '{container_name}' has been stopped.")
                    break
                time.sleep(0.1)
            else:
                print(f"Error: Container '{container_name}' did not stop within the expected time.")
                raise RuntimeError
        else:
            print(f"Container '{container_name}' is already stopped.")

    except docker.errors.NotFound:
        print(f"Container '{container_name}' not found. Run 'docker compose create' first. Exiting ...")
        raise docker.errors.NotFound

    except Exception as e:
        print(f"An error occurred while managing the container '{container_name}': {e}")

    client.close()

def restart_container(container_name: str):
    stop_container_if_running(container_name)
    start_container(container_name)


# ------------------------------------------------------------------------------------------------
# API methods

def call_zend_rpc(method: str, *params):
    rpc_call = [method] + list(params)
    rpc_url = f"http://{ZEN_RPC_USER}:{ZEN_RPC_PASSWORD}@{zend_container_name}:{ZEN_RPC_PORT}"

    try:
        rpc_connection = AuthServiceProxy(rpc_url)
        return rpc_connection.batch_([rpc_call])[0]

    except (JSONRPCException, ConnectionRefusedError) as e:
        if DEBUG:
            print(f"DEBUG - RPC request failed: {e}")
        return None

def call_evmapp_rpc(method: str, params: Optional[list]=[]):
    rpc_url = f"http://{evmapp_container_name}:{SCNODE_REST_PORT}/ethv1"

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1
    }

    try:
        response = requests.post(rpc_url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        if DEBUG:
            print(f"DEBUG - HTTP request failed: {e}")
        return None

    except ValueError as e:
        if DEBUG:
            print(f"DEBUG - Error processing the response: {e}")
        return None

def call_evmapp_rest(route: str, postdata: Optional[dict]={}):
    rest_url = f"http://{evmapp_container_name}:{SCNODE_REST_PORT}{route}"

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(rest_url, headers=headers, json=postdata)
        response.raise_for_status()
        json = response.json()
        return json["result"]

    except requests.exceptions.RequestException as e:
        if DEBUG:
            print(f"DEBUG - HTTP request failed: {e}")
        return None

    except ValueError as e:
        if DEBUG:
            print(f"DEBUG - Error processing the response: {e}")
        return None

    except KeyError as e:
        if DEBUG:
            print(f"DEBUG - Error processing the response: {e}")
        return None


# ------------------------------------------------------------------------------------------------
# snapshot methods

# take zend utxo dump
def get_zend_snapshot():
    zend_running = get_container_status(zend_container_name) == "running"

    if not zend_running:
        start_container(zend_container_name)
    zend_reseed_complete = path_exists(zend_reseed_status_file)
    if zend_reseed_complete:
        zend_ready_to_snapshot = path_exists(zend_ready_to_snapshot_file)
        if zend_ready_to_snapshot:
            print(f"ZEND -  Waiting for '{zend_container_name}' container to complete the snapshot.")
            zend_snapshot_complete = path_exists(zend_snapshot_complete_file)
            if zend_snapshot_complete:
                print(f"ZEND -  '{zend_container_name}' snapshot complete. File written to './{zend_snapshot_file.split('/', 2)[2]}'")
                if not DEBUG:
                    stop_container_if_running(zend_container_name)
        else:
            blockchaininfo = call_zend_rpc("getblockchaininfo")
            zend_rpc_ready = blockchaininfo and "verificationprogress" in blockchaininfo
            if zend_rpc_ready:
                zend_cur_height = call_zend_rpc("getblockcount")
                orchestator_zend_snapshot_hash = False
                if path_exists(orchestator_zend_snapshot_hash_file):
                    orchestator_zend_snapshot_hash = read_str_file(orchestator_zend_snapshot_hash_file)
                if orchestator_zend_snapshot_hash:
                    # check if snapshot height has seen enough confirmations
                    if zend_cur_height >= target_height:
                        # sanity check
                        current_zend_snapshot_hash = call_zend_rpc("getblock", str(ZEND_SNAPSHOT_BLOCK_HEIGHT))["hash"]
                        assertion_msg = (f"ZEND -  {zend_container_name} hash of block {ZEND_SNAPSHOT_BLOCK_HEIGHT} has changed from originally "
                                         f"detected hash '{orchestator_zend_snapshot_hash}' to '{current_zend_snapshot_hash}'.\n\n"
                                         "ZEND -  This could indicate unstable network conditions, please confirm the network is stable.\n"
                                         f"ZEND -  To rerun taking the snapshot run 'rm ./{orchestator_zend_snapshot_hash_file.split('/', 2)[2]}' in './deployments/{evmapp_network}'.\n"
                                         "ZEND -  Then restart the snapshotting process by running 'docker-compose up -d'")
                        assert orchestator_zend_snapshot_hash == current_zend_snapshot_hash, assertion_msg
                        # zend ready to snapshot
                        print(f"ZEND -  '{zend_container_name}' snapshot block {ZEND_SNAPSHOT_BLOCK_HEIGHT} with hash {current_zend_snapshot_hash} has been confirmed by at least"
                              f" {ZEND_SNAPSHOT_BLOCK_HEIGHT_MIN_CONF} block confirmations.")
                        print(f"ZEND - Triggering snapshot in '{zend_container_name}' container.")
                        write_str_file(zend_ready_to_snapshot_file, orchestator_zend_snapshot_hash)
                        restart_container(zend_container_name)
                    else:
                        print(f"ZEND -  Waiting for '{zend_container_name}' confirmations, snapshot height - {ZEND_SNAPSHOT_BLOCK_HEIGHT},"
                              f" current height - {zend_cur_height}, target height - {target_height}, remaining - {target_height-zend_cur_height}")
                else:
                    # check snapshot height
                    if zend_cur_height >= ZEND_SNAPSHOT_BLOCK_HEIGHT:
                        detected_hash = call_zend_rpc("getblock", str(ZEND_SNAPSHOT_BLOCK_HEIGHT))["hash"]
                        # RPC call balance is type Decimal()
                        zend_sidechain_balance_satoshi = int(call_zend_rpc("getscinfo", SCNODE_GENESIS_SCID, True, False)["items"][0]["balance"] * 10**8)
                        if NETWORK == "testnet":
                            zend_sidechain_balance_satoshi += int(call_zend_rpc("getscinfo", PREGOBI_SCID, True, False)["items"][0]["balance"] * 10**8)
                        print(f"ZEND -  '{zend_container_name}' snapshot block {ZEND_SNAPSHOT_BLOCK_HEIGHT} reached. Detected block hash - {detected_hash}")
                        print("ZEND - Capturing zend active sidechain balances at snapshot block height.")
                        write_str_file(orchestator_zend_snapshot_hash_file, detected_hash)
                        write_str_file(zend_snapshot_scid_balance_file, str(zend_sidechain_balance_satoshi))
                    else:
                        print(f"ZEND -  Waiting to reach '{zend_container_name}' snapshot height - {ZEND_SNAPSHOT_BLOCK_HEIGHT}, current height - {zend_cur_height}, remaining - {ZEND_SNAPSHOT_BLOCK_HEIGHT-zend_cur_height}")
                # if chain is fully synced return height for main_interval update interval adjustment, if we're syncing but close to the snapshot always return height
                if blockchaininfo["verificationprogress"] > Decimal("0.99999") or zend_cur_height >= ZEND_SNAPSHOT_BLOCK_HEIGHT - 7:
                    return zend_cur_height
            else:
                print(f"ZEND -  Waiting for '{zend_container_name}' container RPC to be ready.")
    else:
        print(f"ZEND -  Waiting for '{zend_container_name}' container to complete reseeding.")
    return None

# take evmapp snapshot
def get_evmapp_snapshot():
    evmapp_running = get_container_status(evmapp_container_name) == "running"
    if not evmapp_running:
        start_container(evmapp_container_name)
    evmapp_reseed_complete = path_exists(evmapp_reseed_status_file)
    if evmapp_reseed_complete:
        evmapp_rpc_ready = call_evmapp_rpc("eth_blockNumber")
        if evmapp_rpc_ready:
            response = call_evmapp_rest("/mainchain/bestBlockReferenceInfo")
            if not response:
                return
            evmapp_mc_ref_height = response["blockReferenceInfo"]["height"]
            orchestator_zend_snapshot_hash = False
            if path_exists(orchestator_zend_snapshot_hash_file):
               orchestator_zend_snapshot_hash = read_str_file(orchestator_zend_snapshot_hash_file)
            # check if snapshot mc ref height has seen enough confirmations
            if orchestator_zend_snapshot_hash:
                # snapshot height confirmed
                if evmapp_mc_ref_height >= target_mc_ref_height:
                    # sanity check
                    response = call_evmapp_rest("/mainchain/blockReferenceInfoBy", {"height":ZEND_SNAPSHOT_BLOCK_HEIGHT,"format":True})
                    if not response:
                        return
                    block_reference = response["blockReferenceInfo"]
                    block_ref_mc_hash = block_reference["hash"]
                    block_ref_sc_hash = block_reference["mainchainReferenceDataSidechainBlockId"]
                    assertion_msg = ("EVMAPP - Mainchain block reference hash mismatch!\n"
                                     f"EVMAPP - Expected: {orchestator_zend_snapshot_hash}\n"
                                     F"EVMAPP - Detected: {block_ref_mc_hash}")
                    assert orchestator_zend_snapshot_hash == block_ref_mc_hash, assertion_msg
                    response = call_evmapp_rest("/block/findById", {"blockId":block_ref_sc_hash})
                    if not response:
                        return
                    evmapp_snapshot_height = response["height"]
                    if not path_exists(evmapp_snapshot_path):
                        os.mkdir(evmapp_snapshot_path)
                    # evmapp ready for snapshot
                    print(f"EVMAPP - Snapshot block {evmapp_snapshot_height} with hash {block_ref_sc_hash} has been confirmed by at least"
                          f" {ZEND_SNAPSHOT_BLOCK_HEIGHT_MIN_CONF - evmapp_mc_ref_delay} mainchain block reference confirmations.\nEVMAPP - Taking snapshot with '{evmapp_container_name}' container.")
                    response = call_evmapp_rpc("zen_dump",["0x" + block_ref_sc_hash, evmapp_snapshot_file])
                    if response and not ("error" in response and response["error"]) and response["result"] == None:
                        print(f"EVMAPP - '{evmapp_container_name}' dump response:", response)
                        if path_exists(evmapp_snapshot_file):
                            write_str_file(evmapp_snapshot_complete_file, str(evmapp_snapshot_height))
                    elif "error" in response and response["error"]:
                        print(f"EVMAPP - Error: '{evmapp_container_name}' dump request failed with error:", response["error"])
                    else:
                        print(f"EVMAPP - Error: '{evmapp_container_name}' dump request failed.")
                # snashot height reached
                elif evmapp_mc_ref_height >= ZEND_SNAPSHOT_BLOCK_HEIGHT:
                    response = call_evmapp_rest("/mainchain/blockReferenceInfoBy", {"height":ZEND_SNAPSHOT_BLOCK_HEIGHT,"format":True})
                    if not response:
                        return
                    block_reference = response["blockReferenceInfo"]
                    block_ref_sc_hash = block_reference["mainchainReferenceDataSidechainBlockId"]
                    response = call_evmapp_rest("/block/findById", {"blockId":block_ref_sc_hash})
                    if not response:
                        return
                    evmapp_snapshot_height = response["height"]
                    response = call_evmapp_rest("/block/best")
                    if not response:
                        return
                    evmapp_curr_height = response["height"]
                    print(f"EVMAPP - Waiting for confirmations, '{evmapp_container_name}' snapshot height - {evmapp_snapshot_height},"
                              f" current height - {evmapp_curr_height}, target mc block ref height delta - {target_mc_ref_height - evmapp_mc_ref_height}")
                else:
                    print(f"EVMAPP - Waiting for confirmations, snapshot mc block ref height - {ZEND_SNAPSHOT_BLOCK_HEIGHT},"
                          f" current mc block ref height - {evmapp_mc_ref_height}, target mc block ref height - {target_mc_ref_height}")
        else:
            print(f"EVMAPP - Waiting for '{evmapp_container_name}' container RPC to be ready.")
    else:
        print(f"EVMAPP - Waiting for '{evmapp_container_name}' container to complete reseeding.")

# get evmapp forger stakes
def get_evmapp_stakes_snapshot():
    rpc_url = f"http://{evmapp_container_name}:{SCNODE_REST_PORT}/ethv1"
    evmapp_snapshot_height = read_str_file(evmapp_snapshot_complete_file)
    if not path_exists(evmapp_snapshot_path):
        os.mkdir(evmapp_snapshot_path)
    evmapp_running = get_container_status(evmapp_container_name) == "running"
    if not evmapp_running:
        start_container(evmapp_container_name)
    evmapp_reseed_complete = path_exists(evmapp_reseed_status_file)
    if evmapp_reseed_complete:
        evmapp_rpc_ready = call_evmapp_rpc("eth_blockNumber")
        if evmapp_rpc_ready:
            print(f"STAKES - taking '{evmapp_container_name}' stakes snapshot at height '{evmapp_snapshot_height}.'")
            _ = execute_external_command("get_all_forger_stakes", evmapp_snapshot_height, rpc_url, evmapp_stakes_file)
            if path_exists(evmapp_stakes_file):
                write_str_file(evmapp_stakes_complete_file)
                if not DEBUG:
                    stop_container_if_running(evmapp_container_name)
        else:
            print(f"STAKES - Waiting for '{evmapp_container_name}' container RPC to be ready.")
    else:
        print(f"STAKES - Waiting for '{evmapp_container_name}' container to complete reseeding.")


# ------------------------------------------------------------------------------------------------
# snapshot transform methods

# tramsform zend snapshot to format accepted by ZendBackupVault.sol
def run_zend_to_horizen():
    print("TRANSFORM - running zend_to_horizen.")
    _ = execute_external_command("zend_to_horizen", zend_snapshot_file, automappings_file, zend_vault_file, evmapp_vault_file)
    if path_exists(zend_vault_file) and path_exists(evmapp_vault_file):
        write_str_file(zend_to_horizen_complete_file)

# tramsform evmapp snapshot to format accepted by EONBackupVault.sol
def run_setup_eon2_json():
    print("TRANSFORM - running setup_eon2_json.")
    _ = execute_external_command("setup_eon2_json", evmapp_snapshot_file, evmapp_stakes_file, evmapp_vault_file, evmapp_accounts_file)
    if path_exists(evmapp_accounts_file):
        write_str_file(setup_eon2_json_complete_file)


# ------------------------------------------------------------------------------------------------
# snapshot verification methods

def run_check_addresses_balance_from_eon():
    print("CHECK - running check_addresses_balance_from_eon.")
    _ = execute_external_command("check_addresses_balance_from_eon", evmapp_snapshot_file, evmapp_stakes_file, evmapp_vault_file, evmapp_accounts_file)
    write_str_file(check_addresses_balance_from_eon_complete_file)

def run_check_addresses_balance_from_zend():
    print("CHECK - running check_addresses_balance_from_zend.")
    _ = execute_external_command("check_addresses_balance_from_zend", zend_snapshot_file, automappings_file, zend_vault_file, evmapp_vault_file)
    write_str_file(check_addresses_balance_from_zend_complete_file)

def run_check_total_balance_from_zend():
    print("CHECK - running check_total_balance_from_zend.")
    zend_sidechain_balance_satoshi = read_str_file(zend_snapshot_scid_balance_file)
    _ = execute_external_command("check_total_balance_from_zend", str(ZEND_SNAPSHOT_BLOCK_HEIGHT), zend_snapshot_file, str(zend_sidechain_balance_satoshi), NETWORK)
    write_str_file(check_total_balance_from_zend_complete_file)


# ------------------------------------------------------------------------------------------------
# snapshot cumulative migration hash generation for verification through vault smart contracts

def run_migrationhash(source: str):
    network = "evmapp" if source == "eon" else "zend"
    json_file = evmapp_accounts_file
    out_file = migrationhash_evmapp_file
    complete_file = migrationhash_evmapp_complete_file
    if network == "zend":
        json_file = zend_vault_file
        out_file = migrationhash_zend_file
        complete_file = migrationhash_zend_complete_file
    print(f"MIGRATIONHASH - running migrationhash for {network}.")
    result = execute_external_command("migrationhash", json_file, source)
    if result:
        print(f"MIGRATIONHASH - calculated migrationhash '{result.rstrip()}' for {json_file}.")
        print(f"MIGRATIONHASH - migrationhash written to './{out_file.split('/', 2)[2]}'.")
        write_str_file(out_file, result.rstrip())
        write_str_file(complete_file)


# ------------------------------------------------------------------------------------------------
# debug and helper section

# helpers to start over
# WARNING: ON 'FORCE_NEW_SNAPSHOT' SNAPSHOT, TRANSFORM AND STATE FILES ARE DELETED
# ON 'FORCE_RESEED' NODES ARE RESEEDED BUT DOWNLOADED SEEDS ARE KEPT

remove_dirs = []
remove_files = []

if FORCE_NEW_SNAPSHOT:
    remove_dirs += [
        zend_snapshot_path,
        evmapp_snapshot_path
    ]

    remove_files += [
        zend_ready_to_snapshot_file,
        zend_snapshot_complete_file,
        zend_snapshot_scid_balance_file,
        evmapp_snapshot_complete_file,
        evmapp_stakes_complete_file,
        orchestator_zend_snapshot_hash_file,
        zend_to_horizen_complete_file,
        zend_vault_file,
        evmapp_accounts_file,
        setup_eon2_json_complete_file,
        check_addresses_balance_from_eon_complete_file,
        check_addresses_balance_from_zend_complete_file,
        check_total_balance_from_zend_complete_file,
        migrationhash_zend_complete_file,
        migrationhash_evmapp_complete_file,
        migrationhash_zend_file,
        migrationhash_evmapp_file
    ]

if FORCE_RESEED:
    remove_files += [
        zend_reseed_status_file,
        evmapp_reseed_status_file
    ]

if FORCE_NEW_SNAPSHOT or FORCE_RESEED:
    if FORCE_NEW_SNAPSHOT:
        print("DEBUG - Reinitializing snapshotting process and starting from scratch!")
    import shutil
    for dir in remove_dirs:
        if path_exists(dir):
            shutil.rmtree(dir, ignore_errors=True)
    for file in remove_files:
        if path_exists(file):
            os.remove(file)
    if FORCE_RESEED:
        print("DEBUG - Forcing reseed of nodes from downloaded seeds!")
        containers = [zend_container_name, evmapp_container_name]
        for container in containers:
            running = get_container_status(container) == "running"
            if running:
                restart_container(container)
            else:
                start_container(container)


# ------------------------------------------------------------------------------------------------
# main program logic

def main():
    # signal handling
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    complete = False
    zend_notified = False
    evmapp_notified = False
    evmapp_stakes_notified = False
    zend_to_horizen_notified = False
    setup_eon2_json_notified = False
    check_addresses_balance_from_eon_notified = False
    check_addresses_balance_from_zend_notified = False
    check_total_balance_from_zend_notified = False
    migrationhash_zend_notified = False
    migrationhash_evmapp_notified = False

    main_interval_default = main_interval = 10
    main_interval_waiting = 150
    main_interval_snapshot = 1

    while not complete:
        # zend snapshot
        zend_snapshot_complete = path_exists(zend_snapshot_complete_file)
        if zend_snapshot_complete:
            if not zend_notified:
                print(f"ORCHESTRATOR - '{zend_container_name}' snapshot complete. File written to './{zend_snapshot_file.split('/', 2)[2]}'")
                zend_notified = True
        else:
            height = get_zend_snapshot()
            # adjust main_interval based on closeness to snapshot block height or confirmation block height
            if type(height) == int and ZEND_SNAPSHOT_BLOCK_HEIGHT - height > 7:
                notify = main_interval != main_interval_waiting
                main_interval = main_interval_waiting
                if notify:
                    print(f"ORCHESTRATOR - {ZEND_SNAPSHOT_BLOCK_HEIGHT - height} blocks remaining until {zend_container_name} snapshot height. Increasing orchestrator update interval to {main_interval} seconds.")
            if type(height) == int and 2 < ZEND_SNAPSHOT_BLOCK_HEIGHT - height <= 7:
                notify = main_interval != main_interval_default
                main_interval = main_interval_default
                if notify:
                    print(f"ORCHESTRATOR - {ZEND_SNAPSHOT_BLOCK_HEIGHT - height} blocks remaining until {zend_container_name} snapshot height. Decreasing orchestrator update interval to {main_interval} seconds.")
            if type(height) == int and 0 < ZEND_SNAPSHOT_BLOCK_HEIGHT - height <= 2:
                notify = main_interval != main_interval_snapshot
                main_interval = main_interval_snapshot
                if notify:
                    print(f"ORCHESTRATOR - {ZEND_SNAPSHOT_BLOCK_HEIGHT - height} blocks remaining until {zend_container_name} snapshot height. Decreasing orchestrator update interval to {main_interval} second.")
            if type(height) == int and ZEND_SNAPSHOT_BLOCK_HEIGHT <= height < target_height - 2:
                notify = main_interval != main_interval_waiting
                main_interval = main_interval_waiting
                if notify:
                    print(f"ORCHESTRATOR - {target_height - height} blocks remaining until {zend_container_name} snapshot block is confirmed. Increasing orchestrator update interval to {main_interval} seconds.")
            if type(height) == int and ZEND_SNAPSHOT_BLOCK_HEIGHT <= height >= target_height - 2 and height < target_height:
                notify = main_interval != main_interval_default
                main_interval = main_interval_default
                if notify:
                    print(f"ORCHESTRATOR - {target_height - height} blocks remaining until {zend_container_name} snapshot block is confirmed by {ZEND_SNAPSHOT_BLOCK_HEIGHT_MIN_CONF} blocks. Decreasing orchestrator update interval to {main_interval} seconds.")
            if type(height) == int and height >= target_height:
                notify = main_interval != main_interval_snapshot
                main_interval = main_interval_snapshot
                if notify:
                    print(f"ORCHESTRATOR - confirmation height reached. Decreasing orchestrator update interval to {main_interval} seconds.")

        # evmapp snapshot
        evmapp_snapshot_complete = path_exists(evmapp_snapshot_complete_file)
        if zend_snapshot_complete and not evmapp_snapshot_complete:
            get_evmapp_snapshot()
            evmapp_snapshot_complete = path_exists(evmapp_snapshot_complete_file)
        if evmapp_snapshot_complete:
            if not evmapp_notified:
                print(f"ORCHESTRATOR - '{evmapp_container_name}' snapshot complete. File written to './{evmapp_snapshot_file.split('/', 2)[2]}'")
                evmapp_notified = True

        # evmapp stakes
        evmapp_stakes_complete = path_exists(evmapp_stakes_complete_file)
        if evmapp_snapshot_complete and not evmapp_stakes_complete:
            get_evmapp_stakes_snapshot()
            evmapp_stakes_complete = path_exists(evmapp_stakes_complete_file)
        if evmapp_stakes_complete:
            if not evmapp_stakes_notified:
                print(f"ORCHESTRATOR - '{evmapp_container_name}' stakes snapshot complete. File written to './{evmapp_stakes_file.split('/', 2)[2]}'")
                evmapp_stakes_notified = True

        snapshots_complete = zend_snapshot_complete and evmapp_snapshot_complete and evmapp_stakes_complete

        # zend_to_horizen transform
        zend_to_horizen_complete = path_exists(zend_to_horizen_complete_file)
        if snapshots_complete and not zend_to_horizen_complete:
            run_zend_to_horizen()
            zend_to_horizen_complete = path_exists(zend_to_horizen_complete_file)
        if zend_to_horizen_complete:
            if not zend_to_horizen_notified:
                print(f"ORCHESTRATOR - zend_to_horizen transformation complete. Files written './{zend_vault_file.split('/', 2)[2]}' and './{evmapp_vault_file.split('/', 2)[2]}'")
                zend_to_horizen_notified = True

        # setup_eon2_json transform
        setup_eon2_json_complete = path_exists(setup_eon2_json_complete_file)
        if snapshots_complete and not setup_eon2_json_complete:
            run_setup_eon2_json()
            setup_eon2_json_complete = path_exists(setup_eon2_json_complete_file)
        if setup_eon2_json_complete:
            if not setup_eon2_json_notified:
                print(f"ORCHESTRATOR - setup_eon2_json transformation complete. File written to './{evmapp_accounts_file.split('/', 2)[2]}'")
                zsetup_eon2_json_notified = True

        transforms_complete = zend_to_horizen_complete and setup_eon2_json_complete

        # check_addresses_balance_from_eon check
        check_addresses_balance_from_eon_complete = path_exists(check_addresses_balance_from_eon_complete_file)
        if transforms_complete and not check_addresses_balance_from_eon_complete:
            run_check_addresses_balance_from_eon()
            check_addresses_balance_from_eon_complete = path_exists(check_addresses_balance_from_eon_complete_file)
        if check_addresses_balance_from_eon_complete:
            if not check_addresses_balance_from_eon_notified:
                print("ORCHESTRATOR - check_addresses_balance_from_eon check complete.")
                check_addresses_balance_from_eon_notified = True

        # check_addresses_balance_from_zend check
        check_addresses_balance_from_zend_complete = path_exists(check_addresses_balance_from_zend_complete_file)
        if transforms_complete and not check_addresses_balance_from_zend_complete:
            run_check_addresses_balance_from_zend()
            check_addresses_balance_from_zend_complete = path_exists(check_addresses_balance_from_zend_complete_file)
        if check_addresses_balance_from_zend_complete:
            if not check_addresses_balance_from_zend_notified:
                print("ORCHESTRATOR - check_addresses_balance_from_zend check complete.")
                check_addresses_balance_from_zend_notified = True

        # This test only works reliably if the snapshot block is not yet in the canonical chain and detected by the orchestrator as it is mined, i.e.:
        # 1. ZEND is running and fully sync'd
        # 2. The snapshot block is mined while the orchestrator is running and we are able to store the sidechain balances at the same height (see var zend_sidechain_balance_satoshi)
        # or
        # 3. The sidechain and mainchain hard forks kicking off the migration have happened already disabling forward and backward transfers between mainchain and sidechains.
        #
        # As all of these conditions can not be met before the actual migration, it's possible that between detecting the snapshot block hash, and storing of the sidechain balances
        # transactions are included in mainchain blocks that change the balance of sidechains (forward or backward transfers). Causing this test to fail.
        # This is almost certainly the case if the snapshot block is taken from a block in the past, as we take the sidechain balances at current height, and current height != snapshot height.
        #
        # To skip this test run the orchestrator container with environment variables DEBUG=True and SKIP_CHECK_TOTAL_BALANCE_FROM_ZEND=True
        if not SKIP_CHECK_TOTAL_BALANCE_FROM_ZEND:
            # check_total_balance_from_zend check
            check_total_balance_from_zend_complete = path_exists(check_total_balance_from_zend_complete_file)
            if transforms_complete and not check_total_balance_from_zend_complete:
                run_check_total_balance_from_zend()
                check_total_balance_from_zend_complete = path_exists(check_total_balance_from_zend_complete_file)
            if check_total_balance_from_zend_complete:
                if not check_total_balance_from_zend_notified:
                    print("ORCHESTRATOR - check_total_balance_from_zend check complete.")
                    check_total_balance_from_zend_notified = True
            checks_complete = check_addresses_balance_from_eon_complete and check_addresses_balance_from_zend_complete and check_total_balance_from_zend_complete
        else:
            checks_complete = check_addresses_balance_from_eon_complete and check_addresses_balance_from_zend_complete

        # calculate zend migrationhash
        migrationhash_zend_complete = path_exists(migrationhash_zend_complete_file)
        if checks_complete and not migrationhash_zend_complete:
            run_migrationhash("zend")
            migrationhash_zend_complete = path_exists(migrationhash_zend_complete_file)
        if migrationhash_zend_complete:
            if not migrationhash_zend_notified:
                print(f"ORCHESTRATOR - zend migrationhash generation complete. File written to './{migrationhash_zend_file.split('/', 2)[2]}'")
                migrationhash_zend_notified = True

        # calculate evmapp migrationhash
        migrationhash_evmapp_complete = path_exists(migrationhash_evmapp_complete_file)
        if checks_complete and not migrationhash_evmapp_complete:
            run_migrationhash("eon")
            migrationhash_evmapp_complete = path_exists(migrationhash_evmapp_complete_file)
        if migrationhash_evmapp_complete:
            if not migrationhash_evmapp_notified:
                print(f"ORCHESTRATOR - evmapp migrationhash generation complete. File written to './{migrationhash_evmapp_file.split('/', 2)[2]}'")
                migrationhash_evmapp_notified = True

        migrationhash_complete = migrationhash_zend_complete and migrationhash_evmapp_complete

        complete = snapshots_complete and transforms_complete and checks_complete and migrationhash_complete

        time.sleep(main_interval)

    print("ORCHESTRATOR - Snapshotting complete. Exiting ...")
