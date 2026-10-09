"""
Financial calculation engine, SQLite database persistence, bill splitting algorithms,
PDF report generation, and Gmail SMTP email integration.
"""

import sqlite3
import re
import io
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Any, Tuple, Optional
import pandas as pd

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

DB_PATH_DEFAULT = "expenses.db"

# Financial Helper Functions
def to_decimal(val: Any, default: str = "0.00") -> Decimal:
    """
    Safely converts input (float, int, str) to Decimal rounded to 2 decimal places.
    """
    if val is None:
        return Decimal(default)
    try:
        # Strip currency symbols and whitespace
        cleaned = re.sub(r"[^\d.-]", "", str(val)).strip()
        if not cleaned:
            return Decimal(default)
        d = Decimal(cleaned)
        return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal(default)


def recalculate_receipt_totals(
    items: List[Dict[str, Any]],
    tax: Any = "0.00",
    discount: Any = "0.00",
    service_charge: Any = "0.00"
) -> Tuple[Decimal, Decimal]:
    """
    Recalculates subtotal and calculated_total using Decimal arithmetic.
    Returns (calculated_subtotal, calculated_total).
    """
    dec_tax = to_decimal(tax)
    dec_discount = to_decimal(discount)
    dec_service = to_decimal(service_charge)

    subtotal = Decimal("0.00")
    for item in items:
        qty = to_decimal(item.get("quantity", 1))
        unit_p = to_decimal(item.get("unit_price", 0))
        item_tot = to_decimal(item.get("total", 0))

        if item_tot == Decimal("0.00") and unit_p > Decimal("0.00"):
            item_tot = (qty * unit_p).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        subtotal += item_tot

    calculated_total = subtotal + dec_tax + dec_service - dec_discount
    if calculated_total < Decimal("0.00"):
        calculated_total = Decimal("0.00")

    return subtotal, calculated_total


def check_total_mismatch(
    printed_total: Any,
    calculated_total: Any,
    tolerance: Decimal = Decimal("0.02")
) -> Tuple[bool, Decimal]:
    """
    Compares printed total vs calculated total.
    Returns (has_mismatch, difference_amount).
    """
    dec_printed = to_decimal(printed_total)
    dec_calculated = to_decimal(calculated_total)
    diff = abs(dec_printed - dec_calculated)
    has_mismatch = diff > tolerance
    return has_mismatch, diff


# SQLite Database Operations
def get_db_connection(db_path: str = DB_PATH_DEFAULT) -> sqlite3.Connection:
    """
    Establishes SQLite connection with row factory support.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DB_PATH_DEFAULT) -> None:
    """
    Initializes database tables if they do not already exist.
    """
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                merchant TEXT NOT NULL,
                date TEXT,
                currency TEXT DEFAULT 'USD',
                subtotal REAL DEFAULT 0.0,
                tax REAL DEFAULT 0.0,
                discount REAL DEFAULT 0.0,
                service_charge REAL DEFAULT 0.0,
                final_total REAL DEFAULT 0.0,
                calculated_total REAL DEFAULT 0.0,
                payment_method TEXT DEFAULT 'Unknown',
                category TEXT DEFAULT 'Other',
                notes TEXT,
                has_mismatch INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS receipt_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                quantity REAL DEFAULT 1.0,
                unit_price REAL DEFAULT 0.0,
                total REAL DEFAULT 0.0,
                category TEXT DEFAULT 'Other',
                FOREIGN KEY (receipt_id) REFERENCES receipts (id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bill_splits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_id INTEGER NOT NULL,
                participant_name TEXT NOT NULL,
                share_amount REAL NOT NULL,
                percentage REAL DEFAULT 0.0,
                split_mode TEXT DEFAULT 'Equal',
                created_at TEXT NOT NULL,
                FOREIGN KEY (receipt_id) REFERENCES receipts (id) ON DELETE CASCADE
            )
        """)
        conn.commit()
    finally:
        conn.close()


def save_receipt(receipt_dict: Dict[str, Any], db_path: str = DB_PATH_DEFAULT) -> int:
    """
    Saves a confirmed receipt and its line items to SQLite.
    Returns the generated receipt ID.
    """
    init_db(db_path)
    now_str = datetime.now().isoformat()
    
    subtotal, calculated_total = recalculate_receipt_totals(
        receipt_dict.get("items", []),
        receipt_dict.get("tax", 0),
        receipt_dict.get("discount", 0),
        receipt_dict.get("service_charge", 0)
    )

    final_total = to_decimal(receipt_dict.get("final_total", calculated_total))
    has_mismatch, _ = check_total_mismatch(final_total, calculated_total)

    receipt_date = receipt_dict.get("date") or date.today().isoformat()

    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO receipts (
                merchant, date, currency, subtotal, tax, discount, service_charge,
                final_total, calculated_total, payment_method, category, notes,
                has_mismatch, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(receipt_dict.get("merchant") or "Unknown Merchant"),
            receipt_date,
            str(receipt_dict.get("currency") or "USD"),
            float(subtotal),
            float(to_decimal(receipt_dict.get("tax"))),
            float(to_decimal(receipt_dict.get("discount"))),
            float(to_decimal(receipt_dict.get("service_charge"))),
            float(final_total),
            float(calculated_total),
            str(receipt_dict.get("payment_method") or "Unknown"),
            str(receipt_dict.get("category") or receipt_dict.get("suggested_category") or "Other"),
            str(receipt_dict.get("notes") or ""),
            1 if has_mismatch else 0,
            now_str,
            now_str
        ))
        receipt_id = cursor.lastrowid

        # Insert line items
        for item in receipt_dict.get("items", []):
            qty = float(to_decimal(item.get("quantity", 1)))
            u_price = float(to_decimal(item.get("unit_price", 0)))
            i_total = float(to_decimal(item.get("total", qty * u_price)))
            cursor.execute("""
                INSERT INTO receipt_items (receipt_id, name, quantity, unit_price, total, category)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                receipt_id,
                str(item.get("name") or "Unnamed Item"),
                qty,
                u_price,
                i_total,
                str(item.get("category") or receipt_dict.get("category") or "Other")
            ))

        conn.commit()
        return receipt_id
    finally:
        conn.close()


def get_receipts(
    db_path: str = DB_PATH_DEFAULT,
    search_merchant: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    category: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Queries saved receipts with optional search and filter parameters.
    """
    init_db(db_path)
    query = "SELECT * FROM receipts WHERE 1=1"
    params = []

    if search_merchant and search_merchant.strip():
        query += " AND merchant LIKE ?"
        params.append(f"%{search_merchant.strip()}%")

    if date_from:
        query += " AND date >= ?"
        params.append(date_from)

    if date_to:
        query += " AND date <= ?"
        params.append(date_to)

    if min_amount is not None:
        query += " AND final_total >= ?"
        params.append(min_amount)

    if max_amount is not None:
        query += " AND final_total <= ?"
        params.append(max_amount)

    if category and category != "All":
        query += " AND category = ?"
        params.append(category)

    query += " ORDER BY date DESC, id DESC"

    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_receipt_details(receipt_id: int, db_path: str = DB_PATH_DEFAULT) -> Optional[Dict[str, Any]]:
    """
    Retrieves a single receipt along with its line items and bill splits.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM receipts WHERE id = ?", (receipt_id,))
        receipt_row = cursor.fetchone()
        if not receipt_row:
            return None

        receipt_dict = dict(receipt_row)

        cursor.execute("SELECT * FROM receipt_items WHERE receipt_id = ?", (receipt_id,))
        items = [dict(r) for r in cursor.fetchall()]
        receipt_dict["items"] = items

        cursor.execute("SELECT * FROM bill_splits WHERE receipt_id = ?", (receipt_id,))
        splits = [dict(r) for r in cursor.fetchall()]
        receipt_dict["splits"] = splits

        return receipt_dict
    finally:
        conn.close()


def update_receipt(receipt_id: int, updated_dict: Dict[str, Any], db_path: str = DB_PATH_DEFAULT) -> bool:
    """
    Updates a saved receipt and replaces its line items.
    """
    init_db(db_path)
    now_str = datetime.now().isoformat()

    subtotal, calculated_total = recalculate_receipt_totals(
        updated_dict.get("items", []),
        updated_dict.get("tax", 0),
        updated_dict.get("discount", 0),
        updated_dict.get("service_charge", 0)
    )

    final_total = to_decimal(updated_dict.get("final_total", calculated_total))
    has_mismatch, _ = check_total_mismatch(final_total, calculated_total)

    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE receipts SET
                merchant = ?, date = ?, currency = ?, subtotal = ?, tax = ?,
                discount = ?, service_charge = ?, final_total = ?, calculated_total = ?,
                payment_method = ?, category = ?, notes = ?, has_mismatch = ?, updated_at = ?
            WHERE id = ?
        """, (
            str(updated_dict.get("merchant") or "Unknown Merchant"),
            str(updated_dict.get("date") or date.today().isoformat()),
            str(updated_dict.get("currency") or "USD"),
            float(subtotal),
            float(to_decimal(updated_dict.get("tax"))),
            float(to_decimal(updated_dict.get("discount"))),
            float(to_decimal(updated_dict.get("service_charge"))),
            float(final_total),
            float(calculated_total),
            str(updated_dict.get("payment_method") or "Unknown"),
            str(updated_dict.get("category") or "Other"),
            str(updated_dict.get("notes") or ""),
            1 if has_mismatch else 0,
            now_str,
            receipt_id
        ))

        # Delete existing line items and re-insert
        cursor.execute("DELETE FROM receipt_items WHERE receipt_id = ?", (receipt_id,))
        for item in updated_dict.get("items", []):
            qty = float(to_decimal(item.get("quantity", 1)))
            u_price = float(to_decimal(item.get("unit_price", 0)))
            i_total = float(to_decimal(item.get("total", qty * u_price)))
            cursor.execute("""
                INSERT INTO receipt_items (receipt_id, name, quantity, unit_price, total, category)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                receipt_id,
                str(item.get("name") or "Unnamed Item"),
                qty,
                u_price,
                i_total,
                str(item.get("category") or updated_dict.get("category") or "Other")
            ))

        conn.commit()
        return True
    finally:
        conn.close()


def delete_receipt(receipt_id: int, db_path: str = DB_PATH_DEFAULT) -> bool:
    """
    Deletes a receipt and associated line items and splits.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# Bill Splitting Algorithms
def split_bill_equal(final_total: Any, participant_names: List[str]) -> Tuple[bool, List[Dict[str, Any]], str]:
    """
    Splits bill total equally among participants, adjusting leftover cents deterministically.
    """
    names = [n.strip() for n in participant_names if n.strip()]
    if not names:
        return False, [], "Please provide at least one participant name."

    total_dec = to_decimal(final_total)
    if total_dec <= Decimal("0.00"):
        return False, [], "Bill total must be greater than zero."

    num = len(names)
    # Convert to minor units (cents)
    total_cents = int((total_dec * 100).to_integral_value())
    base_cents = total_cents // num
    remainder = total_cents % num

    splits = []
    for i, name in enumerate(names):
        person_cents = base_cents + (1 if i < remainder else 0)
        share = Decimal(person_cents) / Decimal("100")
        percentage = (share / total_dec * Decimal("100")).quantize(Decimal("0.01"))
        splits.append({
            "participant_name": name,
            "share_amount": float(share),
            "percentage": float(percentage),
            "split_mode": "Equal"
        })

    return True, splits, "Equal split computed successfully."


def split_bill_percentage(
    final_total: Any,
    participant_percentages: Dict[str, Any]
) -> Tuple[bool, List[Dict[str, Any]], str]:
    """
    Splits bill according to custom user percentages.
    Validates that total percentage equals 100%.
    """
    total_dec = to_decimal(final_total)
    if total_dec <= Decimal("0.00"):
        return False, [], "Bill total must be greater than zero."

    cleaned_percentages = {n.strip(): to_decimal(p) for n, p in participant_percentages.items() if n.strip()}
    if not cleaned_percentages:
        return False, [], "No participants specified."

    sum_pct = sum(cleaned_percentages.values())
    if abs(sum_pct - Decimal("100.00")) > Decimal("0.05"):
        return False, [], f"Total percentage must sum to 100%. Current sum: {sum_pct:.2f}%"

    splits = []
    accumulated_share = Decimal("0.00")
    names = list(cleaned_percentages.keys())

    for i, name in enumerate(names):
        pct = cleaned_percentages[name]
        if i == len(names) - 1:
            # Assign remaining amount to last person to avoid penny drift
            share = total_dec - accumulated_share
        else:
            share = (total_dec * pct / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            accumulated_share += share

        splits.append({
            "participant_name": name,
            "share_amount": float(share),
            "percentage": float(pct),
            "split_mode": "Percentage"
        })

    return True, splits, "Percentage split computed successfully."


def split_bill_fixed(
    final_total: Any,
    participant_amounts: Dict[str, Any]
) -> Tuple[bool, List[Dict[str, Any]], str]:
    """
    Splits bill based on custom fixed amounts per person.
    Validates that allocations sum up to final_total.
    """
    total_dec = to_decimal(final_total)
    if total_dec <= Decimal("0.00"):
        return False, [], "Bill total must be greater than zero."

    cleaned_amounts = {n.strip(): to_decimal(a) for n, a in participant_amounts.items() if n.strip()}
    if not cleaned_amounts:
        return False, [], "No participants specified."

    sum_amounts = sum(cleaned_amounts.values())
    if abs(sum_amounts - total_dec) > Decimal("0.02"):
        return False, [], (
            f"Allocations total ({sum_amounts:.2f}) does not match bill total ({total_dec:.2f}). "
            f"Difference: {abs(sum_amounts - total_dec):.2f}"
        )

    splits = []
    for name, amt in cleaned_amounts.items():
        pct = (amt / total_dec * Decimal("100")).quantize(Decimal("0.01")) if total_dec > Decimal("0.00") else Decimal("0.00")
        splits.append({
            "participant_name": name,
            "share_amount": float(amt),
            "percentage": float(pct),
            "split_mode": "Fixed Amount"
        })

    return True, splits, "Fixed amount split verified successfully."


def split_bill_itemized(
    items: List[Dict[str, Any]],
    tax: Any,
    discount: Any,
    service_charge: Any,
    item_assignments: Dict[int, List[str]]
) -> Tuple[bool, List[Dict[str, Any]], str]:
    """
    Splits bill by assigning specific items to participants.
    Tax, discount, and service charge are distributed proportionally to each person's item subtotal share.
    """
    dec_tax = to_decimal(tax)
    dec_discount = to_discount = to_decimal(discount)
    dec_service = to_decimal(service_charge)

    # Compute total item subtotal
    subtotal, calculated_total = recalculate_receipt_totals(items, dec_tax, dec_discount, dec_service)
    
    if calculated_total <= Decimal("0.00"):
        return False, [], "Calculated total must be greater than zero."

    person_item_subtotals: Dict[str, Decimal] = {}

    for idx, item in enumerate(items):
        item_tot = to_decimal(item.get("total", 0))
        assigned_people = item_assignments.get(idx, [])
        assigned_people = [p.strip() for p in assigned_people if p.strip()]

        if not assigned_people:
            return False, [], f"Item '{item.get('name', 'Item ' + str(idx+1))}' has no assigned participants."

        num_assigned = Decimal(len(assigned_people))
        item_share = (item_tot / num_assigned).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        for person in assigned_people:
            person_item_subtotals[person] = person_item_subtotals.get(person, Decimal("0.00")) + item_share

    raw_assigned_subtotal = sum(person_item_subtotals.values())
    if raw_assigned_subtotal <= Decimal("0.00"):
        return False, [], "Subtotal of assigned items must be positive."

    splits = []
    people = list(person_item_subtotals.keys())
    accumulated_total = Decimal("0.00")

    for i, person in enumerate(people):
        p_subtotal = person_item_subtotals[person]
        proportion = p_subtotal / raw_assigned_subtotal

        if i == len(people) - 1:
            person_final_share = calculated_total - accumulated_total
        else:
            p_tax = dec_tax * proportion
            p_service = dec_service * proportion
            p_disc = dec_discount * proportion
            person_final_share = (p_subtotal + p_tax + p_service - p_disc).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            accumulated_total += person_final_share

        pct = (person_final_share / calculated_total * Decimal("100")).quantize(Decimal("0.01"))

        splits.append({
            "participant_name": person,
            "share_amount": float(person_final_share),
            "percentage": float(pct),
            "split_mode": "Itemized"
        })

    return True, splits, "Itemized split computed successfully."


def save_bill_splits(receipt_id: int, splits_list: List[Dict[str, Any]], db_path: str = DB_PATH_DEFAULT) -> bool:
    """
    Saves bill split allocations to SQLite.
    """
    init_db(db_path)
    now_str = datetime.now().isoformat()
    conn = get_db_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bill_splits WHERE receipt_id = ?", (receipt_id,))
        for split in splits_list:
            cursor.execute("""
                INSERT INTO bill_splits (receipt_id, participant_name, share_amount, percentage, split_mode, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                receipt_id,
                str(split["participant_name"]),
                float(to_decimal(split["share_amount"])),
                float(to_decimal(split.get("percentage", 0))),
                str(split.get("split_mode", "Equal")),
                now_str
            ))
        conn.commit()
        return True
    finally:
        conn.close()


# Dashboard & Analytics Helpers
def get_dashboard_metrics(
    db_path: str = DB_PATH_DEFAULT,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> Dict[str, Any]:
    """
    Computes key financial KPI metrics.
    """
    receipts = get_receipts(db_path, date_from=date_from, date_to=date_to)
    if not receipts:
        return {
            "total_expenses": 0.0,
            "total_receipts": 0,
            "average_bill": 0.0,
            "highest_bill": 0.0,
            "latest_receipt": "None"
        }

    totals = [r["final_total"] for r in receipts]
    total_exp = sum(totals)
    count = len(receipts)
    avg_bill = total_exp / count if count > 0 else 0.0
    highest_bill = max(totals) if totals else 0.0

    return {
        "total_expenses": round(total_exp, 2),
        "total_receipts": count,
        "average_bill": round(avg_bill, 2),
        "highest_bill": round(highest_bill, 2),
        "latest_receipt": receipts[0]["merchant"] if receipts else "None"
    }


def get_spending_by_category(
    db_path: str = DB_PATH_DEFAULT,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> pd.DataFrame:
    """
    Returns spending aggregated by category.
    """
    receipts = get_receipts(db_path, date_from=date_from, date_to=date_to)
    if not receipts:
        return pd.DataFrame(columns=["Category", "Amount"])

    df = pd.DataFrame(receipts)
    df_cat = df.groupby("category")["final_total"].sum().reset_index()
    df_cat.columns = ["Category", "Amount"]
    df_cat["Amount"] = df_cat["Amount"].round(2)
    return df_cat.sort_values(by="Amount", ascending=False)


def get_spending_over_time(
    db_path: str = DB_PATH_DEFAULT,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> pd.DataFrame:
    """
    Returns daily spending trends over time.
    """
    receipts = get_receipts(db_path, date_from=date_from, date_to=date_to)
    if not receipts:
        return pd.DataFrame(columns=["Date", "Amount"])

    df = pd.DataFrame(receipts)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df_time = df.groupby("date")["final_total"].sum().reset_index()
    df_time.columns = ["Date", "Amount"]
    df_time["Amount"] = df_time["Amount"].round(2)
    return df_time.sort_values(by="Date")


def get_spending_by_merchant(
    db_path: str = DB_PATH_DEFAULT,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    top_n: int = 10
) -> pd.DataFrame:
    """
    Returns spending aggregated by top merchants.
    """
    receipts = get_receipts(db_path, date_from=date_from, date_to=date_to)
    if not receipts:
        return pd.DataFrame(columns=["Merchant", "Amount"])

    df = pd.DataFrame(receipts)
    df_merch = df.groupby("merchant")["final_total"].sum().reset_index()
    df_merch.columns = ["Merchant", "Amount"]
    df_merch["Amount"] = df_merch["Amount"].round(2)
    return df_merch.sort_values(by="Amount", ascending=False).head(top_n)


# PDF Report Generation
def generate_pdf_report(receipts_list: List[Dict[str, Any]], title: str = "Expense Tracker Report") -> bytes:
    """
    Generates a PDF document summary using ReportLab.
    Returns PDF content as bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=22,
        textColor=colors.HexColor('#1E293B'),
        spaceAfter=12
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#64748B'),
        spaceAfter=20
    )
    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontSize=10,
        fontName='Helvetica-Bold',
        textColor=colors.white
    )
    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#334155')
    )

    story = []
    story.append(Paragraph(title, title_style))
    story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Receipts Count: {len(receipts_list)}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#E2E8F0'), spaceAfter=15))

    if not receipts_list:
        story.append(Paragraph("No receipts found for the selected criteria.", styles['Normal']))
    else:
        # Table columns: ID, Date, Merchant, Category, Payment, Total
        table_data = [[
            Paragraph("ID", table_header_style),
            Paragraph("Date", table_header_style),
            Paragraph("Merchant", table_header_style),
            Paragraph("Category", table_header_style),
            Paragraph("Payment", table_header_style),
            Paragraph("Total", table_header_style)
        ]]

        total_sum = Decimal("0.00")
        for r in receipts_list:
            r_total = to_decimal(r.get("final_total", 0))
            total_sum += r_total
            curr = str(r.get("currency") or "USD")
            table_data.append([
                Paragraph(str(r.get("id", "")), table_cell_style),
                Paragraph(str(r.get("date", "")), table_cell_style),
                Paragraph(str(r.get("merchant", "")), table_cell_style),
                Paragraph(str(r.get("category", "Other")), table_cell_style),
                Paragraph(str(r.get("payment_method", "Unknown")), table_cell_style),
                Paragraph(f"{curr} {r_total:.2f}", table_cell_style)
            ])

        # Summary footer row
        table_data.append([
            Paragraph("<b>TOTAL</b>", table_cell_style),
            Paragraph("", table_cell_style),
            Paragraph("", table_cell_style),
            Paragraph("", table_cell_style),
            Paragraph("", table_cell_style),
            Paragraph(f"<b>{total_sum:.2f}</b>", table_cell_style)
        ])

        t = Table(table_data, colWidths=[30, 75, 160, 110, 85, 80])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3B82F6')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F8FAFC')]),
            ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.HexColor('#1E293B')),
            ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#E2E8F0')),
        ]))
        story.append(t)

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# CSV Data Exporter
def generate_receipts_csv(receipts_list: List[Dict[str, Any]]) -> str:
    """
    Converts list of receipt dictionaries to CSV string.
    """
    if not receipts_list:
        return "id,merchant,date,currency,final_total,category,payment_method,has_mismatch\n"
    df = pd.DataFrame(receipts_list)
    cols = ["id", "merchant", "date", "currency", "subtotal", "tax", "discount", "service_charge", "final_total", "category", "payment_method", "has_mismatch", "notes"]
    available_cols = [c for c in cols if c in df.columns]
    return df[available_cols].to_csv(index=False)


def generate_items_csv(db_path: str = DB_PATH_DEFAULT) -> str:
    """
    Export all line items across all receipts as CSV.
    """
    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        df = pd.read_sql_query("""
            SELECT ri.id, ri.receipt_id, r.merchant, r.date, ri.name as item_name,
                   ri.quantity, ri.unit_price, ri.total, ri.category
            FROM receipt_items ri
            JOIN receipts r ON ri.receipt_id = r.id
            ORDER BY r.date DESC, r.id DESC
        """, conn)
        return df.to_csv(index=False)
    finally:
        conn.close()


# Gmail SMTP Email Integration
def send_email_summary(
    recipient_email: str,
    subject: str,
    body_text: str,
    pdf_bytes: Optional[bytes] = None,
    pdf_filename: str = "expense_summary.pdf",
    gmail_address: Optional[str] = None,
    gmail_app_password: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Sends an email summary with optional PDF attachment using Gmail SMTP.
    Requires Gmail App Password.
    """
    if not recipient_email or "@" not in recipient_email or "." not in recipient_email:
        return False, "Invalid recipient email address format."

    if not gmail_address or not gmail_app_password:
        return False, "Gmail credentials missing. Please configure GMAIL_ADDRESS and GMAIL_APP_PASSWORD in settings or secrets.toml."

    try:
        msg = MIMEMultipart()
        msg["From"] = gmail_address
        msg["To"] = recipient_email
        msg["Subject"] = subject

        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        if pdf_bytes:
            part = MIMEApplication(pdf_bytes, Name=pdf_filename)
            part["Content-Disposition"] = f'attachment; filename="{pdf_filename}"'
            msg.attach(part)

        # Connect via TLS on port 587
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
        server.starttls()
        server.login(gmail_address, gmail_app_password)
        server.send_message(msg)
        server.quit()

        return True, f"Email summary successfully sent to {recipient_email}!"

    except smtplib.SMTPAuthenticationError:
        return False, "Gmail Authentication failed. Please ensure GMAIL_APP_PASSWORD is an active App Password, not your standard password."
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"
