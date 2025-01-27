import subprocess
import sys
import os
import time
import signal
import docker
import requests
import json
from enum import Enum

# ------------------------------------------------------------------------------------------------
# script variables
COMPOSE_PROJECT_NAME = os.getenv("COMPOSE_PROJECT_NAME")
COMPOSE_PROJECT_DIR = os.getenv("COMPOSE_PROJECT_DIR")
PARACHAIN_SPEC_REL_PATH = "./files/parachain-spec"
ZEND_DUMP_REL_PATH = "./files/dumps/zend"
EON_DUMP_REL_PATH = "./files/dumps/eon"
ZEND_CONTAINER_NAME = os.getenv("ZEND_CONTAINER_NAME", "zend")
ZEND_IP_ADDRESS = os.getenv("ZEND_IP_ADDRESS")
SCNODE_REST_PORT = os.getenv("SCNODE_REST_PORT")
ZEND_DUMPER_CONTAINER_NAME = os.getenv("ZEND_DUMPER_CONTAINER_NAME", "zend-dumper")
EVMAPP_CONTAINER_NAME = os.getenv("EVMAPP_CONTAINER_NAME", "evmapp")
INET_DOCKER_NETWORK = COMPOSE_PROJECT_NAME + "_inet"
ZEND_BLOCK_HEIGHT_TARGET = int(os.getenv("ZEND_BLOCK_HEIGHT_TARGET"))
EVMAPP_BLOCK_HEIGHT_TARGET = int(os.getenv("EVMAPP_BLOCK_HEIGHT_TARGET"))

class ServiceAction(Enum):
    ZEND_DUMP = "zend-dump"
    EON_DUMP = "eon-dump"
    SNAPSHOT_CREATION = "snapshot-creation"

def decimal_to_hex(decimal_number):
    if not isinstance(decimal_number, int) or decimal_number < 0:
        raise ValueError("Input must be a non-negative integer.")
    return hex(decimal_number)

# ------------------------------------------------------------------------------------------------
# manage containers

def start_container(container_name: str):
    client = docker.from_env()
    
    try:
        # Check if the container is running
        container = client.containers.get(container_name)
        if container.status == "running":
            print(f"Container '{container_name}' is already running.")
            return
        else:
            print(f"Container '{container_name}' is found but not running. Restarting...")
            container.start()
    except docker.errors.NotFound:
        print(f"Container '{container_name}' not found. Starting it with docker-compose...")
        try:
            # Start the container with docker-compose
            subprocess.run(
                ["docker", "compose", "-f", "docker-compose.yml", "up", "-d", container_name],
                check=True
            )
            print(f"Container '{container_name}' has been started.")
        except subprocess.CalledProcessError as e:
            print(f"Failed to start the container '{container_name}': {e}")

def stop_container_if_running(container_name: str):
    client = docker.from_env()

    try:
        # Check if the container is running
        container = client.containers.get(container_name)
        if container.status == "running":
            print(f"Container '{container_name}' is running. Stopping it...")
            if container_name == ZEND_DUMPER_CONTAINER_NAME:
                container.kill()
            else:
                container.stop()

            # Wait for the container to stop
            for _ in range(10):  # Check for up to 10 seconds
                container.reload()
                if container.status != "running":
                    print(f"Container '{container_name}' has been stopped.")
                    break
                time.sleep(1)
            else:
                print(f"Container '{container_name}' did not stop within the expected time.")
        else:
            print(f"Container '{container_name}' is already stopped.")
    except docker.errors.NotFound:
        print(f"Container '{container_name}' not found. Nothing to stop.")
    except Exception as e:
        print(f"An error occurred while managing the container '{container_name}': {e}")

# ------------------------------------------------------------------------------------------------
# zend methods

def get_zend_block_height():
    """Retrieve the current block height from the zend container"""
    try:
        result = subprocess.run(
            ["docker", "exec", ZEND_CONTAINER_NAME, "gosu", "user", "zen-cli", "getblockcount"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        print(f"Current zend block height: {int(result.stdout.strip())}")
        return int(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"Error retrieving block height: {e.stderr.strip()}")
        return None
    except ValueError:
        print("Failed to parse block height.")
        return None
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return None

def get_zend_block_hash(block_number):
    """Retrieve the block hash for a specific block number."""
    try:
        result = subprocess.run(
            ["docker", "exec", ZEND_CONTAINER_NAME, "gosu", "user", "zen-cli", "getblockhash", str(block_number)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error retrieving block hash for block {block_number}: {e.stderr.strip()}")
        return None
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return None

def invalidate_block(block_hash):
    """Invalidate a specific block by its hash."""
    try:
        subprocess.run(
            ["docker", "exec", ZEND_CONTAINER_NAME, "gosu", "user", "zen-cli", "invalidateblock", block_hash],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        print(f"Invalidated block with hash {block_hash}.")
    except subprocess.CalledProcessError as e:
        print(f"Error invalidating block {block_hash}: {e.stderr.strip()}")
    except Exception as e:
        print(f"Unexpected error while invalidating block {block_hash}: {str(e)}")

def connect_zend_container():
    """Connect the zend container to the inet network if not already connected."""
    try:
        # Inspect the container to get its current networks
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{json .NetworkSettings.Networks}}", ZEND_CONTAINER_NAME],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        # Parse the output to get the network list
        networks = json.loads(result.stdout)

        # Check if the container is already connected to the target network
        if INET_DOCKER_NETWORK in networks:
            print(f"Container {ZEND_CONTAINER_NAME} is already connected to the network {INET_DOCKER_NETWORK}.")
            return

        # Connect the container to the network
        subprocess.run(
            ["docker", "network", "connect", INET_DOCKER_NETWORK, ZEND_CONTAINER_NAME],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        print(f"Connected container {ZEND_CONTAINER_NAME} to network {INET_DOCKER_NETWORK}.")
    except subprocess.CalledProcessError as e:
        print(f"Error: {e.stderr.strip()}")
    except json.JSONDecodeError:
        print("Error decoding the network details. Ensure the container exists.")
    except Exception as e:
        print(f"Unexpected error: {str(e)}")

def disconnect_zend_container():
    """Disconnect the zend container from the inet network if connected."""
    try:
        # Inspect the container to get its current networks
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{json .NetworkSettings.Networks}}", ZEND_CONTAINER_NAME],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        # Parse the output to get the network list
        networks = json.loads(result.stdout)

        # Check if the container is connected to the target network
        if INET_DOCKER_NETWORK not in networks:
            print(f"Container {ZEND_CONTAINER_NAME} is not connected to the network {INET_DOCKER_NETWORK}.")
            return

        # Disconnect the container from the network
        subprocess.run(
            ["docker", "network", "disconnect", INET_DOCKER_NETWORK, ZEND_CONTAINER_NAME],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        print(f"Disconnected container {ZEND_CONTAINER_NAME} from network {INET_DOCKER_NETWORK}.")
    except subprocess.CalledProcessError as e:
        print(f"Error: {e.stderr.strip()}")
    except json.JSONDecodeError:
        print("Error decoding the network details. Ensure the container exists.")
    except Exception as e:
        print(f"Unexpected error: {str(e)}")

def invalidate_blocks_to_threshold():
    """Invalidate blocks down to the specified threshold."""
    current_height = get_zend_block_height()
    if current_height is None:
        print("Failed to retrieve current block height for invalidation.")
        return

    print(f"Starting block invalidation from height {current_height} to {ZEND_BLOCK_HEIGHT_TARGET}.")
    for block_number in range(current_height, ZEND_BLOCK_HEIGHT_TARGET, -1):
        block_hash = get_zend_block_hash(block_number)
        if block_hash:
            invalidate_block(block_hash)
        else:
            print(f"Skipping block {block_number} due to missing block hash.")

    print("Block invalidation complete. Node should now have a height of the threshold.")

# ------------------------------------------------------------------------------------------------
# evmapp methods

def call_evmapp_ethv1(method, params=None):
    """Call the ethv1 method defined as input field, optional parameters"""
    evmapp_url = f'http://{ZEND_IP_ADDRESS}:{SCNODE_REST_PORT}/ethv1'
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    if params is None:
        params = []

    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1
    }

    try:
        response = requests.post(evmapp_url, headers=headers, json=payload)
        response.raise_for_status() 
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"HTTP request failed: {e}")
        return None
    except ValueError as e:
        print(f"Error processing the response: {e}")
        return None

def get_evmapp_block_height():
    """Retrieve the current block height from the evmapp container calling the eth_blockNumber"""
    response_data = call_evmapp_ethv1('eth_blockNumber')

    if response_data and "result" in response_data:
        hex_block_number = response_data["result"]
        # Convert the hexadecimal block number to decimal
        decimal_block_number = int(hex_block_number, 16)
        print(f"Evmapp block number in decimal: {decimal_block_number}")
    else:
        print("Error: No result field found in the response or request failed.")

def call_zen_dump_ethv1_method():
    """Create the evmapp zen dump calling the zen_dump ethv1 method"""
    hex_eon_height_target = decimal_to_hex(EVMAPP_BLOCK_HEIGHT_TARGET)
    response_data = call_evmapp_ethv1('zen_dump', [hex_eon_height_target, "/tmp/file.json"])
    if response_data:
        print("Zen dump response:", response_data)
    else:
        print("Error: Zen dump request failed.")

def execute_get_all_forger_stakes_script():
    evmapp_url = f'http://{ZEND_IP_ADDRESS}:{SCNODE_REST_PORT}/ethv1'
    get_all_forger_stakes_script_path = "./horizen-scripts/get_all_forger_stakes.py"
    get_all_forger_stakes_script_parameters = [EVMAPP_BLOCK_HEIGHT_TARGET, evmapp_url, f"{EON_DUMP_REL_PATH}/eon_stakes.json"] 
    execute_external_horizen_script(get_all_forger_stakes_script_path, *get_all_forger_stakes_script_parameters)

# ------------------------------------------------------------------------------------------------
# snapshot creation methods

def create_para_spec_json(output_file):
    try:
        command = [
            "docker", "run", "--rm",
            "--entrypoint", "horizen-spec-builder",
            "horizen/horizen-node:0.2.0-dev2-spec-builder",
            "build-spec",
            "--chain", "local",
            "--disable-default-bootnode"
        ]
        print(f"Running Docker command to create {output_file}")
        
        with open(output_file, "w") as outfile:
            subprocess.run(command, check=True, stdout=outfile, text=True)
        
        print(f"JSON file {output_file} created successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to create {output_file} with Docker command.")
        print(f"Command Output:\n{e.output}")
        raise
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise

def execute_setup_eon2_genesis_script():
    setup_eon2_genesis_json_script_path = "./horizen-scripts/setup_eon2_genesis_json.py"
    setup_eon2_genesis_json_script_parameters = [f"{EON_DUMP_REL_PATH}/eon.dump", f"{EON_DUMP_REL_PATH}/eon_stakes.json", f"{ZEND_DUMP_REL_PATH}/utxos.csv", f"{PARACHAIN_SPEC_REL_PATH}/para-spec.json", f"{PARACHAIN_SPEC_REL_PATH}/para-spec-plain.json"] 
    execute_external_horizen_script(setup_eon2_genesis_json_script_path, *setup_eon2_genesis_json_script_parameters)

def create_para_spec_raw(output_file):
    try:
        para_spec_plain_absolute_path = COMPOSE_PROJECT_DIR + "/orchestrator/files/parachain-spec/para-spec-plain.json"

        command = [
            "docker", "run", "--rm",
            "-v", f"{para_spec_plain_absolute_path}:/tmp/para-spec.json",
            "--entrypoint", "horizen-spec-builder",
            "horizen/horizen-node:0.2.0-dev2-spec-builder",
            "build-spec",
            "--chain", "/tmp/para-spec.json",
            "--disable-default-bootnode", "--raw"
        ]
        print(f"Running Docker command to create {output_file}")
        
        with open(output_file, "w") as outfile:
            subprocess.run(command, check=True, stdout=outfile, text=True)
        
        print(f"Raw file {output_file} created successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to create {output_file} with Docker command.")
        print(f"Command Output:\n{e.output}")
        raise
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise

def create_para_genesis_wasm(output_file):
    try:
        para_spec_raw_absolute_path = COMPOSE_PROJECT_DIR + "/orchestrator/files/parachain-spec/para-spec-raw.json"

        command = [
            "docker", "run", "--rm",
            "-v", f"{para_spec_raw_absolute_path}:/tmp/para-spec-raw.json",
            "--entrypoint", "horizen-spec-builder",
            "horizen/horizen-node:0.2.0-dev2-spec-builder",
            "export-genesis-wasm",
            "--chain", "/tmp/para-spec-raw.json"
        ]
        print(f"Running Docker command to create {output_file}")
        
        with open(output_file, "w") as outfile:
            subprocess.run(command, check=True, stdout=outfile, text=True)
        
        print(f"Raw file {output_file} created successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to create {output_file} with Docker command.")
        print(f"Command Output:\n{e.output}")
        raise
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise

def create_para_genesis_state(output_file):
    try:
        para_spec_raw_absolute_path = COMPOSE_PROJECT_DIR + "/orchestrator/files/parachain-spec/para-spec-raw.json"

        command = [
            "docker", "run", "--rm",
            "-v", f"{para_spec_raw_absolute_path}:/tmp/para-spec-raw.json",
            "--entrypoint", "horizen-spec-builder",
            "horizen/horizen-node:0.2.0-dev2-spec-builder",
            "export-genesis-state",
            "--chain", "/tmp/para-spec-raw.json"
        ]
        print(f"Running Docker command to create {output_file}")
        
        with open(output_file, "w") as outfile:
            subprocess.run(command, check=True, stdout=outfile, text=True)
        
        print(f"Raw file {output_file} created successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to create {output_file} with Docker command.")
        print(f"Command Output:\n{e.output}")
        raise
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise

def execute_external_horizen_script(script_path, *args):
    try:
        command = [sys.executable, script_path] + list(args)
        print(f"Running external script: {script_path} with arguments: {args}")
        subprocess.run(command, check=True, text=True)
        print(f"External script {script_path} executed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to execute {script_path}.")
        print(f"Command Output:\n{e.output}")
        raise
    except Exception as e:
        print(f"Unexpected error while calling external script: {e}")
        raise

# ------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        action = os.getenv("SERVICE_ACTION")

        if action == ServiceAction.ZEND_DUMP.value or not action:

            # manage running instance of zend-dumper, if there is a zend-dumper instance running kill it
            stop_container_if_running(ZEND_DUMPER_CONTAINER_NAME)

            # start zend instance
            start_container(ZEND_CONTAINER_NAME)
            connect_zend_container()
            time.sleep(60)

            # retrieve the current height from zend and compare it to the target
            zend_block_height = get_zend_block_height()
            if zend_block_height <= ZEND_BLOCK_HEIGHT_TARGET:

                # wait till it is synched
                while True:
                    if zend_block_height >= ZEND_BLOCK_HEIGHT_TARGET:
                        disconnect_zend_container()
                        invalidate_blocks_to_threshold()
                        # stop the zend container 
                        stop_container_if_running(ZEND_CONTAINER_NAME)
                        # start the zend-dumper container to create the dump
                        start_container(ZEND_DUMPER_CONTAINER_NAME)
                        break 
                    else:
                        zend_block_height = get_zend_block_height()
                        time.sleep(10)  # check zend block height every 10 seconds


        if action == ServiceAction.EON_DUMP.value or not action:

            # start zend instance
            stop_container_if_running(ZEND_DUMPER_CONTAINER_NAME)
            start_container(ZEND_CONTAINER_NAME)
            connect_zend_container()

            # start evmapp instance
            start_container(EVMAPP_CONTAINER_NAME)
            time.sleep(60)

            # retrieve the current height from evmapp and compare it to the target
            evmapp_block_height = get_evmapp_block_height()
            if evmapp_block_height <= EVMAPP_BLOCK_HEIGHT_TARGET:

                # wait till it is synched
                while True:
                    if zend_block_height >= ZEND_BLOCK_HEIGHT_TARGET:
                        call_zen_dump_ethv1_method()
                        break 
                    else:
                        evmapp_block_height = get_evmapp_block_height()
                        time.sleep(10) # check evmapp block height every 10 seconds

            # create eon_stakes.json file with the eon stakes info
            execute_get_all_forger_stakes_script()
        

        if action == ServiceAction.SNAPSHOT_CREATION.value or not action:
            # step 1: create para-spec.json file with build-spec command
            create_para_spec_json(f"{PARACHAIN_SPEC_REL_PATH}/para-spec.json")
            
            # step 2: fill the para-spec file with the addresses from zend and eon
            execute_setup_eon2_genesis_script()

            # step 3: generate para-spec-raw.json file 
            create_para_spec_raw(f"{PARACHAIN_SPEC_REL_PATH}/para-spec-raw.json")

            # Step 4: generate para-genesis.wasm file with export-genesis-wasm command
            create_para_genesis_wasm(f"{PARACHAIN_SPEC_REL_PATH}/para-genesis.wasm")

            # Step 5: generate para-genesis-state export-genesis-state
            create_para_genesis_state(f"{PARACHAIN_SPEC_REL_PATH}/para-genesis-state")

        # invalid action provided
        if action and action not in {e.value for e in ServiceAction}:
            print(f"Unknown service action: {action}")

    except Exception as e:
        print("Orchestrator service execution failed.")
