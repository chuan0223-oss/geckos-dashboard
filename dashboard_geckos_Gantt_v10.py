import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import datetime
import io

# 設定網頁標題與佈局 (Wide Mode)
st.set_page_config(page_title="Geckos Dashboard Pro", layout="wide")

# =========================================================================
# 🔐 [資安強化] 身分驗證 (讀取 Secrets)
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
    # [區塊 1] 篩選條件
    # =========================================================================
    st.sidebar.header("篩選條件")
    
    # 1. 開案類別
    open_type_col = '開案類別'
    open_type_filter = st.sidebar.multiselect("開案類別", options=df_full[open_type_col].unique()) if open_type_col in df_full.columns else []

    # 2. 產品類別
    if '產品類別' in df_full.columns:
        cat_col_name = '產品類別'
    elif '專案類別' in df_full.columns:
        cat_col_name = '專案類別'
    else:
        cat_col_name = None
    
    if cat_col_name:
        cat_filter = st.sidebar.multiselect("產品類別", options=df_full[cat_col_name].unique())
    else:
        cat_filter = []

    # 3. 產品應用場景
    scene_col = '產業應用場景'
    scene_filter = st.sidebar.multiselect("產品應用場景", options=df_full[scene_col].unique()) if scene_col in df_full.columns else []

    # 4. 專案
    project_options = df_full['專案'].unique() if '專案' in df_full.columns else []
    project_filter = st.sidebar.multiselect("專案", options=project_options)

    # 5. 市場
    market_filter = st.sidebar.multiselect("市場", options=df_full['市場'].unique()) if '市場' in df_full.columns else []
    
    # 6. 預計訂單時間
    order_col = '預計訂單起始點'
    order_start_filter = st.sidebar.multiselect("預計訂單時間", options=df_full[order_col].unique()) if order_col in df_full.columns else []
    
    # --- 匯率設定 ---
    st.sidebar.divider()
    st.sidebar.header("💱 匯率設定")
    rmb_rate = st.sidebar.number_input("RMB 換 TWD 匯率", value=4.4, step=0.01, format="%.2f")

    # --- 執行篩選 ---
    df_filtered = df_full.copy()
    
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

    # --- 計算顯示用的欄位 (僅供顯示，不寫回存檔) ---
    val_twd = df_chart_source[col_twd].fillna(0)
    val_rmb = df_chart_source[col_rmb].fillna(0) if col_rmb else 0
    # [關鍵] 這裡計算了 Calculated_Total_TWD，所以後面的圖表必須用 df_chart_source
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

        icon_map = {
            'NPDR': '🔵', 
            'DV': '🔶', 
            'EV': '🟥', 
            'Order': '🟢'
        }

        col_map_alerts = {
            'NPDR': start_col, 
            'DV': '設計驗證時間', 
            'EV': '工程驗證時間', 
            'Order': '預計訂單起始點'
        }
        
        stage_name_display = {
            'NPDR': 'NPDR開案',
            'DV': '設計驗證(DV)',
            'EV': '工程驗證(EV)',
            'Order': '預計訂單(Order)'
        }
        
        week_items = []
        month_items = []

        for idx, row in df_alerts.iterrows():
            for key, col_name in col_map_alerts.items():
                if col_name in df_alerts.columns:
                    raw_val = row[col_name]
                    dt = pd.to_datetime(raw_val, errors='coerce')
                    if pd.isnull(dt):
                        dt = parse_quarter_date_end(raw_val)
                    
                    if pd.notnull(dt):
                        icon = icon_map.get(key, '⚪')
                        display_name = stage_name_display.get(key, key)
                        
                        days_diff = (dt - now).days
                        
                        if days_diff < 0:
                            count_down_str = "(已完成)"
                            msg = f"<span style='color: #999999;'>{icon} {row['專案']} - {display_name} | {dt.strftime('%Y-%m-%d')} {count_down_str}</span>"
                        else:
                            if days_diff == 0:
                                count_down_str = "(今天)"
                            else:
                                count_down_str = f"(剩餘 {days_diff} 天)"
                            msg = f"{icon} **{row['專案']}** - {display_name} | {dt.strftime('%Y-%m-%d')} {count_down_str}"
                        
                        if start_week <= dt <= end_week:
                            week_items.append({'dt': dt, 'msg': msg})
                        
                        if dt.year == current_year and dt.month == current_month:
                            month_items.append({'dt': dt, 'msg': msg})

        week_items.sort(key=lambda x: x['dt'])
        month_items.sort(key=lambda x: x['dt'])

        if week_items or month_items:
            with st.expander("🔔 本週/本月重點提醒 (Milestone Alerts)", expanded=True):
                c1, c2 = st.columns(2)
                with c1:
                    if week_items:
                        st.error("📅 **本週重點 (This Week)**")
                        for item in week_items: 
                            st.markdown(item['msg'], unsafe_allow_html=True)
                    else:
                        st.info("📅 本週無重點事項")
                with c2:
                    if month_items:
                        st.info("🗓️ **本月重點 (This Month)**")
                        for item in month_items: 
                            st.markdown(item['msg'], unsafe_allow_html=True)
                    else:
                        st.write("🗓️ 本月無重點事項")

    # =========================================================================
    # [區塊 3] 專案研發全週期路徑圖 (Roadmap)
    # =========================================================================
    st.subheader("🚀 專案研發全週期路徑圖 (Roadmap)")
    
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
                        if end_node == 'EV': return '#E74C3C'
                        if end_node == 'Order': return '#2ECC71'
                        if start_node == 'NPDR' and end_node == 'DV': return '#F39C12'
                        if start_node == 'DV' and end_node == 'EV':   return '#E74C3C'
                        return '#7F8C8D'

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
                    
                    markers_config = {
                        'NPDR':  {'color': '#2E86C1', 'symbol': 'circle', 'name': 'NPDR 開案'},
                        'DV':    {'color': '#F39C12', 'symbol': 'diamond', 'name': '設計驗證 (DV)'},
                        'EV':    {'color': '#E74C3C', 'symbol': 'square', 'name': '工程驗證 (EV)'},
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
                    
                    no_data_x, no_data_y, no_data_hover = [], [], []
                    for p in plot_data:
                        if not p['has_data']:
                            no_data_x.append(current_week_str) 
                            no_data_y.append(p['專案'])
                            no_data_hover.append(f"<b>{p['專案']}</b><br>❌ 無有效時間資料")
                    if no_data_x:
                        fig.add_trace(go.Scatter(x=no_data_x, y=no_data_y, mode='markers', marker=dict(color='gray', symbol='circle-x', size=12), name='無時間資料', hovertext=no_data_hover, hoverinfo="text"))

                    legend_items = [("🟦 NPDR開案", '#2E86C1'), ("🟧 標準設計 (往DV)", '#F39C12'), ("🟥 標準工程 (往EV)", '#E74C3C'), ("🟩 標準導入 (往Order)", '#2ECC71'), ("⬜ 其他路徑", '#7F8C8D'), ("❌ 無資料", 'gray')]
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
    # [區塊 7] 詳細資料檢視
    # =========================================================================
    st.subheader("📋 詳細資料檢視 (可編輯模式)")
    st.info(f"💡 提示：您可在此修改數值或勾選「刪除」來移除資料。所有變更需點擊「🔄 更新數據」或「🗑️ 刪除勾選資料」才會生效。")

    column_cfg = {
        "專案": st.column_config.TextColumn("專案", width="medium", disabled=False, required=True, pinned=True),
        "🗑️ 刪除": st.column_config.CheckboxColumn("刪除", width="small", default=False)
    }

    display_df = df_chart_source.drop(columns=['Calculated_Total_TWD'], errors='ignore').copy()
    display_df.insert(0, "🗑️ 刪除", False)

    edited_df = st.data_editor(
        display_df, 
        column_config=column_cfg,
        num_rows="dynamic", 
        use_container_width=True
    )

    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
    
    with col_btn1:
        if st.button("🔄 更新數據 (Update)", type="primary"):
            data_to_update = edited_df.drop(columns=["🗑️ 刪除"])
            st.session_state['full_df'].update(data_to_update)
            new_rows = data_to_update.loc[~data_to_update.index.isin(st.session_state['full_df'].index)]
            if not new_rows.empty:
                st.session_state['full_df'] = pd.concat([st.session_state['full_df'], new_rows])
            
            # 強制移除 working_df，觸發下次 rerun 從 full_df 重新載入
            if 'working_df' in st.session_state:
                del st.session_state['working_df']

            st.toast("✅ 數據已更新！", icon="🎉")
            st.rerun()

    with col_btn2:
        if st.button("🗑️ 刪除勾選資料 (Delete Selected)", type="secondary"):
            rows_to_delete = edited_df[edited_df["🗑️ 刪除"] == True].index
            if len(rows_to_delete) > 0:
                st.session_state['full_df'] = st.session_state['full_df'].drop(rows_to_delete)
                
                # 同樣需要重置 working_df
                if 'working_df' in st.session_state:
                    del st.session_state['working_df']

                st.toast(f"✅ 已刪除 {len(rows_to_delete)} 筆資料！", icon="🗑️")
                st.rerun()
            else:
                st.warning("⚠️ 請先勾選要刪除的資料列")

    with col_btn3:
        csv_buffer = io.StringIO()
        st.session_state['full_df'].to_csv(csv_buffer, index=False)
        csv_data = csv_buffer.getvalue().encode('utf-8-sig')
        
        st.download_button(
            label="💾 完整存檔 (Download Full CSV)",
            data=csv_data,
            file_name="project_data_full.csv",
            mime="text/csv"
        )

    st.divider()

    # =========================================================================
    # [區塊 4] & [區塊 5] (折疊收納)
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
                    # [V35] 修改顯示格式為千分位
                    fig_market = px.bar(df_market, x='市場', y='Calculated_Total_TWD', color='產業應用場景', 
                                        barmode='stack', text_auto=',.0f', title='各地區市場應用 (含RMB)')
                    st.plotly_chart(fig_market, use_container_width=True)
                elif '市場' not in df_chart_source.columns or '產業應用場景' not in df_chart_source.columns:
                    st.info("缺少 '市場' 或 '產業應用場景' 欄位，無法繪製市場圖")
                else:
                    st.info("無營收數據")

    # =========================================================================
    # [區塊 6] 營收 Top 10 專案 (折疊收納)
    # =========================================================================
    st.divider()
    with st.expander("🏆 營收 Top 10 專案 - 點擊展開", expanded=False):
        if total_revenue_twd > 0:
            df_chart = df_chart_source.groupby('專案')['Calculated_Total_TWD'].sum().reset_index()
            df_chart = df_chart.nlargest(10, 'Calculated_Total_TWD').sort_values('Calculated_Total_TWD', ascending=True)
            
            # [V35] 修改顯示格式為千分位
            fig_bar = px.bar(df_chart, x='Calculated_Total_TWD', y='專案', orientation='h', text_auto=',.0f', 
                             color='Calculated_Total_TWD', color_continuous_scale='Blues')
            fig_bar.update_layout(xaxis_title="預估營收 (含RMB換算)", yaxis_title="專案")
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("無營收數據")
