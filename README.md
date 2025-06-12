# Horizen Migration Snapshot Automation

This repository contains resources for automatically creating the Horizen to Base migration snapshots with the data from the Horizen Mainchain and EON EVM Sidechain on mainnet or testnet.

---

## Software Requirements

* docker
* docker compose plugin
* jq
* pwgen
* gnu-sed for Darwin distributions

## Hardware Requirements

* x86-64 CPU (no support for ARM based Macs)
* At least 16GB of RAM
* About 40GB of free disk space for Testnet snapshot creation
* About 200GB of free disk space for Mainnet snapshot creation
* Fast internet to speed up downloading of ~90GB of blockchain bootstraps for Mainnet and synchronization of nodes
---

## Setup

Run the init.sh script to initialize the deployment for the first time. Select  the **network** to run (eon or gobi). All other questions can be answered with 'no'.

```shell
./scripts/init.sh

=== Checking all the requirements ===

What network would you like to setup 'eon' (mainnet) or 'gobi' (testnet):
1) eon
2) gobi
#? 2

You have selected: gobi

=== Preparing deployment directory ./gobi ===

=== Creating .env file ===

=== Generating a random throwaway wallet seed phrase ===


=== Setting up the docker containers local user and group ids ===

The uid:gid with which to run the processes inside of the container will default to 1000:1000
Do you want to change the user (please answer 'no' if you're unsure) ? ('yes' or 'no') no

=== Setting up the height targets ===

The testnet snashopt height defaults to 1700420.
Would you like to override the default height? ('yes' or 'no') no

=== Setting up required files in deployment directory ===

=== Initializing and building required docker containers ===

[...]

=== Project has been initialized correctly for gobi testnet network ===

=== RUNNING SNAPSHOTTING PROCESS ===

To start the snapshotting procedure run:

docker compose -f ./deployments/gobi/docker-compose.yml up -d

=== Refer to docs/automated-snapshot.md for details ===
```

The script will generate the required deployment files under the [deployments](../deployments) directory and provide instructions on how to run the compose stack.

---
## Snapshotting workflow
Once all containers have been started the automation will follow this general execution flow:
1. Download a bootstrap and reseed the Mainchain ZEND node
2. Download a bootstrap and reseed the Sidechain EVMAPP node
3. Fully synchronize the ZEND node
4. Check mainchain block height for having reached the snapshot block height
5. Once snapshot block height has been reached, store the snapshot block hash
6. Wait for 100 mainchain block confirmations
7. Take the mainchain snapshot from the snapshot block hash
8. Check snapshot block hash mainchain block reference exists in the sidechain and has been confirmed by at least 94 mainchain block references
9. Take the sidechain snapshot and snapshot of sidechain forger stake balances
10. Transform the snapshot files into the format required by the smart contracts using the [migration-scripts](https://github.com/HorizenOfficial/horizen-migration/tree/main/dump-scripts/python#migration-scripts)
11. Run all migration check scripts from https://github.com/HorizenOfficial/horizen-migration/tree/main/dump-scripts/python/horizen_dump_scripts
12. Calculate and store the migration hashes of the mainchain and sidechain snapshot files required for independently verifying the accuracy of the snapshots using [horizen-migration-check](https://github.com/HorizenOfficial/horizen-migration-check)

---
## Following snapshot progress
You can follow the progress by attaching to the container log stream of the 'orchestrator' container:
```shell
docker compose -f ./deployments/{network}/docker-compose.yml logs -ft orchestrator
```
Or all containers:
```shell
docker compose -f ./deployments/{network}/docker-compose.yml logs -ft --tail=10
```
The following line will be printed by the 'orchestrator' container on completion:
```shell
orchestrator-testnet  | ORCHESTRATOR - Snapshotting complete. Exiting ...
```

---
## Migration Artifacts
Once the snapshotting process is complete containers will be stopped and the migration files will be stored in: `./deployments/{network}/migration-artifacts`
```shell
ls migration-artifacts/
evmapp  gobi.json  gobi.json.migrationhash  zend  zend.json  zend.json.migrationhash
```
---
## Submitting snapshot results
Multiple people from the Horizen team will independently create migration snapshots. Results of these independent snapshots will be compared by the team before importing the snapshots into the smart contracts to ensure everyone arrived at the same migration hash.

If you would like to provide your own independent verification of your snapshot results please follow these steps.
1. Create a PGP key if you don't have one already and setup gpg signing
2. Create detached PGP signatures of the `*.migrationhash` files in the `./deployments/{network}/migration-artifacts/` folder by e.g. running the following:
```shell
for file in ./deployments/gobi/migration-artifacts/*.migrationhash; do
  gpg --detach-sign --output "${file}.asc" "${file}"
done
```
3. Fork the https://github.com/HorizenOfficial/horizen-migration repository on Github, clone it and checkout a new branch with a name of your choice
4. Create a new folder in your local fork `./snapshots/{network (testnet or mainnet)}/signatures/{your_name_here}`
5. Copy all `*.migrationhash` and `*.migrationhash.asc` files from the `migration-artifacts/` folder to `./snapshots/{network (testnet or mainnet)}/signatures/{your_name_here}`.

E.g.:
```
mkdir -p ~/horizen-migration/snapshots/testnet/signatures/cronic
cp ~/horizen-migration-snapshot-automation/deployments/gobi/migration-artifacts/*.migrationhash{,.asc} ~/horizen-migration/snapshots/testnet/signatures/cronic
```
6. Export your PGP public key and store it in the `./snapshots/{network (testnet or mainnet)}/signatures/{your_name_here}` folder, for example:
```shell
gpg --armor --export cronic@horizenlabs.io > ~/horizen-migration/snapshots/testnet/signatures/cronic/cronic.asc
```
7. Commit your local changes and push your branch to Github
8. Open a Pull Request from your fork of the repository to the main branch of https://github.com/HorizenOfficial/horizen-migration

---
## Debug options
You can adjust the following debug options by editing `./deployments/{network}/.env`. These can be useful to reproducibly retake a snapshot at the same height, or to take the snapshot again at a different block height (by editing `ZEND_SNAPSHOT_BLOCK_HEIGHT=` in the same file first).

Run `docker compose up -d` any time you edit `.env` to apply the changes.

```
# Debugging methods. DEBUG=True will expose extra log lines and keep node containers running after completion.
# DEBUG=True && FORCE_NEW_SNAPSHOT=True will delete created balance snapshots and snapshot related .state/ files in
# the ./migration-artifacts directory. This way a snapshot can be retaken easily.
# DEBUG=True && FORCE_RESEED=True will reseed the nodes by force, downloaded files in ./migration-artifacts/.seeds will not be deleted to speed up the reseed.
# DEBUG=True && SKIP_CHECK_TOTAL_BALANCE_FROM_ZEND=True will skip the check_total_balance_from_zend test that has some race conditions.
# See line 721 - 731 code comments in orchestrator/orchestrator.py.
DEBUG=False
FORCE_NEW_SNAPSHOT=False
FORCE_RESEED=False
SKIP_CHECK_TOTAL_BALANCE_FROM_ZEND=False
```

