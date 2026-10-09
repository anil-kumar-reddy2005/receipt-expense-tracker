# 🧾 Receipt & Expense Tracker

An AI-powered receipt scanning, financial verification, and expense management web application built with **Streamlit** and **Google's Gemini Vision AI** (`google-genai` SDK).

---

## 🌟 Features

- **📸 AI Vision Receipt Extraction:** Upload photo receipts (JPG, PNG, WEBP). Automatically extracts merchant, date, currency, itemized line items, quantities, unit prices, tax, discounts, and totals using Gemini Vision AI.
- **🛡️ Financial Accuracy & User Correction:** Recalculates subtotals and totals using Python's `Decimal` precision engine. Detects mismatches between printed total and itemized sum with warning badges. Allows users to edit any field before confirming.
- **🗄️ Persistent SQLite Storage:** Save confirmed receipts locally. Search and filter history by merchant, date range, category, or bill amount. Edit or delete receipts safely.
- **💸 Smart Bill Splitter:** Split bills among multiple people using 4 split modes: Equal Split (with 1-cent rounding adjustment), Percentage Allocation, Fixed Amount, or Itemized Assignment (proportional tax/discount sharing).
- **📊 Interactive Analytics & Dashboard:** View financial metrics (Total Spent, Avg Bill, Highest Receipt), spending trend lines, category donut charts, and top merchant bar charts powered by Plotly.
- **📄 Printable PDF Reports & CSV Export:** Download structured PDF summary reports using ReportLab or export raw data as Receipts Summary CSV and Line Items CSV.
- **📧 Optional Gmail SMTP Summaries:** Send automated email summaries with PDF report attachments using Gmail App Passwords.

---

## 🛠️ Technology Stack

- **Python:** 3.10 or newer
- **User Interface:** Streamlit (Custom Glassmorphic Dark Theme)
- **AI / Multimodal Vision:** Google Gen AI SDK (`google-genai`) with configurable Gemini models (`gemini-2.5-flash`, `gemini-2.0-flash`)
- **Data & Visualization:** Pandas, Plotly Express
- **Financial Arithmetic:** Python `decimal.Decimal` module
- **Database:** SQLite3
- **PDF Generation:** ReportLab
- **Email:** Standard library `smtplib` / `email` via TLS

---

## 📁 Project Structure

```
receipt-expense-tracker/
├── app.py                      # Main Streamlit UI, multi-section navigation, state management & views
├── prompts.py                  # AI prompt templates, system instructions, untrusted input safety rules
├── receipt_processor.py        # Gemini API client wrapper, image validation, JSON parsing & sanitization
├── expense_utils.py            # Decimal math engine, SQLite CRUD, bill splitting, PDF & email logic
├── test_tracker.py             # Complete automated unit test suite (mocked Gemini, math, database, splits)
├── requirements.txt            # Python package dependencies
├── README.md                   # Complete documentation
├── .gitignore                  # Excludes secrets, database files, caches, venv
└── .streamlit/
    ├── secrets.toml.example    # Secrets template
    └── config.toml             # Custom theme configuration
```

---

## 🚀 Setup & Installation (Windows PowerShell)

### 1. Prerequisites
- Python 3.10+ installed and added to PATH.
- Google Gemini API Key from [Google AI Studio](https://aistudio.google.com/).

### 2. Virtual Environment & Dependencies
Open PowerShell and navigate to the project directory:

```powershell
# Navigate into the project folder
cd receipt-expense-tracker

# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Upgrade pip and install dependencies
pip install -r requirements.txt
```

### 3. API Key & Secrets Setup
Copy the secrets example template:

```powershell
Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
```

Edit `.streamlit/secrets.toml` with your text editor:

```toml
# Google Gemini API Key
GEMINI_API_KEY = "your_actual_gemini_api_key_here"

# Optional Gmail Credentials (for email summaries)
GMAIL_ADDRESS = "your_email@gmail.com"
GMAIL_APP_PASSWORD = "your_16_character_app_password"
```

*(Note: You can also enter or override your Gemini API Key directly inside the application under **⚙️ Settings**).*

---

## 🧪 Running Unit Tests

Run the automated unit test suite (no paid API calls required):

```powershell
python -m unittest test_tracker.py
```

---

## 💻 Launching the Application

Run Streamlit app:

```powershell
streamlit run app.py
```

The app will open automatically in your browser at `http://localhost:8501`.

---

## ☁️ Deploying to Streamlit Community Cloud

1. Push your repository to GitHub (ensure `.streamlit/secrets.toml` is **NOT** committed; check `.gitignore`).
2. Go to [Streamlit Community Cloud](https://share.streamlit.io/).
3. Click **New App**, select your GitHub repository, branch `main`, and set Main file path to `app.py` (or `receipt-expense-tracker/app.py`).
4. Under **Advanced Settings > Secrets**, paste the contents of your `secrets.toml` (with your actual `GEMINI_API_KEY`).
5. Click **Deploy**.

---

## 🔒 Security & Best Practices

- **Untrusted Input Protection:** Prompt instructions strictly isolate text found inside receipt images to prevent prompt injection attacks.
- **Secrets Management:** Credentials are read from `.streamlit/secrets.toml` or session state; never hardcoded in source code.
- **Input Sanitization:** Image uploads are validated against MIME type, extension, and file size limits (10 MB).
- **Financial Integrity:** Python `Decimal` is used to calculate line totals and prevent floating-point rounding drift.

---

## ⚠️ Limitations & Disclaimer

- **Expense Management Tool:** This application is designed for personal expense tracking and bill splitting assistance. It is not an official tax, accounting, or audit authority tool.
- **Hosted Storage Note:** Local SQLite database persistence (`expenses.db`) operates on local disk. On hosted environments like Streamlit Community Cloud, SQLite data may reset upon container restarts unless persistent storage mounts are configured.
