import datetime
import json
import os
import sys
import csv
import binascii


"""
This script transforms the account data dumped from Eon and Zend in the format requested for the genesis
state in Horizen.
It takes as input:
 - the json file with the data dumped from Eon
 - the json file with the list of Eon delegators and their stakes
 - the csv file with the Zend addresses mapped to Horizen addresses with their balance
 - the Horizen config file.
 - the output filename to be generated

It creates a new Horizen config file with the data from Eon/Zend.
"""

native_smart_contracts = ["0x0000000000000000000011111111111111111111",
						  "0x0000000000000000000022222222222222222222",
						  "0x0000000000000000000022222222222222222333",
						  "0x0000000000000000000044444444444444444444",
						  "0x0000000000000000000088888888888888888888"]

def is_native_smart_contract(account_address):
	return account_address in native_smart_contracts

if len(sys.argv) != 6:
	print(
		"Usage: python3 {} <Eon dump file name> <Eon stakes file name> <Zend dump file name> <Horizen config file> <output_file>"
		.format(os.path.basename(__file__)))
	sys.exit(1)

eon_dump_file_name = sys.argv[1]
eon_stakes_file_name = sys.argv[2]
zend_dump_file_name = sys.argv[3]
horizen_genesis_file_name = sys.argv[4]
result_file_name = sys.argv[5]

with open(eon_dump_file_name, 'r') as eon_dump_file:
	eon_dump_data = json.load(eon_dump_file)

results = {}
# Importing the EON accounts
for account in eon_dump_data['accounts']:
	if not is_native_smart_contract(account):
		source_account_data = eon_dump_data['accounts'][account]
		dest_account_data = {}

		nonce = hex(source_account_data['nonce'])
		dest_account_data["nonce"] = nonce
		balance = int(source_account_data['balance'])
		dest_account_data["balance"] = hex(balance)
		if 'code' in source_account_data:
			code = bytes.fromhex(source_account_data['code'][2:])
			dest_account_data["code"] = list(code)

		if 'storage' in source_account_data:
			dest_account_data["storage"] = source_account_data['storage']
			for key, value in dest_account_data['storage'].items():
				if len(value) < 64:
					dest_account_data['storage'][key] = value.zfill(64)

		results[account.lower()] = dest_account_data
	else:
		source_account_data = eon_dump_data['accounts'][account]
		balance = int(source_account_data['balance'])
		if balance != 0:
			dest_account_data = {}
			nonce = hex(source_account_data['nonce'])
			dest_account_data["nonce"] = nonce
			dest_account_data["balance"] = hex(balance)
			results[account.lower()] = dest_account_data

# Importing the EON stakes
with open(eon_stakes_file_name, 'r') as eon_stakes_file:
	eon_stakes_data = json.load(eon_stakes_file)

for stake in eon_stakes_data.items():
	account = stake[0].lower()
	stake_amount = stake[1]
	if account in results:
		balance = int(results[account]["balance"], 16)
		balance = balance + stake_amount
		results[account]["balance"] = hex(balance)
	else:
		dest_account_data = {"nonce": "0x0",
							 "balance": hex(stake_amount)}
		results[account] = dest_account_data

# Importing Zend balances
zend = {}
with open(zend_dump_file_name, 'r') as zend_dump_file:
	zend_dump_data_reader = csv.reader(zend_dump_file)
	for (horizen_address, balance, zend_address) in zend_dump_data_reader:
		if horizen_address in results:
			print(
				"PANIC: Collision between a Horizen-mapped Zend address and an Eon account! "
				"Horizen Zend address {0}, original Zend address {1}"
				.format(horizen_address, zend_address))
		else:
			zend[horizen_address] = hex(int(balance))

with open(horizen_genesis_file_name, "r") as horizen_genesis_file:
	genesis_data = json.load(horizen_genesis_file)

if "eonRestore" not in genesis_data["genesis"]["runtimeGenesis"]["patch"]:
	genesis_data["genesis"]["runtimeGenesis"]["patch"]["eonRestore"] = {"accounts": {}, "zend": {}}

if "accounts" not in genesis_data["genesis"]["runtimeGenesis"]["patch"]["eonRestore"]:
	genesis_data["genesis"]["runtimeGenesis"]["patch"]["eonRestore"]["accounts"] = {};
if "zend" not in genesis_data["genesis"]["runtimeGenesis"]["patch"]["eonRestore"]:
	genesis_data["genesis"]["runtimeGenesis"]["patch"]["eonRestore"]["zend"] = {};

genesis_data["genesis"]["runtimeGenesis"]["patch"]["eonRestore"]["accounts"].update(results)
genesis_data["genesis"]["runtimeGenesis"]["patch"]["eonRestore"]["zend"].update(zend)

with open(result_file_name, "w") as jsonFile:
	json.dump(genesis_data, jsonFile, indent=4)