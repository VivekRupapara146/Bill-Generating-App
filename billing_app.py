"""
Billing/Invoice Generator – Tkinter + SQLite + ReportLab (single file)
----------------------------------------------------------------------
Features
- Add line items (Item Name, Qty, Rate); auto Amount (Qty × Rate)
- Auto Sr. numbers and running totals
- Fields: Chalan/Invoice No (auto), Party Name, City, Date, L.R. No.
- Tax % and P&F (packing & forwarding/other charge) inputs
- Save invoice to SQLite database (invoices.db)
- Export nicely formatted PDF (logo support, table borders, multi-page)
- CSV import/export for invoices
- Admin menu (reset chalan counter, backup DB, settings, item master)
- Helpful messages and safer chalan numbering (persists across restarts)

How to run
1) Python 3.10+
2) pip install reportlab
3) python billing_app.py

A file `invoices.db` will be created in the same folder. PDFs will be saved in `./pdf/`.

Tip: Rename this file to `billing_app.py` before running.
"""

import os
import sqlite3
import shutil
import csv
import pandas as pd
from datetime import datetime
from dataclasses import dataclass
from typing import List, Tuple, Optional
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image
from xml.sax.saxutils import escape
from item_master_csv import get_all_master_items, add_master_item, update_master_item, delete_master_item, get_item_rate_by_name
from reportlab.lib.pagesizes import A5, landscape

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

# PDF export (install: pip install reportlab)
try:
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle, Image, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
except Exception:
    pdf_canvas = None  # Graceful fallback if reportlab isn't installed

DB_FILE = "invoices.db"
PDF_DIR = "pdf"
APP_TITLE = "Invoice/Chalan Generator"
# Default company details (editable from Settings)
DEFAULTS = {
    "company_name": "COMPANY NAME",
    "company_city": "CITY",
    "company_mobile": "+91-123456789",
    "bank_ac_name": "VIVEK G. RUPAPARA",
    "bank_name": "BANK",
    "bank_ac_no": "123456789",
    "bank_ifsc": "XYZ0123456",
    "logo_path": "",  # optional path to logo image
}
@dataclass
class LineItem:
    item: str
    qty: float
    rate: float

    @property
    def amount(self) -> float:
        return round(self.qty * self.rate, 2)


# ------------------------ Database helpers ------------------------

def init_db():
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    # cur.execute(
    #     """
    #     CREATE TABLE IF NOT EXISTS item_master (
    #         id INTEGER PRIMARY KEY AUTOINCREMENT,
    #         name TEXT UNIQUE,
    #         last_rate REAL
    #     );
    #     """
    # )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS item_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            default_rate REAL NOT NULL
        );
        """
    )
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Create invoices table if it doesn't exist
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chalan_no INTEGER,
            party_name TEXT,
            city TEXT,
            date TEXT,
            lr_no TEXT,
            tax REAL,
            pf REAL,
            total REAL
        )
    """)
# Initialize chalan_no if not already present
    cur.execute("SELECT value FROM meta WHERE key='chalan_no'")
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("chalan_no", "0"))

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chalan_no INTEGER UNIQUE,
            party_name TEXT,
            city TEXT,
            lr_no TEXT,
            dt TEXT,
            tax_percent REAL,
            pandf REAL,
            subtotal REAL,
            tax_amount REAL,
            grand_total REAL
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER,
            sr INTEGER,
            item_name TEXT,
            qty REAL,
            rate REAL,
            amount REAL,
            FOREIGN KEY(invoice_id) REFERENCES invoices(id)
        );
        """
    )
    # store a counter and settings for chalan numbers and company details
    # cur.execute(
    #     """
    #     CREATE TABLE IF NOT EXISTS meta (
    #         key TEXT PRIMARY KEY,
    #         value TEXT
    #     );
    #     """
    # )
    # item master
    
    # Ensure company defaults are stored if not present
    for k, v in DEFAULTS.items():
        cur.execute("SELECT value FROM meta WHERE key=?", (k,))
        if cur.fetchone() is None:
            cur.execute("INSERT INTO meta(key, value) VALUES(?, ?)", (k, str(v)))
    con.commit()
    con.close()


def meta_get(key: str, fallback: Optional[str] = None) -> Optional[str]:
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("SELECT value FROM meta WHERE key=?", (key,))
    row = cur.fetchone()
    con.close()
    return row[0] if row else fallback


def meta_set(key: str, value: str):
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", (key, str(value)))
    con.commit()
    con.close()


def get_next_chalan_no() -> int:
    """Return the next chalan number and persist it.
    Logic:
      - If meta 'chalan_no' exists, increment and use it.
      - If meta missing (rare), set it to max(chalan_no in invoices, 0) + 1 and store.
    This avoids accidental resets if meta row was removed.
    """
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("SELECT value FROM meta WHERE key='chalan_no'")
    row = cur.fetchone()
    if row is None:
        cur.execute("SELECT MAX(chalan_no) FROM invoices")
        mx = cur.fetchone()[0] or 0
        next_no = mx + 1
        cur.execute("INSERT INTO meta(key, value) VALUES('chalan_no', ?)", (str(next_no),))
    else:
        try:
            next_no = int(row[0]) + 1
        except Exception:
            cur.execute("SELECT MAX(chalan_no) FROM invoices")
            mx = cur.fetchone()[0] or 0
            next_no = mx + 1
        cur.execute("UPDATE meta SET value=? WHERE key='chalan_no'", (str(next_no),))
    con.commit()
    con.close()
    return next_no


def reset_chalan_counter(to_value: int = 0):
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('chalan_no', ?)", (str(to_value),))
    con.commit()
    con.close()


def persist_invoice(chalan_no: int, party_name: str, city: str, lr_no: str, dt: str,
                    tax_percent: float, pandf: float,
                    items: List[LineItem]) -> Tuple[int, float, float, float]:
    subtotal = round(sum(i.amount for i in items), 2)
    tax_amount = round(subtotal * (tax_percent / 100.0), 2) if tax_percent else 0.0
    grand_total = round(subtotal + tax_amount + (pandf or 0.0), 2)

    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()

    cur.execute(
        """
        INSERT INTO invoices (chalan_no, party_name, city, lr_no, dt, tax_percent, pandf, subtotal, tax_amount, grand_total)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (chalan_no, party_name, city, lr_no, dt, tax_percent, pandf, subtotal, tax_amount, grand_total)
    )
    invoice_id = cur.lastrowid

    for idx, li in enumerate(items, start=1):
        cur.execute(
            """
            INSERT INTO invoice_items (invoice_id, sr, item_name, qty, rate, amount)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (invoice_id, idx, li.item, li.qty, li.rate, li.amount)
        )

    con.commit()
    con.close()
    return invoice_id, subtotal, tax_amount, grand_total


def fetch_invoice_by_chalan(chalan_no: int):
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("SELECT id, party_name, city, lr_no, dt, tax_percent, pandf FROM invoices WHERE chalan_no=?", (chalan_no,))
    row = cur.fetchone()
    if not row:
        con.close()
        return None
    invoice_id, party_name, city, lr_no, dt, tax_percent, pandf = row
    cur.execute("SELECT sr, item_name, qty, rate FROM invoice_items WHERE invoice_id=? ORDER BY sr", (invoice_id,))
    items = [LineItem(r[1], float(r[2]), float(r[3])) for r in cur.fetchall()]
    con.close()
    return {
        "chalan_no": chalan_no,
        "party_name": party_name,
        "city": city,
        "lr_no": lr_no,
        "dt": dt,
        "tax_percent": tax_percent,
        "pandf": pandf,
        "items": items,
    }


# ------------------------ Item Master helpers ------------------------

def get_all_master_items() -> List[Tuple[int, str, float]]:
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("SELECT id, name, default_rate FROM item_master ORDER BY name")
    rows = cur.fetchall()
    con.close()
    return rows


def add_master_item(name: str, rate: float) -> bool:
    try:
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()
        cur.execute("INSERT INTO item_master (name, default_rate) VALUES (?, ?)", (name.strip(), rate))
        con.commit()
        con.close()
        return True
    except sqlite3.IntegrityError:
        return False


def update_master_item(item_id: int, name: str, rate: float):
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("UPDATE item_master SET name=?, default_rate=? WHERE id=?", (name.strip(), rate, item_id))
    con.commit()
    con.close()


def delete_master_item(item_id: int):
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("DELETE FROM item_master WHERE id=?", (item_id,))
    con.commit()
    con.close()


def get_item_rate_by_name(name: str) -> Optional[float]:
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("SELECT default_rate FROM item_master WHERE name=?", (name,))
    row = cur.fetchone()
    con.close()
    return float(row[0]) if row else None


# ------------------------ CSV / Backup helpers ------------------------

def export_all_invoices_to_csv(path: str):
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("SELECT * FROM invoices")
    invoices = cur.fetchall()
    # header
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(["id","chalan_no","party_name","city","lr_no","dt","tax_percent","pandf","subtotal","tax_amount","grand_total"])
        for inv in invoices:
            w.writerow(inv)
        # write items in separate file or same file? we'll create a sibling file for items
    cur.execute("SELECT * FROM invoice_items")
    items = cur.fetchall()
    items_path = os.path.splitext(path)[0] + "_items.csv"
    with open(items_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(["id","invoice_id","sr","item_name","qty","rate","amount"])
        for it in items:
            w.writerow(it)
    con.close()
    return path, items_path


def import_invoices_from_csv(inv_csv: str, items_csv: str):
    # naive import: assumes CSVs are correctly formatted. Will skip chalan_no conflicts.
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    imported = 0
    with open(inv_csv, newline='', encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                cur.execute(
                    "INSERT INTO invoices (chalan_no, party_name, city, lr_no, dt, tax_percent, pandf, subtotal, tax_amount, grand_total) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        int(row['chalan_no']), row.get('party_name',''), row.get('city',''), row.get('lr_no',''), row.get('dt',''), float(row.get('tax_percent') or 0), float(row.get('pandf') or 0), float(row.get('subtotal') or 0), float(row.get('tax_amount') or 0), float(row.get('grand_total') or 0)
                    )
                )
                imported += 1
            except sqlite3.IntegrityError:
                # skip duplicates
                continue
    # items
    with open(items_csv, newline='', encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                cur.execute(
                    "INSERT INTO invoice_items (invoice_id, sr, item_name, qty, rate, amount) VALUES (?, ?, ?, ?, ?, ?)",
                    (int(row['invoice_id']), int(row['sr']), row.get('item_name',''), float(row.get('qty') or 0), float(row.get('rate') or 0), float(row.get('amount') or 0))
                )
            except sqlite3.IntegrityError:
                continue
    con.commit()
    con.close()
    return imported


def backup_database(dest_folder: str) -> str:
    os.makedirs(dest_folder, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    dest = os.path.join(dest_folder, f'invoices_backup_{ts}.db')
    shutil.copy2(DB_FILE, dest)
    return dest


# ------------------------ PDF Export (improved layout with Paragraphs) ------------------------

def export_pdf(filename: str, chalan_no: int, party_name: str, city: str, lr_no: str, dt: str,
               items: List[LineItem], subtotal: float, tax_percent: float, tax_amount: float,
               pandf: float, grand_total: float):

    os.makedirs(PDF_DIR, exist_ok=True)
    fullpath = os.path.join(PDF_DIR, filename)

    styles = getSampleStyleSheet()
    story = []

    # Company info
    company_name = meta_get('company_name', DEFAULTS['company_name'])
    company_city = meta_get('company_city', DEFAULTS['company_city'])
    company_mobile = meta_get('company_mobile', DEFAULTS['company_mobile'])
    logo_path = meta_get('logo_path', DEFAULTS['logo_path']) or None

    if logo_path and os.path.exists(logo_path):
        story.append(Image(logo_path, width=30*mm, height=30*mm))
    story.append(Paragraph(f"<b>{company_name}</b>", styles['Title']))
    story.append(Paragraph(f"{company_city} | MOB: {company_mobile}", styles['Normal']))
    story.append(Spacer(1, 12))

    # Invoice meta
    story.append(Paragraph(f"Chalan No: {chalan_no}", styles['Normal']))
    story.append(Paragraph(f"Date: {dt}", styles['Normal']))
    story.append(Paragraph(f"Party: {escape(party_name)}", styles['Normal']))
    story.append(Paragraph(f"City: {escape(city)}", styles['Normal']))
    story.append(Paragraph(f"L.R. No: {escape(lr_no)}", styles['Normal']))
    story.append(Spacer(1, 12))

    # Table data
    table_data = [["Sr", "Item Name", "Qty", "Rate", "Amount"]]
    for idx, li in enumerate(items, start=1):
        safe_item = escape((li.item or "-").strip())
        table_data.append([
            str(idx),
            Paragraph(safe_item.replace('\n', '<br/>'), styles['Normal']),
            f"{li.qty:g}",
            f"{li.rate:.2f}",
            f"{li.amount:.2f}"
        ])

    # Totals
    table_data.append(["", "", "", "Sub Total", f"{subtotal:.2f}"])
    table_data.append(["", "", "", f"Tax {tax_percent:.2f}%", f"{tax_amount:.2f}"])
    table_data.append(["", "", "", "P & F", f"{pandf:.2f}"])
    table_data.append(["", "", "", "Grand Total", f"{grand_total:.2f}"])

    # Table layout
    usable_width = A5[0] - 20*mm  # adjust left/right margins
    col_widths = [15*mm, usable_width-15*mm-80*mm, 20*mm, 25*mm, 25*mm]  # adjust column widths

    tbl = Table(table_data, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('ALIGN', (2,1), (-1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('SPAN', (0, len(table_data)-4), (1, len(table_data)-4)),
        ('SPAN', (0, len(table_data)-3), (1, len(table_data)-3)),
        ('SPAN', (0, len(table_data)-2), (1, len(table_data)-2)),
        ('SPAN', (0, len(table_data)-1), (1, len(table_data)-1)),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 20))

    # Bank details
    bank_ac_name = meta_get('bank_ac_name', DEFAULTS['bank_ac_name'])
    bank_name = meta_get('bank_name', DEFAULTS['bank_name'])
    bank_ac_no = meta_get('bank_ac_no', DEFAULTS['bank_ac_no'])
    bank_ifsc = meta_get('bank_ifsc', DEFAULTS['bank_ifsc'])

    story.append(Paragraph(f"A/C NAME : {bank_ac_name}", styles['Normal']))
    story.append(Paragraph(f"BANK NAME : {bank_name}", styles['Normal']))
    story.append(Paragraph(f"A/C NO : {bank_ac_no}    IFSC : {bank_ifsc}", styles['Normal']))

    # Build PDF
    doc = SimpleDocTemplate(fullpath, pagesize=A5, leftMargin=10*mm, rightMargin=10*mm,topMargin=15*mm, bottomMargin=15*mm)
    doc.build(story)

    return fullpath


# ------------------------ UI App ------------------------

class BillingApp(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.master.title(APP_TITLE)
        self.pack(fill="both", expand=True)

        # State
        self.items: List[LineItem] = []
        # Ensure DB & meta defaults exist before reading next chalan
        init_db()
        self.chalan_no = get_next_chalan_no()

        self._build_ui()
        self._refresh_table()

    # -- UI Layout
    def _build_ui(self):
        pad = {"padx": 6, "pady": 4}

        # Menu
        menubar = tk.Menu(self.master)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New Invoice", command=self.new_invoice)
        file_menu.add_command(label="Open Invoice...", command=self.open_invoice_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Export All to CSV...", command=self.export_all_csv_dialog)
        file_menu.add_command(label="Backup DB...", command=self.backup_db_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.master.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        admin_menu = tk.Menu(menubar, tearoff=0)
        admin_menu.add_command(label="Settings", command=self.open_settings)
        admin_menu.add_command(label="Item Master", command=self.open_item_master)
        admin_menu.add_command(label="Import Invoices from CSV...", command=self.import_csv_dialog)
        admin_menu.add_command(label="Reset Chalan Counter", command=self.reset_chalan_dialog)
        menubar.add_cascade(label="Admin", menu=admin_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.master.config(menu=menubar)

        # Top form
        top = ttk.LabelFrame(self, text="Invoice Details")
        top.pack(fill="x", **pad)

        self.party_var = tk.StringVar()
        self.city_var = tk.StringVar()
        self.lr_var = tk.StringVar()
        self.date_var = tk.StringVar(value=datetime.now().strftime("%d/%m/%Y"))

        self.chalan_label = ttk.Label(top, text=f"Chalan No: {self.chalan_no}")
        self.chalan_label.grid(row=0, column=0, sticky="w", **pad)
        ttk.Label(top, text="Party Name").grid(row=1, column=0, sticky="e", **pad)
        ttk.Entry(top, textvariable=self.party_var, width=40).grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(top, text="City").grid(row=1, column=2, sticky="e", **pad)
        ttk.Entry(top, textvariable=self.city_var, width=22).grid(row=1, column=3, sticky="w", **pad)

        ttk.Label(top, text="L.R. No.").grid(row=2, column=0, sticky="e", **pad)
        ttk.Entry(top, textvariable=self.lr_var, width=20).grid(row=2, column=1, sticky="w", **pad)

        ttk.Label(top, text="Date").grid(row=0, column=2, sticky="e", **pad)
        ttk.Entry(top, textvariable=self.date_var, width=20).grid(row=0, column=3, sticky="w", **pad)

        # Items entry (with combobox for master items)
        entry = ttk.LabelFrame(self, text="Add Item")
        entry.pack(fill="x", **pad)

        self.item_var = tk.StringVar()
        self.qty_var = tk.StringVar()
        self.rate_var = tk.StringVar()

        ttk.Label(entry, text="Item Name").grid(row=0, column=0, sticky="e", **pad)
        self.item_combo = ttk.Combobox(entry, textvariable=self.item_var, width=40)
        self.item_combo.grid(row=0, column=1, **pad)
        self.item_combo.bind('<<ComboboxSelected>>', self._on_master_item_selected)

        ttk.Label(entry, text="Qty").grid(row=0, column=2, sticky="e", **pad)
        ttk.Entry(entry, textvariable=self.qty_var, width=10).grid(row=0, column=3, **pad)
        ttk.Label(entry, text="Rate").grid(row=0, column=4, sticky="e", **pad)
        ttk.Entry(entry, textvariable=self.rate_var, width=12).grid(row=0, column=5, **pad)
        ttk.Button(entry, text="Add", command=self.add_item).grid(row=0, column=6, **pad)

        # Table
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, **pad)

        cols = ("sr", "item", "qty", "rate", "amount")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=10)
        for c, w in zip(cols, (60, 340, 90, 100, 120)):
            self.tree.heading(c, text=c.upper())
            self.tree.column(c, width=w, anchor="e" if c != "item" else "w")
        self.tree.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        sb.pack(side="right", fill="y")

        # Bottom totals
        totals = ttk.LabelFrame(self, text="Totals")
        totals.pack(fill="x", **pad)

        self.tax_var = tk.StringVar(value="0")
        self.pandf_var = tk.StringVar(value="0")
        self.subtotal_var = tk.StringVar(value="0.00")
        self.tax_amt_var = tk.StringVar(value="0.00")
        self.grand_var = tk.StringVar(value="0.00")

        ttk.Label(totals, text="Tax %").grid(row=0, column=0, sticky="e", **pad)
        ttk.Entry(totals, textvariable=self.tax_var, width=10).grid(row=0, column=1, **pad)
        ttk.Label(totals, text="P & F").grid(row=0, column=2, sticky="e", **pad)
        ttk.Entry(totals, textvariable=self.pandf_var, width=12).grid(row=0, column=3, **pad)

        ttk.Label(totals, text="Sub Total").grid(row=0, column=4, sticky="e", **pad)
        ttk.Label(totals, textvariable=self.subtotal_var).grid(row=0, column=5, sticky="w", **pad)
        ttk.Label(totals, text="Tax Amount").grid(row=0, column=6, sticky="e", **pad)
        ttk.Label(totals, textvariable=self.tax_amt_var).grid(row=0, column=7, sticky="w", **pad)
        ttk.Label(totals, text="Grand Total").grid(row=0, column=8, sticky="e", **pad)
        ttk.Label(totals, textvariable=self.grand_var, font=("TkDefaultFont", 10, "bold")).grid(row=0, column=9, sticky="w", **pad)

        # Actions
        actions = ttk.Frame(self)
        actions.pack(fill="x", **pad)
        ttk.Button(actions, text="Delete Selected", command=self.delete_selected).pack(side="left", padx=4)
        ttk.Button(actions, text="Save Invoice", command=self.save_invoice).pack(side="left", padx=4)
        ttk.Button(actions, text="Export PDF", command=self.export_current_pdf).pack(side="left", padx=4)
        ttk.Button(actions, text="New Invoice", command=self.new_invoice).pack(side="right", padx=4)

        # populate combobox values
        self._refresh_item_master_values()
    
    def open_item_master(self):
        win = tk.Toplevel(self.master)
        win.title("Item Master")
        win.geometry("400x300")

        tree = ttk.Treeview(win, columns=("name", "rate"), show="headings")
        tree.heading("name", text="Item Name")
        tree.heading("rate", text="Last Rate")
        tree.column("name", width=220)
        tree.column("rate", width=100, anchor="e")
        tree.pack(fill="both", expand=True)

        # Load items from DB
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()
        cur.execute("SELECT name, last_rate FROM item_master ORDER BY name")
        for row in cur.fetchall():
            tree.insert("", "end", values=row)
        con.close()


    # -- Item ops
    
    def _refresh_item_master_values(self):
        items = get_all_master_items()
        names = [r[1] for r in items]
        self.item_combo['values'] = names
    
    def load_items(self):
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()
        cur.execute("SELECT name FROM item_master")
        items = [row[0] for row in cur.fetchall()]
        con.close()
        return items


    def _on_master_item_selected(self, ev=None):
        name = self.item_var.get()
        rate = get_item_rate_by_name(name)
        if rate is not None:
            self.rate_var.set(f"{rate:.2f}")

    def add_item(self):
        try:
            self.update()   # 👈 force UI to update bindings

            name = (self.item_var.get() or "").strip()
            if not name:
                raise ValueError("Item name required")

            qty = float(self.qty_var.get())
            rate = float(self.rate_var.get())
            if qty <= 0 or rate < 0:
                raise ValueError
        except Exception:
            messagebox.showerror("Invalid Input", "Enter valid Item, Qty (>0) and Rate (>=0)")
            return

        self.items.append(LineItem(name, qty, rate))
        
        # --- Auto-update Item Master ---
        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()
        cur.execute("INSERT OR IGNORE INTO item_master(name, default_rate) VALUES(?, ?)", (name, rate))
        cur.execute("UPDATE item_master SET default_rate=? WHERE name=?", (rate, name))
        con.commit()
        con.close()
        
        # refresh Dropdown
        self._refresh_item_master_values()  # reload all master items into the combobox

        self.item_var.set("")
        self.qty_var.set("")
        self.rate_var.set("")
        self._refresh_table()

    def reset_chalan_dialog(self):
        if messagebox.askyesno("Reset Counter", "Are you sure you want to reset Chalan counter to 1?"):
            # con = sqlite3.connect(DB_FILE)
            # cur = con.cursor()
            # cur.execute("UPDATE meta SET value='0' WHERE key='chalan_no'")
            # con.commit()
            # con.close()
            reset_chalan_counter(0)  # persist in DB

            # fetch new number
            self.chalan_no = get_next_chalan_no()

            # reset current invoice state
            self.items.clear()
            self.party_var.set("")
            self.city_var.set("")
            self.lr_var.set("")
            self.date_var.set(datetime.now().strftime("%d/%m/%Y"))
            self.tax_var.set("0")
            self.pandf_var.set("0")

            # refresh UI (table + chalan label + totals)
            self._refresh_table()
            self.chalan_label.config(text=f"Chalan No: {self.chalan_no}")

            messagebox.showinfo(
                "Reset Done",
                f"Chalan counter reset.\nCurrent Chalan No: {self.chalan_no}\nInvoice form cleared."
            )



    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        indices = sorted([self.tree.index(i) for i in sel], reverse=True)
        for idx in indices:
            if 0 <= idx < len(self.items):
                self.items.pop(idx)
        self._refresh_table()

    # -- Totals
    def _recompute_totals(self):
        subtotal = round(sum(li.amount for li in self.items), 2)
        try:
            tax_pct = float(self.tax_var.get() or 0)
        except ValueError:
            tax_pct = 0.0
            self.tax_var.set("0")
        try:
            pandf = float(self.pandf_var.get() or 0)
        except ValueError:
            pandf = 0.0
            self.pandf_var.set("0")
        tax_amount = round(subtotal * (tax_pct/100.0), 2)
        grand = round(subtotal + tax_amount + pandf, 2)
        self.subtotal_var.set(f"{subtotal:.2f}")
        self.tax_amt_var.set(f"{tax_amount:.2f}")
        self.grand_var.set(f"{grand:.2f}")
        return subtotal, tax_pct, tax_amount, pandf, grand

    def _refresh_table(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for idx, li in enumerate(self.items, start=1):
            self.tree.insert("", "end", values=(idx, li.item, f"{li.qty:g}", f"{li.rate:.2f}", f"{li.amount:.2f}"))
        self._recompute_totals()

    # -- Invoice ops
    def save_invoice(self):
        if self.item_var.get().strip() and self.qty_var.get().strip() and self.rate_var.get().strip():
            try:
                self.add_item()
            except Exception:
                pass
        if not self.items:
            messagebox.showwarning("No items", "Please add at least one item")
            return
        party = self.party_var.get().strip()
        city = self.city_var.get().strip()
        lr_no = self.lr_var.get().strip()
        dt = self.date_var.get().strip() or datetime.now().strftime("%d/%m/%Y")
        subtotal, tax_pct, tax_amt, pandf, grand = self._recompute_totals()

        try:
            invoice_id, *_ = persist_invoice(
                self.chalan_no, party, city, lr_no, dt, tax_pct, pandf, self.items
            )
        except sqlite3.IntegrityError:
            messagebox.showerror("Save Failed", "Chalan number already exists. Start a new invoice.")
            return
        messagebox.showinfo("Saved", f"Invoice saved with ID #{invoice_id}")

    def export_current_pdf(self):
        # print("DEBUG items:", [(li.item, li.qty, li.rate, li.amount) for li in self.items])
        if self.item_var.get().strip() and self.qty_var.get().strip() and self.rate_var.get().strip():
            try:
                self.add_item()
            except Exception:
                pass
        if not self.items:
            messagebox.showwarning("No items", "Please add at least one item")
            return
        party = self.party_var.get().strip() or ""
        city = self.city_var.get().strip() or ""
        lr_no = self.lr_var.get().strip() or ""
        dt = self.date_var.get().strip() or datetime.now().strftime("%d/%m/%Y")
        subtotal, tax_pct, tax_amt, pandf, grand = self._recompute_totals()

        filename = f"Invoice_{self.chalan_no}.pdf"
        try:
            path = export_pdf(filename, self.chalan_no, party, city, lr_no, dt,
                               self.items, subtotal, tax_pct, tax_amt, pandf, grand)
        except Exception as e:
            messagebox.showerror("PDF Error", str(e))
            return

        # open the PDF in default viewer
        try:
            if os.name == 'nt':
                os.startfile(path)
            elif os.name == 'posix' and os.uname().sysname == 'Darwin':
                os.system(f"open '{path}'")
            else:
                os.system(f"xdg-open '{path}'")
        except Exception:
            pass
        messagebox.showinfo("PDF Exported", f"Saved to: {path}")

    def new_invoice(self):
        # begin a fresh invoice number
        self.items.clear()
        self.party_var.set("")
        self.city_var.set("")
        self.lr_var.set("")
        self.date_var.set(datetime.now().strftime("%d/%m/%Y"))
        self.tax_var.set("0")
        self.pandf_var.set("0")
        self.chalan_no = get_next_chalan_no()
        self.chalan_label.config(text=f"Chalan No: {self.chalan_no}")
        self._refresh_table()
        messagebox.showinfo("New Invoice", f"Chalan No: {self.chalan_no}")

    # -- Admin / Menu actions
    def open_settings(self):
        def save_settings():
            meta_set('company_name', e_name.get().strip())
            meta_set('company_city', e_city.get().strip())
            meta_set('company_mobile', e_mobile.get().strip())
            meta_set('bank_ac_name', e_acname.get().strip())
            meta_set('bank_name', e_bank.get().strip())
            meta_set('bank_ac_no', e_acno.get().strip())
            meta_set('bank_ifsc', e_ifsc.get().strip())
            meta_set('logo_path', e_logo.get().strip())
            top.destroy()
            messagebox.showinfo('Settings', 'Saved')

        top = tk.Toplevel(self.master)
        top.title('Settings')
        pad = {'padx':6, 'pady':4}
        ttk.Label(top, text='Company Name').grid(row=0, column=0, **pad)
        e_name = ttk.Entry(top, width=40)
        e_name.grid(row=0, column=1, **pad)
        e_name.insert(0, meta_get('company_name', DEFAULTS['company_name']))

        ttk.Label(top, text='City').grid(row=1, column=0, **pad)
        e_city = ttk.Entry(top, width=40); e_city.grid(row=1, column=1, **pad)
        e_city.insert(0, meta_get('company_city', DEFAULTS['company_city']))

        ttk.Label(top, text='Mobile').grid(row=2, column=0, **pad)
        e_mobile = ttk.Entry(top, width=40); e_mobile.grid(row=2, column=1, **pad)
        e_mobile.insert(0, meta_get('company_mobile', DEFAULTS['company_mobile']))

        ttk.Label(top, text='Bank A/C Name').grid(row=3, column=0, **pad)
        e_acname = ttk.Entry(top, width=40); e_acname.grid(row=3, column=1, **pad)
        e_acname.insert(0, meta_get('bank_ac_name', DEFAULTS['bank_ac_name']))

        ttk.Label(top, text='Bank Name').grid(row=4, column=0, **pad)
        e_bank = ttk.Entry(top, width=40); e_bank.grid(row=4, column=1, **pad)
        e_bank.insert(0, meta_get('bank_name', DEFAULTS['bank_name']))

        ttk.Label(top, text='Bank A/C No').grid(row=5, column=0, **pad)
        e_acno = ttk.Entry(top, width=40); e_acno.grid(row=5, column=1, **pad)
        e_acno.insert(0, meta_get('bank_ac_no', DEFAULTS['bank_ac_no']))

        ttk.Label(top, text='IFSC').grid(row=6, column=0, **pad)
        e_ifsc = ttk.Entry(top, width=40); e_ifsc.grid(row=6, column=1, **pad)
        e_ifsc.insert(0, meta_get('bank_ifsc', DEFAULTS['bank_ifsc']))

        ttk.Label(top, text='Logo Path').grid(row=7, column=0, **pad)
        e_logo = ttk.Entry(top, width=40); e_logo.grid(row=7, column=1, **pad)
        e_logo.insert(0, meta_get('logo_path', DEFAULTS['logo_path']))
        def pick_logo():
            p = filedialog.askopenfilename(title='Select logo (PNG/JPG)', filetypes=[('Images','*.png;*.jpg;*.jpeg;*.gif'), ('All','*.*')])
            if p:
                e_logo.delete(0, 'end'); e_logo.insert(0, p)
        ttk.Button(top, text='Browse', command=pick_logo).grid(row=7, column=2, **pad)

        ttk.Button(top, text='Save', command=save_settings).grid(row=8, column=1, sticky='e', **pad)

    def open_item_master(self):
        # Admin-only dialog to manage master items
        top = tk.Toplevel(self.master)
        top.title('Item Master')
        pad = {'padx':6, 'pady':4}

        frame = ttk.Frame(top)
        frame.pack(fill='both', expand=True, **pad)

        cols = ('id', 'name', 'rate')
        tree = ttk.Treeview(frame, columns=cols, show='headings')
        for c, w in zip(cols, (50, 300, 100)):
            tree.heading(c, text=c.upper())
            tree.column(c, width=w, anchor='w')
        tree.pack(side='left', fill='both', expand=True)

        sb = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscroll=sb.set)
        sb.pack(side='right', fill='y')

        def refresh():
            for i in tree.get_children():
                tree.delete(i)
            for r in get_all_master_items():
                tree.insert('', 'end', values=r)

        def add_item_dialog():
            nm = simpledialog.askstring('Add Item', 'Item name:', parent=top)
            if not nm:
                return
            try:
                rt = float(simpledialog.askstring('Rate', 'Default rate:', parent=top) or 0)
            except Exception:
                messagebox.showerror('Invalid', 'Enter numeric rate')
                return
            ok = add_master_item(nm, rt)
            if not ok:
                messagebox.showerror('Exists', 'Item already exists')
            refresh()
            self._refresh_item_master_values()

        def edit_item_dialog():
            sel = tree.selection()
            if not sel:
                return
            vals = tree.item(sel[0])['values']
            item_id, name, rate = vals
            new_name = simpledialog.askstring('Edit Item', 'Item name:', initialvalue=name, parent=top)
            if new_name is None:
                return
            try:
                new_rate = float(simpledialog.askstring('Rate', 'Default rate:', initialvalue=str(rate), parent=top) or 0)
            except Exception:
                messagebox.showerror('Invalid', 'Enter numeric rate')
                return
            update_master_item(item_id, new_name, new_rate)
            refresh()
            self._refresh_item_master_values()

        def delete_item_dialog():
            sel = tree.selection()
            if not sel:
                return
            vals = tree.item(sel[0])['values']
            item_id = vals[0]
            if not messagebox.askyesno('Delete', f"Delete '{vals[1]}'?"):
                return
            delete_master_item(item_id)
            refresh()
            self._refresh_item_master_values()

        btns = ttk.Frame(top)
        btns.pack(fill='x', pady=6)
        ttk.Button(btns, text='Add', command=add_item_dialog).pack(side='left', padx=4)
        ttk.Button(btns, text='Edit', command=edit_item_dialog).pack(side='left', padx=4)
        ttk.Button(btns, text='Delete', command=delete_item_dialog).pack(side='left', padx=4)

        refresh()

    def open_invoice_dialog(self):
        def do_open():
            try:
                ch = int(e.get())
            except Exception:
                messagebox.showerror('Invalid', 'Enter valid number')
                return
            data = fetch_invoice_by_chalan(ch)
            if not data:
                messagebox.showerror('Not found', f'No invoice with chalan {ch}')
                return
            # populate UI
            self.items = data['items']
            self.party_var.set(data['party_name'])
            self.city_var.set(data['city'])
            self.lr_var.set(data['lr_no'])
            self.date_var.set(data['dt'])
            self.tax_var.set(str(data['tax_percent'] or 0))
            self.pandf_var.set(str(data['pandf'] or 0))
            self.chalan_no = data['chalan_no']
            self.chalan_label.config(text=f"Chalan No: {self.chalan_no}")
            self._refresh_table()
            top.destroy()

        top = tk.Toplevel(self.master)
        top.title('Open Invoice')
        ttk.Label(top, text='Enter chalan no').pack(padx=6, pady=6)
        e = ttk.Entry(top); e.pack(padx=6, pady=6)
        ttk.Button(top, text='Open', command=do_open).pack(padx=6, pady=6)

    def export_all_csv_dialog(self):
        path = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV','*.csv')], title='Export invoices to CSV')
        if not path:
            return
        inv_p, items_p = export_all_invoices_to_csv(path)
        messagebox.showinfo('Exported', f'Invoices -> {inv_p}\\nItems -> {items_p}')

    def import_csv_dialog(self):
        inv = filedialog.askopenfilename(title='Select invoices CSV')
        if not inv:
            return
        items = filedialog.askopenfilename(title='Select invoice_items CSV')
        if not items:
            return
        count = import_invoices_from_csv(inv, items)
        messagebox.showinfo('Imported', f'Imported {count} invoices (skipped duplicates)')

    def backup_db_dialog(self):
        folder = filedialog.askdirectory(title='Select backup folder')
        if not folder:
            return
        dest = backup_database(folder)
        messagebox.showinfo('Backup', f'Backup saved to {dest}')

    # def reset_chalan_dialog(self):
    #     if not messagebox.askyesno('Reset', 'Reset chalan counter? This affects future generated numbers.'):
    #         return
    #     val = tk.simpledialog.askinteger('Reset chalan', 'Set chalan no to (next generated)', initialvalue=1, minvalue=0)
    #     if val is None:
    #         return
    #     reset_chalan_counter(val)
    #     messagebox.showinfo('Reset', f'Chalan counter set. Next generated will be {val}')

    def show_about(self):
        messagebox.showinfo('About', f'{APP_TITLE}\\nPowered by ReportLab for PDFs (optional).')

    def export_current_pdf_and_open(self):
        # kept for backwards compatibility
        return self.export_current_pdf()


# ------------------------ App entry ------------------------

def main():
    init_db()
    root = tk.Tk()
    # nicer default ttk theme
    try:
        root.style = ttk.Style()
        if 'clam' in root.style.theme_names():
            root.style.theme_use('clam')
    except Exception:
        pass
    app = BillingApp(root)
    root.minsize(900, 650)
    root.mainloop()


if __name__ == "__main__":
    main()

