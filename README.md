# ShineLight POS

A point-of-sale system for Ghanaian retail shops and restaurants. It is installed once per business: one computer runs the server, and every till, tablet or phone on the shop network uses it in a web browser.

## What it does (Phase 1)

### Selling
- **Retail register:** barcode scanning, product search and category grid.
- **Sale adjustments:** line and whole-sale discounts, price overrides, and hold/recall of sales.
- **Payments:** split tenders across cash (with change), MTN MoMo / Telecel Cash / AT Money (with a reference), card, bank transfer, customer credit and loyalty points.

### Restaurant
- **Tables:** a floor plan with tables, plus open orders for dine-in, takeaway and delivery.
- **Order handling:** modifiers (e.g. "Protein: Chicken +15"), and kitchen tickets that list only new food items.
- **Table management:** move or merge tables, print the bill, then pay.

### Records and control
- **Receipts:** printed for 80 mm or 58 mm thermal printers through the browser. Receipts and refund slips can be reprinted.
- **Ghana taxes:** VAT, NHIL and GETFund are configurable. Prices can include tax or have it added. Each product is standard-rated, zero-rated or exempt.
- **Shifts:** an opening float; cash in, cash out and drops; expected vs. counted cash; X and Z reports.
- **Refunds and voids:** full or partial, with restocking. They need a manager PIN and are recorded in the activity log.

### Back office
- **Inventory:** stock levels, adjustments with reasons, stock counts, movement history, suppliers, and purchase orders with goods receiving.
- **Customers:** loyalty points, credit accounts with limits, and repayments.
- **Reports:**
  - Sales, profit and margin by day and hour, product, category, staff and payment method (including MoMo by network).
  - A tax report for VAT returns, stock valuation and an end-of-day report.
  - CSV export for each report.
- **Staff:** roles (owner, manager, cashier, waiter), quick PIN sign-in, the till lock screen, and an audit log.
- **Setup and admin:** a first-run setup wizard with optional demo data, the Django admin at `/admin/`, and a backup script.

> **Tax rates:** the defaults are VAT 15%, NHIL 2.5% and GETFund 2.5%, all charged on the item value. Ghana's levy rules have changed several times, so confirm the current rates and whether any tax compounds with GRA or your accountant, then adjust them in **Settings → Taxes**.

## Install on the shop computer (Windows)

You need [Python 3.12+](https://www.python.org/downloads/) and [Node.js 20+](https://nodejs.org/).

In PowerShell **as Administrator**:

```powershell
.\scripts\setup.ps1             # installs everything, creates backend\.env, builds the app
.\scripts\install-service.ps1   # starts with Windows, restarts if it stops, nightly backups, firewall
```

Open the address that `install-service.ps1` prints and follow the setup wizard. **[docs/SHOP-SETUP.md](docs/SHOP-SETUP.md)** is the full guide for the shop owner: a fixed address for the shop PC, connecting tills, printers, backups and restoring.

To try the POS without installing it as a start-up task, run `.\scripts\run.ps1` instead (it stops when the window closes).

**Several tills:** SQLite works well for one or two tills. For more, install PostgreSQL and set `DATABASE_URL` in `backend\.env` (see `backend\.env.example`).

**Backups:** these run every evening once the service is installed, or on demand with **Settings → Backups** or `.\scripts\backup.ps1`. Restore with `.\scripts\restore.ps1`. Copy the `backups` folder off the computer regularly.

## Mobile money through Paystack

When Paystack is set up, choosing **Mobile Money** at the till sends a payment prompt to the customer's phone (MTN, Telecel or AT). The till waits while they approve with their MoMo PIN; the network gives them 180 seconds. The sale can only be completed once the server has confirmed the payment with Paystack, for the exact amount, and each payment can be used on only one sale. Cashiers can still record a MoMo payment by hand ("Record manually instead"), for example when the customer sent money to your merchant number.

1. Create a Paystack business account for Ghana and add your business email in **Settings → Business**. Paystack emails payment receipts to it.
2. Put your secret key in `backend\.env` and restart the POS:
   ```
   PAYSTACK_SECRET_KEY=sk_test_...   # test mode: MTN 0551234987 approves without a PIN
   ```
   Switch to your `sk_live_...` key when you are ready to take real money. Keep the key secret: it never leaves the shop computer.
3. Optional: if the POS is reachable from the internet, set the webhook URL in the Paystack dashboard to `https://<your-address>/api/payments/paystack/webhook/`. Without a webhook the till checks the payment status itself, which is the normal case for a shop PC.

**Reports → Payments → Paystack MoMo prompts** lists every prompt. A payment that was approved but is **not on a sale** (for example, the cashier stopped waiting and the customer approved later) is flagged, so you can refund the customer or record the sale.

**Refunds:** on a sale paid by a Paystack prompt, **Refund…** offers *Mobile Money through Paystack*, which sends the money back to the same number after manager approval. Money that never reached a sale can be returned with **Send back** in the report above.
- Paystack takes refunds from your Paystack balance, so a refund can be refused if the balance is too low. A processed refund can still take up to 10 business days to reach the customer.
- The items and sales totals are updated first, then the refund is sent. If Paystack refuses it, the sale shows **Failed** with the reason, and the customer is still owed the money: use **Try again**, or pay them another way and press **Paid by hand**. If a cash payment comes out of the drawer this way, record it as a cash-out on the shift.
- If the connection drops, the refund shows **Not sent yet**. **Check status** finds out what happened and sends it if needed, and the same refund can't be paid twice.
- A refund goes back through one Paystack payment at a time, up to the amount left on that payment. Sales paid through Paystack can't be voided, because a void would not return the customer's money.

**Reports → Payments → Paystack refunds** lists every refund and its status. Without a webhook, press **Check status** to update it.

**Training:** `PAYSTACK_SECRET_KEY=sk_fake` runs a built-in simulator that moves no money. Numbers ending in `0000` are declined, numbers ending in `1111` ask for the code `123456`, and all other numbers are approved. For refunds, a payment from a number ending in `2222` is refused when sent, one ending in `3333` fails on the first status check, and all others are sent back on the first status check.

## Development

```powershell
.\scripts\dev.ps1       # Django on :8000 + Vite hot reload on :5173
```

Tests:

```powershell
cd backend;  .\.venv\Scripts\python -m pytest
cd frontend; npm test
cd frontend; npm run e2e   # builds the app, starts Django on a fresh database, drives a full shop day in Edge
```

The end-to-end test (`frontend/e2e/pos.spec.ts`) goes through setup, a scanned sale with options paid by a Paystack MoMo prompt (simulated, including a declined attempt) plus cash, a cash refund and a refund through Paystack, a restaurant table order with a kitchen ticket, closing the shift (expected vs. counted cash) and the reports. It uses the installed Microsoft Edge because Windows can block Playwright's own Chromium build. Set `E2E_BROWSER=chromium` to use Playwright's Chromium instead.

The local development database (`backend\db.sqlite3`) was created during testing. It has demo data and a test owner account: username `owner`, password `owner123`, PIN `1234`. Delete `db.sqlite3` and run `python manage.py migrate` to start fresh.

### Layout

```
backend/   Django + Django REST Framework API
  apps/accounts     users, roles, PIN login, manager approval, audit log
  apps/business     business settings, branches, invoice numbering, tax engine, setup wizard
  apps/catalog      categories, products, variants, barcodes, modifiers, CSV import/export
  apps/inventory    stock ledger, adjustments, counts, suppliers, purchase orders
  apps/customers    customers, credit and loyalty ledger
  apps/shifts       shifts, cash movements, X/Z report calculation
  apps/sales        cart pricing, checkout, refunds, voids, held sales
  apps/restaurant   floor areas, tables, orders, kitchen tickets
  apps/reports      dashboards and reports
frontend/  React + TypeScript + Vite + Tailwind
scripts/   setup, run, dev and backup scripts (PowerShell)
```

### Design rules
- **Prices are worked out once, on the server.** The till's totals come from `/api/sales/quote/`, the same code that charges the sale (`apps/sales/pricing.py`).
- **Money is never stored as floating-point numbers.** Every amount is a `Decimal` rounded to pesewas.
- **Stock only changes through `apps/inventory/services.change_stock`.** It locks the stock row and writes a ledger entry.
- **Completed sales are never edited.** Corrections are made with refunds or voids. Invoice numbers are sequential per branch, ready for GRA E-VAT.

## Roadmap
- **Phase 2:**
  - Payments and invoicing: ~~Paystack MoMo prompts and refunds~~ (done), card payments through Paystack Terminal, GRA E-VAT submission, and SMS/WhatsApp receipts.
  - Restaurant: a kitchen display screen, split bills by item or seat, tips, and recipes that deduct ingredients.
  - Promotions and gift cards.
  - Multi-branch stock transfers.
- **Phase 3:**
  - An offline mode (PWA) and direct ESC/POS printing with the cash drawer kick.
  - A customer display, scales, staff time clock, expenses and an accounting export.
  - A pharmacy mode with batch and expiry tracking.
