import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from datetime import datetime

# --- TAX CALCULATION FUNCTIONS (LOGIC UNCHANGED) ---
def calculate_total_income(regime, salary, business_income, house_income, other_sources, house_loan_interest=0):
    # Salary – Apply standard deduction
    if regime == 'new':
        salary -= 75000
    else:
        salary -= 50000

    # House Property – Apply 30% standard deduction THEN subtract loan interest
    house_income *= 0.70
    house_income -= house_loan_interest  # Deduct interest on house property loan

    # Total income excluding capital gains
    total = max(0, salary) + max(0, business_income) + max(0, house_income) + max(0, other_sources)
    return total

def calculate_surcharge_rate(total_income, regime, capital_gains_income):
    """Determine surcharge rate based on total income & regime, with CG max 15%"""
    rate = 0
    if total_income > 50000000:  # > 5 cr
        rate = 0.37 if regime == "old" else 0.25
    elif total_income > 20000000:  # 2–5 cr
        rate = 0.25
    elif total_income > 10000000:  # 1–2 cr
        rate = 0.15
    elif total_income > 5000000:  # 50L–1cr
        rate = 0.10

    # Capital gains surcharge cap at 15%
    if capital_gains_income > 0 and rate > 0.15:
        rate = 0.15

    return rate

def calculate_tax_old_regime(total_income, stcg, ltcg):
    # Base tax (normal income)
    tax = 0
    if total_income <= 250000:
        tax = 0
    elif total_income <= 500000:
        tax = (total_income - 250000) * 0.05
    elif total_income <= 1000000:
        tax = 12500 + (total_income - 500000) * 0.2
    else:
        tax = 112500 + (total_income - 1000000) * 0.3

    # Capital gains tax (separate calculation)
    cg_tax = stcg * 0.20
    if ltcg > 125000:
        cg_tax += (ltcg - 125000) * 0.125

    # Apply rebate ONLY to regular income tax (NOT capital gains)
    rebate_applied = 0
    if total_income <= 500000:  # ₹5L limit
        rebate_applied = min(12500, tax)  # Max ₹12.5K rebate on regular tax only
        tax_after_rebate = max(0, tax - rebate_applied)
    else:
        tax_after_rebate = tax

    # Total tax = Regular tax (after rebate) + Capital gains tax (no rebate)
    total_tax_before_surcharge = tax_after_rebate + cg_tax

    # Surcharge
    surcharge_rate = calculate_surcharge_rate(total_income + stcg + ltcg, "old", stcg + ltcg)
    surcharge = total_tax_before_surcharge * surcharge_rate

    # Cess
    cess = (total_tax_before_surcharge + surcharge) * 0.04

    return round(max(total_tax_before_surcharge, 0), 2), round(surcharge, 2), round(cess, 2), round(rebate_applied, 2), 0

def calculate_tax_new_regime(total_income, stcg, ltcg):
    # NEW REGIME TAX SLABS FOR FY 2024-25
    slabs = [
        (400000, 0.00),    # 0 to 4L: 0%
        (400000, 0.05),    # 4L to 8L: 5%
        (400000, 0.10),    # 8L to 12L: 10%
        (400000, 0.15),    # 12L to 16L: 15%
        (400000, 0.20),    # 16L to 20L: 20%
        (400000, 0.25),    # 20L to 24L: 25%
        (float('inf'), 0.30) # Above 24L: 30%
    ]

    # Step 1: Apply LTCG exemption of ₹1.25L first
    exempt_ltcg = min(ltcg, 125000)
    taxable_ltcg_after_exemption = max(0, ltcg - exempt_ltcg)

    # Step 2: Calculate available basic exemption (₹4,00,000 for new regime)
    basic_exemption_limit = 400000

    # Step 3: Apply basic exemption in priority order
    # Priority: 1. Other income, 2. STCG, 3. Taxable LTCG
    remaining_exemption = basic_exemption_limit

    # Use exemption for other income first
    other_income_exempted = min(total_income, remaining_exemption)
    remaining_exemption = max(0, remaining_exemption - other_income_exempted)
    taxable_other_income = max(0, total_income - other_income_exempted)

    # Use remaining exemption for STCG
    stcg_exempted = min(stcg, remaining_exemption)
    remaining_exemption = max(0, remaining_exemption - stcg_exempted)
    taxable_stcg = max(0, stcg - stcg_exempted)

    # Use remaining exemption for taxable LTCG
    ltcg_exempted = min(taxable_ltcg_after_exemption, remaining_exemption)
    final_taxable_ltcg = max(0, taxable_ltcg_after_exemption - ltcg_exempted)

    # Step 4: Calculate tax on REGULAR income starting from appropriate slab
    regular_tax = 0
    if taxable_other_income > 0:
        exemption_used_from_regular = other_income_exempted
        if exemption_used_from_regular >= 400000:
            income_remaining = taxable_other_income
            for i in range(1, len(slabs)):
                slab_limit, rate = slabs[i]
                if income_remaining <= 0:
                    break
                taxable_in_slab = min(income_remaining, slab_limit)
                regular_tax += taxable_in_slab * rate
                income_remaining -= taxable_in_slab
        else:
            remaining_in_first_slab = 400000 - exemption_used_from_regular
            income_remaining = taxable_other_income
            if remaining_in_first_slab > 0:
                tax_free_amount = min(income_remaining, remaining_in_first_slab)
                income_remaining -= tax_free_amount
            for i in range(1, len(slabs)):
                if income_remaining <= 0:
                    break
                slab_limit, rate = slabs[i]
                taxable_in_slab = min(income_remaining, slab_limit)
                regular_tax += taxable_in_slab * rate
                income_remaining -= taxable_in_slab

    # Step 5: Calculate capital gains tax separately
    cg_tax = taxable_stcg * 0.20 + final_taxable_ltcg * 0.125

    # Step 6: Apply rebate ONLY to regular income tax
    rebate_applied = 0
    if total_income <= 1200000:
        rebate_applied = min(60000, regular_tax)
        regular_tax_after_rebate = max(0, regular_tax - rebate_applied)
    else:
        regular_tax_after_rebate = regular_tax

    # Step 7: Total tax before relief
    total_tax_before_surcharge = regular_tax_after_rebate + cg_tax

    # Step 8: Apply Marginal Relief
    marginal_relief_applied = 0
    total_taxable_income = total_income + stcg + ltcg
    if 1200000 < total_taxable_income <= 1260000:
        marginal_relief_amount = total_taxable_income - 1200000
        if total_tax_before_surcharge > marginal_relief_amount:
            marginal_relief_applied = total_tax_before_surcharge - marginal_relief_amount
            total_tax_before_surcharge = marginal_relief_amount

    # Step 9: Calculate surcharge
    surcharge_rate = calculate_surcharge_rate(total_income + stcg + ltcg, "new", stcg + ltcg)
    surcharge = total_tax_before_surcharge * surcharge_rate

    # Step 10: Calculate cess
    cess = (total_tax_before_surcharge + surcharge) * 0.04

    return round(max(total_tax_before_surcharge, 0), 2), round(surcharge, 2), round(cess, 2), round(rebate_applied, 2), round(marginal_relief_applied, 2)

# --- PROFESSIONAL EXCEL EXPORT (LOGIC UNCHANGED) ---
def create_professional_excel_report(salary, business_income, house_income, other_sources, stcg, ltcg, regime, house_loan_interest=0):
    """Create Excel report with professional colors and improved visibility using xlsxwriter"""
    processed_salary = salary - (75000 if regime == 'new' else 50000)
    processed_house = (house_income * 0.70) - house_loan_interest
    total_income_calc = max(0, processed_salary) + max(0, business_income) + max(0, processed_house) + max(0, other_sources)
    if regime == 'new':
        tax, surcharge, cess, rebate, marginal_relief = calculate_tax_new_regime(total_income_calc, stcg, max(0, ltcg))
    else:
        tax, surcharge, cess, rebate, marginal_relief = calculate_tax_old_regime(total_income_calc, stcg, max(0, ltcg))
    output = BytesIO()
    try:
        import xlsxwriter
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Income Tax Computation')
        title_format = workbook.add_format({'bold': True, 'font_size': 18, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#003366', 'font_color': '#FFFFFF', 'border': 2, 'border_color': '#000000'})
        header_format = workbook.add_format({'bold': True, 'font_size': 13, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#0066CC', 'font_color': '#FFFFFF', 'border': 1, 'border_color': '#000000'})
        section_format = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#8B0000', 'font_color': '#FFFFFF', 'border': 1, 'border_color': '#000000'})
        bullet_format = workbook.add_format({'bold': True, 'font_size': 12, 'align': 'left', 'valign': 'vcenter', 'bg_color': '#FF8C00', 'font_color': '#FFFFFF', 'border': 1, 'border_color': '#000000'})
        data_format = workbook.add_format({'font_size': 10, 'align': 'left', 'valign': 'vcenter', 'border': 1, 'border_color': '#000000'})
        amount_format = workbook.add_format({'font_size': 10, 'bold': True, 'align': 'right', 'valign': 'vcenter', 'num_format': '₹#,##0.00', 'border': 1, 'border_color': '#000000'})
        total_format = workbook.add_format({'font_size': 11, 'bold': True, 'align': 'right', 'valign': 'vcenter', 'num_format': '₹#,##0.00', 'bg_color': '#E8F4FD', 'border': 1, 'border_color': '#000000'})
        worksheet.set_column('A:A', 50); worksheet.set_column('B:B', 20); worksheet.set_column('C:C', 18); worksheet.set_column('D:D', 20)
        row = 0
        worksheet.write(row, 0, 'Particulars', header_format); worksheet.write(row, 1, 'Details', header_format); worksheet.write(row, 2, 'Sub-total', header_format); worksheet.write(row, 3, 'Total', header_format); row += 1
        worksheet.merge_range(f'A{row+1}:D{row+1}', 'INCOME TAX COMPUTATION - A.Y. 2026-27', title_format); row += 2
        worksheet.merge_range(f'A{row+1}:D{row+1}', 'STATEMENT OF INCOME', section_format); row += 2
        if salary > 0:
            worksheet.merge_range(f'A{row+1}:D{row+1}', '● INCOME FROM SALARY', bullet_format); row += 1
            worksheet.write(row, 0, 'Salary Income', data_format); worksheet.write(row, 1, salary, amount_format); row += 1
            worksheet.write(row, 0, f'Less: Standard deduction u/s 16(ia)', data_format); worksheet.write(row, 1, 75000 if regime == 'new' else 50000, amount_format); row += 1
            worksheet.write(row, 0, 'Net Income from Salary', data_format); worksheet.write(row, 2, max(0, processed_salary), total_format); row += 2
        if house_income != 0 or house_loan_interest > 0:
            worksheet.merge_range(f'A{row+1}:D{row+1}', '● INCOME FROM HOUSE PROPERTY', bullet_format); row += 1
            worksheet.write(row, 0, 'Property Type', data_format); worksheet.write(row, 1, 'Let-out property' if house_income > 0 else 'Self-occupied', data_format); row += 1
            worksheet.write(row, 0, 'Gross annual value' if house_income > 0 else 'Deemed Rental', data_format); worksheet.write(row, 1, abs(house_income) if house_income != 0 else 0, amount_format); row += 1
            worksheet.write(row, 0, 'Less: Municipal taxes', data_format); worksheet.write(row, 1, 0, amount_format); row += 1
            worksheet.write(row, 0, 'Less: Standard deduction u/s 24(a)', data_format); worksheet.write(row, 1, abs(house_income) * 0.30 if house_income != 0 else 0, amount_format); row += 1
            if house_loan_interest > 0:
                worksheet.write(row, 0, 'Less: Interest on housing loan u/s 24(b)', data_format); worksheet.write(row, 1, house_loan_interest, amount_format); row += 1
            worksheet.write(row, 0, 'Net Income from House Property', data_format); worksheet.write(row, 2, processed_house, total_format); row += 2
        if business_income > 0:
            worksheet.merge_range(f'A{row+1}:D{row+1}', '● PROFITS AND GAINS OF BUSINESS OR PROFESSION', bullet_format); row += 1
            worksheet.write(row, 0, 'Business/Professional Income', data_format); worksheet.write(row, 1, business_income, amount_format); row += 1
            worksheet.write(row, 0, 'Net Income from Business/Profession', data_format); worksheet.write(row, 2, business_income, total_format); row += 2
        if stcg > 0 or ltcg > 0:
            worksheet.merge_range(f'A{row+1}:D{row+1}', '● CAPITAL GAINS', bullet_format); row += 1
            if stcg > 0:
                worksheet.write(row, 0, 'Short Term Capital Gains', data_format); worksheet.write(row, 1, stcg, amount_format); row += 1
            if ltcg > 0:
                worksheet.write(row, 0, 'Long Term Capital Gains', data_format); worksheet.write(row, 1, ltcg, amount_format); row += 1
                if ltcg > 125000:
                    worksheet.write(row, 0, 'Less: Exemption u/s 112A', data_format); worksheet.write(row, 1, 125000, amount_format); row += 1
            net_cg = stcg + max(0, ltcg - 125000)
            worksheet.write(row, 0, 'Net Capital Gains', data_format); worksheet.write(row, 2, net_cg, total_format); row += 2
        if other_sources > 0:
            worksheet.merge_range(f'A{row+1}:D{row+1}', '● INCOME FROM OTHER SOURCES', bullet_format); row += 1
            worksheet.write(row, 0, 'Interest Income', data_format); worksheet.write(row, 1, other_sources, amount_format); row += 1
            worksheet.write(row, 0, 'Net Income from Other Sources', data_format); worksheet.write(row, 2, other_sources, total_format); row += 2
        gross_total = total_income_calc + stcg + max(0, ltcg)
        worksheet.write(row, 0, 'Income chargeable under the head House Property', data_format); worksheet.write(row, 3, gross_total, total_format); row += 2
        worksheet.merge_range(f'A{row+1}:D{row+1}', 'TAX COMPUTATION', section_format); row += 2
        worksheet.write(row, 0, f'Tax as per {regime.upper()} regime', data_format); worksheet.write(row, 3, tax, total_format); row += 1
        if surcharge > 0:
            worksheet.write(row, 0, 'Add: Surcharge', data_format); worksheet.write(row, 3, surcharge, amount_format); row += 1
        if cess > 0:
            worksheet.write(row, 0, 'Add: Health & Education Cess', data_format); worksheet.write(row, 3, cess, amount_format); row += 1
        if rebate > 0:
            worksheet.write(row, 0, 'Less: Rebate u/s 87A', data_format); worksheet.write(row, 3, rebate, amount_format); row += 1
        if marginal_relief > 0:
            worksheet.write(row, 0, 'Less: Marginal Relief', data_format); worksheet.write(row, 3, marginal_relief, amount_format); row += 1
        total_tax = tax + surcharge + cess
        worksheet.write(row, 0, 'TOTAL TAX LIABILITY', data_format); worksheet.write(row, 3, total_tax, total_format)
        workbook.close()
        output.seek(0)
        return output
    except ImportError:
        # Fallback logic if xlsxwriter is not installed
        st.error("The 'xlsxwriter' library is required for professional Excel export. Please install it (`pip install xlsxwriter`) and try again.")
        return None

# --- APP LAYOUT STARTS HERE ---

st.set_page_config(
    page_title="APMH Tax Calculator",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 1. INITIALIZE THEME IN SESSION STATE (MUST BE AT THE TOP OF THE SCRIPT FLOW)
if "theme" not in st.session_state:
    st.session_state.theme = "light"

# 2. SIDEBAR CODE (MUST RUN BEFORE CSS IS RENDERED)
with st.sidebar:
    st.markdown("### 🌗 Display Mode")
    is_dark = st.toggle("Enable Dark Mode", key="theme_toggle")

    # This logic updates the theme in the session state
    if is_dark:
        st.session_state.theme = "dark"
    else:
        st.session_state.theme = "light"

    # --- Original sidebar content ---
    st.markdown("### 📊 Quick Regime Comparison")
    st.info("""
    **Old Regime Features:**
    - Standard deduction (₹50,000)
    - Multiple deductions available
    - Basic exemption: ₹2.5L
    - **Rebate: Up to ₹5L income, max ₹12.5K**
    
    **New Regime Features:**
    - Higher standard deduction (₹75,000)
    - Limited deductions
    - Basic exemption: ₹4L
    - **Rebate: Up to ₹12L income, max ₹60K**
    - **🆕 Marginal Relief: ₹12L-₹12.6L income**
    - **Smart CG exemption utilization**
    """)
    
    st.markdown("### 📈 Tax Slabs")
    regime_info = st.selectbox("View details for:", ["New Regime", "Old Regime"])
    
    if regime_info == "New Regime":
        st.markdown("""
        - **₹0 - 4L:** 0%
        - **₹4L - 8L:** 5%
        - **₹8L - 12L:** 10%
        - **₹12L - 16L:** 15%
        - **₹16L - 20L:** 20%
        - **₹20L - 24L:** 25%
        - **Above ₹24L:** 30%
        
        **🆕 Special Benefits:**
        - **Rebate:** ₹60K for income ≤ ₹12L
        - **Marginal Relief:** Income ₹12L-₹12.6L
        - Tax limited to (Income - ₹12L)
        
        **CG Exemption Priority:**
        1. Other income uses ₹4L exemption
        2. STCG uses remaining exemption
        3. LTCG (after ₹1.25L) uses last
        
        **Tax Rates:** STCG: 20% | LTCG: 12.5%
        """)
    else:
        st.markdown("""
        **Old Regime:**
        - **₹0 - 2.5L:** 0%
        - **₹2.5L - 5L:** 5%
        - **₹5L - 10L:** 20%
        - **Above ₹10L:** 30%
        
        **Capital Gains:**
        - **STCG:** 20%
        - **LTCG:** 12.5% (above ₹1.25L)
        """)

# 3. BODY TAG & CSS (MUST RUN AFTER SIDEBAR TO GET THE LATEST THEME)

# This line injects the theme attribute into the body of the app
st.markdown(f"<body data-theme='{st.session_state.theme}'></body>", unsafe_allow_html=True)

# Your full CSS block with percent signs corrected to %%
st.markdown(f"""
<style>
/* ------------------ THEME VARIABLES ------------------ */
:root {{
    --light-bg: #f9f9ff;
    --light-bg-gradient: linear-gradient(135deg, #f9f9ff 0%%, #f2f3ff 100%%);
    --light-text: #2f2f2f;
    --light-header-bg: linear-gradient(90deg, #825CFF, #6E48AA);
    --light-header-text: white;
    --light-container-bg: white;
    --light-input-bg: white;
    --light-input-border: #e3e3e3;
    --light-input-text: #2f2f2f;
    --light-accent: #825CFF;
    --light-sidebar-bg: #fafaff;
}}

[data-theme="dark"] {{
    --bg-color: #0E1117;
    --bg-gradient: linear-gradient(135deg, #0E1117 0%%, #1a1c24 100%%);
    --text-color: #FAFAFA;
    --header-bg: linear-gradient(90deg, #6E48AA, #583391);
    --header-text: white;
    --container-bg: #1c1e24;
    --input-bg: #262730;
    --input-border: #444;
    --input-text: #FAFAFA;
    --accent-color: #825CFF;
    --sidebar-bg: #1c1e24;
}}

[data-theme="light"] {{
    --bg-color: var(--light-bg);
    --bg-gradient: var(--light-bg-gradient);
    --text-color: var(--light-text);
    --header-bg: var(--light-header-bg);
    --header-text: var(--light-header-text);
    --container-bg: var(--light-container-bg);
    --input-bg: var(--light-input-bg);
    --input-border: var(--light-input-border);
    --input-text: var(--light-input-text);
    --accent-color: var(--light-accent);
    --sidebar-bg: var(--light-sidebar-bg);
}}

/* ------------------ BASE STYLES ------------------ */
html, body, [class*="css"]  {{
    font-family: 'Poppins', sans-serif;
}}

body {{
    background: var(--bg-gradient);
    color: var(--text-color);
}}
.stApp {{
    background: var(--bg-color);
}}

.main-header {{
    background: var(--header-bg);
    color: var(--header-text);
    padding: 1.8rem 1rem;
    border-radius: 15px;
    text-align: center;
    font-size: 1.6rem;
    font-weight: 600;
    margin-bottom: 2rem;
    box-shadow: 0 5px 15px rgba(130,92,255,0.3);
}}

.input-container, .result-container, .metric-card {{
    background: var(--container-bg);
    border-radius: 15px;
    padding: 1.5rem 1.8rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 15px rgba(0,0,0,0.06);
    transition: transform 0.2s ease;
}}
.input-container:hover, .metric-card:hover {{
    transform: translateY(-2px);
}}

label, .stTextInput label, .stNumberInput label, .stSelectbox label {{
    color: var(--text-color);
    font-weight: 600;
}}

.stTextInput input, .stNumberInput input, .stSelectbox select {{
    background-color: var(--input-bg) !important;
    color: var(--input-text) !important;
    border-radius: 30px !important;
    border: 2px solid var(--input-border) !important;
    padding: 0.5rem 1rem !important;
    font-size: 15px;
}}
.stTextInput input:focus, .stNumberInput input:focus, .stSelectbox select:focus {{
    border-color: var(--accent-color) !important;
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent-color) 20%%, transparent) !important;
}}

.stButton > button {{
    background: linear-gradient(90deg, #825CFF, #7A5CFF);
    color: white;
    border: none;
    border-radius: 30px;
    padding: 0.7rem 1.8rem;
    font-size: 16px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 4px 10px rgba(130,92,255,0.3);
}}
.stButton > button:hover {{
    background: linear-gradient(90deg, #6B3CFF, #825CFF);
    transform: translateY(-2px);
}}

.result-container h2, .result-container .stMetricLabel {{
    color: var(--accent-color);
}}

[data-testid="stSidebar"] {{
    background: var(--sidebar-bg);
}}

</style>
""", unsafe_allow_html=True)


# --- MAIN APP CONTENT (LOGIC UNCHANGED) ---
st.markdown("""
    <div class="main-header">
        <h1>💼 APMH Income Tax Calculator</h1>
        <p>Income Tax Planning & Calculation Tool | AY 2026-27 </p>
    </div>
""", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["🧮 Calculate Tax", "📊 Analysis", "📋 Tax Planning"])

# Define variables in the main scope to be accessible everywhere
salary = business_income = house_income = house_loan_interest = other_sources = stcg = ltcg = tds_paid = 0.0
regime = 'new'

with tab1:
    st.markdown('<div class="input-container">', unsafe_allow_html=True)
    with st.form("tax_form"):
        st.markdown("### 🔧 Tax Regime Selection")
        regime = st.radio("Select Tax Regime", ["old", "new"], horizontal=True, help="New regime: ₹4L basic exemption + ₹60K rebate + Marginal Relief | Old regime: ₹2.5L basic exemption + ₹12.5K rebate")
        st.markdown("### 💰 Income Details")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**Employment Income**")
            salary = st.number_input("Salary Income (₹)", min_value=0.0, step=10000.0, placeholder="Enter amount", value=None, key="salary")
            business_income = st.number_input("Business/Professional Income (₹)", min_value=0.0, step=10000.0, placeholder="Enter amount", value=None, key="business_income")
        with col2:
            st.markdown("**Property & Other Income**")
            house_income = st.number_input("House Property Income (₹)", min_value=0.0, step=5000.0, placeholder="Enter amount", value=None, key="house_income")
            house_loan_interest = st.number_input("Interest on House Property Loan (₹)", min_value=0.0, step=5000.0, placeholder="Enter amount", value=None, key="house_loan_interest")
            other_sources = st.number_input("Other Sources Income (₹)", min_value=0.0, step=5000.0, placeholder="Enter amount", value=None, key="other_sources")
        with col3:
            st.markdown("**Capital Gains & TDS**")
            stcg = st.number_input("Short-Term Capital Gains (₹)", min_value=0.0, step=5000.0, placeholder="Enter amount", value=None, key="stcg")
            ltcg = st.number_input("Long-Term Capital Gains (₹)", min_value=0.0, step=5000.0, placeholder="Enter amount", value=None, key="ltcg")
            tds_paid = st.number_input("TDS/Advance Tax Paid (₹)", min_value=0.0, step=1000.0, placeholder="Enter amount", value=None, key="tds_paid")
        submitted = st.form_submit_button("🧮 Calculate Tax", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if submitted:
        salary_val = salary or 0.0; business_income_val = business_income or 0.0; house_income_val = house_income or 0.0; house_loan_interest_val = house_loan_interest or 0.0; other_sources_val = other_sources or 0.0; stcg_val = stcg or 0.0; ltcg_val = ltcg or 0.0; tds_paid_val = tds_paid or 0.0
        total_income = calculate_total_income(regime, salary_val, business_income_val, house_income_val, other_sources_val, house_loan_interest_val)
        if regime == 'old':
            base_tax, surcharge, cess, rebate_applied, marginal_relief_applied = calculate_tax_old_regime(total_income, stcg_val, ltcg_val)
        else:
            base_tax, surcharge, cess, rebate_applied, marginal_relief_applied = calculate_tax_new_regime(total_income, stcg_val, ltcg_val)
        total_tax = base_tax + surcharge + cess
        net_tax = total_tax - tds_paid_val
        total_taxable_income = total_income + stcg_val + ltcg_val
        st.markdown('<div class="result-container">', unsafe_allow_html=True)
        st.markdown("### 📊 Tax Calculation Results")
        res_col1, res_col2, res_col3, res_col4 = st.columns(4)
        with res_col1:
            st.metric("💼 Taxable Income", f"₹{total_taxable_income:,.0f}", delta=f"Regime: {regime.upper()}")
        with res_col2:
            st.metric("🧾 Base Tax", f"₹{base_tax:,.0f}", delta="After all reliefs")
        with res_col3:
            st.metric("📈 Total Liability", f"₹{total_tax:,.0f}", delta="Including surcharge & cess")
        with res_col4:
            status_emoji = "💵 Refund" if net_tax < 0 else "📌 Payable"
            st.metric(f"{status_emoji}", f"₹{abs(net_tax):,.0f}", delta="After TDS adjustment")
        # Rest of result display...
        st.markdown('</div>', unsafe_allow_html=True)


# --- (REST OF THE SCRIPT: tab2, tab3, and Excel export) ---

with tab2:
    # This tab needs access to the calculated variables.
    # We will show a message if the calculation hasn't run yet.
    if not submitted:
        st.info("Please calculate the tax on the first tab to see the analysis.")
    else:
        st.markdown("### 📊 Tax Analysis & Visualizations")
        # ... (visualization code using calculated variables) ...

with tab3:
    st.markdown("### 📋 Tax Planning Suggestions")
    # ... (static content, unchanged) ...


st.markdown("---")
st.markdown("### 📄 Export Tax Computation to Excel")
st.info("🎨 Generate professional Excel report with clear visibility and FIXED syntax")

if st.button("📊 Generate & Download Excel Report", type="primary"):
    try:
        # Use st.session_state to get the most recent values from the form inputs
        salary_val = st.session_state.get('salary', 0.0) or 0.0
        business_income_val = st.session_state.get('business_income', 0.0) or 0.0
        house_income_val = st.session_state.get('house_income', 0.0) or 0.0
        house_loan_interest_val = st.session_state.get('house_loan_interest', 0.0) or 0.0
        other_sources_val = st.session_state.get('other_sources', 0.0) or 0.0
        stcg_val = st.session_state.get('stcg', 0.0) or 0.0
        ltcg_val = st.session_state.get('ltcg', 0.0) or 0.0

        excel_output = create_professional_excel_report(
            salary_val, business_income_val, house_income_val, other_sources_val,
            stcg_val, ltcg_val, regime, house_loan_interest_val
        )
        if excel_output:
            st.success("✅ Professional Excel report generated successfully! 🎨")
            st.download_button(
                label="📥 Download Excel Report",
                data=excel_output.getvalue(),
                file_name=f"Income_Tax_Computation_AY_2026-27_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    except Exception as e:
        st.error(f"❌ Error generating Excel: {e}")

st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 20px;'>
    <p>💼 APMH Tax Calculator | Built with ❤️ using Streamlit</p>
    <p><small>⚠️ This calculator is for reference only. Please consult a APMH LLP for accurate advice.</small></p>
    <p><small>🆕 Now includes Marginal Relief for New Regime (₹12L-₹12.6L income range)</small></p>
</div>
""", unsafe_allow_html=True)
