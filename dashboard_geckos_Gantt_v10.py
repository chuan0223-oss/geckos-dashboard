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
    """將 '2026Q2' 轉為該季的【最後一天】 (例如 2026-06-30)"""
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
    # [區塊 1] 篩選條件 (V65.1: 修正縮排 Bug)
    # =========================================================================
    st.sidebar.header("🔍 專案篩選器")
    
    # --- 1. 核心篩選 ---
    st.sidebar.markdown("### 🎯 核心鎖定")
    
    # 專案負責人
    pm_col = '專案負責人'
    pm_options = sorted(df_full[pm_col].unique().astype(str)) if pm_col in df_full.columns else []
    pm_options = [x for x in pm_options if x.lower() != 'nan' and x.strip() != '']
    pm_filter = st.sidebar.multiselect("👤 專案負責人 (PM)", options=pm_options)

    # 專案名稱
    project_options = df_full['專案'].unique() if '專案' in df_full.columns else []
    project_filter = st.sidebar.multiselect("🏷️ 專案名稱", options=project_options)

    # --- 2. 類別與屬性 ---
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

    # --- 3. 市場與時程 ---
    market_filter = []
    order_start_filter = []
    order_col = '預計訂單起始點'

    with st.sidebar.expander("🌍 市場與時程", expanded=False):
        market_filter = st.multiselect("目標市場", options=df_full['市場'].unique()) if '市場' in df_full.columns else []
        order_start_filter = st.multiselect("預計訂單時間 (Quarter)", options=sorted(df_full[order_col].astype(str).unique())) if order_col in df_full.columns else []
    
    # --- 4. 全域設定 ---
    st.sidebar.divider()
    st.sidebar.markdown("### ⚙️ 參數設定")
    rmb_rate = st.sidebar.number_input("💱 RMB 換 TWD 匯率", value=4.4, step=0.01, format="%.2f")

    # --- 執行篩選邏輯 ---
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

    # --- Session State ---
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

    # --- 計算顯示用的欄位 ---
    val_twd = df_chart_source[col_twd].fillna(0)
    val_rmb = df_chart_source[col_rmb].fillna(0) if col_rmb else 0
    df_chart_source['Calculated_Total_TWD'] = val_twd + (val_rmb * rmb_rate)
    
    total_revenue_twd = df_chart_source['Calculated_Total_TWD'].sum()
    project_count_unique = df_chart_source['專案'].nunique()

    # =========================================================================
    # [區塊 2] KPI Metrics
    # =========================================================================
    st.divider()
    
    if not df_chart_source.empty and total_revenue_twd > 0:
        df_grouped = df_chart_source.groupby('專案')['Calculated_Total_TWD'].sum()
        top_project_name = df_grouped.idxmax()
        top_project_rev = df_grouped.max()
        top_contributor_text = top_project_name
    else:
        top_contributor_text = "無資料"
        top_project_rev = 0

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric(label=f"💰 預估總營收 (TWD) - 匯率 {rmb_rate}", value=f"{total_revenue_twd:,.0f}")
    kpi2.metric(label="👑 營收貢獻王 (含RMB換算)", value=top_contributor_text, delta=f"{top_project_rev:,.0f}")
    kpi3.metric(label="📊 篩選後專案數 (Unique)", value=project_count_unique)

    st.divider()

    # =========================================================================
    # [區塊 8] 本週/本月重點提醒 (Milestone Alerts)
    # =========================================================================
    if not df_chart_source.empty:
        now = pd.Timestamp.now().normalize()
        start_week = now - pd.Timedelta(days=now.dayofweek)
        end_week = start_week + pd.Timedelta(days=6)
        current_month = now.month
        current_year = now.year

        df_alerts = df_chart_source.drop_duplicates(subset=['專案'])
        
        start_col = None
        possible_start_cols = ['開案時間', '开案时间', 'NPDR開案時間', 'NPDR开案时间', 'NPDR']
        for col in possible_start_cols:
            if col in df_alerts.columns:
                start_col = col
                break
        if not start_col: start_col = '開案時間'

        icon_map = {'NPDR': '🔵', 'DV': '🔶', 'EV': '🟥', 'Order': '🟢'}
        col_map_alerts = {'NPDR': start_col, 'DV': '設計驗證時間', 'EV': '工程驗證時間', 'Order': '預計訂單起始點'}
        stage_name_display = {'NPDR': 'NPDR開案', 'DV': '設計驗證(DV)', 'EV': '工程驗證(EV)', 'Order': '預計訂單(Order)'}
        
        type_style_map = {
            'NPDR': {'bg': '#EBF5FB', 'border': '#2E86C1'},
            'MDR':  {'bg': '#E8F8F5', 'border': '#17A589'},
            'TDR':  {'bg': '#FEF9E7', 'border': '#F1C40F'},
            'default': {'bg': '#F2F3F4', 'border': '#95A5A6'}
        }
        urgent_style = {'bg': '#FDEDEC', 'border': '#E74C3C', 'text': '#C0392B'}

        week_items = []
        month_items = []

        for idx, row in df_alerts.iterrows():
            p_type = row.get('開案類別', 'default')
            if pd.isna(p_type) or p_type not in type_style_map:
                month_style = type_style_map['default']
                p_type_display = p_type if pd.notnull(p_type) else "Unknown"
            else:
                month_style = type_style_map[p_type]
                p_type_display = p_type
            
            pm_name = row.get('專案負責人', '')
            pm_str = f"(👤 PM: {pm_name})" if pd.notnull(pm_name) and str(pm_name).strip() != '' else ""

            for key, col_name in col_map_alerts.items():
                if col_name in df_alerts.columns:
                    raw_val = row[col_name]
                    # V56 Fix
                    dt = parse_quarter_date_end(raw_val)
                    if pd.isnull(dt):
                        dt = pd.to_datetime(raw_val, errors='coerce')
                    
                    if pd.notnull(dt):
                        icon = icon_map.get(key, '⚪')
                        display_name = stage_name_display.get(key, key)
                        days_diff = (dt - now).days
                        
                        if start_week <= dt <= end_week:
                            if days_diff < 0:
                                count_down_str = "(已完成)"
                                content_style = "color: #999999;" 
                            else:
                                count_down_str = "(今天)" if days_diff == 0 else f"(剩餘 {days_diff} 天)"
                                content_style = f"color: {urgent_style['text']};"

                            card_html = f"""
                            <div style="
                                background-color: {urgent_style['bg']};
                                border-left: 5px solid {urgent_style['border']};
                                padding: 10px;
                                margin-bottom: 8px;
                                border-radius: 4px;
                                box-shadow: 1px 1px 3px rgba(0,0,0,0.1);
                            ">
                                <div style="font-size: 0.85em; font-weight: bold; color: {urgent_style['text']}; margin-bottom: 4px;">
                                    {p_type_display} (Urgent)
                                </div>
                                <div style="{content_style}">
                                    {icon} <b>{row['專案']}</b> <span style="font-size:0.9em; opacity:0.8;">{pm_str}</span> - {display_name} | {dt.strftime('%Y-%m-%d')} {count_down_str}
                                </div>
                            </div>
                            """
                            week_items.append({'dt': dt, 'html': card_html})
                        
                        if dt.year == current_year and dt.month == current_month:
                            if days_diff < 0:
                                count_down_str = "(已完成)"
                                content_style = "color: #999999;" 
                            else:
                                count_down_str = "(今天)" if days_diff == 0 else f"(剩餘 {days_diff} 天)"
                                content_style = "color: #333333;"

                            card_html = f"""
                            <div style="
                                background-color: {month_style['bg']};
                                border-left: 5px solid {month_style['border']};
                                padding: 10px;
                                margin-bottom: 8px;
                                border-radius: 4px;
                                box-shadow: 1px 1px 3px rgba(0,0,0,0.1);
                            ">
                                <div style="font-size: 0.85em; font-weight: bold; color: {month_style['border']}; margin-bottom: 4px;">
                                    {p_type_display}
                                </div>
                                <div style="{content_style}">
                                    {icon} <b>{row['專案']}</b> <span style="font-size:0.9em; opacity:0.8;">{pm_str}</span> - {display_name} | {dt.strftime('%Y-%m-%d')} {count_down_str}
                                </div>
                            </div>
                            """
                            month_items.append({'dt': dt, 'html': card_html})

        week_items.sort(key=lambda x: x['dt'])
        month_items.sort(key=lambda x: x['dt'])

        if week_items or month_items:
            with st.expander("🔔 本週/本月重點提醒 (Milestone Alerts)", expanded=True):
                c1, c2 = st.columns(2)
                with c1:
                    with st.container(border=True):
                        st.markdown(f"<h3 style='color:#E74C3C;'>🔥 本週重點 (Urgent)</h3>", unsafe_allow_html=True)
                        if week_items:
                            for item in week_items: st.markdown(item['html'], unsafe_allow_html=True)
                        else:
                            st.success("✅ 本週無重點事項")
                with c2:
                    with st.container(border=True):
                        st.markdown(f"<h3 style='color:#2E86C1;'>🗓️ 本月重點 (Upcoming)</h3>", unsafe_allow_html=True)
                        if month_items:
                            for item in month_items: st.markdown(item['html'], unsafe_allow_html=True)
                        else:
                            st.info("ℹ️ 本月無重點事項")

    # =========================================================================
    # [區塊 9] 專案負責人工作儀表板
    # =========================================================================
    if not df_chart_source.empty:
        st.subheader("👥 專案負責人工作儀表板 (PM Workload Dashboard)")
        
        if '專案負責人' in df_chart_source.columns:
            df_chart_source['專案負責人_display'] = df_chart_source['專案負責人'].apply(lambda x: x if pd.notnull(x) and str(x).strip() != '' else "未指派 (Unassigned)")
            unique_pms = sorted(df_chart_source['專案負責人_display'].unique())
            
            type_style_map_pm = {
                'NPDR': {'bg': '#EBF5FB', 'border': '#2E86C1'},
                'MDR':  {'bg': '#E8F8F5', 'border': '#17A589'},
                'TDR':  {'bg': '#FEF9E7', 'border': '#F1C40F'},
                'default': {'bg': '#F2F3F4', 'border': '#95A5A6'}
            }
            
            pm_col_map = {'NPDR': start_col, 'DV': '設計驗證時間', 'EV': '工程驗證時間', 'Order': '預計訂單起始點'}
            pm_stage_name = {'NPDR': 'NPDR開案', 'DV': 'DV', 'EV': 'EV', 'Order': 'Order'}

            now = pd.Timestamp.now().normalize()

            for pm in unique_pms:
                pm_projects = df_chart_source[df_chart_source['專案負責人_display'] == pm].drop_duplicates(subset=['專案'])
                proj_count = len(pm_projects)
                
                with st.expander(f"👤 {pm} (手上專案數：{proj_count})", expanded=False):
                    if not pm_projects.empty:
                        pm_cards = []
                        for idx, row in pm_projects.iterrows():
                            p_type = row.get('開案類別', 'default')
                            if pd.isna(p_type) or p_type not in type_style_map_pm:
                                style = type_style_map_pm['default']
                                p_type_display = p_type if pd.notnull(p_type) else "?"
                            else:
                                style = type_style_map_pm[p_type]
                                p_type_display = p_type
                            
                            next_stage = None
                            min_days = float('inf')
                            for stage_code, col_name in pm_col_map.items():
                                if col_name in pm_projects.columns:
                                    raw_val = row[col_name]
                                    dt = parse_quarter_date_end(raw_val)
                                    if pd.isnull(dt): dt = pd.to_datetime(raw_val, errors='coerce')
                                    if pd.notnull(dt):
                                        diff = (dt - now).days
                                        if diff >= 0 and diff < min_days:
                                            min_days = diff
                                            next_stage = {'name': pm_stage_name[stage_code], 'date': dt.strftime('%Y-%m-%d'), 'days': diff}
                            
                            status_text = f"🔜 下一階段: {next_stage['name']}<br>📅 {next_stage['date']} (剩 {next_stage['days']} 天)" if next_stage else "✅ 所有階段已完成 (或未設定)"
                            if next_stage and next_stage['days'] < 7: status_text = "🔥 " + status_text
                            
                            border_color = '#E74C3C' if next_stage and next_stage['days'] < 7 else style['border']
                            pm_cards.append({'days': min_days if next_stage else 9999, 'html': f"<div style='background:{style['bg']};border-top:5px solid {border_color};padding:10px;margin:5px;box-shadow:0 2px 4px rgba(0,0,0,0.1);height:100%'><b>{p_type_display}</b><br><b>{row['專案']}</b><br><small>{status_text}</small></div>"})
                        
                        pm_cards.sort(key=lambda x: x['days'])
                        cols = st.columns(3)
                        for i, card in enumerate(pm_cards):
                            with cols[i % 3]: st.markdown(card['html'], unsafe_allow_html=True)
                    else:
                        st.info("此 PM 目前無專案")

    st.divider()

    # =========================================================================
    # [區塊 3] 專案研發全週期路徑圖 (Roadmap)
    # =========================================================================
    # [V64.5 Fix]: 定義 current_types 避免 NameError
    current_types = open_type_filter if open_type_filter else ["全部"]
    type_label = ", ".join(current_types)
    st.subheader(f"🚀 專案研發全週期路徑圖 (Roadmap) - 類別: [{type_label}]")
    
    show_schedules = st.checkbox("👁️ 顯示所有節點時程 (Show All Node Schedules)", value=False)
    
    if not df_chart_source.empty:
        try:
            plot_data = []
            
            df_roadmap_unique = df_chart_source.drop_duplicates(subset=['專案'])
            
            start_col = None
            possible_start_cols = ['開案時間', '开案时间', 'NPDR開案時間', 'NPDR开案时间', 'NPDR']
            for col in possible_start_cols:
                if col in df_roadmap_unique.columns:
                    start_col = col
                    break
            if not start_col: start_col = '開案時間'

            col_map = {'NPDR': start_col, 'DV': '設計驗證時間', 'EV': '工程驗證時間', 'Order': '預計訂單起始點'}
            available_cols = {k: v for k, v in col_map.items() if v in df_roadmap_unique.columns}
            
            all_active_weeks = set() 
            current_date = pd.Timestamp.now().normalize()
            current_week_str = get_week_str(current_date)
            all_active_weeks.add(current_week_str) 

            if available_cols:
                for idx, row in df_roadmap_unique.iterrows():
                    dates = {}
                    for key in ['NPDR', 'DV', 'EV']:
                        if key in available_cols:
                            dt = pd.to_datetime(row[available_cols[key]], errors='coerce')
                            if pd.notnull(dt): 
                                dates[key] = dt
                                all_active_weeks.add(get_week_str(dt))
                    
                    if 'Order' in available_cols:
                        raw_order = row[available_cols['Order']]
                        dt_order = parse_quarter_date_end(raw_order)
                        if pd.isnull(dt_order): dt_order = pd.to_datetime(raw_order, errors='coerce')
                        if pd.notnull(dt_order): 
                            dates['Order'] = dt_order
                            all_active_weeks.add(get_week_str(dt_order))

                    if dates:
                        sorted_points = sorted(dates.items(), key=lambda x: x[1])
                        plot_data.append({
                            '專案': row['專案'], 
                            'dates': dates, 
                            'sorted_points': sorted_points,
                            'min_week': get_week_str(sorted_points[0][1]),
                            'has_data': True
                        })
                    else:
                        plot_data.append({
                            '專案': row['專案'], 
                            'dates': {}, 
                            'sorted_points': [],
                            'min_week': current_week_str,
                            'has_data': False
                        })

                if plot_data:
                    sorted_weeks = sorted(list(all_active_weeks))
                    plot_data.sort(key=lambda x: x['min_week'])

                    fig = go.Figure()
                    
                    def get_line_color(start_node, end_node):
                        if end_node == 'DV': return '#F39C12'
                        if end_node == 'EV': return '#9B59B6'
                        if end_node == 'Order': return '#2ECC71'
                        if start_node == 'NPDR' and end_node == 'DV': return '#F39C12'
                        if start_node == 'DV' and end_node == 'EV':   return '#9B59B6'
                        return '#7F8C8D'

                    # [V60] 1. 繪製連線
                    for p in plot_data:
                        if not p['has_data']: continue 
                        
                        points = p['sorted_points']
                        if len(points) < 2: continue
                            
                        for i in range(len(points) - 1):
                            start_node, start_date = points[i]
                            end_node, end_date = points[i+1]
                            start_week = get_week_str(start_date)
                            end_week = get_week_str(end_date)
                            days_remaining = (end_date - current_date).days
                            weeks_remaining = days_remaining / 7.0
                            days_elapsed = (current_date - start_date).days
                            weeks_elapsed = days_elapsed / 7.0

                            hover_lines = [f"<b>{p['專案']} ({start_node} ➔ {end_node})</b>"]
                            if days_remaining > 0:
                                hover_lines.append(f"⏳ 距 {end_node} 剩下: <b>{weeks_remaining:.1f} 週 ({days_remaining} 天)</b>")
                            else:
                                hover_lines.append(f"✅ {end_node} 已完成/過期 ({abs(weeks_remaining):.1f} 週前)")
                            
                            if start_node == 'NPDR' and days_elapsed > 0:
                                hover_lines.append(f"🚩 距 NPDR 開案已過: <b>{weeks_elapsed:.1f} 週 ({days_elapsed} 天)</b>")

                            hover_lines.append(f"<span style='font-size:12px; color:gray'>({start_date.strftime('%Y.%m.%d')} - {end_date.strftime('%Y.%m.%d')})</span>")
                            hover_txt = "<br>".join(hover_lines)
                            
                            x_trace = [start_week]
                            try:
                                start_idx = sorted_weeks.index(start_week)
                                end_idx = sorted_weeks.index(end_week)
                                if end_idx > start_idx + 1:
                                    x_trace.extend(sorted_weeks[start_idx+1 : end_idx])
                            except: pass
                            x_trace.append(end_week)
                            y_trace = [p['專案']] * len(x_trace)
                            text_trace = [hover_txt] * len(x_trace)
                            line_color = get_line_color(start_node, end_node)

                            fig.add_trace(go.Scatter(
                                x=x_trace, y=y_trace, mode='lines+markers',
                                marker=dict(opacity=0, size=10),
                                line=dict(color=line_color, width=6), 
                                text=text_trace, hovertemplate="%{text}<extra></extra>", showlegend=False
                            ))
                    
                    # [V60] 2. 繪製標準節點
                    markers_config = {
                        'NPDR':  {'color': '#2E86C1', 'symbol': 'circle', 'name': 'NPDR 開案'},
                        'DV':    {'color': '#F39C12', 'symbol': 'diamond', 'name': '設計驗證 (DV)'},
                        'EV':    {'color': '#9B59B6', 'symbol': 'square', 'name': '工程驗證 (EV)'},
                        'Order': {'color': '#27AE60', 'symbol': 'star', 'name': '預計訂單 (Order)', 'size': 14}
                    }

                    for key, config in markers_config.items():
                        x_vals, y_vals, texts, hover_texts = [], [], [], []
                        for p in plot_data:
                            if not p['has_data']: continue
                            
                            if key in p['dates']:
                                dt = p['dates'][key]
                                x_vals.append(get_week_str(dt))
                                y_vals.append(p['專案'])
                                date_display = dt.strftime("%Y.%m.%d")
                                diff_days = (dt - current_date).days
                                diff_weeks = diff_days / 7.0
                                
                                if diff_days > 0:
                                    time_status = f"(再 {diff_weeks:.1f} 週 / {diff_days} 天)"
                                else:
                                    time_status = f"(已過 {abs(diff_weeks):.1f} 週 / {abs(diff_days)} 天)"
                                
                                hover_content = f"<b>{p['專案']} - {config['name']}</b><br>日期: {date_display} {time_status}"
                                hover_texts.append(hover_content)
                                texts.append(f"{date_display}" if show_schedules else "")

                        if x_vals:
                            mode_setting = 'markers+text' if show_schedules else 'markers'
                            fig.add_trace(go.Scatter(
                                x=x_vals, y=y_vals, mode=mode_setting,
                                marker=dict(color=config['color'], symbol=config['symbol'], size=config.get('size', 10), line=dict(width=2, color='white')),
                                name=config['name'], text=texts, hovertext=hover_texts, hoverinfo="text", textposition="bottom center"
                            ))
                    
                    # [V60] 3. 繪製 "規劃中" 沙漏
                    planning_x, planning_y, planning_hover = [], [], []
                    for p in plot_data:
                        if 'NPDR' not in p['dates']:
                            planning_x.append(current_week_str) 
                            planning_y.append(p['專案'])
                            planning_hover.append(f"<b>{p['專案']}</b><br>⏳ 時程規劃中 (待提供)<br><span style='color:gray; font-size:0.8em'>請 PM 盡快補齊時程</span>")
                    
                    if planning_x:
                        fig.add_trace(go.Scatter(
                            x=planning_x, 
                            y=planning_y, 
                            mode='markers', 
                            marker=dict(color='#95A5A6', symbol='hourglass', size=12, line=dict(width=1, color='#7F8C8D')), 
                            name='⏳ 規劃中 (待提供)', 
                            hovertext=planning_hover, 
                            hoverinfo="text"
                        ))

                    legend_items = [("🟦 NPDR開案", '#2E86C1'), ("🟧 標準設計 (往DV)", '#F39C12'), ("🟪 標準工程 (往EV)", '#9B59B6'), ("🟩 標準導入 (往Order)", '#2ECC71'), ("⬜ 其他路徑", '#7F8C8D'), ("⏳ 規劃中", '#95A5A6')]
                    for name, color in legend_items:
                         fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=color, width=6), name=name))
                    
                    fig.add_vline(x=current_week_str, line_width=2, line_dash="dash", line_color="#E74C3C", opacity=0.8)
                    fig.add_annotation(x=current_week_str, y=1.02, yref='paper', text=f"📍 本週 ({current_week_str})", showarrow=False, font=dict(color="#E74C3C", size=12, weight="bold"), bgcolor="rgba(255, 255, 255, 0.8)", bordercolor="#E74C3C")

                    try:
                        current_week_idx = sorted_weeks.index(current_week_str)
                        start_idx_view = max(0, current_week_idx - 1) 
                        end_idx_view = len(sorted_weeks) - 1
                    except:
                        start_idx_view = 0
                        end_idx_view = len(sorted_weeks) - 1

                    chart_height = max(400, 150 + (len(plot_data) * 45))
                    fig.update_layout(xaxis=dict(title="時間軸 (週次)", type='category', categoryorder='array', categoryarray=sorted_weeks, tickangle=-45, range=[start_idx_view - 0.5, end_idx_view + 0.5]), yaxis=dict(title="專案", autorange="reversed"), legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5), margin=dict(l=0, r=0, t=80, b=20), height=chart_height, hoverlabel=dict(bgcolor="white", font_size=14, font_family="Arial"))
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("篩選後無有效時間資料，無法繪製路徑圖。")
            else:
                st.warning("Excel 中缺少時間欄位")
        except Exception as e:
            st.error(f"路徑圖錯誤: {e}")
    else:
        st.write("無資料")

    st.divider()

    # =========================================================================
    # [區塊 10] 預計訂單 Top 10 (V65.4: Dual Key Sorting + Visual Zero)
    # =========================================================================
    st.divider()
    with st.expander("⏳ 預計訂單即將到期 Top 10 (Countdown to Order) - By Project Deadline", expanded=True):
        st.markdown("""
        <span style='background-color:#E74C3C; padding:2px 6px; border-radius:4px; color:white; font-size:0.8em'>🔴 緊急 (≤30天/已過期)</span>
        <span style='background-color:#F1C40F; padding:2px 6px; border-radius:4px; color:black; font-size:0.8em; margin-left:5px'>🟡 注意 (31~90天)</span>
        <span style='background-color:#2ECC71; padding:2px 6px; border-radius:4px; color:white; font-size:0.8em; margin-left:5px'>🟢 充裕 (>90天)</span>
        """, unsafe_allow_html=True)
        
        if '預計訂單起始點' in df_chart_source.columns:
            cols_to_keep = ['專案', '預計訂單起始點', col_twd]
            if col_rmb: cols_to_keep.append(col_rmb)
            if '專案負責人' in df_chart_source.columns: cols_to_keep.append('專案負責人')
            
            df_time = df_chart_source[cols_to_keep].copy()
            
            def convert_date_for_chart(x):
                d = parse_quarter_date_end(x)
                if pd.isnull(d): d = pd.to_datetime(x, errors='coerce')
                return d
            
            df_time['OrderDate'] = df_time['預計訂單起始點'].apply(convert_date_for_chart)
            df_time = df_time.dropna(subset=['OrderDate'])
            
            # Group by Revenue first
            grp_cols = ['專案']
            df_rev_agg = df_chart_source.groupby(grp_cols)[[col_twd, col_rmb] if col_rmb else [col_twd]].sum().reset_index()
            
            # Deduplicate by earliest date
            df_time_dedup = df_time.sort_values('OrderDate').drop_duplicates(subset=['專案'], keep='first')
            
            # Merge
            df_final = pd.merge(df_time_dedup, df_rev_agg, on='專案', how='left', suffixes=('', '_sum'))
            
            twd_col_sum = f"{col_twd}_sum" if f"{col_twd}_sum" in df_final.columns else col_twd
            rmb_col_sum = f"{col_rmb}_sum" if col_rmb and f"{col_rmb}_sum" in df_final.columns else col_rmb
            
            if not df_final.empty:
                now = pd.Timestamp.now().normalize()
                df_final['DaysDiff'] = (df_final['OrderDate'] - now).dt.days
                
                # [V65.4 Logic] Calulate Total Rev for Sorting
                df_final['Total_Revenue_Sort'] = df_final[twd_col_sum].fillna(0) + (df_final[rmb_col_sum].fillna(0) * rmb_rate if rmb_col_sum else 0)

                # [V65.2] Logic: Filter out past due
                df_final = df_final[df_final['DaysDiff'] >= 0]
                
                if df_final.empty:
                    st.success("🎉 目前沒有即將到期的緊急訂單！ (所有專案皆已過期或無資料)")
                else:
                    # [V65.4] Dual Sort: Days (Asc) -> Revenue (Desc)
                    df_final = df_final.sort_values(by=['DaysDiff', 'Total_Revenue_Sort'], ascending=[True, False])
                    
                    # Take Strict Top 10
                    df_plot = df_final.head(10).copy()
                    
                    # Reverse for Plotly (Bottom-Up)
                    df_plot = df_plot.sort_values(by=['DaysDiff', 'Total_Revenue_Sort'], ascending=[False, True])
                    
                    # [V65.3] Visual Buffer for 0 days
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
                        pm_txt = f" ({pm})" if pd.notnull(pm) and str(pm) else ""
                        return f"{row['專案']}{pm_txt}"
                    
                    df_plot['Y_Label'] = df_plot.apply(get_label, axis=1)
                    
                    def get_bar_text(row):
                        if row['DaysDiff'] == 0:
                            return f"{row['OrderDate'].strftime('%Y-%m-%d')} (🔥 本日到期！)"
                        else:
                            return f"{row['OrderDate'].strftime('%Y-%m-%d')} (剩 {abs(row['DaysDiff'])} 天)"
                    
                    df_plot['Bar_Text'] = df_plot.apply(get_bar_text, axis=1)
                    
                    def get_rev_text(row):
                        parts = []
                        twd = row.get(twd_col_sum, 0)
                        rmb = row.get(rmb_col_sum, 0) if rmb_col_sum else 0
                        if twd > 0: parts.append(f"TWD {twd:,.0f}")
                        if rmb > 0: parts.append(f"RMB {rmb:,.0f}")
                        return f"<b>💰 {' | '.join(parts)}</b>" if parts else ""
                    
                    df_plot['Text_Rev'] = df_plot.apply(get_rev_text, axis=1)
                    
                    # Hybrid Positioning
                    threshold = max_val * 0.15 if max_val > 0 else 0
                    
                    final_bar_text = []
                    final_bar_pos = []
                    final_scatter_text = []
                    
                    for idx, row in df_plot.iterrows():
                        if row['Plot_Value'] > threshold:
                            final_bar_text.append(row['Bar_Text'])
                            final_bar_pos.append('inside')
                            final_scatter_text.append(row['Text_Rev'])
                        else:
                            final_bar_text.append("") 
                            final_bar_pos.append('none')
                            combined = f"{row['Bar_Text']}   {row['Text_Rev']}"
                            final_scatter_text.append(combined)
                            
                    fig_time = go.Figure()

                    fig_time.add_trace(go.Bar(
                        x=df_plot['Plot_Value'],
                        y=df_plot['Y_Label'],
                        orientation='h',
                        marker_color=df_plot['Color'],
                        text=final_bar_text,
                        textposition=final_bar_pos, 
                        name='Days',
                        hoverinfo='y+text'
                    ))

                    fig_time.add_trace(go.Scatter(
                        x=df_plot['Plot_Value'],
                        y=df_plot['Y_Label'],
                        mode='text',
                        text=final_scatter_text,
                        textposition='middle right',
                        textfont=dict(color='#333333', size=13),
                        showlegend=False,
                        cliponaxis=False
                    ))

                    today_str = now.strftime('%Y-%m-%d')
                    fig_time.add_vline(x=0, line_width=2, line_dash="dash", line_color="#E74C3C")
                    fig_time.add_annotation(
                        x=0, y=1.02, yref='paper', 
                        text=f"📍 本日 ({today_str})", 
                        showarrow=False, 
                        font=dict(color="#E74C3C", size=12, weight="bold"), 
                        bgcolor="rgba(255, 255, 255, 0.8)", 
                        bordercolor="#E74C3C"
                    )

                    range_max = max_val * 1.35 if max_val > 0 else 10

                    fig_time.update_layout(
                        title='🚨 專案到期日戰情室',
                        xaxis_title="距離預計訂單起始點 (天) - 依 時間急迫性 > 預估營收 排序",
                        yaxis_title="專案 (負責人)",
                        xaxis=dict(
                            zeroline=True, 
                            zerolinewidth=3, 
                            zerolinecolor='#E74C3C',
                            range=[0, range_max]
                        ),
                        height=max(400, 100 + (len(df_plot) * 40)),
                        margin=dict(r=150, t=80)
                    )
                    
                    st.plotly_chart(fig_time, use_container_width=True)
            else:
                st.info("目前篩選範圍內無有效的預計訂單日期資料。")
        else:
            st.warning("缺少必要欄位")

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
                elif not cat_col_name:
                    st.info("無 '產品類別' (或 '專案類別') 欄位，無法繪製圓餅圖")
                else:
                    st.info("營收總和為 0")

            with row2_col2:
                st.subheader("🌍 市場 x 應用場景")
                if total_revenue_twd > 0 and '市場' in df_chart_source.columns and '產業應用場景' in df_chart_source.columns:
                    df_market = df_chart_source.groupby(['市場', '產業應用場景'])['Calculated_Total_TWD'].sum().reset_index()
                    fig_market = px.bar(df_market, x='市場', y='Calculated_Total_TWD', color='產業應用場景', barmode='stack', text_auto=',.0f', title='各地區市場應用 (含RMB)')
                    st.plotly_chart(fig_market, use_container_width=True)
                elif '市場' not in df_chart_source.columns or '產業應用場景' not in df_chart_source.columns:
                    st.info("缺少 '市場' 或 '產業應用場景' 欄位，無法繪製市場圖")
                else:
                    st.info("無營收數據")

    # =========================================================================
    # [區塊 6] 營收 Top 10 專案
    # =========================================================================
    st.divider()
    with st.expander("🏆 營收 Top 10 專案 - 點擊展開", expanded=False):
        if total_revenue_twd > 0:
            df_chart = df_chart_source.groupby('專案')['Calculated_Total_TWD'].sum().reset_index()
            df_chart = df_chart.nlargest(10, 'Calculated_Total_TWD').sort_values('Calculated_Total_TWD', ascending=True)
            fig_bar = px.bar(df_chart, x='Calculated_Total_TWD', y='專案', orientation='h', text_auto=',.0f', color='Calculated_Total_TWD', color_continuous_scale='Blues')
            fig_bar.update_layout(xaxis_title="預估營收 (含RMB換算)", yaxis_title="專案")
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("無營收數據")

    # =========================================================================
    # [區塊 7] 詳細資料檢視 (V64.1: Moved to Bottom)
    # =========================================================================
    st.divider()
    st.subheader("📋 詳細資料檢視 (可編輯模式)")
    st.info("💡 提示：您可直接在表格修改，或勾選左側「📝 編輯」開啟詳細編輯視窗。欲刪除資料請勾選「🗑️ 刪除」。")

    display_df = df_chart_source.drop(columns=['Calculated_Total_TWD'], errors='ignore').copy()
    
    if "🗑️ 刪除" in display_df.columns: display_df.drop(columns=["🗑️ 刪除"], inplace=True)
    if "📝 編輯" in display_df.columns: display_df.drop(columns=["📝 編輯"], inplace=True)
    
    # 強制字串型別
    cols_to_stringify = [
        '專案負責人', '目標規格', '信賴性測試要求', '對標競爭產品', '預估市場規模', 
        '目標客戶1', '目標客戶2', '目標客戶3', '目標客戶4', '目標客戶5', 
        '預計訂單起始點', '專案開發完成時間', '開案時間', '設計驗證時間', '工程驗證時間'
    ]
    for c in cols_to_stringify:
        if c in display_df.columns:
            display_df[c] = display_df[c].astype(str).replace('nan', '').replace('NaT', '')

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
            
            text_fields = ['專案負責人', '目標規格', '信賴性測試要求', '對標競爭產品', '預估市場規模', 
                           '目標客戶1', '目標客戶2', '目標客戶3', '目標客戶4', '目標客戶5', 
                           '專案', '產品類別', '產業應用場景', '開案類別', '市場']
            
            date_fields = ['預計訂單起始點', '專案開發完成時間', '開案時間', '設計驗證時間', '工程驗證時間']
            
            col_count = 3
            cols_layout = st.columns(col_count)
            
            for i, col_name in enumerate(cols):
                val = target_row[col_name]
                col_obj = cols_layout[i % col_count]
                
                if col_name in text_fields:
                    new_values[col_name] = col_obj.text_input(col_name, value=str(val) if pd.notnull(val) else "")
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
                    else:
                        display_val = ""
                    new_val_str = col_obj.text_input(col_name, value=display_val, help="請輸入數字，若無資料請留空")
                    
                    if new_val_str.strip() == "": new_values[col_name] = np.nan
                    else:
                        try: new_values[col_name] = float(new_val_str)
                        except: new_values[col_name] = new_val_str

            submitted = st.form_submit_button("💾 儲存變更 (Save Changes)", type="primary")
            
            if submitted:
                for col, new_val in new_values.items():
                    st.session_state['working_df'].at[target_index, col] = new_val
                    if target_index in st.session_state['full_df'].index:
                        st.session_state['full_df'].at[target_index, col] = new_val
                
                st.session_state['working_df'].at[target_index, "📝 編輯"] = False
                st.toast(f"✅ 專案 {project_name} 資料已更新！", icon="💾")
                st.rerun()

    # V65.5: Update save buttons
    col_btn1, col_btn2 = st.columns([1, 1])
    
    with col_btn1:
        col_act1, col_act2 = st.columns(2)
        with col_act1:
            if st.button("🔄 更新表格數據 (Update Table)", type="secondary"):
                data_to_update = edited_df.drop(columns=["📝 編輯", "🗑️ 刪除"], errors='ignore')
                st.session_state['full_df'].update(data_to_update)
                new_rows = data_to_update.loc[~data_to_update.index.isin(st.session_state['full_df'].index)]
                if not new_rows.empty:
                    st.session_state['full_df'] = pd.concat([st.session_state['full_df'], new_rows])
                
                if 'working_df' in st.session_state: del st.session_state['working_df']
                st.toast("✅ 表格數據已更新！", icon="🎉")
                st.rerun()
        
        with col_act2:
            if st.button("🗑️ 刪除勾選資料 (Delete Selected)", type="primary"):
                rows_to_delete = edited_df[edited_df["🗑️ 刪除"] == True].index
                if len(rows_to_delete) > 0:
                    st.session_state['full_df'] = st.session_state['full_df'].drop(rows_to_delete)
                    if 'working_df' in st.session_state: del st.session_state['working_df']
                    st.toast(f"✅ 已刪除 {len(rows_to_delete)} 筆資料！", icon="🗑️")
                    st.rerun()
                else:
                    st.warning("⚠️ 請先勾選要刪除的資料列")

    with col_btn2:
        today_str = datetime.datetime.now().strftime("%Y%m%d")
        
        # 1. Full Export
        csv_buffer = io.StringIO()
        st.session_state['full_df'].to_csv(csv_buffer, index=False)
        csv_data = csv_buffer.getvalue().encode('utf-8-sig')
        
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                label="💾 完整存檔 (Full Download)",
                data=csv_data,
                file_name=f"Geckos_project_data{today_str}.csv",
                mime="text/csv"
            )
        
        # 2. PM Export (Masked)
        with col_dl2:
            df_pm = st.session_state['full_df'].copy()
            cols_to_blank = ['預期毛利率', '預估市場規模', '預估市占率'] # Using 占 based on file
            # Also handle potential typo 佔
            if '預估市佔率' in df_pm.columns: cols_to_blank.append('預估市佔率')
            
            for c in cols_to_blank:
                if c in df_pm.columns:
                    df_pm[c] = ""
            
            csv_buffer_pm = io.StringIO()
            df_pm.to_csv(csv_buffer_pm, index=False)
            csv_data_pm = csv_buffer_pm.getvalue().encode('utf-8-sig')
            
            st.download_button(
                label="💾 專案存檔 for PM (Masked Data)",
                data=csv_data_pm,
                file_name=f"Geckos_project_data{today_str}_PM.csv", # Added _PM for safety
                mime="text/csv"
            )
