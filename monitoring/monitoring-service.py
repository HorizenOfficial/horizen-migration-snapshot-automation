import subprocess
import sys
import os
import time
import signal
import docker
import requests
import json

# ------------------------------------------------------------------------------------------------
# env variables
ZEND_CONTAINER_NAME = os.getenv("ZEND_CONTAINER_NAME", "zend")
ZEND_IP_ADDRESS = os.getenv("ZEND_IP_ADDRESS")
SCNODE_REST_PORT = os.getenv("SCNODE_REST_PORT")
ZEND_DUMPER_CONTAINER_NAME = os.getenv("ZEND_DUMPER_CONTAINER_NAME", "zend-dumper")
EVMAPP_CONTAINER_NAME = os.getenv("EVMAPP_CONTAINER_NAME", "evmapp")
INET_DOCKER_NETWORK = os.getenv("INET_DOCKER_NETWORK", "inet")
ZEND_BLOCK_HEIGHT_TARGET = int(os.getenv("ZEND_BLOCK_HEIGHT_TARGET"))
EVMAPP_BLOCK_HEIGHT_TARGET = int(os.getenv("EVMAPP_BLOCK_HEIGHT_TARGET"))

# ------------------------------------------------------------------------------------------------
# manage containers

def ensure_container_running(container_name: str):
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
# snapshot creation methods

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

def disconnect_zend_from_inet():
    """Disconnect the zend container from the inet network."""
    try:
        subprocess.run(
            ["docker", "network", "disconnect", "inet", ZEND_CONTAINER_NAME],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        print(f"Disconnected container {ZEND_CONTAINER_NAME} from network {INET_DOCKER_NETWORK}.")
    except subprocess.CalledProcessError as e:
        print(f"Error disconnecting container: {e.stderr.strip()}")
    except Exception as e:
        print(f"Unexpected error while disconnecting container: {str(e)}")

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
    url = f'http://{ZEND_IP_ADDRESS}:{SCNODE_REST_PORT}/ethv1'
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
        response = requests.post(url, headers=headers, json=payload)
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

def call_zen_dump_etv1_method():
    """Create the evmapp zen dump calling the zen_dump ethv1 method"""
    response_data = call_evmapp_ethv1('zen_dump', ["latest", "/tmp/file.json"])

    if response_data:
        print("Zen dump response:", response_data)
    else:
        print("Error: Zen dump request failed.")

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

def create_para_spec_raw(output_file):
    try:
        para_spec_path = get_para_spec_json_path_from_env()

        command = [
            "docker", "run", "--rm",
            "-v", f"{para_spec_path}:/tmp/para-spec.json",
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
        para_spec_raw_path = get_para_spec_raw_path_from_env()

        command = [
            "docker", "run", "--rm",
            "-v", f"{para_spec_raw_path}:/tmp/para-spec-raw.json",
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
        para_spec_raw_path = get_para_spec_raw_path_from_env()

        command = [
            "docker", "run", "--rm",
            "-v", f"{para_spec_raw_path}:/tmp/para-spec-raw.json",
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

def fill_para_spec_with_dumps_data(script_path, *args):
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

def get_para_spec_json_path_from_env():
    para_spec_path = os.getenv("PARA_SPEC_JSON_PATH")
    if para_spec_path:
        print(f"The para-spec.json absolute path is: {para_spec_path}")
    else:
        print("PARA_SPEC_JSON_PATH environment variable is not set.")
    return para_spec_path

def get_para_spec_raw_path_from_env():
    para_spec_raw_path = os.getenv("PARA_SPEC_RAW_PATH")
    if para_spec_raw_path:
        print(f"The para-spec.json absolute path is: {para_spec_raw_path}")
    else:
        print("PARA_SPEC_RAW_PATH environment variable is not set.")
    return para_spec_raw_path

# ------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        action = os.getenv("SERVICE_ACTION")

        if action == "zend-dump":
            # manage running instance of zend-dumper, if there is a zend-dumper instance running kill it
            stop_container_if_running(ZEND_DUMPER_CONTAINER_NAME)

            # start zend instance
            ensure_container_running(ZEND_CONTAINER_NAME)
            time.sleep(60)

            # retrieve the current height from zend and compare it to the target
            zend_block_height = get_zend_block_height()
            if zend_block_height <= ZEND_BLOCK_HEIGHT_TARGET:

                # wait till it is synched
                while True:
                    if zend_block_height >= ZEND_BLOCK_HEIGHT_TARGET:
                        disconnect_zend_from_inet()
                        invalidate_blocks_to_threshold()
                        # stop the zend container 
                        stop_container_if_running(ZEND_CONTAINER_NAME)
                        # start the zend-dumper container to create the dump
                        ensure_container_running(ZEND_DUMPER_CONTAINER_NAME)
                        break 
                    else:
                        zend_block_height = get_zend_block_height()
                        time.sleep(10)  # check zend block height every 10 seconds

        if action == "eon-dump":

            # start evmapp instance
            ensure_container_running(EVMAPP_CONTAINER_NAME)
            time.sleep(60)

            # retrieve the current height from evmapp and compare it to the target
            evmapp_block_height = get_evmapp_block_height()
            if evmapp_block_height <= EVMAPP_BLOCK_HEIGHT_TARGET:

                # wait till it is synched
                while True:
                    if zend_block_height >= ZEND_BLOCK_HEIGHT_TARGET:
                        call_zen_dump_etv1_method()
                        break 
                    else:
                        evmapp_block_height = get_evmapp_block_height()
                        time.sleep(10) # check evmapp block height every 10 seconds

        if action == "snapshot-creation":
            # step 1: create para-spec.json file with build-spec command
            create_para_spec_json("./files/parachain-spec/para-spec.json")
            
            # step 2: fill the para-spec file with the addresses from zend and eon
            setup_eon2_genesis_json_script_path = "./horizen-scripts/setup_eon2_genesis_json.py"
            setup_eon2_genesis_json_script_parameters = ["./files/dumps/eon/eon.dump", "./files/dumps/eon/eon_stakes.json", "./files/dumps/zend/utxos.csv", "./files/parachain-spec/para-spec.json", "./files/parachain-spec/para-spec-plain.json"] 
            fill_para_spec_with_dumps_data(setup_eon2_genesis_json_script_path, *setup_eon2_genesis_json_script_parameters)

            # step 3: generate para-spec-raw.json file 
            create_para_spec_raw("./files/parachain-spec/para-spec-raw.json")

            # Step 4: generate para-genesis.wasm file with export-genesis-wasm command
            create_para_genesis_wasm("./files/parachain-spec/para-genesis.wasm")

            # Step 5: generate para-genesis-state export-genesis-state
            create_para_genesis_state("./files/parachain-spec/para-genesis-state")

    except Exception as e:
        print("Monitoring service execution failed.")
