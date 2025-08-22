import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# TAX CALCULATION FUNCTIONS (Final Corrected Version with Marginal Relief)

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
    elif total_income > 5000000:   # 50L–1cr
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
        (float('inf'), 0.30)  # Above 24L: 30%
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
            # Full ₹4L exemption used from regular income
            # Start from ₹4L-8L slab (index 1)
            income_remaining = taxable_other_income
            
            # Apply slabs starting from 4L-8L (5%)
            for i in range(1, len(slabs)):  # Start from index 1 (₹4L-8L slab)
                slab_limit, rate = slabs[i]
                
                if income_remaining <= 0:
                    break
                
                taxable_in_slab = min(income_remaining, slab_limit)
                regular_tax += taxable_in_slab * rate
                income_remaining -= taxable_in_slab
        else:
            # Partial exemption used from regular income
            remaining_in_first_slab = 400000 - exemption_used_from_regular
            income_remaining = taxable_other_income
            
            # If there's still room in the 0% slab
            if remaining_in_first_slab > 0:
                tax_free_amount = min(income_remaining, remaining_in_first_slab)
                income_remaining -= tax_free_amount
            
            # Apply remaining slabs
            for i in range(1, len(slabs)):
                if income_remaining <= 0:
                    break
                
                slab_limit, rate = slabs[i]
                taxable_in_slab = min(income_remaining, slab_limit)
                regular_tax += taxable_in_slab * rate
                income_remaining -= taxable_in_slab
    
    # Step 5: Calculate capital gains tax separately
    cg_tax = taxable_stcg * 0.20 + final_taxable_ltcg * 0.125
    
    # Step 6: Apply rebate ONLY to regular income tax (NOT capital gains)
    rebate_applied = 0
    if total_income <= 1200000:  # ₹12L limit
        rebate_applied = min(60000, regular_tax)  # Max ₹60K rebate on regular tax only
        regular_tax_after_rebate = max(0, regular_tax - rebate_applied)
    else:
        regular_tax_after_rebate = regular_tax
    
    # Step 7: Total tax = Regular tax (after rebate) + Capital gains tax (no rebate)
    total_tax_before_surcharge = regular_tax_after_rebate + cg_tax
    
    # Step 8: Apply Marginal Relief for income between ₹12L to ₹12.6L
    marginal_relief_applied = 0
    total_taxable_income = total_income + stcg + ltcg
    
    if 1200000 < total_taxable_income <= 1260000:
        # Calculate tax without rebate for marginal relief comparison
        tax_without_rebate = regular_tax + cg_tax
        
        # Marginal relief calculation
        marginal_relief_amount = total_taxable_income - 1200000
        
        # Apply marginal relief - tax cannot exceed the excess over ₹12L
        if total_tax_before_surcharge > marginal_relief_amount:
            marginal_relief_applied = total_tax_before_surcharge - marginal_relief_amount
            total_tax_before_surcharge = marginal_relief_amount
    
    # Step 9: Calculate surcharge
    surcharge_rate = calculate_surcharge_rate(total_income + stcg + ltcg, "new", stcg + ltcg)
    surcharge = total_tax_before_surcharge * surcharge_rate
    
    # Step 10: Calculate cess
    cess = (total_tax_before_surcharge + surcharge) * 0.04
    
    return round(max(total_tax_before_surcharge, 0), 2), round(surcharge, 2), round(cess, 2), round(rebate_applied, 2), round(marginal_relief_applied, 2)

# STREAMLIT UI START - ENHANCED VERSION

st.set_page_config(
    page_title="APMH Tax Calculator", 
    page_icon="💰", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Advanced CSS styling with light blue theme
st.markdown("""
    <style>
    .main {
        padding: 0rem 1rem;
    }
    .stApp {
        background: linear-gradient(135deg, #ADD8E6 0%, #87CEFA 100%);
    }
    .main-header {
        background: linear-gradient(90deg, #4169E1, #6495ED);
        padding: 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        text-align: center;
        color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .input-container {
        background: white;
        padding: 2rem;
        border-radius: 15px;
        box-shadow: 0 8px 16px rgba(0,0,0,0.1);
        margin-bottom: 2rem;
    }
    .result-container {
        background: linear-gradient(135deg, #ADD8E6 0%, #87CEFA 100%);
        padding: 2rem;
        border-radius: 15px;
        box-shadow: 0 8px 16px rgba(0,0,0,0.1);
        color: #191970;
    }
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        margin: 0.5rem;
        text-align: center;
    }
    .stButton > button {
        background: linear-gradient(90deg, #4169E1, #6495ED);
        color: white;
        border: none;
        padding: 0.75rem 2rem;
        border-radius: 25px;
        font-weight: bold;
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.3);
    }
    .sidebar .sidebar-content {
        background: linear-gradient(135deg, #ADD8E6 0%, #87CEFA 100%);
    }
    </style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
    <div class="main-header">
        <h1>💼 APMH Income Tax Calculator</h1>
        <p>Income Tax Planning & Calculation Tool | AY 2026-27 </p>
    </div>
""", unsafe_allow_html=True)

# Sidebar for regime comparison
with st.sidebar:
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

# Main content area with tabs
tab1, tab2, tab3 = st.tabs(["🧮 Calculate Tax", "📊 Analysis", "📋 Tax Planning"])

with tab1:
    # Input form with enhanced styling
    st.markdown('<div class="input-container">', unsafe_allow_html=True)
    
    with st.form("tax_form"):
        st.markdown("### 🔧 Tax Regime Selection")
        regime = st.radio(
            "Select Tax Regime", 
            ["old", "new"], 
            horizontal=True,
            help="New regime: ₹4L basic exemption + ₹60K rebate + Marginal Relief | Old regime: ₹2.5L basic exemption + ₹12.5K rebate"
        )
        
        st.markdown("### 💰 Income Details")
        
        # Create 3 columns for better layout
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("**Employment Income**")
            salary = st.number_input(
                "Salary Income (₹)", 
                min_value=0.0, 
                step=10000.0,
                help="Enter your annual salary before standard deduction"
            )
            business_income = st.number_input(
                "Business/Professional Income (₹)", 
                min_value=0.0, 
                step=10000.0,
                help="Net business or professional income"
            )
            
        with col2:
            st.markdown("**Property & Other Income**")
            house_income = st.number_input(
                "House Property Income (₹)", 
                min_value=0.0, 
                step=5000.0,
                help="Net Annual Value (after municipal taxes)"
            )
            house_loan_interest = st.number_input(
                "Interest on House Property Loan (₹)", 
                min_value=0.0, 
                step=5000.0,
                help="Annual interest paid on loan for let out property"
            )
            other_sources = st.number_input(
                "Other Sources Income (₹)", 
                min_value=0.0, 
                step=5000.0,
                help="Interest, dividends, etc."
            )
            
        with col3:
            st.markdown("**Capital Gains & TDS**")
            stcg = st.number_input(
                "Short-Term Capital Gains (₹)", 
                min_value=0.0, 
                step=5000.0,
                help="STCG from equity/mutual funds (20% tax rate)"
            )
            ltcg = st.number_input(
                "Long-Term Capital Gains (₹)", 
                min_value=0.0, 
                step=5000.0,
                help="LTCG total amount (₹1.25L exemption + 12.5% tax)"
            )
            tds_paid = st.number_input(
                "TDS/Advance Tax Paid (₹)", 
                min_value=0.0, 
                step=1000.0,
                help="Total tax already paid"
            )
        
        submitted = st.form_submit_button("🧮 Calculate Tax", use_container_width=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

    # Calculate and display results
    if submitted:
        total_income = calculate_total_income(regime, salary, business_income, house_income, other_sources, house_loan_interest)
        
        if regime == 'old':
            base_tax, surcharge, cess, rebate_applied, marginal_relief_applied = calculate_tax_old_regime(total_income, stcg, ltcg)
        else:
            base_tax, surcharge, cess, rebate_applied, marginal_relief_applied = calculate_tax_new_regime(total_income, stcg, ltcg)
        
        total_tax = base_tax + surcharge + cess
        net_tax = total_tax - tds_paid
        total_taxable_income = total_income + stcg + ltcg
        
        # Results with enhanced styling
        st.markdown('<div class="result-container">', unsafe_allow_html=True)
        st.markdown("### 📊 Tax Calculation Results")
        
        # Create metrics in columns
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "💼 Taxable Income",
                f"₹{total_taxable_income:,.0f}",
                delta=f"Regime: {regime.upper()}"
            )
            
        with col2:
            st.metric(
                "🧾 Base Tax",
                f"₹{base_tax:,.0f}",
                delta=f"After all reliefs"
            )
            
        with col3:
            st.metric(
                "📈 Total Liability",
                f"₹{total_tax:,.0f}",
                delta=f"Including surcharge & cess"
            )
            
        with col4:
            status_emoji = "💵 Refund" if net_tax < 0 else "📌 Payable"
            st.metric(
                f"{status_emoji}",
                f"₹{abs(net_tax):,.0f}",
                delta=f"After TDS adjustment"
            )
        
        # Show rebate and marginal relief information
        if rebate_applied > 0 or marginal_relief_applied > 0:
            st.markdown("### 🎯 Tax Benefits Applied")
            
            benefit_col1, benefit_col2 = st.columns(2)
            
            with benefit_col1:
                if rebate_applied > 0:
                    st.success(f"✅ **Rebate Applied:** ₹{rebate_applied:,.0f}")
                    if regime == 'new':
                        st.info("Income ≤ ₹12L, so rebate applied on regular income tax")
                    else:
                        st.info("Income ≤ ₹5L, so rebate applied on regular income tax")
                else:
                    rebate_limit = "₹12L" if regime == 'new' else "₹5L"
                    st.info(f"No rebate applied (income > {rebate_limit} or no regular tax)")
            
            with benefit_col2:
                if marginal_relief_applied > 0:
                    st.success(f"✅ **Marginal Relief Applied:** ₹{marginal_relief_applied:,.0f}")
                    st.info(f"Income between ₹12L-₹12.6L, tax limited to ₹{total_taxable_income - 1200000:,.0f}")
                elif regime == 'new' and 1200000 < total_taxable_income <= 1260000:
                    st.warning("Marginal relief calculated but tax already optimized")
                elif regime == 'new':
                    if total_taxable_income <= 1200000:
                        st.info("Income ≤ ₹12L - rebate applied instead")
                    else:
                        st.info("Income > ₹12.6L - no marginal relief applicable")
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Show house property calculation breakdown
        if house_income > 0 or house_loan_interest > 0:
            st.markdown("### 🏠 House Property Income Breakdown")
            net_house_income = (house_income * 0.70) - house_loan_interest
            
            house_breakdown = {
                "Component": ["Gross Annual Value", "Less: 30% Standard Deduction", "Less: Interest on Loan", "Net House Property Income"],
                "Amount (₹)": [f"₹{house_income:,.0f}", f"₹{house_income * 0.30:,.0f}", f"₹{house_loan_interest:,.0f}", f"₹{max(0, net_house_income):,.0f}"]
            }
            
            house_df = pd.DataFrame(house_breakdown)
            st.dataframe(house_df, use_container_width=True)
            
            if net_house_income < 0:
                st.info("📌 **Note:** House property shows loss (can be set off against other income as per IT rules)")
        
        # Show detailed calculation for new regime with marginal relief
        if regime == 'new' and (stcg > 0 or ltcg > 0 or total_income > 0):
            st.markdown("### 🎯 New Regime - Detailed Calculation Breakdown")
            
            # Calculate exemption breakdown
            basic_exemption_limit = 400000
            taxable_ltcg_after_exemption = max(0, ltcg - 125000)
            
            # Calculate step-by-step utilization
            remaining_exemption = basic_exemption_limit
            
            other_exemption = min(total_income, remaining_exemption)
            remaining_after_other = max(0, remaining_exemption - other_exemption)
            
            stcg_exemption = min(stcg, remaining_after_other)
            remaining_after_stcg = max(0, remaining_after_other - stcg_exemption)
            
            ltcg_exemption = min(taxable_ltcg_after_exemption, remaining_after_stcg)
            
            final_taxable_other = max(0, total_income - other_exemption)
            final_taxable_stcg = max(0, stcg - stcg_exemption)
            final_taxable_ltcg = max(0, taxable_ltcg_after_exemption - ltcg_exemption)
            
            st.success(f"**✅ CORRECTED: Slab calculation starts after basic exemption use**")
            st.write(f"1. **LTCG Exemption:** ₹1,25,000 applied to ₹{ltcg:,.0f} → Taxable LTCG = ₹{taxable_ltcg_after_exemption:,.0f}")
            st.write(f"2. **Basic Exemption (₹4,00,000) Utilization:**")
            st.write(f"   - Other income: ₹{other_exemption:,.0f} used, taxable = ₹{final_taxable_other:,.0f}")
            st.write(f"   - STCG: ₹{stcg_exemption:,.0f} used, taxable = ₹{final_taxable_stcg:,.0f}")
            st.write(f"   - LTCG: ₹{ltcg_exemption:,.0f} used, taxable = ₹{final_taxable_ltcg:,.0f}")
            if other_exemption >= 400000:
                st.write(f"3. **Tax Slab Applied:** Starts from ₹4L-8L slab at 5% (basic exemption fully used)")
            
            # Show marginal relief calculation if applicable
            if 1200000 < total_taxable_income <= 1260000:
                st.markdown("#### 🎯 Marginal Relief Calculation")
                excess_over_12l = total_taxable_income - 1200000
                st.success(f"""
                **📋 Marginal Relief Applied:**
                - Total Income: ₹{total_taxable_income:,.0f}
                - Income Range: ₹12,00,000 - ₹12,60,000 ✅
                - Excess over ₹12L: ₹{excess_over_12l:,.0f}
                - **Tax Limited to:** ₹{excess_over_12l:,.0f}
                - **Relief Amount:** ₹{marginal_relief_applied:,.0f}
                
                💡 **This ensures you don't pay more tax than the excess over ₹12L!**
                """)
            elif total_taxable_income <= 1200000:
                st.info("💰 **Income ≤ ₹12L:** Rebate of ₹60K applied instead of marginal relief")
            elif total_taxable_income > 1260000:
                st.warning("❌ **Income > ₹12.6L:** No marginal relief applicable")
            
            # Show exemption utilization table
            exemption_data = {
                "Income Type": ["Other Income", "STCG", "LTCG (after ₹1.25L exemption)", "Total Used"],
                "Amount": [f"₹{total_income:,.0f}", f"₹{stcg:,.0f}", f"₹{taxable_ltcg_after_exemption:,.0f}", "-"],
                "Exemption Used": [f"₹{other_exemption:,.0f}", f"₹{stcg_exemption:,.0f}", 
                                 f"₹{ltcg_exemption:,.0f}", f"₹{other_exemption + stcg_exemption + ltcg_exemption:,.0f}"],
                "Taxable Amount": [f"₹{final_taxable_other:,.0f}", 
                                 f"₹{final_taxable_stcg:,.0f}",
                                 f"₹{final_taxable_ltcg:,.0f}", "-"]
            }
            
            exemption_df = pd.DataFrame(exemption_data)
            st.dataframe(exemption_df, use_container_width=True)
        
        # Detailed breakdown
        st.markdown("### 📋 Detailed Tax Breakdown")
        breakdown_components = ["Base Tax", "Surcharge", "Cess", "Total Tax", "TDS Paid", "Net Amount"]
        breakdown_amounts = [f"{base_tax:,.2f}", f"{surcharge:,.2f}", f"{cess:,.2f}", 
                           f"{total_tax:,.2f}", f"{tds_paid:,.2f}", f"{abs(net_tax):,.2f}"]
        breakdown_percentages = [f"{(base_tax/total_tax*100):.1f}%" if total_tax > 0 else "0%",
                               f"{(surcharge/total_tax*100):.1f}%" if total_tax > 0 else "0%",
                               f"{(cess/total_tax*100):.1f}%" if total_tax > 0 else "0%",
                               "100%", "-", "-"]
        
        # Add rebate and marginal relief to breakdown if applicable
        if rebate_applied > 0 or marginal_relief_applied > 0:
            if rebate_applied > 0:
                breakdown_components.insert(-3, "Less: Rebate Applied")
                breakdown_amounts.insert(-3, f"({rebate_applied:,.2f})")
                breakdown_percentages.insert(-3, "-")
            
            if marginal_relief_applied > 0:
                breakdown_components.insert(-3, "Less: Marginal Relief")
                breakdown_amounts.insert(-3, f"({marginal_relief_applied:,.2f})")
                breakdown_percentages.insert(-3, "-")
        
        breakdown_data = {
            "Component": breakdown_components,
            "Amount (₹)": breakdown_amounts,
            "Percentage": breakdown_percentages
        }
        
        df = pd.DataFrame(breakdown_data)
        st.dataframe(df, use_container_width=True)

with tab2:
    st.markdown("### 📊 Tax Analysis & Visualizations")
    
    if 'total_tax' in locals():
        # Pie chart for tax breakdown
        col1, col2 = st.columns(2)
        
        with col1:
            fig_pie = go.Figure(data=[go.Pie(
                labels=['Base Tax', 'Surcharge', 'Cess'],
                values=[base_tax, surcharge, cess],
                hole=0.4,
                marker_colors=['#FF6B6B', '#4ECDC4', '#45B7D1']
            )])
            fig_pie.update_layout(title="Tax Component Breakdown", height=400)
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with col2:
            # Income vs Tax chart
            income_components = ['Salary', 'Business', 'House Property', 'Other Sources', 'STCG', 'LTCG']
            net_house_for_chart = max(0, (house_income * 0.7) - house_loan_interest) if 'house_loan_interest' in locals() else house_income * 0.7
            income_values = [max(0, salary-75000 if regime=='new' else salary-50000), 
                           business_income, net_house_for_chart, other_sources, stcg, ltcg]
            
            fig_bar = px.bar(
                x=income_components,
                y=income_values,
                title="Income Source Breakdown",
                color=income_values,
                color_continuous_scale="viridis"
            )
            fig_bar.update_layout(height=400)
            st.plotly_chart(fig_bar, use_container_width=True)
        
        # Effective tax rate
        if total_taxable_income > 0:
            effective_rate = (total_tax / total_taxable_income) * 100
            st.success(f"🎯 Your effective tax rate is **{effective_rate:.2f}%**")
            
            # Show marginal relief benefit if applicable
            if regime == 'new' and marginal_relief_applied > 0:
                st.info(f"💡 **Marginal Relief Saved:** ₹{marginal_relief_applied:,.0f} - Without this relief, your tax would be higher!")

with tab3:
    st.markdown("### 📋 Tax Planning Suggestions")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 💡 Tax Saving Tips")
        st.info("""
        **For Old Regime:**
        - 80C investments (₹1.5L)
        - 80D medical insurance
        - HRA exemption
        - LTA exemption
        
        **For New Regime:**
        - **₹4L basic exemption**
        - Rebate up to ₹12L income
        - **🆕 Marginal Relief for ₹12L-₹12.6L**
        - Smart CG exemption utilization
        - Focus on long-term investments
        
        **House Property:**
        - Interest on loan fully deductible
        - 30% standard deduction available
        """)
    
    with col2:
        st.markdown("#### 📈 Investment & Planning Strategy")
        st.success("""
        **Tax-Efficient Options:**
        - ELSS Mutual Funds
        - PPF (Public Provident Fund)
        - NSC (National Savings Certificate)
        - Tax-Free Bonds
        - **Equity investments** (LTCG benefit)
        - **Real Estate** (rental income + loan interest benefit)
        
        **🆕 New Regime Strategy:**
        - Keep total income near **₹12L** for full rebate
        - If above ₹12L, try to stay under **₹12.6L** for marginal relief
        - **Sweet spot:** ₹12L-₹12.6L pays minimal tax due to marginal relief
        """)
    
    # Marginal Relief demonstration table
    if regime == 'new':
        st.markdown("#### 🎯 Marginal Relief Demonstration")
        st.info("See how marginal relief protects you from sudden tax jumps:")
        
        demo_data = {
            "Income (₹)": ["11,99,000", "12,01,000", "12,30,000", "12,60,000", "12,61,000"],
            "Without Relief": ["₹0*", "₹15,000+", "₹45,000+", "₹75,000+", "₹75,300+"],
            "With Marginal Relief": ["₹0*", "₹1,000", "₹30,000", "₹60,000", "₹75,300"],
            "Benefit": ["-", "₹14,000 saved", "₹15,000 saved", "₹15,000 saved", "-"]
        }
        
        demo_df = pd.DataFrame(demo_data)
        st.dataframe(demo_df, use_container_width=True)
        st.caption("*After ₹60K rebate. Marginal relief ensures smooth tax progression.")
    
    # Tax calendar
    st.markdown("#### 📅 Important Tax Dates")
    tax_dates = pd.DataFrame({
        "Date": ["31st July","15th March","15th December", "15th September", "15th June"],
        "Event": ["ITR Filing Due Date", "Q4 Advance Tax","Q3 Advance Tax", "Q2 Advance Tax", "Q1 Advance Tax"],
        "Amount": ["Annual Return", "100% of Tax","75% of Tax", "45% of Tax", "15% of Tax"]
    })
    st.dataframe(tax_dates, use_container_width=True)

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 20px;'>
    <p>💼 APMH Tax Calculator | Built with ❤️ using Streamlit</p>
    <p><small>⚠️ This calculator is for reference only. Please consult a APMH LLP for accurate advice.</small></p>
    <p><small>🆕 Now includes Marginal Relief for New Regime (₹12L-₹12.6L income range)</small></p>
</div>
""", unsafe_allow_html=True)
