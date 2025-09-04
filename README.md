# Bill-Generating-App
Built a full-featured Billing &amp; Invoice Generator in Python using Tkinter, SQLite, and ReportLab. Enabled invoice creation with auto-increment chalan numbers, item management, tax/total calculations, PDF export, and database persistence with backup. Designed an intuitive UI for efficient invoicing and client-ready document generation.

# Billing & Invoice Generator

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
