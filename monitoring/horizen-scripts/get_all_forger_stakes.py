import json
import sys
import os
from web3 import Web3

"""
This script retrieves all the stakes in EON network and creates a json file with the list of all
delegators with the total sum of their stakes.
It takes as input the block height at which it retrieves the stakes.

"""

if len(sys.argv) != 4:
	print(
		"Usage: python3 {} <block height> <rpc url> <output_file>"
		.format(os.path.basename(__file__)))
	sys.exit(1)

block_height = int(sys.argv[1])
rpc = sys.argv[2]
result_file_name = sys.argv[3]


w3 = Web3(Web3.HTTPProvider(rpc))

# Contract details
ABI = [
	{
		"inputs": [
			{
				"internalType": "bytes32",
				"name": "signPubKey",
				"type": "bytes32"
			},
			{
				"internalType": "bytes32",
				"name": "vrf1",
				"type": "bytes32"
			},
			{
				"internalType": "bytes1",
				"name": "vrf2",
				"type": "bytes1"
			},
			{
				"internalType": "address",
				"name": "delegator",
				"type": "address"
			},
			{
				"internalType": "uint32",
				"name": "consensusEpochStart",
				"type": "uint32"
			},
			{
				"internalType": "uint32",
				"name": "maxNumOfEpoch",
				"type": "uint32"
			}
		],
		"name": "stakeTotal",
		"outputs": [
			{
				"internalType": "uint256[]",
				"name": "listOfStakes",
				"type": "uint256[]"
			}
		],
		"stateMutability": "view",
		"type": "function"
	},
	{
		"inputs": [
			{
				"internalType": "int32",
				"name": "startIndex",
				"type": "int32"
			},
			{
				"internalType": "int32",
				"name": "pageSize",
				"type": "int32"
			}
		],
		"name": "getPagedForgers",
		"outputs": [
			{
				"internalType": "int32",
				"name": "nextIndex",
				"type": "int32"
			},
			{
				"components": [
					{
						"internalType": "bytes32",
						"name": "signPubKey",
						"type": "bytes32"
					},
					{
						"internalType": "bytes32",
						"name": "vrf1",
						"type": "bytes32"
					},
					{
						"internalType": "bytes1",
						"name": "vrf2",
						"type": "bytes1"
					},
					{
						"internalType": "uint32",
						"name": "rewardShare",
						"type": "uint32"
					},
					{
						"internalType": "address",
						"name": "reward_address",
						"type": "address"
					}
				],
				"internalType": "struct ForgerStakesV2.ForgerInfo[]",
				"name": "listOfForgerInfo",
				"type": "tuple[]"
			}
		],
		"stateMutability": "view",
		"type": "function"
	},
	{
		"inputs": [
			{
				"internalType": "bytes32",
				"name": "signPubKey",
				"type": "bytes32"
			},
			{
				"internalType": "bytes32",
				"name": "vrf1",
				"type": "bytes32"
			},
			{
				"internalType": "bytes1",
				"name": "vrf2",
				"type": "bytes1"
			},
			{
				"internalType": "int32",
				"name": "startIndex",
				"type": "int32"
			},
			{
				"internalType": "int32",
				"name": "pageSize",
				"type": "int32"
			}
		],
		"name": "getPagedForgersStakesByForger",
		"outputs": [
			{
				"internalType": "int32",
				"name": "nextIndex",
				"type": "int32"
			},
			{
				"components": [
					{
						"internalType": "address",
						"name": "delegator",
						"type": "address"
					},
					{
						"internalType": "uint256",
						"name": "stakedAmount",
						"type": "uint256"
					}
				],
				"internalType": "struct ForgerStakesV2.StakeDataDelegator[]",
				"name": "listOfDelegatorStakes",
				"type": "tuple[]"
			}
		],
		"stateMutability": "view",
		"type": "function"
	}

]

contract_address = '0x0000000000000000000022222222222222222333'
contract = w3.eth.contract(address=contract_address, abi=ABI)

forgers = []
index = 0
page_size = 10
while index != -1:
	results = contract.functions.getPagedForgers(index, page_size).call(block_identifier=block_height)
	(index, forger_data) = results
	forgers = forgers + list(map(lambda data: data[:3], forger_data))

page_size = 10
stakes = {}
for forger in forgers:
	index = 0
	while index != -1:
		results = contract.functions.getPagedForgersStakesByForger(forger[0], forger[1],
														  forger[2], index, page_size).call(block_identifier=block_height)
		(index, forger_stakes) = results
		for (owner, amount) in forger_stakes:
			if owner in stakes:
				stakes[owner] = stakes[owner] + amount
			else:
				stakes[owner] = amount

# Checking that the total amount is correct
total = contract.functions.stakeTotal("0x0000000000000000000000000000000000000000000000000000000000000000",
										"0x0000000000000000000000000000000000000000000000000000000000000000",
										"0x00",
										"0x0000000000000000000000000000000000000000",
										0,
										0
										).call(block_identifier=block_height)
total_stakes = 0
for key, value in stakes.items():
	total_stakes = total_stakes + value

assert total_stakes == total[0]

with open(result_file_name, "w") as jsonFile:
	json.dump(stakes, jsonFile, indent=4)
