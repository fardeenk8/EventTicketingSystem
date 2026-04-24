from web3 import Web3
import json
import os
from dotenv import load_dotenv

load_dotenv()

GANACHE_URL = "http://127.0.0.1:7545"
w3 = Web3(Web3.HTTPProvider(GANACHE_URL))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, "TicketNFT.json"), "r") as f:
    contract_json = json.load(f)

abi = contract_json["abi"]
bytecode = contract_json["bytecode"]

PRIVATE_KEY = os.getenv("PRIVATE_KEY")
if not PRIVATE_KEY:
    raise Exception("PRIVATE_KEY not found in .env file")

account = w3.eth.account.from_key(PRIVATE_KEY)
public_address = account.address

print("Deploying contract from:", public_address)

contract = w3.eth.contract(abi=abi, bytecode=bytecode)

nonce = w3.eth.get_transaction_count(public_address)
tx = contract.constructor().build_transaction({
    "from": public_address,
    "nonce": nonce,
    "gas": 5000000,
    "gasPrice": w3.to_wei('2', 'gwei')
})

signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)

tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

print("Waiting for deployment...")
receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

contract_address = receipt.contractAddress
print("Contract deployed at:", contract_address)

contract_json["address"] = contract_address

with open(os.path.join(BASE_DIR, "TicketNFT.json"), "w") as f:
    json.dump(contract_json, f, indent=2)

print("Updated TicketNFT.json with deployed contract address!")
