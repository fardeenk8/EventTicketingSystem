import os
import json
import time
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()

GANACHE_URL = "http://127.0.0.1:7545"   
w3 = Web3(Web3.HTTPProvider(GANACHE_URL))

if not w3.is_connected():
    raise Exception("Failed to connect to Ganache at 127.0.0.1:7545")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTRACT_JSON_PATH = os.path.join(BASE_DIR, "TicketNFT.json")

if not os.path.exists(CONTRACT_JSON_PATH):
    raise Exception("TicketNFT.json file not found in smartcontract folder")

with open(CONTRACT_JSON_PATH, "r") as f:
    contract_data = json.load(f)

contract_abi = contract_data["abi"]
raw_address = contract_data.get("address", "").strip()
contract = None
if raw_address:
    contract_address = Web3.to_checksum_address(raw_address)
    contract = w3.eth.contract(address=contract_address, abi=contract_abi)

ADMIN_PRIVATE_KEY = os.getenv("PRIVATE_KEY")

if not ADMIN_PRIVATE_KEY:
    raise Exception("Admin PRIVATE_KEY not found in .env file")

ADMIN_ADDRESS = w3.eth.account.from_key(ADMIN_PRIVATE_KEY).address

def mint_ticket(event_id, to_address=None):
    if contract is None:
        raise Exception("Smart contract address is not configured. Deploy contract first.")

    receiver = to_address or ADMIN_ADDRESS
    try:
        receiver = Web3.to_checksum_address(receiver)
    except Exception:
        raise Exception("Invalid receiver wallet address")

    # Ganache may occasionally throw replacement/non-replacement nonce errors.
    # Retry with fresh pending nonce to keep minting robust.
    receipt = None
    last_error = None
    for _ in range(3):
        try:
            nonce = w3.eth.get_transaction_count(ADMIN_ADDRESS, "pending")
            tx = contract.functions.mintTicket(receiver, int(event_id)).build_transaction({
                "from": ADMIN_ADDRESS,
                "nonce": nonce,
                "gas": 5000000,
                "gasPrice": w3.to_wei('2', 'gwei'),
            })

            signed_tx = w3.eth.account.sign_transaction(tx, ADMIN_PRIVATE_KEY)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            break
        except Exception as e:
            last_error = e
            time.sleep(0.4)

    if receipt is None:
        raise last_error

    transfer_logs = contract.events.Transfer().process_receipt(receipt)
    if not transfer_logs:
        raise Exception("Mint succeeded but token id was not found in logs")

    token_id = int(transfer_logs[0]["args"]["tokenId"])
    return receipt, token_id

def send_eth_to_user(user_wallet, amount_eth):
    try:
        # Convert to checksum format
        to_address = Web3.to_checksum_address(user_wallet)
    except:
        raise Exception("Invalid wallet address format")

    amount_wei = w3.to_wei(amount_eth, "ether")
    nonce = w3.eth.get_transaction_count(ADMIN_ADDRESS)

    tx = {
        'nonce': nonce,
        'to': to_address,
        'value': amount_wei,
        'gas': 500000,
        'gasPrice': w3.eth.gas_price
    }

    signed = w3.eth.account.sign_transaction(tx, ADMIN_PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

    return tx_hash.hex()

