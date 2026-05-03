# Decentralized Event Ticketing System DApp

Blockchain-based event ticketing to reduce fraud and duplication: NFT-style tickets on a local chain, Django web app, and MetaMask for payments.

---

## Team

| Team member | CWID | Email |
|-------------|------|--------|
| Fardeen Javed Kachawa | 818313710 | fardeenk@csu.fullerton.edu |
| Siddhesh Manoj Khatavkar | 819929126 | siddheshkhatavkar@csu.fullerton.edu |
| Yash Ashokbhai Savaliya | 861444743 | Yashhsavaliya27@csu.fullerton.edu |
| Sameera Kudligi Mulimani | 813933314 | Sameerakm19@csu.fullerton.edu |

**GitHub:** [github.com/fardeenk8/EventTicketingSystem](https://github.com/fardeenk8/EventTicketingSystem)

---

## Overview

Organizers create events and mint ticket inventory on-chain; users register (with admin activation), connect MetaMask, browse events, pay in ETH for tickets, download QR PDFs, use resale and auctions, and admins validate entry and handle refunds. Stack: **Django**, **SQLite**, **Solidity ERC-721**, **Ganache**, **MetaMask**, **Web3.py**, **ethers.js**.

---

## Improvements (post–initial setup)

Summarized from *Adv_Blockchain_Project_Report.pdf* and the current codebase.

- **Admin UI (Jazzmin)** — Dark-themed Django `/admin/` with branding, sidebar, and clearer navigation.
- **Web3 + Ganache** — `web3`, `python-dotenv`, `reportlab`, `qrcode`; Django talks to the contract for minting and payouts.
- **User vs admin modules** — Separate flows; staff/superusers go to the organizer dashboard after login, regular users to the user home.
- **Admin approval gate** — New registrations are inactive until an admin sets **Active**; pending users see an approval message instead of logging in.
- **Profile & wallet** — `Profile` stores the connected wallet; MetaMask connect on profile/wallet pages.
- **Wallet dashboard** — Shows address and ETH balance via the provider.
- **Event management** — CRUD events, posters, pricing, quantities, mint progress.
- **NFT minting** — ERC-721 mint from admin; DB tickets with empty owner until sold.
- **Primary purchase** — MetaMask sends ETH to the admin wallet; server assigns tickets and stores `tx_hash`.
- **Dynamic pricing** — `event_pricing` API + polling; uses contract helpers when present, else DB price.
- **My tickets, PDF + QR** — `reportlab` + `qrcode` for downloadable tickets.
- **Transaction history** — Purchase records per user.
- **Resale marketplace** — P2P ETH via MetaMask; server updates ownership.
- **Auctions** — App-layer `Auction` / `Bid`; end-auction transfers ticket to highest bidder after checks.
- **Refunds** — User requests; admin approve (on-chain payout) or reject.
- **QR validation** — Admin scanner; validates token/event and marks ticket used.
- **Reports** — Ticket holders, sales summary, sales PDF, analytics dashboard.

See also **`FEATURES_AND_PROGRESS.md`** for a phased checklist.

---

## Tech stack

| Layer | Technologies |
|-------|----------------|
| Blockchain | Solidity, ERC-721, Ganache, MetaMask, Web3.py |
| Backend | Python, Django |
| Database | SQLite |
| Frontend | Django templates, Bootstrap, JavaScript |

---

## Project structure

```text
EventTicketingSystem/
├── Admins/              # Organizer views, events, minting, reports, QR, refunds
├── Backend/             # Settings, URLs
├── Users/               # User views, wallet, marketplace, auctions
├── smartcontract/       # TicketNFT, Hardhat artifacts, deploy scripts
├── static/              # CSS, assets
├── templates/           # HTML templates
├── docs/report_screenshots/   # UI screenshots (from project report PDF)
├── manage.py
├── commands.md          # Command cheat sheet
├── test_plan.md         # Dry-run / QA
└── FEATURES_AND_PROGRESS.md
```

---

## Prerequisites

- Python 3.x  
- [Ganache GUI](https://trufflesuite.com/ganache/) (or compatible local chain on `http://127.0.0.1:7545`)  
- [MetaMask](https://metamask.io)  
- Git  

---

## Setup

1. **Clone**

   ```bash
   git clone https://github.com/fardeenk8/EventTicketingSystem.git
   cd EventTicketingSystem
   ```

2. **Virtual environment**

   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   ```

3. **Dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Ganache** — Start a workspace with RPC **`http://127.0.0.1:7545`**. Copy an account private key (key icon).

5. **`.env`** in the project root:

   ```env
   PRIVATE_KEY=0xYourGanachePrivateKeyHere
   ```

6. **Contract** (with Ganache running):

   ```bash
   cd smartcontract
   python compile_contract.py
   python deploy_contract.py
   cd ..
   ```

7. **Database**

   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

8. **Run server**

   ```bash
   python manage.py runserver 127.0.0.1:9000
   ```

   Open **http://127.0.0.1:9000/**  
   Django admin: **http://127.0.0.1:9000/admin/**  
   Custom organizer area: **http://127.0.0.1:9000/Admins/adminhome/**  

If port `8000` is busy (e.g. Docker), use `9000` or another free port. Ganache must be running before `runserver` because the app connects to the chain at startup.

**MetaMask:** Add network RPC **`http://127.0.0.1:7545`**. Use the chain ID Ganache reports (often **`1337`** via `eth_chainId` even if the GUI shows another network id).

---

## How it works

1. Admin creates an event and mints ticket NFTs + DB rows.  
2. Users connect MetaMask and buy tickets (ETH to admin); tickets attach to their wallet in the app.  
3. Users can list resale, bid in auctions, download PDF/QR, and view transactions.  
4. Admin scans QR for entry and processes refunds; analytics and sales PDFs summarize activity.

---

## Application screenshots

These images were **extracted from the figures embedded in** *Adv_Blockchain_Project_Report.pdf* and saved under **`docs/report_screenshots/`** as `figure_01.png` … `figure_21.png` (same order as the report).

<details>
<summary><strong>Figures 1–7</strong> — Home, auth, admin</summary>

| # | Description |
|---|-------------|
| 1 | Home page — Login / Register |
| 2 | User registration |
| 3 | User login |
| 4 | Django admin dashboard (Jazzmin) |
| 5 | Admin users list |
| 6 | Organizer admin home (`/Admins/adminhome/`) |
| 7 | Browse events (user nav: Profile, Wallet, Events, …) |

![Figure 1](docs/report_screenshots/figure_01.png)

![Figure 2](docs/report_screenshots/figure_02.png)

![Figure 3](docs/report_screenshots/figure_03.png)

![Figure 4](docs/report_screenshots/figure_04.png)

![Figure 5](docs/report_screenshots/figure_05.png)

![Figure 6](docs/report_screenshots/figure_06.png)

![Figure 7](docs/report_screenshots/figure_07.png)

</details>

<details>
<summary><strong>Figures 8–14</strong> — Events, minting, reports, QR, dashboard, refunds</summary>

| # | Description |
|---|-------------|
| 8 | Create event |
| 9 | Event list / mint tickets |
| 10 | Ticket holders |
| 11 | Sales report |
| 12 | QR scanner |
| 13 | Analytics dashboard |
| 14 | Refund requests |

![Figure 8](docs/report_screenshots/figure_08.png)

![Figure 9](docs/report_screenshots/figure_09.png)

![Figure 10](docs/report_screenshots/figure_10.png)

![Figure 11](docs/report_screenshots/figure_11.png)

![Figure 12](docs/report_screenshots/figure_12.png)

![Figure 13](docs/report_screenshots/figure_13.png)

![Figure 14](docs/report_screenshots/figure_14.png)

</details>

<details>
<summary><strong>Figures 15–21</strong> — Buy flow, tickets, marketplace, QR ticket</summary>

| # | Description |
|---|-------------|
| 15 | User events listing |
| 16 | Event detail / buy tickets |
| 17 | My tickets |
| 18 | Marketplace / auctions |
| 19 | Resale listings |
| 20 | Auction winner / resale context |
| 21 | Ticket PDF / QR for scanning |

![Figure 15](docs/report_screenshots/figure_15.png)

![Figure 16](docs/report_screenshots/figure_16.png)

![Figure 17](docs/report_screenshots/figure_17.png)

![Figure 18](docs/report_screenshots/figure_18.png)

![Figure 19](docs/report_screenshots/figure_19.png)

![Figure 20](docs/report_screenshots/figure_20.png)

![Figure 21](docs/report_screenshots/figure_21.png)

</details>

To regenerate images after updating the PDF:

```bash
pip install pymupdf
python extract_report_pdf_images.py "C:\path\to\Adv_Blockchain_Project_Report.pdf"
```

Or replace files in `docs/report_screenshots/` manually. Raw extracts use names `pdf_page##_img#.png`; numbered figures use `figure_##.png`.

---

## Regenerating screenshots from the PDF

Embedded figures were extracted with **PyMuPDF** (`pip install pymupdf`). Use **`extract_report_pdf_images.py`** in the project root with the path to your PDF.

---

## License / academic use

Use appropriate citation if this repository is referenced for coursework or demos.
