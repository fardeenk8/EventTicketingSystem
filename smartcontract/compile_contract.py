import json
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARTIFACT_PATH = os.path.join(BASE_DIR, "artifacts", "ticket.sol", "TicketNFT.json")
OUTPUT_PATH = os.path.join(BASE_DIR, "TicketNFT.json")
COMPILE_OUTPUT_PATH = os.path.join(BASE_DIR, "TicketNFT_compile_output.json")

if not os.path.exists(ARTIFACT_PATH):
    raise Exception(
        "Hardhat artifact not found. Run `npx hardhat compile` in smartcontract/ first."
    )

with open(ARTIFACT_PATH, "r") as f:
    artifact = json.load(f)

abi = artifact.get("abi")
bytecode = artifact.get("bytecode")
if not abi or not bytecode:
    raise Exception("Invalid Hardhat artifact: missing abi/bytecode")

existing_address = ""
if os.path.exists(OUTPUT_PATH):
    try:
        with open(OUTPUT_PATH, "r") as f:
            existing = json.load(f)
            existing_address = (existing.get("address") or "").strip()
    except Exception:
        existing_address = ""

with open(COMPILE_OUTPUT_PATH, "w") as f:
    json.dump({"artifact_path": ARTIFACT_PATH, "contractName": artifact.get("contractName")}, f, indent=2)

with open(OUTPUT_PATH, "w") as f:
    json.dump({"abi": abi, "bytecode": bytecode, "address": existing_address}, f, indent=2)

print("Compilation successful from Hardhat artifact. Updated TicketNFT.json")
