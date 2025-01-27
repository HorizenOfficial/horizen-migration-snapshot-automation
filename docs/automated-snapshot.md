# Automated Snapshot
## Setup

Run the init.sh script to initialize the deployment for the first time. Select  the **network** to run (eon or gobi).

```shell
./scripts/init.sh
```

The script will generate the required deployment files under the [deployments](../deployments) directory and provide instructions on how to run the compose stack.

--- 

## Zend seed

Syncing a zend node from scratch may take a few hours,
therefore a seed file can be used to speed up the process.

On start up, the zend node will run the [seed.sh](../scripts/forger/seed/seed.sh) script to check if the seed process is required.

The script will be run if the following conditions are met:

- If **blocks** and **chainstate** directories exists in the **seed** directory and are not empty, the script will attempt to run the seed process.
- If **blocks** or **chainstate** directories or the **.seed.complete** file exist in the node's datadir, the seed process will not be run.
- If `ZEN_FORCE_RESEED` is set to `true` in the `deployments/[eon|gobi]/.env` file, the seed process will be run regardless of the previous condition 
(this will remove the **.seed.complete** file and **blocks** and **chainstate** directories, and force the seed process to be run)

Once the seed process has been run successfully at least once a **.seed.complete** file will be created in the seed directory to prevent the seed process to be run again.

The **blocks** and **chainstate** directories can be added to the `deployments/forger/[eon|gobi]/seed` directory either manually or running the [download_seed.sh](../scripts/forger/seed/download_seed.sh) script.
This directory will be mounted into the zend container and used to seed the node.

### Manually

- Find the seed file url in `deployments/[eon|gobi]/.env` file under the `ZEN_SEED_TAR_GZ_URL` variable.
- Download the seed file and extract it into the `deployments/[eon|gobi]/seed` directory.

### Using the download_seed.sh script

- Run the following command to download and extract the seed file into `deployments/[eon|gobi]/seed` directory:
    ```shell
    ./deployments/[eon|gobi]/scripts/download_seed.sh
    ```
---

## Orchestrator service
The `orchestrator-service` container will take care of spinning up in sequence the correct node and generate the dumps from mainchain and sidechain data. 

The orchestrator service behaviour is regulated by the `SERVICE_ACTION` environment variable. Its value can be `zend-dump`, `eon-dump` or `snapshot-creation` to respectively perform the mainchain dump, the sidechain dump or the creation of the Horizen 2 snapshot with the logic described in the following section. Otherwise its value can be null and in this case the orchestrator-service will perform all the dumps and snapshot creation workflow.

Another values to pass to the orchestrator-service through the environment are the `ZEND_BLOCK_HEIGHT_TARGET` and `EVMAPP_BLOCK_HEIGHT_TARGET` which define the mainchain and sidechain height at which perform the data dump. 
 
--- 

## Running the stack

1. Prerequisites
    - Storage: A minimum of **250 GB** of free space is required to run evmapp and zend nodes on mainnet and around **25 GB** on testnet. 
   Keep in mind that the storage requirements will grow over time.

2. Set the `SERVICE_ACTION` in `.env` file as `zend-dump` and run the `orchestrator-service` container:
    ```shell
    docker compose -f deployments/[eon|gobi]/docker-compose.yml up -d orchestrator-service
    ```
    It will spin up the `zend` container. Let it sync and monitor the situation through docker logs (the `orchestrator-service` will output the zend height at fixed rate) or check it interacting directly with the `zend` container:
    ```shell
    docker compose -f deployments/[eon|gobi]/docker-compose.yml exec zend gosu user zen-cli getblockcount
    ```
    When the zend node will reach the target height defined by `ZEND_BLOCK_HEIGHT_TARGET` variable the `orchestrator-service` will stop it and it will spin up a `zend-dumper` instance that will generate the mainchain data dump. The file called `utxos.csv` will be saved in `deployments/[eon|gobi]/orchestrator/files/dumps/zend` folder. At the end of the file generation process the `orchestrator-service` container will stop.

3. Set the `SERVICE_ACTION` in `.env` file as `eon-dump` and run the `orchestrator-service` container:
    ```shell
    docker compose -f deployments/[eon|gobi]/docker-compose.yml up -d orchestrator-service
    ```
    It will spin up the `zend` and `evmapp` containers. Let the `evmapp` node sync (in this step we assume that the zend node is synchronized with its target height). Monitor the situation through docker logs (the `orchestrator-service` will output the evmapp height at fixed rate) or check it interacting directly with the `evmapp` container:
    ```shell 
    docker compose -f deployments/[eon|gobi]/docker-compose.yml exec evmapp gosu user bash -c 'curl -sXPOST "http://127.0.0.1:[SCNODE_REST_PORT]/block/best" -H "accept: application/json" | jq '.result.height''
    ```
    When the evmapp node will reach the target height defined by `EVMAPP_BLOCK_HEIGHT_TARGET` variable the `orchestrator-service` will generate the sidechain data dump. The files called `eon_stakes.csv` and `eon.dump` will be saved in `deployments/[eon|gobi]/orchestrator/files/dumps/eon` folder. At the end of the files generation process the `orchestrator-service` container will stop.

4. Set the `SERVICE_ACTION` in `.env` file as `snapshot-creation` and run the `orchestrator-service` container:
    ```shell
    docker compose -f deployments/[eon|gobi]/docker-compose.yml up -d orchestrator-service
    ```
    It will generate the Horizen 2 genesis files starting from the initial parachain spec file and the mainchain and sidechain dump files. A custom image docker of the horizen 2 node is used on this step, it is a spec builder image modified to manage large files. The following steps are executed:

    1. generate parachain spec file (`para-spec.json`) executing the build-spec command on the horizen spec builder image.

    2. execute the `setup_eon2_genesis_json.py` script to add mainchain and sidechain addresses/balance to the spec file, this step will create the `para-spec-plain.json` file.

    3. generate parachain raw file (`para-spec-raw.json`) executing the `build-spec` command on the horizen spec builder image with `--raw` flag and passing the `para-spec-plain.json` file as input.

    4. generate parachain wasm file (`para-genesis.wasm`) executing the `export-genesis-wasm` command on the horizen spec builder image passing the `para-spec-raw.json` file as input.

    5. generate the parachain genesis state file (`para-genesis-state`) executing the `export-genesis-state` command on the horizen spec builder image passing the `para-spec-raw.json` file as input.

    All the files will be saved in the `deployments/[eon|gobi]/orchestrator/files/parachain-spec` folder.


5. **NOTE**
    The step number 2 (the one related to `SERVICE_ACTION=zend-dump`) will disconnect the `zend` container from the public internet (`inet` network) and, if necessary, invalidate all the blocks from the tip to the `ZEND_BLOCK_HEIGHT_TARGET` height calling the `invalidateblock` function so that the dumper instance will be able to create the dump file with the correct blockchain state. This means that if the zend node is restarted manually (with `docker compose -f deployments/[eon|gobi]/docker-compose.yml up -d zend`) and the user want to restart the sync process it need to call the `reconsiderblock` function. This can be done with the following process, starting by retrieving the current number:
    ```shell
    docker compose -f deployments/[eon|gobi]/docker-compose.yml exec zend gosu user zen-cli getblockcount
    ```
    call the `getblockhash` function to retrieve the hash
    ```shell
    docker compose -f deployments/[eon|gobi]/docker-compose.yml exec zend gosu user zen-cli getblockhash <block-number>
    ```
    and then call the `reconsiderblock` function passing this hash: 
    ```shell
    docker compose -f deployments/[eon|gobi]/docker-compose.yml exec zend gosu user zen-cli reconsiderblock <block-hash>
    ```
    After that check if the node is receiving new blocks checking the block number again.

---

## Other useful docker commands

- Run the following command to stop the stack:
    ```shell
    docker compose -f deployments/[eon|gobi]/docker-compose.yml stop
    ```
- Run the following command to start the stack again:
    ```shell
    docker compose -f deployments/[eon|gobi]/docker-compose.yml up -d
    ```
- Run the following command to stop the stack and delete the containers:
    ```shell
    docker compose -f deployments/[eon|gobi]/docker-compose.yml down
    ```
- Run the following commands to destroy the stack, **this action will delete your wallet and all the data**:
    ```shell
    docker compose -f deployments/[eon|gobi]/docker-compose.yml down
    docker volume ls # List all the volumes
    docker volume rm [volume_name] # Remove the volumes related to your stack, these volumes are named after the stack name: [COMPOSE_PROJECT_NAME]_[volume-name]
    ```

---
