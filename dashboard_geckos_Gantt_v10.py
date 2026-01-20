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
    
    candidates_twd = [c for c in df_full.columns if '營收' in c and 'TWD' in c]
    if candidates_twd: col_twd = candidates_twd[0]
    
    candidates_rmb = [c for c in df_full.columns if '營收' in c and 'RMB' in c]
    if candidates_rmb: col_rmb = candidates_rmb[0]
    
    if not col_twd:
        candidates_gen = [c for c in df_full.columns if '營收' in c and c != col_rmb]
        if candidates_gen: col_twd = candidates_gen[0]

    if not col_twd:
        st.error("❌ 找不到「預估營收(TWD)」相關欄位，請檢查 Excel 表頭。")
        st.stop()

    # =========================================================================
    # [全域樣式與變數]
    # =========================================================================
    type_style_map = {
        'NPDR': {'bg': '#EBF5FB', 'border': '#2E86C1', 'text': '#2E86C1'},
        'MDR':  {'bg': '#E8F8F5', 'border': '#17A589', 'text': '#17A589'},
        'TDR':  {'bg': '#FEF9E7', 'border': '#F1C40F', 'text': '#D35400'},
        'default': {'bg': '#F2F3F4', 'border': '#95A5A6', 'text': '#7F8C8D'}
    }
    urgent_style = {'bg': '#FDEDEC', 'border': '#E74C3C', 'text': '#C0392B'}
    past_style = {'bg': '#EAECEE', 'border': '#808B96', 'text': '#566573'}
    
    icon_map = {'NPDR': '🔵', 'DV': '🔶', 'EV': '🟥', 'Order': '🟢'}
    
    # [V69.6 Fix] Define priority lists for columns instead of single value
    cols_priority_npdr = ['NPDR', 'NPDR時間', 'NPDR開案時間', '開案時間', '开案时间']
    cols_priority_dv = ['設計驗證時間', 'DV', 'DV時間', '設計驗證']
    cols_priority_ev = ['工程驗證時間', 'EV', 'EV時間', '工程驗證']
    cols_priority_order = ['預計訂單起始點', 'Order', '預計訂單']
    
    # Helper to find first valid date from a list of columns for a row
    def get_first_valid_date(row, cols_list):
        for c in cols_list:
            if c in row.index:
                val = row[c]
                dt = parse_quarter_date_end(val)
                if pd.isnull(dt): dt = pd.to_datetime(val, errors='coerce')
                if pd.notnull(dt): return dt
        return pd.NaT

    # Determine start_col just for reference/Block 8 (use the first available one)
    start_col = '開案時間'
    for c in cols_priority_npdr:
        if c in df_full.columns:
            start_col = c
            break
            
    col_map_alerts = {'NPDR': start_col, 'DV': '設計驗證時間', 'EV': '工程驗證時間', 'Order': '預計訂單起始點'}

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

    val_twd = df_chart_source[col_twd].fillna(0)
    val_rmb = df_chart_source[col_rmb].fillna(0) if col_rmb else 0
    df_chart_source['Calculated_Total_TWD'] = val_twd + (val_rmb * rmb_rate)
    
    total_revenue_twd = df_chart_source['Calculated_Total_TWD'].sum()
    project_count_unique = df_chart_source['專案'].nunique()

    # =========================================================================
    # [區塊 2] KPI Metrics
    # =========================================================================
    st.divider()
    
    if not df_chart_source.empty:
        df_grouped = df_chart_source.groupby('專案')['Calculated_Total_TWD'].sum()
        top_project_name = df_grouped.idxmax()
        top_project_rev = df_grouped.max()
        top_contributor_text = top_project_name
    else:
        top_contributor_text = "無資料"
        top_project_rev = 0

    col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
    
    with col_kpi1:
        st.metric(label=f"💰 預估總營收 (TWD) - 匯率 {rmb_rate}", value=f"{total_revenue_twd:,.0f}")

    with col_kpi2:
        st.metric(label="👑 營收貢獻王 (含RMB)", value=top_contributor_text, delta=f"TWD {top_project_rev:,.0f}")

    with col_kpi3:
        if not df_chart_source.empty:
            df_unique_proj = df_chart_source.drop_duplicates(subset=['專案'])
            if '開案類別' in df_unique_proj.columns:
                type_counts = df_unique_proj['開案類別'].value_counts().reset_index()
                type_counts.columns = ['Type', 'Count']
                
                pro_colors = ['#2C3E50', '#5D6D7E', '#85929E', '#34495E', '#AAB7B8', '#D5DBDB']
                
                st.markdown(f"#### 🍩 總專案數: {project_count_unique}")
                
                fig_donut = go.Figure()
                fig_donut.add_trace(go.Pie(
                    labels=type_counts['Type'], values=type_counts['Count'], hole=0.75,
                    textinfo='label+value', textposition='inside',
                    insidetextorientation='horizontal',
                    insidetextfont=dict(color='white', size=12, weight='bold'),
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
                    annotations=[dict(
                        text=str(project_count_unique), 
                        x=0.5, y=0.5, 
                        font=dict(size=50, color='white', weight='bold'),
                        showarrow=False
                    )],
                    margin=dict(t=0, b=0, l=10, r=10), 
                    height=200, 
                    showlegend=False
                )
                st.plotly_chart(fig_donut, use_container_width=True)
            else:
                st.info("無 '開案類別'")

    st.divider()

    # =========================================================================
    # [區塊 8] 重點提醒
    # =========================================================================
    if not df_chart_source.empty:
        now = pd.Timestamp.now().normalize()
        start_week_date = now - pd.Timedelta(days=now.dayofweek)
        end_week_date = start_week_date + pd.Timedelta(days=6)
        last_week_start = start_week_date - pd.Timedelta(days=7)
        last_week_end = start_week_date - pd.Timedelta(days=1)
        
        df_alerts = df_chart_source.drop_duplicates(subset=['專案'])
        last_week_items, this_week_items, month_items = [], [], []
        
        for idx, row in df_alerts.iterrows():
            p_type = row.get('開案類別', 'default')
            style = type_style_map.get(p_type, type_style_map['default'])
            pm_name = row.get('專案負責人', '')
            pm_str = f"(PM: {pm_name})" if pd.notnull(pm_name) else ""
            
            # [V69.6] Enhanced Alert Logic using Priority Columns
            check_cols = {'NPDR': cols_priority_npdr, 'DV': cols_priority_dv, 'EV': cols_priority_ev, 'Order': cols_priority_order}
            
            # Type specific adjustments for alerts
            if p_type == 'TDR':
                if '開案' in df_alerts.columns: check_cols['TDR開案'] = ['開案']
                if '轉NPDR時間' in df_alerts.columns: check_cols['轉NPDR'] = ['轉NPDR時間']
            elif p_type == 'MDR':
                if '開案' in df_alerts.columns: check_cols['MDR開案'] = ['開案']

            for key, col_list in check_cols.items():
                dt = get_first_valid_date(row, col_list)
                
                if pd.notnull(dt):
                    days_diff = (dt - now).days
                    
                    if last_week_start <= dt <= last_week_end:
                        last_week_items.append({'dt': dt, 'html': f"<div style='background:{past_style['bg']};border-left:5px solid {past_style['border']};padding:8px;margin:6px;border-radius:4px'><div style='font-size:0.8em;font-weight:bold;color:{past_style['text']}'>{p_type} (已完成)</div><div style='color:{past_style['text']};font-size:0.9em'><b>{row['專案']}</b> {pm_str}<br>{key} | {dt.strftime('%m-%d')}</div></div>"})
                    
                    if start_week_date <= dt <= end_week_date:
                        status = "(已過)" if days_diff < 0 else ("(今天)" if days_diff==0 else f"(剩 {days_diff} 天)")
                        bg = style['bg'] if days_diff >= 0 else past_style['bg']
                        border = style['border'] if days_diff >= 0 else past_style['border']
                        txt = style['text'] if days_diff >= 0 else past_style['text']
                        this_week_items.append({'dt': dt, 'html': f"<div style='background:{bg};border-left:5px solid {border};padding:8px;margin:6px;border-radius:4px'><div style='font-size:0.8em;font-weight:bold;color:{txt}'>{p_type}</div><div style='color:#333;font-size:0.9em'><b>{row['專案']}</b> {pm_str}<br>{key} | {dt.strftime('%m-%d')} {status}</div></div>"})
                    
                    if dt.year == now.year and dt.month == now.month:
                        month_items.append({'dt': dt, 'days_diff': days_diff, 'p_type': p_type, 'pm': pm_str, 'key': key, 'proj': row['專案'], 'style': style})

        with st.expander("🔔 專案重點時程 (Milestone Alerts)", expanded=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("#### ⏮️ 上週重點")
                if last_week_items:
                    for i in sorted(last_week_items, key=lambda x:x['dt']): st.markdown(i['html'], unsafe_allow_html=True)
                else: st.info("無紀錄")
            with c2:
                st.markdown("#### 🔥 本週重點")
                if this_week_items:
                    for i in sorted(this_week_items, key=lambda x:x['dt']): st.markdown(i['html'], unsafe_allow_html=True)
                else: st.success("無事項")
            with c3:
                ch1, ch2 = st.columns([2, 1])
                with ch1: st.markdown("#### 🗓️ 本月重點")
                with ch2: show_past = st.checkbox("顯示已過期", value=False)
                
                if month_items:
                    sorted_month = sorted(month_items, key=lambda x:x['dt'])
                    cnt = 0
                    for item in sorted_month:
                        if item['days_diff'] < 0 and not show_past: continue
                        cnt+=1
                        bg = item['style']['bg'] if item['days_diff'] >= 0 else "#F2F3F4"
                        border = item['style']['border'] if item['days_diff'] >= 0 else "#999"
                        txt = item['style']['text'] if item['days_diff'] >= 0 else "#999"
                        status = "(已過)" if item['days_diff'] < 0 else f"(剩 {item['days_diff']} 天)"
                        st.markdown(f"<div style='background:{bg};border-left:5px solid {border};padding:8px;margin:6px;border-radius:4px'><div style='font-size:0.8em;font-weight:bold;color:{txt}'>{item['p_type']}</div><div style='color:#333;font-size:0.9em'><b>{item['proj']}</b> {item['pm']}<br>{item['key']} | {item['dt'].strftime('%m-%d')} {status}</div></div>", unsafe_allow_html=True)
                    if cnt==0: st.info("無即將到來事項")
                else: st.info("無事項")

    # =========================================================================
    # [區塊 9] 專案負責人工作儀表板
    # =========================================================================
    if not df_chart_source.empty:
        st.divider()
        st.subheader("👥 專案負責人工作儀表板")
        
        now = pd.Timestamp.now().normalize()
        
        for pm in unique_pms:
            pm_projects = df_chart_source[df_chart_source['專案負責人_display'] == pm].drop_duplicates(subset=['專案'])
            if not pm_projects.empty:
                with st.expander(f"👤 {pm} ({len(pm_projects)})", expanded=False):
                    cols = st.columns(3)
                    for i, (idx, row) in enumerate(pm_projects.iterrows()):
                        p_type = row.get('開案類別', 'default')
                        style = type_style_map.get(p_type, type_style_map['default'])
                        
                        # Define names for display logic
                        if p_type == 'TDR':
                            names = {'TDR_Start': 'TDR開案', 'TDR_Trans': '轉NPDR', 'NPDR': 'NPDR開案', 'DV': 'DV', 'EV': 'EV', 'Order': 'Order'}
                            check_list = {'TDR_Start': ['開案'], 'TDR_Trans': ['轉NPDR時間'], 'NPDR': cols_priority_npdr, 'DV': cols_priority_dv, 'EV': cols_priority_ev, 'Order': cols_priority_order}
                        else:
                            names = {'NPDR': 'NPDR開案', 'DV': 'DV', 'EV': 'EV', 'Order': 'Order'}
                            check_list = {'NPDR': cols_priority_npdr, 'DV': cols_priority_dv, 'EV': cols_priority_ev, 'Order': cols_priority_order}
                        
                        next_stage = None
                        min_days = float('inf')
                        
                        for stage_key, col_list in check_list.items():
                            dt = get_first_valid_date(row, col_list)
                            if pd.notnull(dt):
                                dd = (dt - now).days
                                if dd >= 0 and dd < min_days:
                                    min_days = dd
                                    next_stage = {'name': names.get(stage_key, stage_key), 'date': dt.strftime('%Y-%m-%d')}
                        
                        status_text = f"🔜 {next_stage['name']}<br>{next_stage['date']} (剩 {min_days} 天)" if next_stage else "✅ 階段完成 / 未設定"
                        border_color = '#E74C3C' if next_stage and min_days < 7 else style['border']
                        
                        html = f"""
                        <div style="background-color: {style['bg']}; 
                                    border-top: 5px solid {border_color}; 
                                    padding: 10px; margin: 5px; 
                                    box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
                                    height: 100%;">
                            <div style="font-weight:bold; color:{style['text']}">{p_type}</div>
                            <div style="font-weight:bold; font-size:1.1em; margin: 4px 0; color: #333333;">{row['專案']}</div>
                            <div style="font-size:0.9em; color:#555">{status_text}</div>
                        </div>
                        """
                        with cols[i % 3]:
                            st.markdown(html, unsafe_allow_html=True)

    st.divider()

    # =========================================================================
    # [區塊 3] 專案研發全週期路徑圖 (V69.6: Smart Column Detection + Full Timeline)
    # =========================================================================
    current_types = open_type_filter if open_type_filter else ["全部"]
    type_label = ", ".join(current_types)
    
    with st.expander(f"🚀 專案研發全週期路徑圖 (Roadmap) - 類別: [{type_label}]", expanded=False):
        c_opts_1, c_opts_2 = st.columns([1, 1])
        with c_opts_1:
            show_schedules = st.checkbox("👁️ 顯示所有節點時程 (Show All Node Schedules)", value=False)
        with c_opts_2:
            show_tdr_order = st.checkbox("顯示 TDR 預計訂單節點", value=False)
        
        if not df_chart_source.empty:
            try:
                plot_data = []
                df_roadmap = df_chart_source.drop_duplicates(subset=['專案'])
                
                # [V69.6 Fix] Collect all valid dates for continuous timeline
                all_valid_dates = []
                current_date = pd.Timestamp.now().normalize()
                all_valid_dates.append(current_date)

                for idx, row in df_roadmap.iterrows():
                    p_type = row.get('開案類別', '')
                    dates = {}
                    
                    # [V69.6 Fix] Smart Detection for Standard Nodes (Any Type)
                    # Check NPDR
                    dt_npdr = get_first_valid_date(row, cols_priority_npdr)
                    if pd.notnull(dt_npdr):
                        dates['NPDR'] = dt_npdr
                        all_valid_dates.append(dt_npdr)
                    
                    # Check DV
                    dt_dv = get_first_valid_date(row, cols_priority_dv)
                    if pd.notnull(dt_dv):
                        dates['DV'] = dt_dv
                        all_valid_dates.append(dt_dv)

                    # Check EV
                    dt_ev = get_first_valid_date(row, cols_priority_ev)
                    if pd.notnull(dt_ev):
                        dates['EV'] = dt_ev
                        all_valid_dates.append(dt_ev)

                    # Check Order
                    dt_order = get_first_valid_date(row, cols_priority_order)
                    if pd.notnull(dt_order):
                        # TDR Order Toggle Check
                        if not (p_type == 'TDR' and not show_tdr_order):
                            dates['Order'] = dt_order
                            all_valid_dates.append(dt_order)
                    
                    # Type Specifics
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
                            '專案': row['專案'], 
                            'dates': dates, 
                            'sorted_points': sorted_points, 
                            'min_week': min_week,
                            'has_data': True
                        })

                if plot_data:
                    # [V69.6 Fix] Robust Continuous Timeline Generation (Monday Alignment)
                    if all_valid_dates:
                        min_date = min(all_valid_dates)
                        max_date = max(all_valid_dates)
                        
                        # Align start to previous Monday
                        start_cursor = min_date - pd.Timedelta(days=min_date.dayofweek) - pd.Timedelta(weeks=4)
                        end_cursor = max_date + pd.Timedelta(weeks=8)
                        
                        sorted_weeks = []
                        curr = start_cursor
                        while curr <= end_cursor:
                            sorted_weeks.append(get_week_str(curr))
                            curr += pd.Timedelta(days=7)
                        
                        # Deduplicate
                        seen = set()
                        sorted_weeks = [x for x in sorted_weeks if not (x in seen or seen.add(x))]
                    else:
                        sorted_weeks = [get_week_str(current_date)]

                    plot_data.sort(key=lambda x: x['min_week'])
                    
                    fig = go.Figure()

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
                                
                                days_rem = (end_dt - current_date).days
                                hover_line = f"<b>{p['專案']}</b><br>{start_node} ➔ {end_node}<br>⏳ 距 {end_node} 剩: {days_rem} 天"

                                fig.add_trace(go.Scatter(
                                    x=x_path, y=[p['專案']] * len(x_path), 
                                    mode='lines', 
                                    line=dict(color=color, width=6), 
                                    showlegend=False, 
                                    hovertext=hover_line,
                                    hoverinfo="text"
                                ))

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
                                diff = (dt - current_date).days
                                status = f"再 {diff} 天" if diff > 0 else f"已過 {abs(diff)} 天"
                                
                                fig.add_trace(go.Scatter(
                                    x=[get_week_str(dt)], y=[p['專案']], 
                                    mode='markers+text' if show_schedules else 'markers',
                                    marker=dict(color=config['c'], symbol=config['s'], size=config.get('size', 12), line=dict(width=2, color='white')),
                                    text=[dt.strftime('%m-%d')] if show_schedules else "", textposition="bottom center",
                                    hovertext=f"<b>{config['n']}</b><br>📅 {dt.strftime('%Y-%m-%d')}<br>({status})", 
                                    hoverinfo="text", showlegend=False
                                ))

                    for key, conf in node_configs.items():
                        fig.add_trace(go.Scatter(
                            x=[None], y=[None], mode='markers',
                            marker=dict(symbol=conf['s'], color=conf['c'], size=10),
                            name=conf['n'], showlegend=True
                        ))

                    current_week_str = get_week_str(current_date)
                    if current_week_str in sorted_weeks:
                        fig.add_vline(x=current_week_str, line_width=2, line_dash="dash", line_color="#E74C3C")
                        fig.add_annotation(x=current_week_str, y=1.05, yref='paper', text=f"📍 本週 ({current_week_str})", showarrow=False, font=dict(color="#E74C3C", size=12, weight="bold"), bgcolor="rgba(255, 255, 255, 0.9)", bordercolor="#E74C3C", borderwidth=1)

                    fig.update_layout(
                        xaxis=dict(title="時間軸 (週次)", type='category', categoryorder='array', categoryarray=sorted_weeks, tickangle=-45), 
                        yaxis=dict(title="專案", autorange="reversed"), 
                        height=max(400, 150 + (len(plot_data) * 45)), 
                        margin=dict(l=0, r=0, t=80, b=20),
                        hoverlabel=dict(font_size=16, font_family="Arial"),
                        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5)
                    )
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"路徑圖錯誤: {e}")

    st.divider()

    # =========================================================================
    # [區塊 6] 營收 Top 10 專案 (含 PM 篩選)
    # =========================================================================
    with st.expander("🏆 營收 Top 10 專案 (含 PM 篩選)", expanded=True):
        if total_revenue_twd > 0:
            b6_col_sel, b6_col_metric = st.columns([1, 2])
            with b6_col_sel:
                pm_sel_b6 = st.selectbox("👤 篩選負責人 (由此查看個別營收)", ["全部 (All)"] + list(unique_pms))
            
            if pm_sel_b6 == "全部 (All)": df_b6 = df_chart_source.copy()
            else: df_b6 = df_chart_source[df_chart_source['專案負責人_display'] == pm_sel_b6]
            
            local_rev = df_b6['Calculated_Total_TWD'].sum()
            with b6_col_metric: st.metric(label=f"💰 預估總營收 (TWD) - {pm_sel_b6}", value=f"{local_rev:,.0f}")

            if not df_b6.empty:
                df_chart = df_b6.groupby('專案')['Calculated_Total_TWD'].sum().reset_index()
                df_chart = df_chart.nlargest(10, 'Calculated_Total_TWD').sort_values('Calculated_Total_TWD', ascending=True)
                fig_bar = px.bar(df_chart, x='Calculated_Total_TWD', y='專案', orientation='h', text_auto=',.0f', color='Calculated_Total_TWD', color_continuous_scale='Blues')
                fig_bar.update_layout(xaxis_title="預估營收 (含RMB換算)", yaxis_title="專案")
                st.plotly_chart(fig_bar, use_container_width=True)
            else: st.warning("此負責人無營收資料")
        else: st.info("無營收數據")

    st.divider()

    # =========================================================================
    # [區塊 10] 預計訂單 Top 10
    # =========================================================================
    with st.expander("⏳ 預計訂單即將到期 Top 10", expanded=True):
        if '預計訂單起始點' in df_chart_source.columns:
            cols_to_keep = ['專案', '預計訂單起始點', col_twd]
            if col_rmb: cols_to_keep.append(col_rmb)
            if '專案負責人' in df_chart_source.columns: cols_to_keep.append('專案負責人')
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
                        return f"{row['專案']} ({pm})" if pd.notnull(pm) else row['專案']
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
                    fig_time.add_trace(go.Bar(x=df_plot['Plot_Value'], y=df_plot['Y_Label'], orientation='h', marker_color=df_plot['Color'], text=final_bar_text, textposition=final_bar_pos, name='Days', hoverinfo='y+text'))
                    fig_time.add_trace(go.Scatter(x=df_plot['Plot_Value'], y=df_plot['Y_Label'], mode='text', text=final_scatter_text, textposition='middle right', textfont=dict(color='#333333', size=13), showlegend=False, cliponaxis=False))
                    
                    today_str = now.strftime('%Y-%m-%d')
                    fig_time.add_vline(x=0, line_width=2, line_dash="dash", line_color="#E74C3C")
                    fig_time.add_annotation(x=0, y=1.02, yref='paper', text=f"📍 本日 ({today_str})", showarrow=False, font=dict(color="#E74C3C", weight="bold"), bgcolor="rgba(255,255,255,0.8)")
                    
                    range_max = max_val * 1.35 if max_val > 0 else 10
                    fig_time.update_layout(title='🚨 專案到期日戰情室', xaxis=dict(zeroline=True, zerolinecolor='#E74C3C', range=[0, range_max]), height=max(400, 100 + (len(df_plot) * 40)), margin=dict(r=150, t=80))
                    st.plotly_chart(fig_time, use_container_width=True)
            else: st.info("無有效日期")

    # =========================================================================
    # [區塊 4] & [區塊 5]
    # =========================================================================
    if not df_chart_source.empty:
        with st.expander("📊 圖表分析 (產品類別 & 市場應用) - 點擊展開", expanded=False):
            row2_col1, row2_col2 = st.columns(2)
            with row2_col1:
                st.subheader("📌 各產品類別營收分佈")
                if total_revenue_twd > 0 and cat_col_name:
                    fig_pie = px.pie(df_chart_source, values='Calculated_Total_TWD', names=cat_col_name, hole=0.4, title=f'各{cat_col_name}營收分佈 (含RMB)')
                    fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                    fig_pie.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.1))
                    st.plotly_chart(fig_pie, use_container_width=True)
                elif not cat_col_name: st.info("無 '產品類別'")
                else: st.info("營收總和為 0")

            with row2_col2:
                st.subheader("🌍 市場 x 應用場景")
                if total_revenue_twd > 0 and '市場' in df_chart_source.columns and '產業應用場景' in df_chart_source.columns:
                    df_market = df_chart_source.groupby(['市場', '產業應用場景'])['Calculated_Total_TWD'].sum().reset_index()
                    fig_market = px.bar(df_market, x='市場', y='Calculated_Total_TWD', color='產業應用場景', barmode='stack', text_auto=',.0f', title='各地區市場應用 (含RMB)')
                    st.plotly_chart(fig_market, use_container_width=True)
                elif '市場' not in df_chart_source.columns: st.info("缺少 '市場' 欄位")
                else: st.info("無營收數據")

    # =========================================================================
    # [區塊 7] 詳細資料檢視 (V69.0: Optimized Buttons)
    # =========================================================================
    st.divider()
    st.subheader("📋 詳細資料檢視 (可編輯模式)")
    st.info("💡 提示：您可直接在表格修改，或勾選左側「📝 編輯」開啟詳細編輯視窗。欲刪除資料請勾選「🗑️ 刪除」。")

    display_df = df_chart_source.drop(columns=['Calculated_Total_TWD'], errors='ignore').copy()
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

    # [V69.0 Change: 4-Column Flat Layout]
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
