import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from datetime import datetime

# --- 1. TAX CALCULATION FUNCTIONS ---

def calculate_total_income(regime, salary, business_income, house_income, other_sources, house_loan_interest=0):
    # Salary – Apply standard deduction
    if regime == 'new':
        salary -= 75000
    else:
        salary -= 50000

    # House Property – Apply 30% standard deduction THEN subtract loan interest
    house_income *= 0.70
    house_income -= house_loan_interest

    # Total income excluding capital gains
    total = max(0, salary) + max(0, business_income) + max(0, house_income) + max(0, other_sources)
    return total

def calculate_surcharge_amount(regular_tax, cg_tax, regular_income, grand_total_income, regime):
    """
    AY 2026-27 Logic:
    1. Capital Gains Surcharge (111A/112A) is CAPPED at 15%.
    2. Regular Income Surcharge follows slab (10/15/25/37) but has 'Step-Up' relief:
       - If Regular Income <= 2Cr, its surcharge is limited to 15% even if Total > 2Cr.
    """
    # 1. CG Rate
    if grand_total_income > 10000000:
        cg_rate = 0.15
    elif grand_total_income > 5000000:
        cg_rate = 0.10
    else:
        cg_rate = 0.0
        
    # 2. Regular Rate
    reg_rate = 0.0
    if grand_total_income > 20000000: # Total > 2Cr
        if regular_income > 20000000: # Regular also > 2Cr
            if regime == 'new':
                reg_rate = 0.25
            else:
                reg_rate = 0.37 if regular_income > 50000000 else 0.25
        else:
            reg_rate = 0.15 # Relief: Regular is small
    elif grand_total_income > 10000000:
        reg_rate = 0.15
    elif grand_total_income > 5000000:
        reg_rate = 0.10
        
    return (regular_tax * reg_rate) + (cg_tax * cg_rate)

def calculate_tax_old_regime(total_income, stcg, ltcg):
    # Base tax (normal income)
    tax = 0
    if total_income <= 250000: tax = 0
    elif total_income <= 500000: tax = (total_income - 250000) * 0.05
    elif total_income <= 1000000: tax = 12500 + (total_income - 500000) * 0.2
    else: tax = 112500 + (total_income - 1000000) * 0.3

    # Capital gains tax
    cg_tax = stcg * 0.20
    if ltcg > 125000: cg_tax += (ltcg - 125000) * 0.125

    # Rebate
    rebate_applied = 0
    if total_income <= 500000:
        rebate_applied = min(12500, tax)
        tax_after_rebate = max(0, tax - rebate_applied)
    else:
        tax_after_rebate = tax

    total_tax_before_surcharge = tax_after_rebate + cg_tax

    # Surcharge (New Split Logic)
    grand_total = total_income + stcg + ltcg
    surcharge = calculate_surcharge_amount(tax_after_rebate, cg_tax, total_income, grand_total, "old")

    # Cess
    cess = (total_tax_before_surcharge + surcharge) * 0.04

    return round(max(total_tax_before_surcharge, 0), 2), round(surcharge, 2), round(cess, 2), round(rebate_applied, 2), 0

def calculate_tax_new_regime(total_income, stcg, ltcg):
    # Slabs AY 2026-27
    slabs = [(400000, 0.00), (400000, 0.05), (400000, 0.10), (400000, 0.15), (400000, 0.20), (400000, 0.25), (float('inf'), 0.30)]

    # 1. Apply Exemption Logic (Standard Priority: Other -> STCG -> LTCG)
    exempt_ltcg = min(ltcg, 125000)
    taxable_ltcg_after_exemption = max(0, ltcg - exempt_ltcg)
    basic_exemption_limit = 400000
    remaining_exemption = basic_exemption_limit

    other_income_exempted = min(total_income, remaining_exemption)
    remaining_exemption = max(0, remaining_exemption - other_income_exempted)
    taxable_other_income = max(0, total_income - other_income_exempted)

    stcg_exempted = min(stcg, remaining_exemption)
    remaining_exemption = max(0, remaining_exemption - stcg_exempted)
    taxable_stcg = max(0, stcg - stcg_exempted)

    ltcg_exempted = min(taxable_ltcg_after_exemption, remaining_exemption)
    final_taxable_ltcg = max(0, taxable_ltcg_after_exemption - ltcg_exempted)

    # 2. Regular Tax
    regular_tax = 0
    if taxable_other_income > 0:
        exemption_used_from_regular = other_income_exempted
        if exemption_used_from_regular >= 400000:
            income_remaining = taxable_other_income
            for i in range(1, len(slabs)):
                slab_limit, rate = slabs[i]
                if income_remaining <= 0: break
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
                if income_remaining <= 0: break
                slab_limit, rate = slabs[i]
                taxable_in_slab = min(income_remaining, slab_limit)
                regular_tax += taxable_in_slab * rate
                income_remaining -= taxable_in_slab

    # 3. CG Tax
    cg_tax = taxable_stcg * 0.20 + final_taxable_ltcg * 0.125

    # 4. Rebate
    rebate_applied = 0
    if total_income <= 1200000:
        rebate_applied = min(60000, regular_tax)
        regular_tax_after_rebate = max(0, regular_tax - rebate_applied)
    else:
        regular_tax_after_rebate = regular_tax

    total_tax_before_surcharge = regular_tax_after_rebate + cg_tax

    # 5. Surcharge (New Split Logic)
    grand_total = total_income + stcg + ltcg
    surcharge = calculate_surcharge_amount(regular_tax_after_rebate, cg_tax, total_income, grand_total, "new")

    # 6. Marginal Relief
    marginal_relief_applied = 0
    if 1200000 < grand_total <= 1260000:
        tax_actual = total_tax_before_surcharge + surcharge
        excess_income = grand_total - 1200000
        if tax_actual > excess_income:
            marginal_relief_applied = tax_actual - excess_income
            # Relief reduces the payable amount. Technically it reduces surcharge first.
            # We adjust return values to reflect net liability correctly.
            # Reset surcharge for calculation flow as it's absorbed
            surcharge = 0 
            total_tax_before_surcharge = excess_income 

    # 7. Cess
    cess = (total_tax_before_surcharge + surcharge) * 0.04

    return round(max(total_tax_before_surcharge, 0), 2), round(surcharge, 2), round(cess, 2), round(rebate_applied, 2), round(marginal_relief_applied, 2)

# --- 2. EXCEL EXPORT FUNCTION ---

def create_professional_excel_report(salary, business_income, house_income, other_sources, stcg, ltcg, regime, house_loan_interest=0, tds_paid=0):
    processed_salary = salary - (75000 if regime == 'new' else 50000)
    processed_house = (house_income * 0.70) - house_loan_interest
    total_income_calc = max(0, processed_salary) + max(0, business_income) + max(0, processed_house) + max(0, other_sources)

    if regime == 'new':
        tax, surcharge, cess, rebate, marginal_relief = calculate_tax_new_regime(total_income_calc, stcg, max(0, ltcg))
    else:
        tax, surcharge, cess, rebate, marginal_relief = calculate_tax_old_regime(total_income_calc, stcg, max(0, ltcg))
    
    total_tax = tax + surcharge + cess
    net_tax_liability = max(0, total_tax - tds_paid)
    advance_tax_applicable = net_tax_liability >= 10000

    output = BytesIO()
    try:
        import xlsxwriter
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Income Tax Computation')

        # Formats
        title_fmt = workbook.add_format({'bold': True, 'font_size': 18, 'align': 'center', 'bg_color': '#003366', 'font_color': '#FFFFFF', 'border': 2})
        header_fmt = workbook.add_format({'bold': True, 'font_size': 13, 'align': 'center', 'bg_color': '#0066CC', 'font_color': '#FFFFFF', 'border': 1})
        section_fmt = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center', 'bg_color': '#8B0000', 'font_color': '#FFFFFF', 'border': 1})
        bullet_fmt = workbook.add_format({'bold': True, 'font_size': 12, 'align': 'left', 'bg_color': '#FF8C00', 'font_color': '#FFFFFF', 'border': 1})
        data_fmt = workbook.add_format({'font_size': 10, 'border': 1})
        amt_fmt = workbook.add_format({'font_size': 10, 'bold': True, 'align': 'right', 'num_format': '₹#,##0.00', 'border': 1})
        total_fmt = workbook.add_format({'font_size': 11, 'bold': True, 'align': 'right', 'num_format': '₹#,##0.00', 'bg_color': '#E8F4FD', 'border': 1})

        worksheet.set_column('A:A', 50)
        worksheet.set_column('B:B', 20)
        worksheet.set_column('C:C', 18)
        worksheet.set_column('D:D', 20)

        row = 0
        worksheet.write_row(row, 0, ['Particulars', 'Details', 'Sub-total', 'Total'], header_fmt)
        row += 2
        worksheet.merge_range(row, 0, row, 3, 'INCOME TAX COMPUTATION - A.Y. 2026-27', title_fmt)
        row += 2
        worksheet.merge_range(row, 0, row, 3, 'STATEMENT OF INCOME', section_fmt)
        row += 2

        # Salary
        if salary > 0:
            worksheet.merge_range(row, 0, row, 3, '● INCOME FROM SALARY', bullet_fmt)
            row += 1
            worksheet.write(row, 0, 'Salary Income', data_fmt)
            worksheet.write(row, 1, salary, amt_fmt)
            row += 1
            worksheet.write(row, 0, 'Less: Standard Deduction', data_fmt)
            worksheet.write(row, 1, 75000 if regime=='new' else 50000, amt_fmt)
            row += 1
            worksheet.write(row, 0, 'Net Salary', data_fmt)
            worksheet.write(row, 2, max(0, processed_salary), total_fmt)
            row += 2

        # House Property
        if house_income != 0:
            worksheet.merge_range(row, 0, row, 3, '● INCOME FROM HOUSE PROPERTY', bullet_fmt)
            row += 1
            worksheet.write(row, 0, 'Gross Annual Value', data_fmt)
            worksheet.write(row, 1, abs(house_income), amt_fmt)
            row += 1
            worksheet.write(row, 0, 'Less: 30% Std Ded', data_fmt)
            worksheet.write(row, 1, abs(house_income)*0.3, amt_fmt)
            row += 1
            if house_loan_interest > 0:
                worksheet.write(row, 0, 'Less: Interest on Loan', data_fmt)
                worksheet.write(row, 1, house_loan_interest, amt_fmt)
                row += 1
            worksheet.write(row, 0, 'Net House Property', data_fmt)
            worksheet.write(row, 2, processed_house, total_fmt)
            row += 2

        # Business & Other
        if business_income > 0:
            worksheet.merge_range(row, 0, row, 3, '● BUSINESS INCOME', bullet_fmt)
            row += 1
            worksheet.write(row, 0, 'Net Business Income', data_fmt)
            worksheet.write(row, 2, business_income, total_fmt)
            row += 2
        
        if other_sources > 0:
            worksheet.merge_range(row, 0, row, 3, '● OTHER SOURCES', bullet_fmt)
            row += 1
            worksheet.write(row, 0, 'Income from Other Sources', data_fmt)
            worksheet.write(row, 2, other_sources, total_fmt)
            row += 2

        # Capital Gains
        if stcg > 0 or ltcg > 0:
            worksheet.merge_range(row, 0, row, 3, '● CAPITAL GAINS', bullet_fmt)
            row += 1
            if stcg > 0:
                worksheet.write(row, 0, 'STCG (111A)', data_fmt)
                worksheet.write(row, 1, stcg, amt_fmt)
                row += 1
            if ltcg > 0:
                worksheet.write(row, 0, 'LTCG (112A)', data_fmt)
                worksheet.write(row, 1, ltcg, amt_fmt)
                row += 1
                if ltcg > 125000:
                    worksheet.write(row, 0, 'Less: Exemption u/s 112A', data_fmt)
                    worksheet.write(row, 1, 125000, amt_fmt)
                    row += 1
            net_cg = stcg + max(0, ltcg - 125000)
            worksheet.write(row, 0, 'Net Capital Gains', data_fmt)
            worksheet.write(row, 2, net_cg, total_fmt)
            row += 2

        gross_total = total_income_calc + stcg + max(0, ltcg)
        worksheet.write(row, 0, 'TOTAL INCOME', data_fmt)
        worksheet.write(row, 3, gross_total, total_fmt)
        row += 2

        # Tax Computation
        worksheet.merge_range(row, 0, row, 3, 'TAX COMPUTATION', section_fmt)
        row += 2
        worksheet.write(row, 0, f'Tax ({regime.upper()})', data_fmt)
        worksheet.write(row, 3, tax, total_fmt)
        row += 1
        if surcharge > 0:
            worksheet.write(row, 0, 'Add: Surcharge', data_fmt)
            worksheet.write(row, 3, surcharge, amt_fmt)
            row += 1
        if cess > 0:
            worksheet.write(row, 0, 'Add: Cess (4%)', data_fmt)
            worksheet.write(row, 3, cess, amt_fmt)
            row += 1
        if rebate > 0:
            worksheet.write(row, 0, 'Less: Rebate 87A', data_fmt)
            worksheet.write(row, 3, rebate, amt_fmt)
            row += 1
        if marginal_relief > 0:
            worksheet.write(row, 0, 'Less: Marginal Relief', data_fmt)
            worksheet.write(row, 3, marginal_relief, amt_fmt)
            row += 1
        
        worksheet.write(row, 0, 'TOTAL TAX LIABILITY', data_fmt)
        worksheet.write(row, 3, total_tax, total_fmt)
        row += 1
        if tds_paid > 0:
            worksheet.write(row, 0, 'Less: TDS Paid', data_fmt)
            worksheet.write(row, 3, tds_paid, amt_fmt)
            row += 1
        
        net_final = total_tax - tds_paid
        lbl = "NET PAYABLE" if net_final >= 0 else "REFUND DUE"
        worksheet.write(row, 0, lbl, data_fmt)
        worksheet.write(row, 3, abs(net_final), total_fmt)
        row += 2

        # Advance Tax Schedule
        if advance_tax_applicable:
            worksheet.merge_range(row, 0, row, 3, 'ADVANCE TAX SCHEDULE', section_fmt)
            row += 2
            q1 = round(net_tax_liability * 0.15)
            q2 = round(net_tax_liability * 0.45) - q1
            q3 = round(net_tax_liability * 0.75) - (q1 + q2)
            q4 = round(net_tax_liability) - (q1 + q2 + q3)
            
            worksheet.write_row(row, 0, ['Due Date', 'Cumulative %', 'Installment', 'Cumulative'], header_fmt)
            row += 1
            installs = [("15 Jun", "15%", q1, q1), ("15 Sep", "45%", q2, q1+q2), ("15 Dec", "75%", q3, q1+q2+q3), ("15 Mar", "100%", q4, q1+q2+q3+q4)]
            for d, p, a, c in installs:
                worksheet.write(row, 0, d, data_fmt)
                worksheet.write(row, 1, p, center_format)
                worksheet.write(row, 2, a, amt_fmt)
                worksheet.write(row, 3, c, amt_fmt)
                row += 1

        workbook.close()
        output.seek(0)
        return output
    except:
        import pandas as pd
        output = BytesIO()
        pd.DataFrame([["Error", "Install xlsxwriter"]]).to_excel(output)
        output.seek(0)
        return output

# --- 3. APP CONFIG & STYLING ---

st.set_page_config(page_title="APMH Tax Calculator", page_icon="💰", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg, #ADD8E6 0%, #87CEFA 100%); }
    .main-header { background: linear-gradient(90deg, #4169E1, #6495ED); padding: 2rem; border-radius: 10px; margin-bottom: 2rem; text-align: center; color: white; }
    .result-container { background: linear-gradient(135deg, #ADD8E6 0%, #87CEFA 100%); padding: 2rem; border-radius: 15px; color: #191970; }
    .stButton > button { background: linear-gradient(90deg, #4169E1, #6495ED); color: white; border: none; padding: 0.75rem; border-radius: 25px; font-weight: bold; width: 100%; }
    </style>
""", unsafe_allow_html=True)

st.markdown("""<div class="main-header"><h1>💼 APMH Income Tax Calculator</h1><p>AY 2026-27 | New Surcharge Rules</p></div>""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 📊 Quick Comparison")
    st.info("New Regime: 15% Surcharge Cap on CG. Regular Income Surcharge limited to 15% if regular income <= 2Cr.")
    regime_view = st.selectbox("View Slabs:", ["New Regime", "Old Regime"])
    if regime_view == "New Regime":
        st.markdown("- 0-4L: 0%\n- 4-8L: 5%\n- 8-12L: 10%\n- 12-16L: 15%\n- 16-20L: 20%\n- 20-24L: 25%\n- >24L: 30%")

tab1, tab2, tab3, tab4 = st.tabs(["🧮 Calculate Tax", "📊 Analysis", "📋 Tax Planning", "📅 Advance Tax"])

with tab1:
    st.markdown("<h3 style='text-align: center;'>Enter Financial Details</h3>", unsafe_allow_html=True)
    with st.form("tax_form"):
        regime = st.radio("Select Tax Regime", ["new", "old"], horizontal=True)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            salary = st.number_input("Salary Income", min_value=0.0, step=10000.0, key="sal")
            business_income = st.number_input("Business Income", min_value=0.0, key="bus")
        with col2:
            house_income = st.number_input("House Property Income", min_value=0.0, key="hp")
            house_loan_interest = st.number_input("Home Loan Interest", min_value=0.0, key="hli")
            other_sources = st.number_input("Other Sources", min_value=0.0, key="os")
        with col3:
            stcg = st.number_input("STCG (111A - 20%)", min_value=0.0, key="stcg")
            ltcg = st.number_input("LTCG (112A - 12.5%)", min_value=0.0, key="ltcg")
            tds_paid = st.number_input("TDS Paid", min_value=0.0, key="tds")

        submitted = st.form_submit_button("🧮 Calculate Tax")

    if submitted:
        # 1. Calculate
        total_income = calculate_total_income(regime, salary, business_income, house_income, other_sources, house_loan_interest)
        if regime == 'old':
            base_tax, surcharge, cess, rebate, marginal = calculate_tax_old_regime(total_income, stcg, ltcg)
        else:
            base_tax, surcharge, cess, rebate, marginal = calculate_tax_new_regime(total_income, stcg, ltcg)
        
        # Note: Marginal relief logic in function returns relief amount. 
        # If it was non-zero, surcharge was likely zeroed out inside.
        total_tax = base_tax + surcharge + cess - marginal
        net_tax = total_tax - tds_paid
        total_taxable = total_income + stcg + ltcg

        # 2. Results UI
        st.markdown('<div class="result-container">', unsafe_allow_html=True)
        st.markdown("### 📊 Results")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Taxable Income", f"₹{total_taxable:,.0f}")
        c2.metric("Base Tax", f"₹{base_tax:,.0f}")
        c3.metric("Total Liability", f"₹{total_tax:,.0f}")
        c4.metric("Payable/Refund", f"₹{abs(net_tax):,.0f}", delta_color="inverse" if net_tax > 0 else "normal")
        st.markdown('</div>', unsafe_allow_html=True)

        # 3. Detailed Breakdown (PRESERVED FROM ORIGINAL)
        if regime == 'new' and (stcg > 0 or ltcg > 0 or total_income > 0):
            st.markdown("### 🎯 New Regime - Detailed Calculation Breakdown")
            
            # Re-calculate exemption logic locally for display (as requested to preserve summary)
            basic_exemption_limit = 400000
            taxable_ltcg_after_exemption = max(0, ltcg - 125000)
            
            remaining_exemption = basic_exemption_limit
            other_exemption = min(total_income, remaining_exemption)
            remaining_after_other = max(0, remaining_exemption - other_exemption)
            stcg_exemption = min(stcg, remaining_after_other)
            remaining_after_stcg = max(0, remaining_after_other - stcg_exemption)
            ltcg_exemption = min(taxable_ltcg_after_exemption, remaining_after_stcg)
            
            final_other = max(0, total_income - other_exemption)
            final_stcg = max(0, stcg - stcg_exemption)
            final_ltcg = max(0, taxable_ltcg_after_exemption - ltcg_exemption)
            
            st.success("**✅ Exemption Utilization Logic:**")
            st.write(f"1. **LTCG Exemption:** ₹1.25L applied to ₹{ltcg:,.0f} -> Taxable: ₹{taxable_ltcg_after_exemption:,.0f}")
            st.write(f"2. **Basic Exemption (₹4L):** Used by Regular: ₹{other_exemption:,.0f}, STCG: ₹{stcg_exemption:,.0f}, LTCG: ₹{ltcg_exemption:,.0f}")
            
            if 1200000 < total_taxable <= 1260000 and marginal > 0:
                st.markdown("#### 🎯 Marginal Relief")
                st.success(f"Income ₹12L-₹12.6L: Relief of **₹{marginal:,.0f}** applied to limit tax to excess income.")

            # Exemption Table
            ex_data = {
                "Income Type": ["Regular Income", "STCG", "LTCG (post 1.25L)", "Total Used"],
                "Amount": [f"₹{total_income:,.0f}", f"₹{stcg:,.0f}", f"₹{taxable_ltcg_after_exemption:,.0f}", "-"],
                "Exemption Used": [f"₹{other_exemption:,.0f}", f"₹{stcg_exemption:,.0f}", f"₹{ltcg_exemption:,.0f}", f"₹{other_exemption+stcg_exemption+ltcg_exemption:,.0f}"],
                "Taxable": [f"₹{final_other:,.0f}", f"₹{final_stcg:,.0f}", f"₹{final_ltcg:,.0f}", "-"]
            }
            st.dataframe(pd.DataFrame(ex_data), use_container_width=True)

        # 4. Breakdown Table
        st.markdown("### 📋 Detailed Tax Breakdown")
        bk_comps = ["Base Tax", "Surcharge", "Cess", "Total Tax", "TDS", "Net"]
        bk_amts = [base_tax, surcharge, cess, total_tax, tds_paid, abs(net_tax)]
        if rebate > 0:
            bk_comps.insert(3, "Less: Rebate")
            bk_amts.insert(3, -rebate)
        if marginal > 0:
            bk_comps.insert(3, "Less: Marginal Relief")
            bk_amts.insert(3, -marginal)
            
        bk_df = pd.DataFrame({"Component": bk_comps, "Amount": [f"₹{x:,.2f}" for x in bk_amts]})
        st.dataframe(bk_df, use_container_width=True)

with tab2:
    if 'total_tax' in locals():
        st.markdown("### 📊 Visual Analysis")
        fig = px.pie(names=['Base Tax', 'Surcharge', 'Cess'], values=[base_tax, surcharge, cess], title="Liability Components")
        st.plotly_chart(fig, use_container_width=True)
        
        fig2 = px.bar(x=['Salary', 'Business', 'Other', 'STCG', 'LTCG'], 
                      y=[max(0,salary-75000), business_income, other_sources, stcg, ltcg],
                      title="Income Breakdown")
        st.plotly_chart(fig2, use_container_width=True)

with tab3:
    st.markdown("### 📋 Tax Planning")
    st.info("💡 **Tip:** For high capital gains, ensure you are leveraging the 15% surcharge cap correctly. This calculator handles it automatically.")

with tab4:
    st.markdown("### 📅 Advance Tax")
    if 'net_tax' in locals() and net_tax >= 10000:
        liability = net_tax
        q1 = round(liability * 0.15)
        q2 = round(liability * 0.45) - q1
        q3 = round(liability * 0.75) - (q1 + q2)
        q4 = round(liability) - (q1 + q2 + q3)
        
        adv_data = {"Deadline": ["15 Jun", "15 Sep", "15 Dec", "15 Mar"], "Payable": [q1, q2, q3, q4]}
        st.dataframe(pd.DataFrame(adv_data), use_container_width=True)
    else:
        st.success("No Advance Tax Liability (< ₹10k or Refund)")

# Footer Export
st.markdown("---")
if st.button("📊 Generate Excel Report", type="primary"):
    # Safety: Ensure variables exist even if button clicked without calc
    s = salary if 'salary' in locals() else 0
    b = business_income if 'business_income' in locals() else 0
    h = house_income if 'house_income' in locals() else 0
    o = other_sources if 'other_sources' in locals() else 0
    stcg_v = stcg if 'stcg' in locals() else 0
    ltcg_v = ltcg if 'ltcg' in locals() else 0
    r = regime if 'regime' in locals() else 'new'
    hl = house_loan_interest if 'house_loan_interest' in locals() else 0
    td = tds_paid if 'tds_paid' in locals() else 0
    
    excel_data = create_professional_excel_report(s, b, h, o, stcg_v, ltcg_v, r, hl, td)
    st.download_button("📥 Download", data=excel_data, file_name="TaxReport.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
