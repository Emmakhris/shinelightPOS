# Setting up ShineLight POS in a shop

One computer in the shop (the **shop PC**) runs the POS. Every till, tablet and phone opens it in a web browser over the shop's Wi‑Fi or network cable. Nothing needs to be installed on the tills.

## What you need

- **Shop PC:** Windows 10 or 11, 4 GB RAM or more. It stays switched on during opening hours.
- **Router:** a Wi‑Fi router or network switch that the shop PC and every till connect to. The POS works without internet; only Paystack MoMo prompts need it.
- **Power:** a UPS (battery backup) for the shop PC and the router, strongly recommended. Power cuts are the most common cause of lost or damaged data.
- **Thermal printer:** an 80 mm or 58 mm receipt printer installed as a normal Windows printer on each till. Set it as the default printer and turn off headers and footers in the browser's print settings.
- **Barcode scanner:** any USB scanner that acts as a keyboard (most do).

## 1. Install on the shop PC

1. Install [Python 3.12+](https://www.python.org/downloads/). Tick **Add python.exe to PATH**.
2. Install [Node.js 20+](https://nodejs.org/).
3. Copy the ShineLight POS folder to the shop PC, e.g. `C:\ShineLightPOS`.
4. Open **PowerShell as Administrator** (right-click Start → *Terminal (Admin)*) and run:

   ```powershell
   cd C:\ShineLightPOS
   Set-ExecutionPolicy -Scope Process Bypass
   .\scripts\setup.ps1
   .\scripts\install-service.ps1
   ```

`install-service.ps1` makes the POS start by itself whenever the PC starts, even before anyone logs in. It restarts the POS if it ever stops, backs up every evening at 21:30, and opens the firewall for the tills. It prints the address the tills should use, for example `http://192.168.1.20:8000`.

5. Open that address on the shop PC and complete the setup wizard. Add the business email if you will use Paystack.

## 2. Give the shop PC a fixed address

The tills reach the POS through the shop PC's address. If the router hands the PC a different address after a restart, the tills lose it.

- **Best:** in the router's settings, find **DHCP reservation** (also called "static lease" or "address binding") and reserve the address that `install-service.ps1` printed for the shop PC.
- Make sure the shop network is set to **Private** on the shop PC: *Settings → Network & internet → Wi‑Fi or Ethernet → (your network) → Private network*. On a Public network, Windows blocks the tills. The install script warns you if this is the case.

## 3. Connect each till or tablet

1. Connect it to the same Wi‑Fi or network as the shop PC.
2. Open Chrome or Edge and go to the address, e.g. `http://192.168.1.20:8000`.
3. Bookmark it, or use *Install app / Add to home screen* so it opens full-screen.
4. Each cashier signs in with their PIN. Press **Lock** when leaving the till.

**Wrong PINs:** after 5 wrong PINs in a row, that person is locked out of PIN use for 15 minutes, and the lockout is recorded in the activity log.
- **Locked out of PIN sign-in:** sign in with your username and password instead.
- **A cashier locked out of manager approval:** a manager can sign in at that till and do the action themselves. Other tills are not affected.
- **Check the activity log:** several lockouts for approvals can mean someone is guessing a manager's PIN. If so, change that PIN.

If a till cannot connect, check that the shop PC is on, then open `http://<address>:8000/api/health/` on the till. It should show `"ok": true`.

## 4. Backups: please read

- A backup is taken every evening and when you press **Settings → Backups → Back up now**. The newest 30 are kept in the `backups` folder.
- **Copy the `backups` folder off the shop PC at least once a week**, to a flash drive or cloud storage such as Google Drive or OneDrive. A backup on the same computer does not help if the computer is stolen, damaged or its disk fails.
- The dashboard shows a red warning if no backup has been made for two days.

**To restore a backup** (for example on a replacement PC after running `setup.ps1`):

```powershell
.\scripts\restore.ps1                               # lists the backups
.\scripts\restore.ps1 2026-11-03_213000_daily       # restores that one
```

To move to a new PC, copy the backup folder into `backups` on the new PC first. The data as it was before the restore is saved too, so a restore can be undone.

## 5. Day to day

- **Logs:** if something goes wrong, the details are in the `logs` folder (`server.log`).
- **Updating:** replace the program files (keep `backend\.env`, `backend\db.sqlite3`, `backend\media` and `backups`), then run `.\scripts\setup.ps1` followed by `.\scripts\install-service.ps1`. Database changes are applied automatically when the POS starts.
- **Stopping auto-start:** run `.\scripts\uninstall-service.ps1` as Administrator. This does not delete any data.
- **More than two tills:** consider PostgreSQL instead of the built-in SQLite database (see `backend\.env.example`).
