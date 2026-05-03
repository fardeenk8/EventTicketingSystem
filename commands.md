# Project commands (Windows PowerShell)

Use this as a **linear checklist** from a fresh setup through running the server. Adjust the path if your project folder is located elsewhere.

---

## 0. One-time: virtual environment and dependencies

```powershell
cd C:\Users\ASHOK\Desktop\Blockchain\EventTicketingSystem

python -m venv venv

.\venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

---

## 1. Environment file (manual step)

In the project root (next to `manage.py`), create or edit `.env`:

```env
PRIVATE_KEY=<Ganache_account_private_key_for_admin>
```

Start **Ganache GUI** with RPC **`http://127.0.0.1:7545`** before smart-contract deploy and before `runserver` (Django connects to Ganache on import).

---

## 2. Smart contract: compile and deploy

```powershell
cd C:\Users\ASHOK\Desktop\Blockchain\EventTicketingSystem\smartcontract

python compile_contract.py
python deploy_contract.py

cd ..
```

---

## 3. Database migrations (and optional superuser)

```powershell
cd C:\Users\ASHOK\Desktop\Blockchain\EventTicketingSystem

python manage.py migrate

python manage.py createsuperuser
```

`createsuperuser` is interactive (username, email, password).

---

## 4. Run the Django development server

**Local only:**

```powershell
python manage.py runserver 127.0.0.1:9000
```

**Listen on all interfaces (same Wi‑Fi / other devices):**

```powershell
python manage.py runserver 0.0.0.0:9000
```

App URL: `http://127.0.0.1:9000/` (or `http://<your-PC-LAN-IP>:9000/` from another device).

---

## Every new terminal session (after initial setup)

```powershell
cd C:\Users\ASHOK\Desktop\Blockchain\EventTicketingSystem
.\venv\Scripts\Activate.ps1
```

Then start **Ganache GUI**, then:

```powershell
python manage.py runserver 127.0.0.1:9000
```

Re-run **compile / deploy** only if you changed the contract or reset Ganache to a new chain. Run **`migrate`** when Django models or migrations change.

---

## If PowerShell blocks `Activate.ps1`

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then run `.\venv\Scripts\Activate.ps1` again.
