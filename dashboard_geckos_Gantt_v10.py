import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import datetime
import io
import numpy as np

# 設定網頁標題與佈局 (Wide Mode)
st.set_page_config(page_title="Geckos Dashboard Pro", layout="wide")

# =========================================================================
# 🔐 [資安強化] 身分驗證
# =========================================================================
def check_password():
    """Returns `True` if the user had a correct password."""
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password" not in st.secrets:
        st.error("⚠️ 系統設定錯誤：未檢測到密碼設定檔 (.streamlit/secrets.toml)。")
        return False

    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    st.title("🔒 Geckos Dashboard 安全登入")
    st.markdown("##### 本系統包含敏感專案資料，請輸入授權密碼。")
    st.text_input("Password", type="password", on_change=password_entered, key="password")
    
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        if "password" not in st.session_state: 
             st.error("❌ 密碼錯誤，請重新輸入。")
    return False

if not check_password():
    st.stop()

# =========================================================================
# ⬇️ Dashboard 主程式
# =========================================================================

st.title("Geckos Project Dashboard (Executive View)")

# 1. 檔案上傳區塊
st.sidebar.header("資料上傳區")
uploaded_file = st.sidebar.file_uploader("請上傳專案總表 (Excel/CSV)", type=["xlsx", "csv"])

# --- 輔助函式 ---
def parse_quarter_date_end(date_str):
    """將 '2026Q2' 轉為該季的【最後一天】"""
    if pd.isna(date_str): return None
    date_str = str(date_str).strip().upper()
    match = re.search(r'(\d{4}).*Q(\d)', date_str)
    if match:
        year = int(match.group(1))
        quarter = int(match.group(2))
        quarter_ends = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
        if quarter in quarter_ends:
            month, day = quarter_ends[quarter]
            return pd.Timestamp(year=year, month=month, day=day)
    return None

def get_week_str(dt):
    if pd.isnull(dt): return None
    iso_cal = dt.isocalendar()
    return f"{iso_cal.year}-W{iso_cal.week:02d}"

# Helper to parse margin ranges
def parse_margin_min(val):
    if pd.isna(val) or str(val).strip() == '': return 0.0
    val_str = str(val).replace('%', '')
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", val_str)
    if not nums: return 0.0
    floats = [float(n) for n in nums]
    min_val = min(floats)
    if min_val > 1.0: return min_val / 100.0
    return min_val

if uploaded_file is not None:
    # 2. 讀取與初始化資料
    try:
        file_id = uploaded_file.file_id if hasattr(uploaded_file, 'file_id') else uploaded_file.name
        
        if 'full_df' not in st.session_state or st.session_state.get('current_file_id') != file_id:
            if uploaded_file.name.endswith('.csv'):
                df_raw = pd.read_csv(uploaded_file)
            else:
                df_raw = pd.read_excel(uploaded_file)
            
            df_raw.columns = df_raw.columns.str.strip()
            
            # [V47] 欄位格式優化
            if '專案負責人' in df_raw.columns:
                df_raw['專案負責人'] = df_raw['專案負責人'].astype(str).replace('nan', '')

            # 數值前處理
            for col in df_raw.columns:
                if '營收' in col: 
                     if df_raw[col].dtype == 'object':
                        df_raw[col] = pd.to_numeric(df_raw[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
                     else:
                        df_raw[col] = df_raw[col].fillna(0)

            st.session_state['full_df'] = df_raw
            st.session_state['current_file_id'] = file_id
            
            if 'working_df' in st.session_state: del st.session_state['working_df']
            if 'last_filtered_shape' in st.session_state: del st.session_state['last_filtered_shape']

    except Exception as e:
        st.error(f"檔案讀取失敗: {e}")
        st.stop()

    df_full = st.session_state['full_df']

    # --- 欄位識別 ---
    col_twd = None
    col_rmb = None
    col_margin = None
    
    candidates_twd = [c for c in df_full.columns if '預估營收' in c and 'TWD' in c]
    if candidates_twd: col_twd = candidates_twd[0]
    elif '預估營收(TWD)' in df_full.columns: col_twd = '預估營收(TWD)'
    
    candidates_rmb = [c for c in df_full.columns if '預估營收' in c and 'RMB' in c]
    if candidates_rmb: col_rmb = candidates_rmb[0]
    elif '預估營收(RMB)' in df_full.columns: col_rmb = '預估營收(RMB)'
    
    if not col_twd:
        candidates_gen = [c for c in df_full.columns if '預估營收' in c and c != col_rmb]
        if candidates_gen: col_twd = candidates_gen[0]

    margin_candidates = ['預估毛利率', '毛利率', '預期毛利率', 'Gross Margin', 'GM']
    for c in margin_candidates:
        if c in df_full.columns:
            col_margin = c
            break

    if not col_twd:
        st.error("❌ 找不到「預估營收(TWD)」相關欄位，請檢查 Excel 表頭。")
        st.stop()

    # 尋找狀態欄位 (用於判斷已結案)
    status_col = None
    for c in ['結案狀態', '專案狀態', '狀態']:
        if c in df_full.columns:
            status_col = c
            break

    # =========================================================================
    # [全域樣式與變數]
    # =========================================================================
    type_style_map = {
        'NPDR': {'bg': '#EBF5FB', 'border': '#2E86C1', 'text': '#2E86C1'},
        'MDR':  {'bg': '#E8F8F5', 'border': '#17A589', 'text': '#17A589'},
        'TDR':  {'bg': '#FEF9E7', 'border': '#F1C40F', 'text': '#D35400'},
        'default': {'bg': '#F2F3F4', 'border': '#95A5A6', 'text': '#7F8C8D'}
    }
    
    cols_priority_npdr = ['NPDR', 'NPDR時間', 'NPDR開案時間', '開案時間', '开案时间']
    cols_priority_dv = ['設計驗證時間', 'DV', 'DV時間', '設計驗證']
    cols_priority_ev = ['工程驗證時間', 'EV', 'EV時間', '工程驗證']
    cols_priority_order = ['預計訂單起始點', 'Order', '預計訂單']
    
    def get_first_valid_date(row, cols_list):
        for c in cols_list:
            if c in row.index:
                val = row[c]
                dt = parse_quarter_date_end(val)
                if pd.isnull(dt): dt = pd.to_datetime(val, errors='coerce')
                if pd.notnull(dt): return dt
        return pd.NaT

    # =========================================================================
    # [區塊 1] 篩選條件
    # =========================================================================
    st.sidebar.header("🔍 專案篩選器")
    st.sidebar.markdown("### 🎯 核心鎖定")
    
    pm_col = '專案負責人'
    pm_options = sorted(df_full[pm_col].unique().astype(str)) if pm_col in df_full.columns else []
    pm_options = [x for x in pm_options if x.lower() != 'nan' and x.strip() != '']
    pm_filter = st.sidebar.multiselect("👤 專案負責人 (PM)", options=pm_options)

    project_options = df_full['專案'].unique() if '專案' in df_full.columns else []
    project_filter = st.sidebar.multiselect("🏷️ 專案名稱", options=project_options)

    open_type_filter = []
    cat_filter = []
    scene_filter = []
    cat_col_name = None

    with st.sidebar.expander("📂 產品與類別屬性", expanded=False):
        open_type_col = '開案類別'
        open_type_filter = st.multiselect("開案類別", options=df_full[open_type_col].unique()) if open_type_col in df_full.columns else []

        if '產品類別' in df_full.columns:
            cat_col_name = '產品類別'
        elif '專案類別' in df_full.columns:
            cat_col_name = '專案類別'
        
        if cat_col_name:
            cat_filter = st.multiselect("產品類別", options=df_full[cat_col_name].unique())

        scene_col = '產業應用場景'
        scene_filter = st.multiselect("產業應用場景", options=df_full[scene_col].unique()) if scene_col in df_full.columns else []

    market_filter = []
    order_start_filter = []
    order_col = '預計訂單起始點'

    with st.sidebar.expander("🌍 市場與時程", expanded=False):
        market_filter = st.multiselect("目標市場", options=df_full['市場'].unique()) if '市場' in df_full.columns else []
        order_start_filter = st.multiselect("預計訂單時間 (Quarter)", options=sorted(df_full[order_col].astype(str).unique())) if order_col in df_full.columns else []
    
    st.sidebar.divider()
    st.sidebar.markdown("### ⚙️ 參數設定")
    rmb_rate = st.sidebar.number_input("💱 RMB 換 TWD 匯率", value=4.4, step=0.01, format="%.2f")

    # --- 執行篩選 ---
    df_filtered = df_full.copy()
    
    if pm_filter and pm_col in df_filtered.columns:
        df_filtered = df_filtered[df_filtered[pm_col].isin(pm_filter)]
    if open_type_filter and open_type_col in df_filtered.columns:
        df_filtered = df_filtered[df_filtered[open_type_col].isin(open_type_filter)]
    if cat_filter and cat_col_name: 
        df_filtered = df_filtered[df_filtered[cat_col_name].isin(cat_filter)]
    if scene_filter and scene_col in df_filtered.columns:
        df_filtered = df_filtered[df_filtered[scene_col].isin(scene_filter)]
    if project_filter and '專案' in df_filtered.columns: 
        df_filtered = df_filtered[df_filtered['專案'].isin(project_filter)]
    if market_filter and '市場' in df_filtered.columns:
        df_filtered = df_filtered[df_filtered['市場'].isin(market_filter)]
    if order_start_filter and order_col in df_filtered.columns:
        df_filtered = df_filtered[df_filtered[order_col].isin(order_start_filter)]

    if 'last_filtered_shape' not in st.session_state:
        st.session_state['last_filtered_shape'] = None
    if 'working_df' not in st.session_state:
        st.session_state['working_df'] = df_filtered

    current_shape = df_filtered.shape
    if st.session_state['last_filtered_shape'] != current_shape or \
       not df_filtered.index.equals(st.session_state['working_df'].index):
        st.session_state['working_df'] = df_filtered
        st.session_state['last_filtered_shape'] = current_shape

    df_chart_source = st.session_state['working_df']

    # --- 全域資料預處理 ---
    if '專案負責人' in df_chart_source.columns:
        df_chart_source['專案負責人_display'] = df_chart_source['專案負責人'].apply(lambda x: x if pd.notnull(x) and str(x).strip() != '' else "未指派")
    else:
        df_chart_source['專案負責人_display'] = "未定義"

    unique_pms = sorted(df_chart_source['專案負責人_display'].unique())
    unique_open_types = sorted(df_chart_source['開案類別'].unique()) if '開案類別' in df_chart_source.columns else []

    val_twd = df_chart_source[col_twd].fillna(0)
    val_rmb = df_chart_source[col_rmb].fillna(0) if col_rmb else 0
    df_chart_source['Calculated_Total_TWD'] = val_twd + (val_rmb * rmb_rate)
    
    col_actual_twd = '實際營收(TWD)' if '實際營收(TWD)' in df_chart_source.columns else None
    col_actual_rmb = '實際營收(RMB)' if '實際營收(RMB)' in df_chart_source.columns else None
    
    val_actual_twd = df_chart_source[col_actual_twd].fillna(0) if col_actual_twd else 0
    val_actual_rmb = df_chart_source[col_actual_rmb].fillna(0) if col_actual_rmb else 0
    df_chart_source['Calculated_Actual_Total_TWD'] = val_actual_twd + (val_actual_rmb * rmb_rate)

    if col_margin:
        df_chart_source['Parsed_Margin_Rate'] = df_chart_source[col_margin].apply(parse_margin_min)
        df_chart_source['Calculated_Gross_Profit'] = df_chart_source['Calculated_Total_TWD'] * df_chart_source['Parsed_Margin_Rate']
    else:
        df_chart_source['Parsed_Margin_Rate'] = 0.0
        df_chart_source['Calculated_Gross_Profit'] = 0.0

    total_revenue_twd = df_chart_source['Calculated_Total_TWD'].sum()
    total_actual_twd = df_chart_source['Calculated_Actual_Total_TWD'].sum()
    total_profit_twd = df_chart_source['Calculated_Gross_Profit'].sum()

    now = pd.Timestamp.now().normalize()

    # =========================================================================
    # [區塊 2] KPI Metrics
    # =========================================================================
    st.divider()

    total_margin_rate = (total_profit_twd / total_revenue_twd * 100) if total_revenue_twd > 0 else 0
    total_ach_rate = (total_actual_twd / total_revenue_twd * 100) if total_revenue_twd > 0 else 0

    df_mdr = df_chart_source[df_chart_source['開案類別'] == 'MDR']
    mdr_rev = df_mdr['Calculated_Total_TWD'].sum()
    mdr_actual = df_mdr['Calculated_Actual_Total_TWD'].sum()
    mdr_ach_rate = (mdr_actual / mdr_rev * 100) if mdr_rev > 0 else 0
    mdr_gp = df_mdr['Calculated_Gross_Profit'].sum()
    mdr_margin = (mdr_gp / mdr_rev * 100) if mdr_rev > 0 else 0

    df_npdr = df_chart_source[df_chart_source['開案類別'] == 'NPDR']
    npdr_rev = df_npdr['Calculated_Total_TWD'].sum()
    npdr_actual = df_npdr['Calculated_Actual_Total_TWD'].sum()
    npdr_ach_rate = (npdr_actual / npdr_rev * 100) if npdr_rev > 0 else 0
    npdr_gp = df_npdr['Calculated_Gross_Profit'].sum()
    npdr_margin = (npdr_gp / npdr_rev * 100) if npdr_rev > 0 else 0

    df_tdr = df_chart_source[df_chart_source['開案類別'] == 'TDR']
    tdr_rev = df_tdr['Calculated_Total_TWD'].sum()
    tdr_actual = df_tdr['Calculated_Actual_Total_TWD'].sum()
    tdr_ach_rate = (tdr_actual / tdr_rev * 100) if tdr_rev > 0 else 0
    tdr_gp = df_tdr['Calculated_Gross_Profit'].sum()
    tdr_margin = (tdr_gp / tdr_rev * 100) if tdr_rev > 0 else 0

    def render_kpi_card(title, icon, rev, actual, ach_rate, gp, margin, border_color, rmb_rate):
        bar_width = min(ach_rate, 100)
        bar_color = "#27AE60" if ach_rate >= 80 else ("#F1C40F" if ach_rate >= 50 else "#E74C3C")
        help_rev = f"匯率換算: RMB * {rmb_rate}"
        help_actual = "實際營收加總 (RMB 依系統匯率轉換)"
        help_ach = "達成率計算方式：實際總營收 / 預估總營收"
        help_gp = "計算方式：營收 * 預估毛利率 (若為區間取最低值)"
        help_margin = "計算方式：(該類別總毛利 / 該類別總營收) * 100%"

        html = f"""<div style="border: 1px solid rgba(128,128,128,0.2); padding: 15px; border-radius: 8px; border-left: 6px solid {border_color}; margin-bottom: 10px; background-color: rgba(128,128,128,0.02);">
<h4 style="margin-top: 0; margin-bottom: 15px; font-size: 1.1em; display: flex; align-items: center;">
<span style="margin-right: 8px;">{icon}</span> {title}
</h4>
<div style="display: flex; justify-content: space-between; margin-top: 10px;">
<div style="width: 48%;" title="{help_rev}">
<div style="font-size: 0.8em; opacity: 0.7; cursor: help;">預估營收 ℹ️</div>
<div style="font-size: 1.1em; font-weight: bold;">{rev:,.0f}</div>
</div>
<div style="width: 48%; text-align: right;" title="{help_actual}">
<div style="font-size: 0.8em; opacity: 0.7; cursor: help;">實際營收 ℹ️</div>
<div style="font-size: 1.1em; font-weight: bold; color: #2980B9;">{actual:,.0f}</div>
</div>
</div>
<div style="margin-top: 8px; margin-bottom: 2px; background-color: rgba(128,128,128,0.2); border-radius: 4px; height: 6px; width: 100%;" title="{help_ach}">
<div style="background-color: {bar_color}; width: {bar_width}%; height: 100%; border-radius: 4px;"></div>
</div>
<div style="text-align: right; font-size: 0.85em; font-weight: bold; color: {bar_color}; margin-bottom: 12px;" title="{help_ach}">
達成率 {ach_rate:.1f}%
</div>
<div style="border-top: 1px dashed rgba(128,128,128,0.3); padding-top: 10px; display: flex; justify-content: space-between;">
<div style="width: 48%;" title="{help_gp}">
<div style="font-size: 0.8em; opacity: 0.7; cursor: help;">預估毛利 ℹ️</div>
<div style="font-size: 1.05em; font-weight: bold; color: #27AE60;">{gp:,.0f}</div>
</div>
<div style="width: 48%; text-align: right;" title="{help_margin}">
<div style="font-size: 0.8em; opacity: 0.7; cursor: help;">毛利率 ℹ️</div>
<div style="font-size: 1.05em; font-weight: bold; color: #8E44AD;">{margin:.1f}%</div>
</div>
</div>
</div>"""
        return html

    # [V74.0] 稍微放大第 5 欄的寬度比例，給予圖表與英雄榜更多空間
    col_kpi1, col_kpi2, col_kpi3, col_kpi4, col_kpi5 = st.columns([1, 1, 1, 1, 1.3])
    
    with col_kpi1:
        st.markdown(render_kpi_card("全體匯總", "🌍", total_revenue_twd, total_actual_twd, total_ach_rate, total_profit_twd, total_margin_rate, "#34495E", rmb_rate), unsafe_allow_html=True)

    with col_kpi2:
        st.markdown(render_kpi_card("MDR 專案", "🔺", mdr_rev, mdr_actual, mdr_ach_rate, mdr_gp, mdr_margin, "#E74C3C", rmb_rate), unsafe_allow_html=True)

    with col_kpi3:
        st.markdown(render_kpi_card("NPDR 專案", "🔵", npdr_rev, npdr_actual, npdr_ach_rate, npdr_gp, npdr_margin, "#3498DB", rmb_rate), unsafe_allow_html=True)

    with col_kpi4:
        st.markdown(render_kpi_card("TDR 專案", "🔸", tdr_rev, tdr_actual, tdr_ach_rate, tdr_gp, tdr_margin, "#E67E22", rmb_rate), unsafe_allow_html=True)

    with col_kpi5:
        if not df_chart_source.empty:
            if status_col:
                df_active_source = df_chart_source[df_chart_source[status_col].astype(str).str.strip() != '已結案']
            else:
                df_active_source = df_chart_source
            
            project_count_unique_active = df_active_source['專案'].nunique()
            df_unique_proj = df_active_source.drop_duplicates(subset=['專案'])
            
            df_hero = df_chart_source.groupby('專案').agg({
                'Calculated_Total_TWD': 'sum',
                'Calculated_Gross_Profit': 'sum',
                'Calculated_Actual_Total_TWD': 'sum'
            }).reset_index()

            if not df_hero.empty and df_hero['Calculated_Total_TWD'].sum() > 0:
                idx_rev = df_hero['Calculated_Total_TWD'].idxmax()
                rev_king = df_hero.loc[idx_rev, '專案']
                rev_val = df_hero.loc[idx_rev, 'Calculated_Total_TWD']
                
                idx_gp = df_hero['Calculated_Gross_Profit'].idxmax()
                gp_king = df_hero.loc[idx_gp, '專案']
                gp_val = df_hero.loc[idx_gp, 'Calculated_Gross_Profit']
                    
                top10_hero = df_hero.nlargest(10, 'Calculated_Total_TWD').copy()
                top10_hero['Ach_Pct'] = np.where(top10_hero['Calculated_Total_TWD'] > 0,
                                                 (top10_hero['Calculated_Actual_Total_TWD'] / top10_hero['Calculated_Total_TWD']) * 100, 0)
                valid_ach = top10_hero[top10_hero['Ach_Pct'] > 0]
                
                if not valid_ach.empty:
                    idx_ach = valid_ach['Ach_Pct'].idxmax()
                    ach_king = valid_ach.loc[idx_ach, '專案']
                    ach_val = valid_ach.loc[idx_ach, 'Ach_Pct']
                else:
                    ach_king, ach_val = "-", 0
                    
            else:
                rev_king, rev_val = "-", 0
                gp_king, gp_val = "-", 0
                ach_king, ach_val = "-", 0

            html_hero = f"""<div style="border: 1px solid rgba(128,128,128,0.2); padding: 15px; border-radius: 8px; border-left: 6px solid #F1C40F; margin-bottom: 5px; background-color: rgba(128,128,128,0.02);">
<h4 style="margin-top: 0; margin-bottom: 15px; font-size: 1.1em; display: flex; align-items: center; color: #333;">
<span style="margin-right: 8px;">🏆</span> 專案英雄榜
</h4>
<div style="display: flex; justify-content: space-between; font-size: 0.9em; margin-bottom: 12px;" title="全專案預估總營收第一名 (對齊區塊6)">
<div>💰 <b>{rev_king}</b> <span style='font-size:0.8em;color:#7F8C8D;'>(營收貢獻王)</span></div>
<div style="font-weight:bold; color:#2980B9;">{rev_val:,.0f}</div>
</div>
<div style="display: flex; justify-content: space-between; font-size: 0.9em; margin-bottom: 12px;" title="全專案預估毛利總額第一名 (對齊區塊11)">
<div>💎 <b>{gp_king}</b> <span style='font-size:0.8em;color:#7F8C8D;'>(獲利貢獻王)</span></div>
<div style="font-weight:bold; color:#27AE60;">{gp_val:,.0f}</div>
</div>
<div style="display: flex; justify-content: space-between; font-size: 0.9em;" title="營收前10大專案中，實際達成率最高者 (對齊區塊12)">
<div>🎯 <b>{ach_king}</b> <span style='font-size:0.8em;color:#7F8C8D;'>(最佳達標專案)</span></div>
<div style="font-weight:bold; color:#E67E22;">{ach_val:.1f}%</div>
</div>
</div>"""
            st.markdown(html_hero, unsafe_allow_html=True)
            
            # Donut Chart - [V74.0] Increased size and height
            if '開案類別' in df_unique_proj.columns:
                type_counts = df_unique_proj['開案類別'].value_counts().reset_index()
                type_counts.columns = ['Type', 'Count']
                pro_colors = ['#2C3E50', '#5D6D7E', '#85929E', '#34495E', '#AAB7B8', '#D5DBDB']
                
                fig_donut = go.Figure()
                fig_donut.add_trace(go.Pie(
                    labels=type_counts['Type'], values=type_counts['Count'], hole=0.75,
                    textinfo='label+value', textposition='inside',
                    insidetextorientation='horizontal',
                    insidetextfont=dict(color='white', size=15, weight='bold'), # [V74.0] 12px -> 15px
                    marker=dict(colors=pro_colors, line=dict(color='#FFFFFF', width=1)),
                    hoverinfo='label+percent+value', showlegend=False, sort=False
                ))
                fig_donut.add_trace(go.Pie(
                    values=[1], labels=["Center"], hole=0,
                    marker=dict(colors=['#2C3E50']),
                    domain=dict(x=[0.25, 0.75], y=[0.25, 0.75]),
                    hoverinfo='skip', showlegend=False, textinfo='none'
                ))
                fig_donut.update_layout(
                    annotations=[dict(text=f"專案: {project_count_unique_active}", x=0.5, y=0.5, font=dict(size=24, color='white', weight='bold'), showarrow=False)],
                    margin=dict(t=10, b=10, l=0, r=0), height=240, showlegend=False # [V74.0] 140px -> 240px
                )
                st.plotly_chart(fig_donut, use_container_width=True)
            else: st.info("無 '開案類別'")
        else:
            st.info("無專案資料")

    st.divider()

    # =========================================================================
    # [區塊 6] 營收 Top 10
    # =========================================================================
    with st.expander("🏆 預估營收 Top 10 專案 (含 PM 篩選)", expanded=True):
        if total_revenue_twd > 0:
            b6_col_metric, b6_col_pm, b6_col_type = st.columns([1.5, 1, 1])
            with b6_col_pm:
                pm_sel_b6 = st.selectbox("👤 篩選負責人", ["全部 (All)"] + list(unique_pms), key='b6_pm')
            with b6_col_type:
                type_sel_b6 = st.selectbox("📂 篩選開案類別", ["全部 (All)"] + list(unique_open_types), key='b6_type')
            
            df_b6 = df_chart_source.copy()
            if pm_sel_b6 != "全部 (All)": df_b6 = df_b6[df_b6['專案負責人_display'] == pm_sel_b6]
            if type_sel_b6 != "全部 (All)": df_b6 = df_b6[df_b6['開案類別'] == type_sel_b6]
            
            local_rev = df_b6['Calculated_Total_TWD'].sum()
            with b6_col_metric: st.metric(label=f"💰 預估總營收 (TWD)", value=f"{local_rev:,.0f}", help="顯示當前篩選條件下的預估總營收")

            if not df_b6.empty:
                df_b6_grouped = df_b6.groupby('專案').agg({
                    'Calculated_Total_TWD': 'sum',
                    'Calculated_Gross_Profit': 'sum',
                    'Calculated_Actual_Total_TWD': 'sum'
                }).reset_index()
                
                if status_col:
                    status_df = df_b6.drop_duplicates(subset=['專案'])[['專案', status_col]]
                    df_b6_grouped = pd.merge(df_b6_grouped, status_df, on='專案', how='left')
                    df_b6_grouped['Project_Display'] = df_b6_grouped.apply(
                        lambda r: f"<b>{r['專案']}</b>" if str(r[status_col]).strip() == '已結案' else r['專案'], axis=1
                    )
                else:
                    df_b6_grouped['Project_Display'] = df_b6_grouped['專案']

                df_chart = df_b6_grouped.nlargest(10, 'Calculated_Total_TWD').sort_values('Calculated_Total_TWD', ascending=True)
                
                if total_revenue_twd > 0: df_chart['Pct'] = (df_chart['Calculated_Total_TWD'] / total_revenue_twd) * 100
                else: df_chart['Pct'] = 0
                
                max_val = df_chart['Calculated_Total_TWD'].max() if not df_chart.empty else 1
                threshold = max_val * 0.15 
                
                def get_smart_color(val): return '#333333' if val < (max_val * 0.4) else '#FFFFFF'
                df_chart['Inside_Color'] = df_chart['Calculated_Total_TWD'].apply(get_smart_color)

                def get_bar_text(row):
                    val_str = f"{row['Calculated_Total_TWD']:,.0f}"
                    pct_str = f"<b>{row['Pct']:.1f}%</b>"
                    if row['Calculated_Total_TWD'] < threshold: return f"{pct_str} | {val_str}"
                    return val_str

                def get_scatter_text(row):
                    if row['Calculated_Total_TWD'] < threshold: return ""
                    return f"<b>{row['Pct']:.1f}%</b>"

                df_chart[['Bar_Text', 'Scatter_Text']] = df_chart.apply(
                    lambda r: pd.Series([get_bar_text(r), get_scatter_text(r)]), 
                    axis=1, result_type='expand'
                )

                fig_bar = px.bar(df_chart, x='Calculated_Total_TWD', y='Project_Display', orientation='h', color='Calculated_Total_TWD', color_continuous_scale='Blues')
                fig_bar.update_traces(text=df_chart['Bar_Text'], texttemplate='%{text}', textposition='outside', textfont=dict(size=14, color='#333333'), constraintext='none')
                fig_bar.add_trace(go.Scatter(x=[0] * len(df_chart), y=df_chart['Project_Display'], text=df_chart['Scatter_Text'], mode='text', textposition='middle right', textfont=dict(size=14, color=df_chart['Inside_Color']), hoverinfo='skip', showlegend=False))
                fig_bar.update_layout(xaxis_title="預估營收 (含RMB換算)", yaxis_title="專案", xaxis=dict(range=[0, max_val * 1.35]))
                st.plotly_chart(fig_bar, use_container_width=True)
            else: st.warning("查無符合條件的專案")
        else: st.info("無營收數據")

    # =========================================================================
    # [區塊 12] 🎯 營收達成率
    # =========================================================================
    with st.expander("🎯 營收達成率 (預估營收 vs 實際營收)", expanded=True):
        if 'df_b6_grouped' in locals() and not df_b6_grouped.empty:
            
            local_target_rev = df_b6['Calculated_Total_TWD'].sum()
            local_actual_rev = df_b6['Calculated_Actual_Total_TWD'].sum()
            
            b12_c1, b12_c2, b12_c3 = st.columns([1, 1, 2])
            with b12_c1:
                st.metric(label="💰 預估總營收 (TWD)", value=f"{local_target_rev:,.0f}", help="當前篩選條件下的預估總營收")
            with b12_c2:
                st.metric(label="📈 實際總營收 (TWD)", value=f"{local_actual_rev:,.0f}", help="當前篩選條件下的實際總營收")
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            df_bullet = df_b6_grouped.nlargest(10, 'Calculated_Total_TWD').sort_values('Calculated_Total_TWD', ascending=True)
            
            df_bullet['Ach_Pct'] = np.where(df_bullet['Calculated_Total_TWD'] > 0, 
                                           (df_bullet['Calculated_Actual_Total_TWD'] / df_bullet['Calculated_Total_TWD']) * 100, 
                                           0)
            
            max_target = df_bullet['Calculated_Total_TWD'].max() if not df_bullet.empty else 1
            max_actual = df_bullet['Calculated_Actual_Total_TWD'].max() if not df_bullet.empty else 1
            axis_max = max(max_target, max_actual)
            
            threshold_ach = axis_max * 0.15 
            
            def get_bullet_texts(row):
                t = float(row['Calculated_Total_TWD'])
                a = float(row['Calculated_Actual_Total_TWD'])
                pct = float(row['Ach_Pct'])
                
                t_str_plain = f"預估: {t:,.0f}"
                t_str_html = f"<span style='font-size:14px; color:#7F8C8D;'>預估: {t:,.0f}</span>"
                a_str = f"<b>達成率: {pct:.1f}%</b>"
                
                t_bar = ""
                a_bar = ""
                scat_out = ""
                scat_in = ""
                
                t_is_short = t < threshold_ach
                a_is_short = a < threshold_ach

                if not t_is_short and not a_is_short:
                    t_bar = t_str_plain
                    scat_in = a_str
                elif t_is_short and a_is_short:
                    scat_out = f"{t_str_html}  |  {a_str}"
                elif not t_is_short and a_is_short:
                    t_bar = t_str_plain
                    a_bar = a_str
                elif t_is_short and not a_is_short:
                    scat_out = f"{t_str_html}  |  {a_str}"
                        
                return pd.Series([t_bar, a_bar, scat_out, scat_in, max(t, a)])

            df_bullet[['T_Bar_Txt', 'A_Bar_Txt', 'Scat_Out_Txt', 'Scat_In_Txt', 'Max_Val']] = df_bullet.apply(get_bullet_texts, axis=1, result_type='expand')

            customdata_array = df_bullet[['Calculated_Total_TWD', 'Calculated_Actual_Total_TWD', 'Ach_Pct']].values
            master_hover = "<b>%{y}</b><br>預估營收: %{customdata[0]:,.0f}<br>實際營收: %{customdata[1]:,.0f}<br>達成率: %{customdata[2]:.1f}%<extra></extra>"

            fig_bullet = go.Figure()
            
            fig_bullet.add_trace(go.Bar(
                x=df_bullet['Calculated_Total_TWD'], y=df_bullet['Project_Display'], orientation='h',
                name='預估營收', marker=dict(color='#D6EAF8'), 
                text=df_bullet['T_Bar_Txt'], textposition='outside', 
                textfont=dict(size=14, color='#7F8C8D'),
                customdata=customdata_array, hovertemplate=master_hover,
                constraintext='none'
            ))
            
            fig_bullet.add_trace(go.Bar(
                x=df_bullet['Calculated_Actual_Total_TWD'], y=df_bullet['Project_Display'], orientation='h',
                name='實際營收', marker=dict(color='#21618C'), width=0.4, 
                text=df_bullet['A_Bar_Txt'], textposition='outside', 
                textfont=dict(size=16, color='#333333'), 
                customdata=customdata_array, hovertemplate=master_hover,
                constraintext='none'
            ))

            fig_bullet.add_trace(go.Scatter(
                x=df_bullet['Max_Val'], y=df_bullet['Project_Display'], mode='text',
                text=df_bullet['Scat_Out_Txt'], textposition='middle right',
                textfont=dict(size=16, color='#333333'),
                hoverinfo='skip', showlegend=False
            ))

            fig_bullet.add_trace(go.Scatter(
                x=[0]*len(df_bullet), y=df_bullet['Project_Display'], mode='text',
                text=df_bullet['Scat_In_Txt'], textposition='middle right',
                textfont=dict(size=16, color='#FFFFFF'), 
                hoverinfo='skip', showlegend=False 
            ))
            
            fig_bullet.update_layout(
                barmode='overlay', xaxis_title="營收金額 (TWD)", yaxis_title="專案",
                xaxis=dict(range=[0, axis_max * 1.35]),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            
            st.plotly_chart(fig_bullet, use_container_width=True)
            st.caption("💡 提示：淺藍色寬條代表「預估營收」，深藍色細條代表「實際營收」。")
        else:
            st.info("無數據可供顯示")

    # =========================================================================
    # [區塊 11] 預估毛利 Top 10
    # =========================================================================
    with st.expander("💎 預估毛利 Top 10 專案 (含 PM 篩選)", expanded=True):
        if 'df_b6_grouped' in locals() and not df_b6_grouped.empty:
            df_gp_chart = df_b6_grouped.nlargest(10, 'Calculated_Gross_Profit').sort_values('Calculated_Gross_Profit', ascending=True)
            
            max_gp = df_gp_chart['Calculated_Gross_Profit'].max() if not df_gp_chart.empty else 1
            threshold_gp = max_gp * 0.15 
            def get_smart_color_gp(val): return '#333333' if val < (max_gp * 0.4) else '#FFFFFF'
            df_gp_chart['Inside_Color'] = df_gp_chart['Calculated_Gross_Profit'].apply(get_smart_color_gp)

            df_gp_chart['Avg_Margin'] = np.where(df_gp_chart['Calculated_Total_TWD'] > 0, 
                                                 (df_gp_chart['Calculated_Gross_Profit'] / df_gp_chart['Calculated_Total_TWD']) * 100, 
                                                 0)
            
            def get_gp_bar_text(row):
                val_str = f"{row['Calculated_Gross_Profit']:,.0f}"
                margin_str = f"<b>{row['Avg_Margin']:.1f}%</b> (毛利率)"
                if row['Calculated_Gross_Profit'] < threshold_gp: return f"{margin_str} | {val_str}"
                return val_str

            def get_gp_scatter_text(row):
                if row['Calculated_Gross_Profit'] < threshold_gp: return ""
                return f"<b>{row['Avg_Margin']:.1f}%</b> (毛利率)"

            df_gp_chart[['Bar_Text', 'Scatter_Text']] = df_gp_chart.apply(
                lambda r: pd.Series([get_gp_bar_text(r), get_gp_scatter_text(r)]), 
                axis=1, result_type='expand'
            )

            fig_gp = px.bar(df_gp_chart, x='Calculated_Gross_Profit', y='Project_Display', orientation='h', color='Calculated_Gross_Profit', color_continuous_scale='Greens')
            fig_gp.update_traces(text=df_gp_chart['Bar_Text'], texttemplate='%{text}', textposition='outside', textfont=dict(size=14, color='#333333'), constraintext='none')
            fig_gp.add_trace(go.Scatter(x=[0] * len(df_gp_chart), y=df_gp_chart['Project_Display'], text=df_gp_chart['Scatter_Text'], mode='text', textposition='middle right', textfont=dict(size=14, color=df_gp_chart['Inside_Color']), hoverinfo='skip', showlegend=False))
            fig_gp.update_layout(xaxis_title="預估毛利 (TWD)", yaxis_title="專案", xaxis=dict(range=[0, max_gp * 1.35]))
            st.plotly_chart(fig_gp, use_container_width=True)
        else: st.info("無毛利數據")

    st.divider()

    # =========================================================================
    # [區塊 10] 預計訂單 Top 10
    # =========================================================================
    with st.expander("⏳ 預計訂單即將到期 Top 10", expanded=True):
        if '預計訂單起始點' in df_chart_source.columns:
            cols_to_keep = ['專案', '預計訂單起始點', col_twd]
            if col_rmb: cols_to_keep.append(col_rmb)
            if '專案負責人' in df_chart_source.columns: cols_to_keep.append('專案負責人')
            if status_col: cols_to_keep.append(status_col)
            
            df_time = df_chart_source[cols_to_keep].copy()
            df_time['OrderDate'] = df_time['預計訂單起始點'].apply(lambda x: parse_quarter_date_end(x) if pd.notnull(x) and 'Q' in str(x) else pd.to_datetime(x, errors='coerce'))
            df_time = df_time.dropna(subset=['OrderDate'])
            
            grp_cols = ['專案']
            df_rev_agg = df_chart_source.groupby(grp_cols)[[col_twd, col_rmb] if col_rmb else [col_twd]].sum().reset_index()
            df_time_dedup = df_time.sort_values('OrderDate').drop_duplicates(subset=['專案'], keep='first')
            df_final = pd.merge(df_time_dedup, df_rev_agg, on='專案', how='left', suffixes=('', '_sum'))
            
            twd_col_sum = f"{col_twd}_sum" if f"{col_twd}_sum" in df_final.columns else col_twd
            rmb_col_sum = f"{col_rmb}_sum" if col_rmb and f"{col_rmb}_sum" in df_final.columns else col_rmb
            
            if not df_final.empty:
                df_final['DaysDiff'] = (df_final['OrderDate'] - now).dt.days
                df_final['Total_Revenue_Sort'] = df_final[twd_col_sum].fillna(0) + (df_final[rmb_col_sum].fillna(0) * rmb_rate if rmb_col_sum else 0)
                df_final = df_final[df_final['DaysDiff'] >= 0]
                
                if df_final.empty: st.success("🎉 目前沒有即將到期的緊急訂單！")
                else:
                    df_final = df_final.sort_values(by=['DaysDiff', 'Total_Revenue_Sort'], ascending=[True, False])
                    df_plot = df_final.head(10).sort_values(by=['DaysDiff', 'Total_Revenue_Sort'], ascending=[False, True])
                    
                    max_val = df_plot['DaysDiff'].max()
                    visual_buffer = max(1, max_val * 0.02) if max_val > 0 else 1
                    df_plot['Plot_Value'] = df_plot['DaysDiff'].replace(0, visual_buffer)
                    
                    def get_status_color(days):
                        if days <= 30: return '#E74C3C'
                        elif days <= 90: return '#F1C40F'
                        else: return '#2ECC71'
                    df_plot['Color'] = df_plot['DaysDiff'].apply(get_status_color)
                    
                    def get_label(row):
                        pm = row.get('專案負責人', '')
                        p_name = row['專案']
                        if status_col and str(row.get(status_col, '')).strip() == '已結案':
                            p_name = f"<b>{p_name}</b>"
                        return f"{p_name} ({pm})" if pd.notnull(pm) else p_name
                    
                    df_plot['Y_Label'] = df_plot.apply(get_label, axis=1)
                    
                    def get_bar_text(row):
                        return f"{row['OrderDate'].strftime('%Y-%m-%d')} (🔥 本日!)" if row['DaysDiff']==0 else f"{row['OrderDate'].strftime('%Y-%m-%d')} (剩 {row['DaysDiff']} 天)"
                    df_plot['Bar_Text'] = df_plot.apply(get_bar_text, axis=1)
                    
                    def get_rev_text(row):
                        parts = []
                        if row.get(twd_col_sum, 0) > 0: parts.append(f"TWD {row[twd_col_sum]:,.0f}")
                        if rmb_col_sum and row.get(rmb_col_sum, 0) > 0: parts.append(f"RMB {row[rmb_col_sum]:,.0f}")
                        return f"<b>💰 {' | '.join(parts)}</b>" if parts else ""
                    df_plot['Rev_Text'] = df_plot.apply(get_rev_text, axis=1)
                    
                    final_bar_text, final_bar_pos, final_scatter_text = [], [], []
                    threshold = max_val * 0.15 if max_val > 0 else 0
                    for idx, row in df_plot.iterrows():
                        if row['Plot_Value'] > threshold:
                            final_bar_text.append(row['Bar_Text'])
                            final_bar_pos.append('inside')
                            final_scatter_text.append(row['Rev_Text'])
                        else:
                            final_bar_text.append("")
                            final_bar_pos.append('none')
                            final_scatter_text.append(f"{row['Bar_Text']}   {row['Rev_Text']}")
                            
                    fig_time = go.Figure()
                    fig_time.add_trace(go.Bar(x=df_plot['Plot_Value'], y=df_plot['Y_Label'], orientation='h', marker_color=df_plot['Color'], text=final_bar_text, textposition=final_bar_pos, name='Days', hoverinfo='y+text', constraintext='none'))
                    fig_time.add_trace(go.Scatter(x=df_plot['Plot_Value'], y=df_plot['Y_Label'], mode='text', text=final_scatter_text, textposition='middle right', textfont=dict(color='#333333', size=13), showlegend=False, cliponaxis=False))
                    
                    today_str = now.strftime('%Y-%m-%d')
                    fig_time.add_vline(x=0, line_width=2, line_dash="dash", line_color="#E74C3C")
                    fig_time.add_annotation(x=0, y=1.02, yref='paper', text=f"📍 本日 ({today_str})", showarrow=False, font=dict(color="#E74C3C", weight="bold"), bgcolor="rgba(255,255,255,0.8)")
                    
                    range_max = max_val * 1.35 if max_val > 0 else 10
                    fig_time.update_layout(title='🚨 專案到期日戰情室', xaxis=dict(zeroline=True, zerolinecolor='#E74C3C', range=[0, range_max]), height=max(400, 100 + (len(df_plot) * 40)), margin=dict(r=150, t=80))
                    st.plotly_chart(fig_time, use_container_width=True)
            else: st.info("無有效日期")

    st.divider()

    # =========================================================================
    # [區塊 3] 專案研發全週期路徑圖
    # =========================================================================
    current_types = open_type_filter if open_type_filter else ["全部"]
    type_label = ", ".join(current_types)
    with st.expander(f"🚀 專案研發全週期路徑圖 (Roadmap) - 類別: [{type_label}]", expanded=True):
        c_opts_1, c_opts_2 = st.columns([1, 1])
        with c_opts_1:
            show_schedules = st.checkbox("👁️ 顯示所有節點時程 (Show All Node Schedules)", value=False)
        with c_opts_2:
            show_tdr_order = st.checkbox("顯示 TDR 預計訂單節點", value=False)
        
        if not df_chart_source.empty:
            try:
                plot_data = []
                df_roadmap = df_chart_source.drop_duplicates(subset=['專案'])
                all_valid_dates = [pd.Timestamp.now().normalize()]

                for idx, row in df_roadmap.iterrows():
                    p_type = row.get('開案類別', '')
                    dates = {}
                    
                    dt_npdr = get_first_valid_date(row, cols_priority_npdr)
                    if pd.notnull(dt_npdr):
                        dates['NPDR'] = dt_npdr
                        all_valid_dates.append(dt_npdr)
                    
                    dt_dv = get_first_valid_date(row, cols_priority_dv)
                    if pd.notnull(dt_dv):
                        dates['DV'] = dt_dv
                        all_valid_dates.append(dt_dv)

                    dt_ev = get_first_valid_date(row, cols_priority_ev)
                    if pd.notnull(dt_ev):
                        dates['EV'] = dt_ev
                        all_valid_dates.append(dt_ev)

                    dt_order = get_first_valid_date(row, cols_priority_order)
                    if pd.notnull(dt_order):
                        if not (p_type == 'TDR' and not show_tdr_order):
                            dates['Order'] = dt_order
                            all_valid_dates.append(dt_order)
                    
                    if p_type == 'TDR':
                        if '開案' in df_roadmap.columns:
                            dt = parse_quarter_date_end(row['開案'])
                            if pd.isnull(dt): dt = pd.to_datetime(row['開案'], errors='coerce')
                            if pd.notnull(dt):
                                dates['TDR_Start'] = dt
                                all_valid_dates.append(dt)
                        if '轉NPDR時間' in df_roadmap.columns:
                            dt = parse_quarter_date_end(row['轉NPDR時間'])
                            if pd.isnull(dt): dt = pd.to_datetime(row['轉NPDR時間'], errors='coerce')
                            if pd.notnull(dt):
                                dates['TDR_Trans'] = dt
                                all_valid_dates.append(dt)
                    
                    if p_type == 'MDR':
                        if '開案' in df_roadmap.columns:
                            dt = parse_quarter_date_end(row['開案'])
                            if pd.isnull(dt): dt = pd.to_datetime(row['開案'], errors='coerce')
                            if pd.notnull(dt):
                                dates['MDR_Start'] = dt
                                all_valid_dates.append(dt)

                    if dates:
                        sorted_points = sorted(dates.items(), key=lambda x: x[1])
                        min_week = get_week_str(sorted_points[0][1])
                        plot_data.append({
                            '專案': row['專案'], 'dates': dates, 'sorted_points': sorted_points, 'min_week': min_week, 'has_data': True, 'type': p_type
                        })

                if plot_data:
                    if all_valid_dates:
                        min_date = min(all_valid_dates)
                        max_date = max(all_valid_dates)
                        start_cursor = min_date - pd.Timedelta(days=min_date.dayofweek) - pd.Timedelta(weeks=4)
                        end_cursor = max_date + pd.Timedelta(weeks=8)
                        sorted_weeks = []
                        curr = start_cursor
                        while curr <= end_cursor:
                            sorted_weeks.append(get_week_str(curr))
                            curr += pd.Timedelta(days=7)
                        seen = set(); sorted_weeks = [x for x in sorted_weeks if not (x in seen or seen.add(x))]
                    else:
                        sorted_weeks = [get_week_str(pd.Timestamp.now().normalize())]

                    type_order = {'MDR': 1, 'NPDR': 2, 'TDR': 3}
                    plot_data.sort(key=lambda x: (type_order.get(x['type'], 4), x['min_week']))
                    
                    fig = go.Figure()
                    
                    y_start = 0
                    current_type = None
                    type_ranges = []
                    
                    for idx, p in enumerate(plot_data):
                        ptype = p['type']
                        if ptype != current_type:
                            if current_type is not None:
                                type_ranges.append({'type': current_type, 'y0': y_start - 0.5, 'y1': idx - 0.5})
                            current_type = ptype
                            y_start = idx
                    if current_type is not None:
                        type_ranges.append({'type': current_type, 'y0': y_start - 0.5, 'y1': len(plot_data) - 0.5})
                        
                    for r in type_ranges:
                        bg_color = 'rgba(255,255,255,0)' 
                        if r['type'] == 'MDR': bg_color = 'rgba(255, 249, 196, 0.3)' 
                        elif r['type'] == 'NPDR': bg_color = 'rgba(235, 245, 251, 0.3)' 
                        elif r['type'] == 'TDR': bg_color = 'rgba(250, 219, 216, 0.3)'
                        
                        fig.add_shape(type="rect", x0=0, x1=1, xref="paper", y0=r['y0'], y1=r['y1'], yref="y", fillcolor=bg_color, layer="below", line_width=0)

                    for p in plot_data:
                        if len(p['sorted_points']) >= 2:
                            for i in range(len(p['sorted_points']) - 1):
                                start_dt = p['sorted_points'][i][1]
                                end_dt = p['sorted_points'][i+1][1]
                                start_node = p['sorted_points'][i][0]
                                end_node = p['sorted_points'][i+1][0]
                                s_week = get_week_str(start_dt)
                                e_week = get_week_str(end_dt)
                                try:
                                    s_idx = sorted_weeks.index(s_week)
                                    e_idx = sorted_weeks.index(e_week)
                                    x_path = sorted_weeks[s_idx : e_idx+1] if s_idx < e_idx else [s_week, e_week]
                                except: x_path = [s_week, e_week]

                                if end_node == 'Order': color = '#2ECC71' 
                                elif end_node == 'EV': color = '#9B59B6' 
                                elif end_node == 'DV': color = '#F39C12' 
                                elif end_node == 'NPDR': color = '#2980B9' 
                                elif end_node == 'TDR_Trans': color = '#D35400' 
                                else: color = '#7F8C8D' 
                                days_rem = (end_dt - pd.Timestamp.now().normalize()).days
                                hover_line = f"<b>{p['專案']}</b><br>{start_node} ➔ {end_node}<br>⏳ 距 {end_node} 剩: {days_rem} 天"
                                fig.add_trace(go.Scatter(x=x_path, y=[p['專案']] * len(x_path), mode='lines', line=dict(color=color, width=6), showlegend=False, hovertext=hover_line, hoverinfo="text"))

                        node_configs = {
                            'MDR_Start': {'c': '#E91E63', 's': 'triangle-up', 'n': 'MDR 開案', 'size': 14},
                            'TDR_Start': {'c': '#D35400', 's': 'triangle-up', 'n': 'TDR 開案', 'size': 14},
                            'TDR_Trans': {'c': '#C0392B', 's': 'pentagon', 'n': '轉 NPDR', 'size': 14},
                            'NPDR': {'c': '#2E86C1', 's': 'circle', 'n': 'NPDR 開案', 'size': 12},
                            'DV': {'c': '#F39C12', 's': 'diamond', 'n': '設計驗證', 'size': 12},
                            'EV': {'c': '#9B59B6', 's': 'square', 'n': '工程驗證', 'size': 12},
                            'Order': {'c': '#27AE60', 's': 'star', 'n': '預計訂單', 'size': 16}
                        }
                        for key, config in node_configs.items():
                            if key in p['dates']:
                                dt = p['dates'][key]
                                diff = (dt - pd.Timestamp.now().normalize()).days
                                status = f"再 {diff} 天" if diff > 0 else f"已過 {abs(diff)} 天"
                                fig.add_trace(go.Scatter(x=[get_week_str(dt)], y=[p['專案']], mode='markers+text' if show_schedules else 'markers', marker=dict(color=config['c'], symbol=config['s'], size=config.get('size', 12), line=dict(width=2, color='white')), text=[dt.strftime('%m-%d')] if show_schedules else "", textposition="bottom center", hovertext=f"<b>{config['n']}</b><br>📅 {dt.strftime('%Y-%m-%d')}<br>({status})", hoverinfo="text", showlegend=False))

                    for key, conf in node_configs.items():
                        fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers', marker=dict(symbol=conf['s'], color=conf['c'], size=10), name=conf['n'], showlegend=True))

                    current_week_str = get_week_str(pd.Timestamp.now().normalize())
                    if current_week_str in sorted_weeks:
                        fig.add_vline(x=current_week_str, line_width=2, line_dash="dash", line_color="#E74C3C")
                        fig.add_annotation(x=current_week_str, y=1.05, yref='paper', text=f"📍 本週 ({current_week_str})", showarrow=False, font=dict(color="#E74C3C", size=12, weight="bold"), bgcolor="rgba(255, 255, 255, 0.9)", bordercolor="#E74C3C", borderwidth=1)

                    fig.update_layout(xaxis=dict(title="時間軸 (週次)", type='category', categoryorder='array', categoryarray=sorted_weeks, tickangle=-45), yaxis=dict(title="專案", autorange="reversed"), height=max(400, 150 + (len(plot_data) * 45)), margin=dict(l=0, r=0, t=80, b=20), hoverlabel=dict(font_size=16, font_family="Arial"), legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5))
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"路徑圖錯誤: {e}")

    st.divider()

    # =========================================================================
    # [區塊 4] & [區塊 5]
    # =========================================================================
    if not df_chart_source.empty:
        with st.expander("📊 圖表分析 (產品類別 & 市場應用) - 點擊展開", expanded=False):
            r2_c1, r2_c2, r2_c3 = st.columns(3)
            
            with r2_c1:
                st.subheader("📌 營收分佈 (Revenue)")
                if total_revenue_twd > 0 and cat_col_name:
                    df_pie_rev = df_chart_source.groupby(cat_col_name).agg(
                        Value=('Calculated_Total_TWD', 'sum'),
                        Projects=('專案', lambda x: ", ".join(sorted([str(i) for i in x.dropna().unique()])))
                    ).reset_index()
                    
                    fig_pie = px.pie(df_pie_rev, values='Value', names=cat_col_name, hole=0.4, custom_data=['Projects'])
                    fig_pie.update_traces(
                        textposition='inside', textinfo='percent+label',
                        hovertemplate="<b>%{label}</b><br>營收: %{value:,.0f}<br>包含專案: %{customdata[0]}"
                    )
                    fig_pie.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0))
                    st.plotly_chart(fig_pie, use_container_width=True)
                else: st.info("無資料")

            with r2_c2:
                st.subheader("💎 毛利分佈 (Profit)")
                if total_profit_twd > 0 and cat_col_name:
                    df_pie_gp = df_chart_source.groupby(cat_col_name).agg(
                        Value=('Calculated_Gross_Profit', 'sum'),
                        Projects=('專案', lambda x: ", ".join(sorted([str(i) for i in x.dropna().unique()])))
                    ).reset_index()

                    fig_pie_gp = px.pie(df_pie_gp, values='Value', names=cat_col_name, hole=0.4, color_discrete_sequence=px.colors.sequential.Greens_r, custom_data=['Projects'])
                    fig_pie_gp.update_traces(
                        textposition='inside', textinfo='percent+label',
                        hovertemplate="<b>%{label}</b><br>毛利: %{value:,.0f}<br>包含專案: %{customdata[0]}"
                    )
                    fig_pie_gp.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0))
                    st.plotly_chart(fig_pie_gp, use_container_width=True)
                else: st.info("無毛利資料")

            with r2_c3:
                st.subheader("🌍 市場應用 (Market)")
                if total_revenue_twd > 0 and '市場' in df_chart_source.columns and '產業應用場景' in df_chart_source.columns:
                    df_market = df_chart_source.groupby(['市場', '產業應用場景'])['Calculated_Total_TWD'].sum().reset_index()
                    fig_market = px.bar(df_market, x='市場', y='Calculated_Total_TWD', color='產業應用場景', barmode='stack', text_auto=',.0f')
                    fig_market.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0))
                    st.plotly_chart(fig_market, use_container_width=True)
                else: st.info("無資料")

    # =========================================================================
    # [區塊 7] 詳細資料檢視
    # =========================================================================
    st.divider()
    st.subheader("📋 詳細資料檢視 (可編輯模式)")
    st.info("💡 提示：您可直接在表格修改，或勾選左側「📝 編輯」開啟詳細編輯視窗。欲刪除資料請勾選「🗑️ 刪除」。")

    display_df = df_chart_source.drop(columns=['Calculated_Total_TWD', 'Parsed_Margin_Rate', 'Calculated_Gross_Profit', 'Calculated_Actual_Total_TWD'], errors='ignore').copy()
    if "🗑️ 刪除" in display_df.columns: display_df.drop(columns=["🗑️ 刪除"], inplace=True)
    if "📝 編輯" in display_df.columns: display_df.drop(columns=["📝 編輯"], inplace=True)
    
    cols_to_stringify = ['專案負責人', '目標規格', '信賴性測試要求', '對標競爭產品', '預估市場規模', '目標客戶1', '目標客戶2', '目標客戶3', '目標客戶4', '目標客戶5', '預計訂單起始點', '專案開發完成時間', '開案時間', '設計驗證時間', '工程驗證時間']
    for c in cols_to_stringify:
        if c in display_df.columns:
            display_df[c] = display_df[c].astype(str).replace('nan', '').replace('NaT', '')
            display_df[c] = display_df[c].str.replace(r'\.0$', '', regex=True)

    display_df.insert(0, "🗑️ 刪除", False)
    display_df.insert(0, "📝 編輯", False)
    
    edited_df = st.data_editor(
        display_df,
        column_config={
            "📝 編輯": st.column_config.CheckboxColumn("編輯", help="勾選以開啟詳細編輯表單", default=False),
            "🗑️ 刪除": st.column_config.CheckboxColumn("刪除", help="勾選以刪除資料", default=False),
            "專案": st.column_config.TextColumn("專案", disabled=True, pinned=True)
        },
        num_rows="dynamic",
        use_container_width=True,
        key="main_data_editor"
    )

    selected_rows = edited_df[edited_df["📝 編輯"] == True]
    if not selected_rows.empty:
        target_index = selected_rows.index[0]
        target_row = selected_rows.iloc[0]
        project_name = target_row.get("專案", "Unknown")
        st.markdown(f"### ✏️ 正在編輯專案：**{project_name}**")
        with st.form(key="detail_edit_form"):
            new_values = {}
            cols = list(display_df.columns)
            for c in ["📝 編輯", "🗑️ 刪除"]:
                if c in cols: cols.remove(c)
            
            text_fields = ['專案負責人', '目標規格', '信賴性測試要求', '對標競爭產品', '預估市場規模', '目標客戶1', '目標客戶2', '目標客戶3', '目標客戶4', '目標客戶5', '專案', '產品類別', '產業應用場景', '開案類別', '市場']
            date_fields = ['預計訂單起始點', '專案開發完成時間', '開案時間', '設計驗證時間', '工程驗證時間']
            col_count = 3
            cols_layout = st.columns(col_count)
            
            for i, col_name in enumerate(cols):
                val = target_row[col_name]
                col_obj = cols_layout[i % col_count]
                if col_name in text_fields:
                    new_values[col_name] = col_obj.text_input(col_name, value=str(val) if pd.notnull(val) and str(val)!='nan' else "")
                elif col_name in date_fields:
                    date_val = None
                    dt = pd.to_datetime(val, errors='coerce')
                    if pd.notnull(dt): date_val = dt.date()
                    else:
                        dt_q = parse_quarter_date_end(val)
                        if pd.notnull(dt_q): date_val = dt_q.date()
                    new_val = col_obj.date_input(col_name, value=date_val)
                    new_values[col_name] = new_val
                else:
                    if pd.notnull(val) and str(val) != 'nan' and str(val) != '':
                        display_val = str(val)
                        if display_val.endswith('.0'): display_val = display_val[:-2]
                    else: display_val = ""
                    new_val_str = col_obj.text_input(col_name, value=display_val, help="請輸入數字")
                    if new_val_str.strip() == "": new_values[col_name] = np.nan
                    else:
                        try: new_values[col_name] = float(new_val_str)
                        except: new_values[col_name] = new_val_str

            submitted = st.form_submit_button("💾 儲存變更", type="primary")
            if submitted:
                for col, new_val in new_values.items():
                    st.session_state['working_df'].at[target_index, col] = new_val
                    if target_index in st.session_state['full_df'].index:
                        st.session_state['full_df'].at[target_index, col] = new_val
                st.session_state['working_df'].at[target_index, "📝 編輯"] = False
                st.toast(f"✅ 專案 {project_name} 資料已更新！", icon="💾")
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    b_col1, b_col2, b_col3, b_col4 = st.columns([1, 1, 1.2, 1.2])
    
    with b_col1:
        if st.button("🔄 更新表格 (Update)", use_container_width=True):
            st.session_state['full_df'].update(edited_df)
            st.rerun()
            
    with b_col2:
        if st.button("🗑️ 刪除勾選 (Delete)", type="primary", use_container_width=True):
            rows = edited_df[edited_df["🗑️ 刪除"]].index
            st.session_state['full_df'] = st.session_state['full_df'].drop(rows)
            st.rerun()
            
    with b_col3:
        csv = st.session_state['full_df'].to_csv(index=False).encode('utf-8-sig')
        st.download_button("💾 完整存檔 (Full)", csv, f"Geckos_{datetime.datetime.now().strftime('%Y%m%d')}.csv", "text/csv", use_container_width=True)
        
    with b_col4:
        df_pm = st.session_state['full_df'].copy()
        cols_to_blank = ['預期毛利率', '預估市場規模', '預估市占率']
        if '預估市佔率' in df_pm.columns: cols_to_blank.append('預估市佔率')
        for c in cols_to_blank:
            if c in df_pm.columns: df_pm[c] = ""
        csv_pm = df_pm.to_csv(index=False).encode('utf-8-sig')
        st.download_button("💾 專案存檔 for PM", csv_pm, f"Geckos_{datetime.datetime.now().strftime('%Y%m%d')}_PM.csv", "text/csv", use_container_width=True)
