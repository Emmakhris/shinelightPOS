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

```powershell
.\scripts\setup.ps1     # installs everything, creates backend\.env, builds the app
.\scripts\run.ps1       # starts the POS and prints the address for other devices
```

Open the address that `run.ps1` prints and follow the setup wizard. To make other devices on the network able to connect, allow port 8000 through Windows Firewall.

**Several tills:** SQLite works well for one or two tills. For more, install PostgreSQL and set `DATABASE_URL` in `backend\.env` (see `backend\.env.example`).

**Backups:** run `.\scripts\backup.ps1` daily (for example with Task Scheduler) and copy the `backups` folder off the computer.

## Development

```powershell
.\scripts\dev.ps1       # Django on :8000 + Vite hot reload on :5173
```

Tests:

```powershell
cd backend;  .\.venv\Scripts\python -m pytest
cd frontend; npm test
```

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
  - Payments and invoicing: live MoMo/card payments (Paystack or Hubtel), GRA E-VAT submission, and SMS/WhatsApp receipts.
  - Restaurant: a kitchen display screen, split bills by item or seat, tips, and recipes that deduct ingredients.
  - Promotions and gift cards.
  - Multi-branch stock transfers.
- **Phase 3:**
  - An offline mode (PWA) and direct ESC/POS printing with the cash drawer kick.
  - A customer display, scales, staff time clock, expenses and an accounting export.
  - A pharmacy mode with batch and expiry tracking.
