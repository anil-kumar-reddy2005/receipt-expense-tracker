"""
Receipt & Expense Tracker - Polished SaaS Dashboard Application
AI-powered receipt scanning, financial verification, SQLite expense history,
bill splitting, interactive analytics, PDF exports, and Gmail SMTP email summaries.
"""

import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
from decimal import Decimal

# Import custom modules
from receipt_processor import (
    validate_image,
    extract_receipt_data,
    resolve_api_key,
    DEFAULT_MODEL_ID,
    FALLBACK_MODEL_IDS
)
from expense_utils import (
    to_decimal,
    recalculate_receipt_totals,
    check_total_mismatch,
    init_db,
    save_receipt,
    get_receipts,
    get_receipt_details,
    update_receipt,
    delete_receipt,
    split_bill_equal,
    split_bill_percentage,
    split_bill_fixed,
    split_bill_itemized,
    save_bill_splits,
    get_dashboard_metrics,
    get_spending_by_category,
    get_spending_over_time,
    get_spending_by_merchant,
    generate_pdf_report,
    generate_receipts_csv,
    generate_items_csv,
    send_email_summary
)

# Page configuration
st.set_page_config(
    page_title="ReceiptSnap AI | Expense Tracker",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Database
init_db()

# Custom Styling (SaaS Dark Glassmorphism)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Main App Background */
    .stApp {
        background-color: #0B0F17;
        color: #F8FAFC;
    }

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #111827;
        border-right: 1px solid rgba(255, 255, 255, 0.08);
    }
    
    /* SaaS Sidebar Header */
    .sidebar-brand {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 12px 8px 20px 8px;
    }
    .sidebar-brand-icon {
        background: linear-gradient(135deg, #0EA5E9, #6366F1);
        width: 38px;
        height: 38px;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 20px;
        box-shadow: 0 4px 12px rgba(14, 165, 233, 0.3);
    }
    .sidebar-brand-text {
        font-weight: 800;
        font-size: 18px;
        letter-spacing: -0.5px;
        color: #F8FAFC;
    }
    .sidebar-brand-sub {
        font-size: 11px;
        color: #64748B;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.8px;
    }

    /* Nav Buttons */
    div.stButton > button {
        border-radius: 10px;
        font-weight: 600;
        transition: all 0.2s ease-in-out;
    }

    /* Card Containers */
    .saas-card {
        background: rgba(17, 24, 39, 0.7);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 22px;
        box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.3);
        margin-bottom: 20px;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .saas-card:hover {
        border-color: rgba(56, 189, 248, 0.3);
    }

    /* Metric Cards */
    .metric-container {
        display: flex;
        flex-direction: column;
        gap: 6px;
    }
    .metric-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .metric-title {
        font-size: 12px;
        font-weight: 700;
        color: #94A3B8;
        text-transform: uppercase;
        letter-spacing: 0.8px;
    }
    .metric-icon-badge {
        width: 32px;
        height: 32px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 16px;
    }
    .icon-blue { background: rgba(56, 189, 248, 0.15); color: #38BDF8; }
    .icon-purple { background: rgba(168, 85, 247, 0.15); color: #C084FC; }
    .icon-green { background: rgba(34, 197, 94, 0.15); color: #4ADE80; }
    .icon-amber { background: rgba(245, 158, 11, 0.15); color: #FBBF24; }

    .metric-num {
        font-size: 28px;
        font-weight: 800;
        color: #F8FAFC;
        letter-spacing: -0.5px;
    }
    .metric-sub {
        font-size: 12px;
        color: #64748B;
        font-weight: 500;
    }

    /* Custom Badges & Alerts */
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
    }
    .status-green { background: rgba(34, 197, 94, 0.15); color: #4ADE80; border: 1px solid rgba(34, 197, 94, 0.3); }
    .status-red { background: rgba(239, 68, 68, 0.15); color: #FCA5A5; border: 1px solid rgba(239, 68, 68, 0.3); }

    .warning-box {
        background: rgba(239, 68, 68, 0.1);
        border: 1px solid rgba(239, 68, 68, 0.4);
        border-radius: 12px;
        padding: 16px 20px;
        color: #FCA5A5;
        margin: 15px 0;
    }

    .success-box {
        background: rgba(34, 197, 94, 0.1);
        border: 1px solid rgba(34, 197, 94, 0.4);
        border-radius: 12px;
        padding: 16px 20px;
        color: #86EFAC;
        margin: 15px 0;
    }

    /* Hide standard footer */
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# Session State Initialization
if "current_page" not in st.session_state:
    st.session_state.current_page = "Dashboard"
if "scanned_data" not in st.session_state:
    st.session_state.scanned_data = None
if "api_key" not in st.session_state:
    st.session_state.api_key = resolve_api_key() or ""
if "selected_model" not in st.session_state:
    st.session_state.selected_model = DEFAULT_MODEL_ID


# Plotly Custom SaaS Theme Helper
def get_plotly_theme():
    return {
        "layout": go.Layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Plus Jakarta Sans, sans-serif", color="#94A3B8"),
            xaxis=dict(
                gridcolor="#1F2937",
                zerolinecolor="#1F2937",
                tickfont=dict(color="#94A3B8")
            ),
            yaxis=dict(
                gridcolor="#1F2937",
                zerolinecolor="#1F2937",
                tickfont=dict(color="#94A3B8")
            ),
            legend=dict(font=dict(color="#F8FAFC")),
            margin=dict(l=20, r=20, t=30, b=20)
        )
    }


# Navigation Sidebar
with st.sidebar:
    st.markdown("""
    <div class="sidebar-brand">
        <div class="sidebar-brand-icon">⚡</div>
        <div>
            <div class="sidebar-brand-text">ReceiptSnap AI</div>
            <div class="sidebar-brand-sub">SaaS Expense Hub</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.caption("NAVIGATION")

    pages = {
        "Dashboard": "📊  Dashboard",
        "Scan Receipt": "📸  Scan Receipt",
        "Expense History": "📜  Expense History",
        "Bill Splitter": "💸  Bill Splitter",
        "Reports & Analytics": "📈  Reports & Analytics",
        "Settings": "⚙️  Settings"
    }

    for page_key, page_label in pages.items():
        is_active = st.session_state.current_page == page_key
        if st.button(
            page_label,
            key=f"nav_{page_key}",
            use_container_width=True,
            type="primary" if is_active else "secondary"
        ):
            st.session_state.current_page = page_key
            st.rerun()

    st.write("")
    st.divider()

    # System Status Card
    api_active = bool(resolve_api_key(st.session_state.api_key))
    status_class = "status-green" if api_active else "status-red"
    status_icon = "🟢" if api_active else "🔴"
    status_text = "API Key Active" if api_active else "API Key Missing"
    
    receipts_count = len(get_receipts())

    st.markdown(f"""
    <div style="background: rgba(31, 41, 55, 0.5); padding: 14px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.05);">
        <div style="font-size: 11px; font-weight: 700; color: #64748B; uppercase; letter-spacing: 0.8px; margin-bottom: 8px;">SYSTEM STATUS</div>
        <div style="margin-bottom: 6px;">
            <span class="status-badge {status_class}">{status_icon} {status_text}</span>
        </div>
        <div style="font-size: 12px; color: #94A3B8; margin-top: 8px;">
            Model: <strong style="color: #F8FAFC;">{st.session_state.selected_model}</strong>
        </div>
        <div style="font-size: 12px; color: #94A3B8;">
            Total Receipts: <strong style="color: #38BDF8;">{receipts_count}</strong>
        </div>
    </div>
    """, unsafe_allow_html=True)


# Category Options
CATEGORIES = [
    "Groceries",
    "Food & Dining",
    "Travel",
    "Shopping",
    "Healthcare",
    "Education",
    "Utilities",
    "Other"
]


# PAGE 1: DASHBOARD
if st.session_state.current_page == "Dashboard":
    # Header Banner
    h_col1, h_col2 = st.columns([3, 1])
    with h_col1:
        st.title("📊 Executive Dashboard")
        st.caption("Real-time spending intelligence, receipt analytics, and expense velocity.")
    
    with h_col2:
        date_filter = st.selectbox(
            "Filter Period",
            ["All Time", "Last 30 Days", "Last 90 Days", "Custom Range"],
            index=0,
            label_visibility="collapsed"
        )

    date_from, date_to = None, None
    if date_filter == "Last 30 Days":
        date_from = (pd.Timestamp.now() - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
    elif date_filter == "Last 90 Days":
        date_from = (pd.Timestamp.now() - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
    elif date_filter == "Custom Range":
        d_range = st.date_input("Select Range", value=(date.today(), date.today()))
        if isinstance(d_range, tuple) and len(d_range) == 2:
            date_from = d_range[0].strftime("%Y-%m-%d")
            date_to = d_range[1].strftime("%Y-%m-%d")

    metrics = get_dashboard_metrics(date_from=date_from, date_to=date_to)

    st.write("")

    # KPI Metric Cards Grid
    k1, k2, k3, k4 = st.columns(4)

    with k1:
        st.markdown(f"""
        <div class="saas-card">
            <div class="metric-container">
                <div class="metric-header">
                    <span class="metric-title">Total Expenditures</span>
                    <div class="metric-icon-badge icon-blue">💰</div>
                </div>
                <div class="metric-num">${metrics['total_expenses']:,.2f}</div>
                <div class="metric-sub">Across {metrics['total_receipts']} verified receipts</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with k2:
        st.markdown(f"""
        <div class="saas-card">
            <div class="metric-container">
                <div class="metric-header">
                    <span class="metric-title">Total Receipts</span>
                    <div class="metric-icon-badge icon-purple">🧾</div>
                </div>
                <div class="metric-num">{metrics['total_receipts']}</div>
                <div class="metric-sub">Processed & saved</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with k3:
        st.markdown(f"""
        <div class="saas-card">
            <div class="metric-container">
                <div class="metric-header">
                    <span class="metric-title">Average Bill Amount</span>
                    <div class="metric-icon-badge icon-green">📈</div>
                </div>
                <div class="metric-num">${metrics['average_bill']:,.2f}</div>
                <div class="metric-sub">Per receipt average</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with k4:
        st.markdown(f"""
        <div class="saas-card">
            <div class="metric-container">
                <div class="metric-header">
                    <span class="metric-title">Highest Bill</span>
                    <div class="metric-icon-badge icon-amber">🔥</div>
                </div>
                <div class="metric-num">${metrics['highest_bill']:,.2f}</div>
                <div class="metric-sub">Peak single expense</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.write("")

    if metrics['total_receipts'] == 0:
        st.markdown("""
        <div class="saas-card" style="text-align: center; padding: 40px;">
            <div style="font-size: 40px; margin-bottom: 12px;">📸</div>
            <h3 style="margin-bottom: 8px;">No Expenses Logged Yet</h3>
            <p style="color: #94A3B8; margin-bottom: 20px;">Upload your first receipt photo to start unlocking real-time financial insights.</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🚀 Go to Scan Receipt", type="primary"):
            st.session_state.current_page = "Scan Receipt"
            st.rerun()
    else:
        # Charts Row
        chart_col1, chart_col2 = st.columns([1.6, 1])

        with chart_col1:
            st.markdown('<div class="saas-card">', unsafe_allow_html=True)
            st.subheader("📅 Spending Trend Over Time")
            df_time = get_spending_over_time(date_from=date_from, date_to=date_to)
            if not df_time.empty:
                fig_line = px.area(
                    df_time,
                    x="Date",
                    y="Amount",
                    labels={"Amount": "Expenditure ($)", "Date": "Date"},
                )
                fig_line.update_traces(
                    line_color="#38BDF8",
                    fillcolor="rgba(56, 189, 248, 0.15)",
                    line_width=3
                )
                fig_line.update_layout(get_plotly_theme()["layout"])
                fig_line.update_layout(height=320)
                st.plotly_chart(fig_line, use_container_width=True)
            else:
                st.caption("No trend data available for selected range.")
            st.markdown('</div>', unsafe_allow_html=True)

        with chart_col2:
            st.markdown('<div class="saas-card">', unsafe_allow_html=True)
            st.subheader("🏷️ Category Breakdown")
            df_cat = get_spending_by_category(date_from=date_from, date_to=date_to)
            if not df_cat.empty:
                fig_donut = px.pie(
                    df_cat,
                    names="Category",
                    values="Amount",
                    hole=0.55,
                    color_discrete_sequence=["#38BDF8", "#818CF8", "#34D399", "#F472B6", "#FBBF24", "#A78BFA"]
                )
                fig_donut.update_layout(get_plotly_theme()["layout"])
                fig_donut.update_layout(height=320, showlegend=True)
                st.plotly_chart(fig_donut, use_container_width=True)
            else:
                st.caption("No category distribution available.")
            st.markdown('</div>', unsafe_allow_html=True)

        # Top Merchants Bar Chart
        st.markdown('<div class="saas-card">', unsafe_allow_html=True)
        st.subheader("🏬 Top Merchant Destinations")
        df_merch = get_spending_by_merchant(date_from=date_from, date_to=date_to)
        if not df_merch.empty:
            fig_bar = px.bar(
                df_merch,
                x="Merchant",
                y="Amount",
                color="Amount",
                labels={"Amount": "Total Spent ($)"},
                color_continuous_scale=["#1E293B", "#38BDF8"]
            )
            fig_bar.update_layout(get_plotly_theme()["layout"])
            fig_bar.update_layout(height=280, coloraxis_showscale=False)
            st.plotly_chart(fig_bar, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # Recent Receipts Data Table
        st.subheader("⚡ Recent Expenses")
        recent_receipts = get_receipts(date_from=date_from, date_to=date_to)[:6]
        if recent_receipts:
            df_recent = pd.DataFrame(recent_receipts)[["id", "date", "merchant", "category", "payment_method", "final_total"]]
            df_recent.columns = ["ID", "Date", "Merchant", "Category", "Payment", "Total ($)"]
            st.dataframe(
                df_recent,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Total ($)": st.column_config.NumberColumn("Total ($)", format="$%.2f")
                }
            )


# PAGE 2: SCAN RECEIPT
elif st.session_state.current_page == "Scan Receipt":
    st.title("📸 Scan & Extract Receipt")
    st.caption("Upload a receipt, bill, or invoice image. Gemini AI will analyze, itemize, and calculate totals.")

    api_key_active = resolve_api_key(st.session_state.api_key)
    if not api_key_active:
        st.warning("⚠️ Gemini API Key is missing. Configure `GEMINI_API_KEY` in `.streamlit/secrets.toml` or set it in **⚙️ Settings**.")

    col_upload, col_preview = st.columns([1.1, 0.9])

    with col_upload:
        st.markdown('<div class="saas-card">', unsafe_allow_html=True)
        uploaded_file = st.file_uploader(
            "Upload Receipt Photo (JPG, JPEG, PNG, WEBP - Max 10 MB)",
            type=["jpg", "jpeg", "png", "webp"],
            help="Select a clear photo of your receipt or bill."
        )

        model_choice = st.selectbox(
            "Gemini Model Architecture",
            [DEFAULT_MODEL_ID] + [m for m in FALLBACK_MODEL_IDS if m != DEFAULT_MODEL_ID],
            index=0
        )
        st.session_state.selected_model = model_choice
        st.markdown('</div>', unsafe_allow_html=True)

    image_bytes = None
    if uploaded_file is not None:
        image_bytes = uploaded_file.getvalue()
        is_valid, err_msg = validate_image(image_bytes, uploaded_file.name, uploaded_file.type)
        
        if not is_valid:
            st.error(f"❌ Image Validation Error: {err_msg}")
            image_bytes = None
        else:
            with col_preview:
                st.markdown('<div class="saas-card">', unsafe_allow_html=True)
                st.caption(f"PREVIEW: {uploaded_file.name} ({(len(image_bytes)/(1024*1024)):.2f} MB)")
                st.image(image_bytes, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)

    scan_disabled = image_bytes is None or not api_key_active
    
    if st.button("🚀 Analyze Receipt with Gemini AI", type="primary", disabled=scan_disabled, use_container_width=True):
        with st.spinner("⚡ Processing receipt image with Gemini Vision..."):
            try:
                extracted = extract_receipt_data(
                    image_bytes=image_bytes,
                    mime_type=uploaded_file.type if uploaded_file else "image/jpeg",
                    api_key=st.session_state.api_key,
                    model_id=st.session_state.selected_model
                )
                st.session_state.scanned_data = extracted
                st.success("🎉 Receipt extracted successfully! Review and confirm details below.")
            except Exception as e:
                st.error(f"❌ AI Extraction Failed: {str(e)}")

    # Verification & Correction Panel
    if st.session_state.scanned_data:
        st.divider()
        st.subheader("✏️ Financial Verification & Correction")
        st.caption("Verify AI extractions and correct any line items or totals before persisting.")

        data = st.session_state.scanned_data

        with st.expander("🔍 Inspect Raw AI JSON Schema Output"):
            st.json(data)

        with st.form("verify_receipt_form"):
            meta1, meta2, meta3, meta4 = st.columns(4)
            with meta1:
                merchant_val = st.text_input("Merchant Name*", value=data.get("merchant", "Unknown Merchant"))
            with meta2:
                date_val = st.text_input("Date (YYYY-MM-DD)*", value=data.get("date") or date.today().isoformat())
            with meta3:
                currency_val = st.text_input("Currency Code", value=data.get("currency", "USD"))
            with meta4:
                payment_val = st.selectbox(
                    "Payment Method",
                    ["Cash", "Credit Card", "Debit Card", "UPI", "Online", "Unknown"],
                    index=["Cash", "Credit Card", "Debit Card", "UPI", "Online", "Unknown"].index(data.get("payment_method", "Unknown"))
                    if data.get("payment_method") in ["Cash", "Credit Card", "Debit Card", "UPI", "Online", "Unknown"] else 5
                )

            cat1, cat2 = st.columns(2)
            with cat1:
                ai_suggested_cat = data.get("suggested_category", "Other")
                category_val = st.selectbox(
                    "Expense Category",
                    CATEGORIES,
                    index=CATEGORIES.index(ai_suggested_cat) if ai_suggested_cat in CATEGORIES else 7
                )
            with cat2:
                notes_val = st.text_input("Notes / Reference ID", value=data.get("notes", ""))

            st.write("---")
            st.subheader("🛒 Purchased Line Items")

            raw_items = data.get("items", [])
            df_items_input = pd.DataFrame(raw_items if raw_items else [{
                "name": "Sample Item", "quantity": 1.0, "unit_price": 0.0, "total": 0.0, "category": category_val
            }])

            edited_df = st.data_editor(
                df_items_input,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "name": st.column_config.TextColumn("Item Description*", required=True),
                    "quantity": st.column_config.NumberColumn("Qty", min_value=0.01, step=1.0, default=1.0),
                    "unit_price": st.column_config.NumberColumn("Unit Price ($)", min_value=0.0, step=0.01, format="$%.2f"),
                    "total": st.column_config.NumberColumn("Item Total ($)", min_value=0.0, step=0.01, format="$%.2f"),
                    "category": st.column_config.SelectboxColumn("Category", options=CATEGORIES, default=category_val)
                }
            )

            st.write("---")
            st.subheader("💰 Financial Reconciliation")

            fin1, fin2, fin3, fin4 = st.columns(4)
            with fin1:
                tax_val = st.number_input("Tax ($)", min_value=0.0, value=float(data.get("tax", 0.0)), step=0.01)
            with fin2:
                discount_val = st.number_input("Discount ($)", min_value=0.0, value=float(data.get("discount", 0.0)), step=0.01)
            with fin3:
                service_charge_val = st.number_input("Service Charge ($)", min_value=0.0, value=float(data.get("service_charge", 0.0)), step=0.01)
            with fin4:
                printed_total_val = st.number_input("Printed Receipt Total ($)*", min_value=0.0, value=float(data.get("final_total", 0.0)), step=0.01)

            edited_items_list = edited_df.to_dict(orient="records")
            calc_subtotal, calc_final_total = recalculate_receipt_totals(
                edited_items_list, tax_val, discount_val, service_charge_val
            )

            has_mismatch, diff_amount = check_total_mismatch(printed_total_val, calc_final_total)

            st.write("")
            ts1, ts2, ts3 = st.columns(3)
            ts1.metric("Calculated Subtotal", f"${calc_subtotal:.2f}")
            ts2.metric("Calculated Final Total", f"${calc_final_total:.2f}")
            ts3.metric("Printed Receipt Total", f"${printed_total_val:.2f}")

            if has_mismatch:
                st.markdown(f"""
                <div class="warning-box">
                    ⚠️ <b>Total Mismatch Detected:</b> Printed receipt total (<b>${printed_total_val:.2f}</b>) 
                    differs from itemized calculation (<b>${calc_final_total:.2f}</b>) by <b>${diff_amount:.2f}</b>.
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="success-box">
                    ✅ <b>Financial Reconciliation Passed!</b> Item subtotals match the printed receipt total.
                </div>
                """, unsafe_allow_html=True)

            submit_save = st.form_submit_button("💾 Confirm & Persist Receipt", type="primary", use_container_width=True)

            if submit_save:
                save_payload = {
                    "merchant": merchant_val,
                    "date": date_val,
                    "currency": currency_val,
                    "subtotal": float(calc_subtotal),
                    "tax": tax_val,
                    "discount": discount_val,
                    "service_charge": service_charge_val,
                    "final_total": printed_total_val,
                    "calculated_total": float(calc_final_total),
                    "payment_method": payment_val,
                    "category": category_val,
                    "notes": notes_val,
                    "items": edited_items_list
                }
                try:
                    r_id = save_receipt(save_payload)
                    st.success(f"✅ Receipt #{r_id} successfully saved to SQLite!")
                    st.session_state.scanned_data = None
                    st.balloons()
                except Exception as e:
                    st.error(f"❌ Save Error: {str(e)}")


# PAGE 3: EXPENSE HISTORY
elif st.session_state.current_page == "Expense History":
    st.title("📜 Expense Storage & History")
    st.caption("Manage saved receipts, inspect line items, download reports, or execute deletions.")

    st.markdown('<div class="saas-card">', unsafe_allow_html=True)
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        search_merchant = st.text_input("Search Merchant", placeholder="e.g. Walmart")
    with f2:
        filter_cat = st.selectbox("Category", ["All"] + CATEGORIES, index=0)
    with f3:
        d_from = st.date_input("From Date", value=None)
        str_d_from = d_from.strftime("%Y-%m-%d") if d_from else None
    with f4:
        d_to = st.date_input("To Date", value=None)
        str_d_to = d_to.strftime("%Y-%m-%d") if d_to else None
    st.markdown('</div>', unsafe_allow_html=True)

    receipts_list = get_receipts(
        search_merchant=search_merchant,
        date_from=str_d_from,
        date_to=str_d_to,
        category=filter_cat
    )

    # Export toolbar
    exp1, exp2, exp3 = st.columns(3)
    with exp1:
        st.download_button(
            "📥 Receipts Summary CSV",
            data=generate_receipts_csv(receipts_list),
            file_name="receipts_summary.csv",
            mime="text/csv",
            use_container_width=True
        )
    with exp2:
        st.download_button(
            "📥 Line Items Detail CSV",
            data=generate_items_csv(),
            file_name="line_items_detail.csv",
            mime="text/csv",
            use_container_width=True
        )
    with exp3:
        if receipts_list:
            st.download_button(
                "📄 PDF Report Download",
                data=generate_pdf_report(receipts_list),
                file_name="expense_report.pdf",
                mime="application/pdf",
                use_container_width=True
            )

    st.divider()

    if not receipts_list:
        st.info("No receipts match your search filters.")
    else:
        st.caption(f"Displaying {len(receipts_list)} expense record(s):")

        for r in receipts_list:
            r_id = r["id"]
            mismatch_tag = "⚠️ Mismatch" if r.get("has_mismatch") else "✅ Verified"
            
            with st.expander(f"🧾 #{r_id} | {r['date']} | **{r['merchant']}** | ${r['final_total']:.2f} | [{r['category']}] ({mismatch_tag})"):
                details = get_receipt_details(r_id)
                if details:
                    d1, d2 = st.columns([2, 1])
                    with d1:
                        st.markdown(f"**Merchant:** {details['merchant']}")
                        st.markdown(f"**Date:** {details['date']} | **Payment Method:** {details['payment_method']}")
                        st.markdown(f"**Category:** `{details['category']}` | **Currency:** {details['currency']}")
                        if details.get("notes"):
                            st.markdown(f"**Notes:** {details['notes']}")
                        
                        st.write("**Line Items:**")
                        if details.get("items"):
                            df_items = pd.DataFrame(details["items"])[["name", "quantity", "unit_price", "total", "category"]]
                            df_items.columns = ["Item", "Qty", "Unit Price ($)", "Total ($)", "Category"]
                            st.dataframe(df_items, use_container_width=True, hide_index=True)

                    with d2:
                        st.markdown(f"**Subtotal:** ${details['subtotal']:.2f}")
                        st.markdown(f"**Tax:** ${details['tax']:.2f}")
                        st.markdown(f"**Discount:** -${details['discount']:.2f}")
                        st.markdown(f"**Service Charge:** ${details['service_charge']:.2f}")
                        st.markdown(f"### Final Total: ${details['final_total']:.2f}")

                        if details.get("splits"):
                            st.write("---")
                            st.write("**Bill Splits:**")
                            for s in details["splits"]:
                                st.caption(f"👤 {s['participant_name']}: **${s['share_amount']:.2f}** ({s['percentage']}%)")

                        st.write("---")
                        confirm_del = st.checkbox("Confirm Delete", key=f"del_chk_{r_id}")
                        if st.button("🗑️ Delete Receipt", key=f"del_btn_{r_id}", type="secondary", disabled=not confirm_del):
                            if delete_receipt(r_id):
                                st.success(f"Receipt #{r_id} deleted!")
                                st.rerun()


# PAGE 4: BILL SPLITTER
elif st.session_state.current_page == "Bill Splitter":
    st.title("💸 Bill & Expense Splitter")
    st.caption("Allocate joint bills among participants with exact financial precision and penny-rounding safety.")

    st.markdown('<div class="saas-card">', unsafe_allow_html=True)
    split_source = st.radio("Select Bill Source", ["Select From Saved Receipts", "Enter Custom Bill"], horizontal=True)

    receipt_to_split = None
    bill_total_input = 100.0
    bill_items_input = []
    receipt_id_selected = None

    if split_source == "Select From Saved Receipts":
        saved_receipts = get_receipts()
        if not saved_receipts:
            st.warning("No saved receipts found. You can enter a custom bill below.")
        else:
            options_dict = {f"#{r['id']} - {r['merchant']} (${r['final_total']:.2f} on {r['date']})": r['id'] for r in saved_receipts}
            selected_option = st.selectbox("Select Receipt to Split", list(options_dict.keys()))
            receipt_id_selected = options_dict[selected_option]
            receipt_to_split = get_receipt_details(receipt_id_selected)

            if receipt_to_split:
                bill_total_input = float(receipt_to_split["final_total"])
                bill_items_input = receipt_to_split.get("items", [])
                st.info(f"Loaded **{receipt_to_split['merchant']}** | Total: **${bill_total_input:.2f}**")
    else:
        bill_total_input = st.number_input("Enter Final Bill Total ($)", min_value=0.01, value=100.0, step=1.0)

    st.markdown('</div>', unsafe_allow_html=True)

    st.subheader("👥 Participant Configuration")
    split_mode = st.selectbox(
        "Choose Split Method",
        ["Equal Split", "Percentage Allocation", "Fixed Amount Allocation", "Itemized Assignment"]
    )

    participants_str = st.text_input("Participant Names (comma separated)", value="Alice, Bob, Charlie")
    participant_list = [p.strip() for p in participants_str.split(",") if p.strip()]

    splits_result = []
    is_valid_split = False
    status_msg = ""

    if split_mode == "Equal Split":
        is_valid_split, splits_result, status_msg = split_bill_equal(bill_total_input, participant_list)

    elif split_mode == "Percentage Allocation":
        st.write("Enter percentage per person (must sum to 100%):")
        pct_inputs = {}
        cols = st.columns(len(participant_list) if participant_list else 1)
        for i, name in enumerate(participant_list):
            with cols[i % len(cols)]:
                pct_inputs[name] = st.number_input(f"{name} (%)", min_value=0.0, max_value=100.0, value=round(100.0/len(participant_list), 2), step=1.0)
        is_valid_split, splits_result, status_msg = split_bill_percentage(bill_total_input, pct_inputs)

    elif split_mode == "Fixed Amount Allocation":
        st.write("Enter fixed amount per person (must sum to bill total):")
        fixed_inputs = {}
        cols = st.columns(len(participant_list) if participant_list else 1)
        for i, name in enumerate(participant_list):
            with cols[i % len(cols)]:
                fixed_inputs[name] = st.number_input(f"{name} ($)", min_value=0.0, value=round(bill_total_input/len(participant_list), 2), step=1.0)
        is_valid_split, splits_result, status_msg = split_bill_fixed(bill_total_input, fixed_inputs)

    elif split_mode == "Itemized Assignment":
        if not bill_items_input:
            st.warning("Itemized splitting requires selecting a saved receipt with line items.")
        else:
            item_assignments = {}
            for idx, item in enumerate(bill_items_input):
                selected_people = st.multiselect(
                    f"Item: {item['name']} (${item['total']:.2f})",
                    options=participant_list,
                    default=participant_list,
                    key=f"item_assign_{idx}"
                )
                item_assignments[idx] = selected_people

            tax_val = receipt_to_split.get("tax", 0.0) if receipt_to_split else 0.0
            disc_val = receipt_to_split.get("discount", 0.0) if receipt_to_split else 0.0
            serv_val = receipt_to_split.get("service_charge", 0.0) if receipt_to_split else 0.0

            is_valid_split, splits_result, status_msg = split_bill_itemized(
                bill_items_input, tax_val, disc_val, serv_val, item_assignments
            )

    st.write("---")

    if is_valid_split:
        st.markdown(f"""
        <div class="success-box">
            ✅ <b>Valid Allocation:</b> {status_msg}
        </div>
        """, unsafe_allow_html=True)

        st.subheader("📊 Participant Breakdown")
        
        cols = st.columns(len(splits_result) if splits_result else 1)
        for i, s in enumerate(splits_result):
            with cols[i % len(cols)]:
                st.markdown(f"""
                <div class="saas-card">
                    <div style="font-size: 14px; font-weight: 700; color: #38BDF8;">👤 {s['participant_name']}</div>
                    <div style="font-size: 24px; font-weight: 800; color: #F8FAFC; margin: 4px 0;">${s['share_amount']:.2f}</div>
                    <div style="font-size: 12px; color: #94A3B8;">Share: {s['percentage']}%</div>
                </div>
                """, unsafe_allow_html=True)

        if receipt_id_selected:
            if st.button("💾 Save Bill Split Allocation", type="primary"):
                if save_bill_splits(receipt_id_selected, splits_result):
                    st.success("Bill split allocation saved to database!")
    else:
        st.markdown(f"""
        <div class="warning-box">
            ❌ <b>Allocation Mismatch:</b> {status_msg}
        </div>
        """, unsafe_allow_html=True)


# PAGE 5: REPORTS & ANALYTICS
elif st.session_state.current_page == "Reports & Analytics":
    st.title("📈 Reports & Summary Dispatch")
    st.caption("Generate executive financial reports, export PDF documents, and send Gmail summaries.")

    receipts_list = get_receipts()

    if not receipts_list:
        st.info("No expense data recorded yet to construct reports.")
    else:
        metrics = get_dashboard_metrics()
        
        st.markdown('<div class="saas-card">', unsafe_allow_html=True)
        st.subheader("📋 Executive Financial Summary")
        r1, r2 = st.columns(2)
        with r1:
            st.write(f"• **Total Receipts Count:** {metrics['total_receipts']}")
            st.write(f"• **Total Expenditure:** ${metrics['total_expenses']:,.2f}")
            st.write(f"• **Average Receipt Value:** ${metrics['average_bill']:,.2f}")
        with r2:
            st.write(f"• **Peak Single Expense:** ${metrics['highest_bill']:,.2f}")
            st.write(f"• **Latest Activity:** {metrics['latest_receipt']}")
        st.markdown('</div>', unsafe_allow_html=True)

        st.subheader("📄 Export PDF Document")
        pdf_bytes = generate_pdf_report(receipts_list)
        st.download_button(
            "📥 Download PDF Summary Report",
            data=pdf_bytes,
            file_name=f"Expense_Report_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            type="primary"
        )

        st.divider()

        st.subheader("📧 Gmail SMTP Email Summary Dispatch")
        st.caption("Send an automated expense summary with attached PDF to your inbox.")

        gmail_user = st.session_state.get("gmail_address") or (st.secrets.get("GMAIL_ADDRESS") if "GMAIL_ADDRESS" in st.secrets else "")
        gmail_pass = st.session_state.get("gmail_app_password") or (st.secrets.get("GMAIL_APP_PASSWORD") if "GMAIL_APP_PASSWORD" in st.secrets else "")

        if not gmail_user or not gmail_pass:
            st.warning("⚠️ Gmail credentials missing. Configure `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` in `.streamlit/secrets.toml` or Settings to enable email dispatch.")

        with st.form("email_form"):
            recipient_email = st.text_input("Recipient Email Address", value=gmail_user if gmail_user else "user@example.com")
            subject_line = st.text_input("Email Subject", value="Receipt & Expense Tracker Summary Report")
            
            summary_text = (
                f"Expense Summary Report\n"
                f"Date: {datetime.now().strftime('%Y-%m-%d')}\n"
                f"Total Spent: ${metrics['total_expenses']:,.2f}\n"
                f"Receipts Count: {metrics['total_receipts']}\n"
                f"Average Bill: ${metrics['average_bill']:,.2f}\n\n"
                f"Attached is your complete PDF expense report."
            )
            
            body_input = st.text_area("Email Body Message", value=summary_text, height=120)
            attach_pdf = st.checkbox("Attach PDF Summary Report", value=True)

            send_btn = st.form_submit_button("✉️ Send Email Summary", type="primary")

            if send_btn:
                with st.spinner("Dispatching email..."):
                    success, msg = send_email_summary(
                        recipient_email=recipient_email,
                        subject=subject_line,
                        body_text=body_input,
                        pdf_bytes=pdf_bytes if attach_pdf else None,
                        gmail_address=gmail_user,
                        gmail_app_password=gmail_pass
                    )
                    if success:
                        st.success(f"✅ {msg}")
                    else:
                        st.error(f"❌ {msg}")


# PAGE 6: SETTINGS
elif st.session_state.current_page == "Settings":
    st.title("⚙️ Application Settings")
    st.caption("Manage AI model selection, API credentials, email integrations, and database operations.")

    st.markdown('<div class="saas-card">', unsafe_allow_html=True)
    st.subheader("🔑 Gemini AI Configuration")

    key_input = st.text_input(
        "Gemini API Key",
        value=st.session_state.api_key,
        type="password",
        help="Get your key from Google AI Studio: https://aistudio.google.com/"
    )
    if st.button("Save API Key"):
        st.session_state.api_key = key_input
        st.success("API Key saved for current session!")

    model_input = st.selectbox(
        "Gemini Vision Model ID",
        [DEFAULT_MODEL_ID] + [m for m in FALLBACK_MODEL_IDS if m != DEFAULT_MODEL_ID],
        index=0
    )
    st.session_state.selected_model = model_input
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="saas-card">', unsafe_allow_html=True)
    st.subheader("📧 Gmail SMTP Integration (Optional)")
    g_user = st.text_input("Gmail Address", value=st.session_state.get("gmail_address", ""))
    g_pass = st.text_input("Gmail App Password", value=st.session_state.get("gmail_app_password", ""), type="password")

    if st.button("Save Email Credentials"):
        st.session_state["gmail_address"] = g_user
        st.session_state["gmail_app_password"] = g_pass
        st.success("Email credentials saved!")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="saas-card">', unsafe_allow_html=True)
    st.subheader("🗄️ Database Management")
    st.write("Database Path: `expenses.db`")
    
    if st.button("⚠️ Reset Database (Clear All Saved Receipts)", type="secondary"):
        confirm_reset = st.checkbox("Confirm permanent deletion of database records")
        if confirm_reset:
            if os.path.exists("expenses.db"):
                os.remove("expenses.db")
                init_db()
                st.success("Database has been reset!")
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
