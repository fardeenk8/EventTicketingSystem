# Event Ticketing System — Features & Progress Overview

This document summarizes **implemented capabilities** in the codebase (beyond a bare Django scaffold). It is organized as a **progression from foundation → platform → blockchain → polish**. Exact day-by-day history is not in the repo; treat this as a **feature inventory** aligned with what ships today.

---

## Phase A — Core platform (initial Django setup)

| Item | Status | Notes |
|------|--------|--------|
| Django project `Backend` | Done | Settings, URLs, WSGI/ASGI |
| SQLite database | Done | `db.sqlite3` |
| Custom apps `Admins`, `Users` | Done | Split organizer vs attendee flows |
| Templates + static assets | Done | Shared layouts, CSS (`static/css/main.css`) |
| Media uploads | Done | Event posters under `MEDIA_ROOT` |
| Authentication hooks | Done | `LOGIN_URL`, redirects after login |

---

## Phase B — Admin experience & Django admin

| Item | Status | Notes |
|------|--------|--------|
| **django-jazzmin** | Done | Replaces default `/admin/` UI (`Backend/settings.py`: `JAZZMIN_SETTINGS`, dark theme, branding, icons) |
| Django **`/admin/`** | Done | Model registration for auth and apps |
| Custom **Admins** dashboard | Done | `/Admins/adminhome/` — list users, activate/deactivate (`is_active`) |
| User deletion | Done | Staff/superuser-only guard on delete |
| **Broad hosting defaults** | Done | `ALLOWED_HOSTS = ["*"]` for LAN/testing |

---

## Phase C — User identity, gates, and wallet UX

| Item | Status | Notes |
|------|--------|--------|
| Registration + validation | Done | Username/email uniqueness, password confirm (`Backend/views.py`) |
| **Admin approval gate** | Done | New users saved with `is_active=False`; login shows pending message if credentials OK |
| Login routing | Done | Staff/superuser → `/Admins/adminhome/`; others → user home |
| **`Profile` model** | Done | One-to-one `User`, stores connected wallet |
| Auto-create profile | Done | `post_save` signal on `User` |
| **MetaMask: Connect + persist** | Done | `save_wallet` API + buttons on profile/wallet pages |
| Wallet dashboard | Done | Address display + ETH balance via provider (`user_wallet.html`) |
| User home | Done | Summary + connect wallet CTA |

---

## Phase D — Events & ticketing (product flows)

| Item | Status | Notes |
|------|--------|--------|
| **CRUD events (admin)** | Done | Create, edit, delete, list with mint progress |
| Event detail (user) | Done | Poster, meta, quantity, buy flow |
| **Mint inventory** | Done | Admin mint loop: on-chain mint + `Ticket` rows with empty `owner_wallet` until sold |
| **Primary purchase** | Done | Browser: ethers.js → ETH transfer to `ADMIN_ADDRESS`; server: `buy_ticket` assigns tickets + `TicketPurchase` + `tx_hash` |
| **Dynamic pricing UI** | Done | `event_pricing` JSON + event page polling; uses contract views **when** ABI exposes pricing helpers, else falls back to DB event price |
| Browse events | Done | Ordered listing |
| **My tickets** | Done | Filtered by `owner_wallet` |
| **PDF ticket + QR** | Done | `reportlab` + `qrcode`; payload ties token + event (`download_ticket`) |
| **Transaction history** | Done | User’s `TicketPurchase` records |

---

## Phase E — Secondary market & auctions

| Item | Status | Notes |
|------|--------|--------|
| **Resale listing** | Done | Seller lists owned ticket + price (`ResaleTicket`) |
| **Marketplace** | Done | Listings grid; buy path triggers MetaMask **P2P ETH to seller**, then server updates ownership |
| **Auctions (application layer)** | Done | Models `Auction`, `Bid`; create auction, place bid, list/detail APIs, seller **end now** transfers ticket in DB to highest bidder (with wallet checks) |
| Contract capability hint | Done | Marketplace template checks ABI for optional on-chain auction methods (`placeBid`) — **current Solidity in repo** focuses on ERC-721 mint/transfer/redeem, not necessarily those extras |

---

## Phase F — Refunds & entry control

| Item | Status | Notes |
|------|--------|--------|
| User **refund request** | Done | Reason + amount tied to ticket; rejects if not owner or ticket already used |
| Admin refund queue | Done | List requests |
| **Approve refund + on-chain payout** | Done | `send_eth_to_user` via admin key; clears ticket assignment for resale pool |
| Reject refund | Done | Marks processed without payout |
| **QR / validation (admin)** | Done | Scanner UI + `validate_ticket`: checks token/event match, assignment, **marks `Ticket.is_used`** once validated |

---

## Phase G — Reporting & analytics (admin)

| Item | Status | Notes |
|------|--------|--------|
| Ticket holders per event | Done | Wallet + username linkage via `Profile` |
| Sales report | Done | Minted/sold/unsold + ETH sums from purchases |
| **Sales report PDF** | Done | Download buyer summary (`download_sales_report`) |
| **Dashboard** | Done | Aggregate counts + chart-ready series (purchases by date, ETH by event) |

---

## Phase H — Smart contract & toolchain

| Item | Status | Notes |
|------|--------|--------|
| **ERC-721 `TicketNFT`** | Done | OpenZeppelin `ERC721` + `Ownable`; enumerable-style supply helper |
| Mint endpoints | Done | `mintTicket`, richer `mintTicketWithDetails` |
| Metadata | Done | Per-token URI / `baseURI` pattern |
| On-chain lifecycle helpers | Done | `verifyTicket`, `redeemTicket`; events for mint/redeem/verify |
| Transfer rule | Done | Block transferring **redeemed** tickets (`_beforeTokenTransfer`) |
| **Deploy pipeline** | Done | `deploy_contract.py` writes address into `TicketNFT.json` |
| **ABI bridge for Django** | Done | `blockchain_utils.py`: Web3 to Ganache, load ABI/address, **mint with nonce retry**, admin payout helper |
| Env-based operator key | Done | `PRIVATE_KEY` via `python-dotenv` |
| Compile helper | Done | `compile_contract.py` pulls Hardhat artifact into `TicketNFT.json` (expects `npx hardhat compile`) |

---

## Phase I — Docs & operations (repo hygiene)

| Item | Status | Notes |
|------|--------|--------|
| `Readme` | Present | High-level overview |
| `requirements.txt` | Present | Django, jazzmin, web3, dotenv, reportlab, qrcode, pillow, py-solc-x |
| **`test_plan.md`** | Present | Dry-run / QA checklist |
| **`commands.md`** | Present | venv → migrate → deploy → runserver |

---

## Architecture snapshot (how layers fit)

1. **Django** = source of truth for users, events, assignments, resale, auctions, refunds UI.  
2. **Ganache + Web3.py** = deploy/mint/refund payouts keyed off `.env`.  
3. **MetaMask + ethers.js** = user-signed ETH transfers (primary pay admin; resale pay seller).  
4. **ERC-721** = NFT ticket identities minted to operator-controlled workflow (inventory minted to admin wallet in current admin mint path).

---

## Optional next steps (not implemented here)

- Tighten **middleware**: guard all `/Admins/*` routes with `@staff_member_required` (today some views rely on login + UI discipline).  
- Align **on-chain vs DB ownership** for primary sales if full wallet custody per buyer is required.  
- Add **automated tests** (pytest Django + contract mocks).  
- Replace **insecure `SECRET_KEY`** before any real deployment.

---

*Generated from repository structure and code paths (`Backend`, `Admins`, `Users`, `smartcontract`). Update this file when you ship new features.*
