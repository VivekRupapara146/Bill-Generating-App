# Bill-Generating-App
Developed a full-featured Billing & Invoice Generator using Python (Tkinter, SQLite, ReportLab). Implemented invoice creation, item master, auto-increment chalan numbering, PDF export, database persistence, and backup. Designed an intuitive UI with automated calculations for tax, totals, and charges, enabling efficient invoicing, record-keeping, and client-ready document generation."

A full-featured **Billing & Invoice Generator** desktop application built with **Python, Tkinter, SQLite, and ReportLab**.  
This app allows you to create, manage, and export invoices (chalans) with an intuitive UI and persistent database storage.

---

## 🚀 Features

- **Invoice Creation**
  - Auto-incrementing chalan/invoice number (persistent across restarts)
  - Party details (name, city, date, LR no.)
  - Configurable tax (%) and P&F charges

- **Item Management**
  - Add, delete, and edit items dynamically
  - Auto-calculated amount (Qty × Rate)
  - Running subtotal, tax, and grand total

- **Database (SQLite)**
  - Save invoices and item details persistently
  - Reload previous invoices with all details
  - Backup database easily

- **PDF Export**
  - Generate client-ready invoice PDFs with all details
  - Formatted output with itemized table and totals

- **User Interface**
  - Built with Tkinter (lightweight and easy to use)
  - Intuitive layout for quick billing
  - Scrollable item table with Sr. No, Item Name, Qty, Rate, Amount

---

## 🛠 Requirements

- Python **3.8+**
- Required libraries:
  - `tkinter` (bundled with Python)
  - `sqlite3` (bundled with Python)
  - `reportlab`

Install `reportlab` via pip if not already installed:

```bash
pip install reportlab
```

How to Run

Clone or download this repository.

Ensure invoices.db is in the same directory as the script (auto-created if missing).

Run the app:
```bash
python billing_app.py
```

Start creating invoices, add items, and export PDFs!

GUI:
<img width="1919" height="1079" alt="image" src="https://github.com/user-attachments/assets/a860e569-070b-4159-b1dc-c2390696b5fe" />

Sample PDF(A5 size):
<img width="557" height="792" alt="image" src="https://github.com/user-attachments/assets/1328f51c-a00e-4406-8522-1ed881c0de74" />


