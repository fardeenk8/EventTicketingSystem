# Event Ticketing System — Dry Run & Feature Test Plan

This document describes how to dry-run the project locally (**Ganache GUI + MetaMask + Django**) and how to verify implemented features end-to-end.

**Base URL:** `http://127.0.0.1:8000/`  
**Project root:** folder containing `manage.py`

---

## Phase 1 — Environment (once per machine)

### 1. Python virtual environment

```powershell
cd C:\Users\ASHOK\Desktop\Blockchain\EventTicketingSystem
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 2. Ganache GUI

- Start a workspace with RPC **`http://127.0.0.1:7545`** (default Quickstart usually matches).
- Note **Chain ID** (often **5777**).
- Copy **Account #0 private key** (or whichever account you designate as “platform admin”).

### 3. `.env` in project root

Same folder as `manage.py`:

```env
PRIVATE_KEY=<paste_that_private_key_without_quotes>
```

That key funds deploy/mint transactions and defines **`ADMIN_ADDRESS`** (derived from this key—the receiver for primary ticket payments).

### 4. Smart contract (Ganache must be running)

```powershell
cd smartcontract
python compile_contract.py
python deploy_contract.py
cd ..
```

Confirm `smartcontract/TicketNFT.json` contains a non-empty **`address`** field.

### 5. Database & server

```powershell
python manage.py migrate
python manage.py createsuperuser
```

Use this account for admin login (`is_staff` / superuser redirects to the admin dashboard).

```powershell
python manage.py runserver
```

If Django exits with **“Failed to connect to Ganache”**, Ganache is off or not listening on **7545**.

---

## Phase 2 — MetaMask (buyer + optional second user)

1. Add network: **RPC URL** `http://127.0.0.1:7545`, **Chain ID** = value shown in Ganache GUI (often **5777**).
2. Import **at least two** Ganache accounts:
   - **Buyer:** any account with test ETH (Ganache accounts start funded).
   - Prefer an account **different** from the `.env` admin account so primary purchases clearly send ETH **to the admin**.

3. Keep MetaMask on this network whenever you buy tickets or pay on resale.

---

## Phase 3 — Smoke test (minimal path)

| Step | Action | What proves it works |
|------|--------|----------------------|
| 1 | Open `http://127.0.0.1:8000/` → register **User A** (normal user) | Account created |
| 2 | Log in as **superuser** → land on **`/Admins/adminhome/`** | Staff routing works |
| 3 | **`/Admins/create_event/`** — create event (poster, price, total tickets) | Event persisted |
| 4 | **`/Admins/event_list/`** → **Mint tickets** for that event | Ganache shows txs; DB tickets with empty owner |
| 5 | Log in as **User A** → **`/Users/wallet/`** → **Connect Wallet** | Address saved; balance shows |
| 6 | **`/Users/events/`** → event → **Buy ticket(s)** | MetaMask ETH tx to admin; success; ticket assigned |
| 7 | **`/Users/my_tickets/`** | Ticket listed for buyer wallet |
| 8 | **Download ticket** | PDF + QR downloads |

---

## Phase 4 — Feature checklist (implemented behavior)

Verify each row by observing the UI plus Ganache transactions / Django behavior where noted.

### A. Authentication & roles

| Feature | How to verify |
|---------|----------------|
| Register / login | Use public login/register from home |
| Admin vs user | Superuser → `/Admins/adminhome/`; normal user → user area |

### B. Blockchain plumbing

| Feature | How to verify |
|---------|----------------|
| Ganache connectivity | Server starts without `blockchain_utils` connection error |
| Deployed contract | `TicketNFT.json` has `address`; event detail does not say contract missing |
| Mint NFTs | Mint creates txs on Ganache + tickets under **`/Admins/event/<id>/tickets/`** |

### C. Wallet & pricing

| Feature | How to verify |
|---------|----------------|
| Connect MetaMask | **`/Users/userhome/`** or **`/Users/wallet/`** — address updates and persists |
| Balance display | **`/Users/wallet/`** shows ETH after connect |
| Dynamic pricing UI | Event detail shows base/current/sold; refreshes (~8s) via `event_pricing` + contract when deployed |

### D. Primary sale

| Feature | How to verify |
|---------|----------------|
| Pay with MetaMask | Confirm tx sending ETH to **admin address** |
| Ticket assignment | **`/Users/my_tickets/`** and **`/Users/transactions/`** show purchase + `tx_hash` |
| Sold-out guard | Quantity greater than remaining → error |

### E. Secondary market

| Feature | How to verify |
|---------|----------------|
| List resale | List from owned ticket → appears **`/Users/marketplace/`** |
| Buy resale | Second user + wallet → MetaMask sends ETH **to seller** → owner updates in app |

### F. Auctions (app-layer bids)

| Feature | How to verify |
|---------|----------------|
| Create auction | Create auction with valid time window |
| Place bid | Higher bid updates highest bidder (stored in DB) |
| End auction | Seller ends when bids exist → ticket ownership moves to winner in DB |

Use marketplace / auction UI or endpoints under **`/Users/auctions/`** as implemented.

### G. Refunds & admin ops

| Feature | How to verify |
|---------|----------------|
| Refund request | User submits → listing **`/Admins/refunds/`** |
| Approve/reject | Admin actions update request |
| QR verify | **`/Admins/qr_scanner/`** + validate ticket from QR payload |

### H. Reports & users

| Feature | How to verify |
|---------|----------------|
| Ticket holders / sales | **`/Admins/event/<id>/ticket_holders/`**, **`sales_report`**, **`download_sales_report`** |
| User list / activate | **`/Admins/adminhome/`** |

---

## Phase 5 — On-chain vs in-app expectations

- **Primary purchase:** Real MetaMask transaction = ETH transfer **to admin**. Success criteria: payment confirms, DB assigns ticket(s), **`/Users/my_tickets/`** updates.
- **Resale:** Real MetaMask transaction = ETH **to seller**; Django updates ticket owner.
- **Auction bids:** Primarily **database** records unless separate payment flows are added—verify bids, winner, and post-end ownership transfer.

---

## Phase 6 — Troubleshooting

| Symptom | Likely fix |
|---------|------------|
| Django won’t start | Start Ganache GUI first; RPC **7545** |
| Wrong network on buy | MetaMask Chain ID must match Ganache (**1337** or **5777** per frontend check—align MetaMask with Ganache workspace) |
| Buy confirms but assignment fails | Wallet not saved on profile, or no unsold tickets |
| Mint fails | Wrong `PRIVATE_KEY`, Ganache restarted (may need redeploy + DB refresh), or gas issues |

---

## Quick reference URLs

| Area | Path |
|------|------|
| Home | `/` |
| User home | `/Users/userhome/` |
| Wallet | `/Users/wallet/` |
| Browse events | `/Users/events/` |
| My tickets | `/Users/my_tickets/` |
| Transactions | `/Users/transactions/` |
| Marketplace | `/Users/marketplace/` |
| Admin home | `/Admins/adminhome/` |
| Create event | `/Admins/create_event/` |
| Event list | `/Admins/event_list/` |
| QR scanner | `/Admins/qr_scanner/` |
| Refunds | `/Admins/refunds/` |

---

## Ganache GUI reminder

- RPC **`http://127.0.0.1:7545`** matches `smartcontract/blockchain_utils.py` and `deploy_contract.py`.
- **`PRIVATE_KEY`** in `.env` should be one Ganache account private key used as deployer, minter, and primary-sale recipient (**ADMIN_ADDRESS**).
