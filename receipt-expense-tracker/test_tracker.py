"""
Automated Unit Tests for Receipt & Expense Tracker application.
Run via: python -m unittest test_tracker.py
"""

import unittest
from unittest.mock import patch, MagicMock
from decimal import Decimal
import os
import json
import sqlite3

from expense_utils import (
    to_decimal,
    recalculate_receipt_totals,
    check_total_mismatch,
    split_bill_equal,
    split_bill_percentage,
    split_bill_fixed,
    split_bill_itemized,
    init_db,
    save_receipt,
    get_receipts,
    get_receipt_details,
    update_receipt,
    delete_receipt,
    generate_pdf_report,
    generate_receipts_csv,
    send_email_summary,
    get_dashboard_metrics,
    get_spending_by_category,
    get_spending_over_time
)
from receipt_processor import (
    validate_image,
    sanitize_extracted_data,
    clean_json_response,
    extract_receipt_data
)

TEST_DB_PATH = "test_expenses.db"


class TestFinancialMath(unittest.TestCase):
    """Tests for Decimal precision financial calculations."""

    def test_to_decimal_conversion(self):
        self.assertEqual(to_decimal("12.345"), Decimal("12.35"))
        self.assertEqual(to_decimal("$45.00"), Decimal("45.00"))
        self.assertEqual(to_decimal(10), Decimal("10.00"))
        self.assertEqual(to_decimal(None), Decimal("0.00"))
        self.assertEqual(to_decimal("invalid"), Decimal("0.00"))

    def test_recalculate_receipt_totals(self):
        items = [
            {"name": "Item A", "quantity": 2, "unit_price": 10.50, "total": 21.00},
            {"name": "Item B", "quantity": 1, "unit_price": 5.25, "total": 5.25}
        ]
        subtotal, total = recalculate_receipt_totals(items, tax="2.50", discount="1.00", service_charge="1.50")
        
        self.assertEqual(subtotal, Decimal("26.25"))
        # 26.25 + 2.50 + 1.50 - 1.00 = 29.25
        self.assertEqual(total, Decimal("29.25"))

    def test_total_mismatch_detection(self):
        printed = Decimal("30.00")
        calculated = Decimal("29.25")
        has_mismatch, diff = check_total_mismatch(printed, calculated)
        self.assertTrue(has_mismatch)
        self.assertEqual(diff, Decimal("0.75"))

        matching_printed = Decimal("29.25")
        has_mismatch_match, diff_match = check_total_mismatch(matching_printed, calculated)
        self.assertFalse(has_mismatch_match)
        self.assertEqual(diff_match, Decimal("0.00"))


class TestBillSplitter(unittest.TestCase):
    """Tests for bill splitting algorithms and penny rounding."""

    def test_split_bill_equal_rounding(self):
        # $10.00 split among 3 people -> 3.34, 3.33, 3.33 -> sum is exactly 10.00
        success, splits, msg = split_bill_equal(10.00, ["Alice", "Bob", "Charlie"])
        self.assertTrue(success)
        self.assertEqual(len(splits), 3)

        shares = [Decimal(str(s["share_amount"])) for s in splits]
        self.assertEqual(sum(shares), Decimal("10.00"))
        self.assertEqual(shares[0], Decimal("3.34"))
        self.assertEqual(shares[1], Decimal("3.33"))
        self.assertEqual(shares[2], Decimal("3.33"))

    def test_split_bill_percentage(self):
        success, splits, _ = split_bill_percentage(100.00, {"Alice": 60, "Bob": 40})
        self.assertTrue(success)
        self.assertEqual(splits[0]["share_amount"], 60.0)
        self.assertEqual(splits[1]["share_amount"], 40.0)

        # Invalid percentage sum
        fail_success, _, err_msg = split_bill_percentage(100.00, {"Alice": 50, "Bob": 40})
        self.assertFalse(fail_success)
        self.assertIn("must sum to 100%", err_msg)

    def test_split_bill_fixed(self):
        success, splits, _ = split_bill_fixed(50.00, {"Alice": 30.00, "Bob": 20.00})
        self.assertTrue(success)

        # Mismatching sum
        fail_success, _, err_msg = split_bill_fixed(50.00, {"Alice": 30.00, "Bob": 10.00})
        self.assertFalse(fail_success)
        self.assertIn("does not match bill total", err_msg)

    def test_split_bill_itemized(self):
        items = [
            {"name": "Pizza", "quantity": 1, "unit_price": 20.00, "total": 20.00},
            {"name": "Salad", "quantity": 1, "unit_price": 10.00, "total": 10.00}
        ]
        # Item 0 (Pizza) assigned to Alice, Item 1 (Salad) assigned to Bob
        assignments = {0: ["Alice"], 1: ["Bob"]}
        success, splits, _ = split_bill_itemized(items, tax=3.00, discount=0.00, service_charge=0.00, item_assignments=assignments)
        
        self.assertTrue(success)
        # Pizza subtotal=20 (2/3 of food), Salad subtotal=10 (1/3 of food)
        # Tax=3 -> Alice tax=2, Bob tax=1 -> Alice total=22, Bob total=11 -> sum = 33
        alice_share = next(s for s in splits if s["participant_name"] == "Alice")["share_amount"]
        bob_share = next(s for s in splits if s["participant_name"] == "Bob")["share_amount"]
        
        self.assertEqual(round(alice_share + bob_share, 2), 33.00)
        self.assertEqual(alice_share, 22.00)
        self.assertEqual(bob_share, 11.00)


class TestReceiptSanitization(unittest.TestCase):
    """Tests for Gemini JSON output parsing and sanitization."""

    def test_clean_json_response(self):
        raw_markdown = "```json\n{\"merchant\": \"Supermart\", \"final_total\": 50.0}\n```"
        cleaned = clean_json_response(raw_markdown)
        self.assertEqual(cleaned, '{"merchant": "Supermart", "final_total": 50.0}')

    def test_sanitize_extracted_data_defaults(self):
        raw_dict = {
            "merchant": " Coffee Shop ",
            "date": "2026-10-09",
            "items": [
                {"name": "Latte", "quantity": 2, "unit_price": 4.5, "total": 9.0}
            ]
        }
        sanitized = sanitize_extracted_data(raw_dict)
        self.assertEqual(sanitized["merchant"], "Coffee Shop")
        self.assertEqual(sanitized["subtotal"], 9.0)
        self.assertEqual(sanitized["final_total"], 9.0)
        self.assertEqual(sanitized["currency"], "USD")

    def test_image_validation(self):
        # Empty file
        valid, msg = validate_image(b"", "receipt.jpg")
        self.assertFalse(valid)
        self.assertIn("empty", msg)

        # Invalid extension
        valid, msg = validate_image(b"fakebytes", "receipt.exe")
        self.assertFalse(valid)
        self.assertIn("Unsupported file extension", msg)

        # Valid image
        valid, msg = validate_image(b"fakebytes", "receipt.png")
        self.assertTrue(valid)


class TestDatabaseCRUD(unittest.TestCase):
    """Tests for SQLite database persistence operations using temporary test database."""

    def setUp(self):
        self.db_path = TEST_DB_PATH
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        init_db(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_save_and_get_receipt(self):
        receipt_data = {
            "merchant": "Test Grocery Store",
            "date": "2026-10-09",
            "currency": "USD",
            "tax": 1.50,
            "discount": 0.50,
            "final_total": 15.00,
            "payment_method": "Credit Card",
            "category": "Groceries",
            "items": [
                {"name": "Milk", "quantity": 1, "unit_price": 4.00, "total": 4.00},
                {"name": "Cereal", "quantity": 2, "unit_price": 5.00, "total": 10.00}
            ]
        }
        r_id = save_receipt(receipt_data, self.db_path)
        self.assertGreater(r_id, 0)

        details = get_receipt_details(r_id, self.db_path)
        self.assertIsNotNone(details)
        self.assertEqual(details["merchant"], "Test Grocery Store")
        self.assertEqual(len(details["items"]), 2)

        receipts_list = get_receipts(self.db_path, search_merchant="Test Grocery")
        self.assertEqual(len(receipts_list), 1)

    def test_update_and_delete_receipt(self):
        receipt_data = {
            "merchant": "Original Merchant",
            "date": "2026-10-09",
            "final_total": 10.00,
            "items": [{"name": "Item 1", "quantity": 1, "unit_price": 10.00, "total": 10.00}]
        }
        r_id = save_receipt(receipt_data, self.db_path)

        receipt_data["merchant"] = "Updated Merchant"
        receipt_data["final_total"] = 12.00
        updated = update_receipt(r_id, receipt_data, self.db_path)
        self.assertTrue(updated)

        details = get_receipt_details(r_id, self.db_path)
        self.assertEqual(details["merchant"], "Updated Merchant")
        self.assertEqual(details["final_total"], 12.00)

        deleted = delete_receipt(r_id, self.db_path)
        self.assertTrue(deleted)
        self.assertIsNone(get_receipt_details(r_id, self.db_path))


class TestMockedGeminiWorkflow(unittest.TestCase):
    """Tests for Gemini Vision extraction workflow with mocked API calls."""

    @patch("receipt_processor.get_gemini_client")
    def test_extract_receipt_data_success(self, mock_get_client):
        # Mock Gemini Client and response
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "merchant": "Target Store",
            "date": "2026-10-09",
            "currency": "USD",
            "items": [
                {"name": "Notebook", "quantity": 2, "unit_price": 3.0, "total": 6.0},
                {"name": "Pen Pack", "quantity": 1, "unit_price": 4.0, "total": 4.0}
            ],
            "subtotal": 10.0,
            "tax": 0.80,
            "discount": 1.00,
            "final_total": 9.80,
            "payment_method": "Credit Card"
        })
        mock_client.models.generate_content.return_value = mock_response

        # Execute extraction with fake image bytes
        image_bytes = b"fake_jpeg_header_bytes_data"
        result = extract_receipt_data(image_bytes, mime_type="image/jpeg", api_key="fake_key_123")

        self.assertEqual(result["merchant"], "Target Store")
        self.assertEqual(result["date"], "2026-10-09")
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["subtotal"], 10.0)
        self.assertEqual(result["tax"], 0.80)
        self.assertEqual(result["discount"], 1.00)
        self.assertEqual(result["final_total"], 9.80)

    @patch("receipt_processor.get_gemini_client")
    def test_extract_receipt_data_missing_fields_recovery(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Return partial JSON missing date, currency, subtotal, final_total
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "merchant": "Corner Store",
            "items": [
                {"name": "Coffee", "quantity": 1, "unit_price": 5.0, "total": 5.0}
            ]
        })
        mock_client.models.generate_content.return_value = mock_response

        result = extract_receipt_data(b"image_bytes", api_key="fake_key")

        self.assertEqual(result["merchant"], "Corner Store")
        self.assertIsNone(result["date"])  # missing date becomes None
        self.assertEqual(result["currency"], "USD")  # defaults to USD
        self.assertEqual(result["subtotal"], 5.0)  # calculated from items sum
        self.assertEqual(result["final_total"], 5.0)  # calculated from subtotal

    @patch("receipt_processor.get_gemini_client")
    def test_extract_receipt_data_invalid_json(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_response = MagicMock()
        mock_response.text = "This is not valid JSON text"
        mock_client.models.generate_content.return_value = mock_response

        with self.assertRaises(ValueError) as context:
            extract_receipt_data(b"image_bytes", api_key="fake_key")

        self.assertIn("Failed to parse Gemini output", str(context.exception))


class TestExportsAndEmail(unittest.TestCase):
    """Tests for PDF report generation, CSV exporters, and Email validation."""

    def test_generate_pdf_report(self):
        sample_receipts = [{
            "id": 1, "merchant": "Test Store", "date": "2026-10-09",
            "currency": "USD", "category": "Groceries", "payment_method": "Cash",
            "final_total": 25.50
        }]
        pdf_bytes = generate_pdf_report(sample_receipts)
        self.assertTrue(isinstance(pdf_bytes, bytes))
        self.assertTrue(len(pdf_bytes) > 0)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_generate_csv_exports(self):
        sample_receipts = [{
            "id": 1, "merchant": "Test Store", "date": "2026-10-09",
            "currency": "USD", "category": "Groceries", "payment_method": "Cash",
            "final_total": 25.50
        }]
        csv_str = generate_receipts_csv(sample_receipts)
        self.assertIn("Test Store", csv_str)
        self.assertIn("25.5", csv_str)

    def test_email_validation(self):
        # Invalid email syntax
        success, msg = send_email_summary("invalid-email", "Subject", "Body")
        self.assertFalse(success)
        self.assertIn("Invalid recipient email", msg)

        # Missing Gmail credentials
        success, msg = send_email_summary("test@example.com", "Subject", "Body", gmail_address="", gmail_app_password="")
        self.assertFalse(success)
        self.assertIn("credentials missing", msg)


class TestAnalyticsAndEmptyStates(unittest.TestCase):
    """Tests for analytics data metrics and empty database handling."""

    def setUp(self):
        self.db_path = TEST_DB_PATH
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        init_db(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_empty_dashboard_metrics(self):
        metrics = get_dashboard_metrics(self.db_path)
        self.assertEqual(metrics["total_expenses"], 0.0)
        self.assertEqual(metrics["total_receipts"], 0)
        self.assertEqual(metrics["average_bill"], 0.0)
        self.assertEqual(metrics["highest_bill"], 0.0)
        self.assertEqual(metrics["latest_receipt"], "None")

    def test_empty_spending_by_category(self):
        df = get_spending_by_category(self.db_path)
        self.assertTrue(df.empty)
        self.assertIn("Category", df.columns)
        self.assertIn("Amount", df.columns)

    def test_empty_spending_over_time(self):
        df = get_spending_over_time(self.db_path)
        self.assertTrue(df.empty)
        self.assertIn("Date", df.columns)
        self.assertIn("Amount", df.columns)


if __name__ == "__main__":
    unittest.main()
