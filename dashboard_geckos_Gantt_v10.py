import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import datetime
import io

# 設定網頁標題與佈局 (Wide Mode)
st.set_page_config(page_title="Geckos Dashboard Pro", layout="wide")

# 標題
st.title("Geckos Project Dashboard (Executive View)")

# 1. 檔案上傳區塊
st.sidebar.header("資料上傳區")
uploaded_file = st.sidebar.file_uploader("請上傳專案總表 (Excel/CSV)", type=["xlsx", "csv"])

# --- 輔助函式 ---
def parse_quarter_date_end(date_str):
    """將 '2026Q2' 轉為季末日期"""
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
    """將日期轉為 YYYY-Www 格式 (ISO Week)"""
    if pd.isnull(dt): return None
    iso_cal = dt.isocalendar()
    return f"{iso_cal.year}-W{iso_cal.week:02d}"

if uploaded_file is not None:
    # 2. 讀取資料
    try:
        if uploaded_file.name.endswith('.csv'):
            df_raw = pd.read_csv(uploaded_file)
        else:
            df_raw = pd.read_excel(uploaded_file)
        
        # 資料前處理 (統一去除空白)
        df_raw.columns = df_raw.columns.str.strip()
        
        # 處理數值欄位
        revenue_col = None
        candidates_priority = [c for c in df_raw.columns if '營收' in c and 'TWD' in c]
        candidates_secondary = [c for c in df_raw.columns if '營收' in c] 
        if candidates_priority: revenue_col = candidates_priority[0]
        elif candidates_secondary: revenue_col = candidates_secondary[0]
        else: revenue_col = '預估營收(TWD)'

        if revenue_col in df_raw.columns:
            if df_raw[revenue_col].dtype == 'object':
                df_raw[revenue_col] = pd.to_numeric(df_raw[revenue_col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            else:
                df_raw[revenue_col] = df_raw[revenue_col].fillna(0)

    except Exception as e:
        st.error(f"檔案讀取失敗: {e}")
        st.stop()

    # =========================================================================
    # [區塊 1] 篩選條件
    # =========================================================================
    st.sidebar.header("篩選條件")
    
    # 1. 專案
    project_options = df_raw['專案'].unique() if '專案' in df_raw.columns else []
    project_filter = st.sidebar.multiselect("專案", options=project_options)

    # 2. 產品類別
    if '產品類別' in df_raw.columns:
        cat_col_name = '產品類別'
    elif '專案類別' in df_raw.columns:
        cat_col_name = '專案類別'
    else:
        cat_col_name = None
    
    if cat_col_name:
        cat_filter = st.sidebar.multiselect("產品類別", options=df_raw[cat_col_name].unique())
    else:
        cat_filter = []

    # 3. 產品應用場景
    scene_col = '產業應用場景'
    scene_filter = st.sidebar.multiselect("產品應用場景", options=df_raw[scene_col].unique()) if scene_col in df_raw.columns else []
    
    # 4. 開案類別
    open_type_col = '開案類別'
    open_type_filter = st.sidebar.multiselect("開案類別", options=df_raw[open_type_col].unique()) if open_type_col in df_raw.columns else []

    # 5. 市場
    market_filter = st.sidebar.multiselect("市場", options=df_raw['市場'].unique()) if '市場' in df_raw.columns else []
    
    # 6. 預計訂單時間
    order_col = '預計訂單起始點'
    order_start_filter = st.sidebar.multiselect("預計訂單時間", options=df_raw[order_col].unique()) if order_col in df_raw.columns else []
    
    # --- 執行篩選 ---
    df_filtered_base = df_raw.copy()
    
    if project_filter and '專案' in df_filtered_base.columns: 
        df_filtered_base = df_filtered_base[df_filtered_base['專案'].isin(project_filter)]
    if cat_filter and cat_col_name: 
        df_filtered_base = df_filtered_base[df_filtered_base[cat_col_name].isin(cat_filter)]
    if scene_filter and scene_col in df_filtered_base.columns:
        df_filtered_base = df_filtered_base[df_filtered_base[scene_col].isin(scene_filter)]
    if open_type_filter and open_type_col in df_filtered_base.columns:
        df_filtered_base = df_filtered_base[df_filtered_base[open_type_col].isin(open_type_filter)]
    if market_filter and '市場' in df_filtered_base.columns:
        df_filtered_base = df_filtered_base[df_filtered_base['市場'].isin(market_filter)]
    if order_start_filter and order_col in df_filtered_base.columns:
        df_filtered_base = df_filtered_base[df_filtered_base[order_col].isin(order_start_filter)]

    # --- Session State 管理數據流 ---
    if 'last_filtered_shape' not in st.session_state:
        st.session_state['last_filtered_shape'] = None
    if 'working_df' not in st.session_state:
        st.session_state['working_df'] = df_filtered_base

    current_shape = df_filtered_base.shape
    if st.session_state['last_filtered_shape'] != current_shape or \
       not df_filtered_base.index.equals(st.session_state['working_df'].index):
        st.session_state['working_df'] = df_filtered_base
        st.session_state['last_filtered_shape'] = current_shape

    df_chart_source = st.session_state['working_df']

    # =========================================================================
    # [區塊 2] KPI Metrics
    # =========================================================================
    st.divider()
    total_revenue = df_chart_source[revenue_col].sum()
    project_count = len(df_chart_source)
    
    if not df_chart_source.empty and total_revenue > 0:
        top_project_row = df_chart_source.loc[df_chart_source[revenue_col].idxmax()]
        top_contributor_text = top_project_row['專案'] if '專案' in top_project_row else "Unknown"
        top_project_rev = top_project_row[revenue_col]
    else:
        top_contributor_text = "無資料"
        top_project_rev = 0

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric(label="💰 預估總營收 (TWD)", value=f"{total_revenue:,.0f}")
    kpi2.metric(label="👑 營收貢獻王", value=top_contributor_text, delta=f"{top_project_rev:,.0f}")
    kpi3.metric(label="📊 篩選後專案數", value=project_count)

    st.divider()

    # =========================================================================
    # [區塊 3] 專案研發全週期路徑圖 (Roadmap) - V28 (恢復精確週數/天數)
    # =========================================================================
    st.subheader("🚀 專案研發全週期路徑圖 (Roadmap)")
    
    show_schedules = st.checkbox("👁️ 顯示所有節點時程 (Show All Node Schedules)", value=False)
    
    if not df_chart_source.empty:
        try:
            plot_data = []
            
            start_col = None
            possible_start_cols = ['開案時間', '开案时间', 'NPDR開案時間', 'NPDR开案时间', 'NPDR']
            for col in possible_start_cols:
                if col in df_chart_source.columns:
                    start_col = col
                    break
            if not start_col: start_col = '開案時間'

            col_map = {'NPDR': start_col, 'DV': '設計驗證時間', 'EV': '工程驗證時間', 'Order': '預計訂單起始點'}
            available_cols = {k: v for k, v in col_map.items() if v in df_chart_source.columns}
            
            all_active_weeks = set() 
            current_date = pd.Timestamp.now().normalize()
            current_week_str = get_week_str(current_date)
            all_active_weeks.add(current_week_str) 

            if available_cols:
                for idx, row in df_chart_source.iterrows():
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

                    # 1. 畫分段連線
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
                                    intermediates = sorted_weeks[start_idx+1 : end_idx]
                                    x_trace.extend(intermediates)
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
                    
                    # 2. 畫節點
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
                                
                                # [核心修正 V28] 恢復精確的 "週數 / 天數" 格式
                                if diff_days > 0:
                                    time_status = f"(再 {diff_weeks:.1f} 週 / {diff_days} 天)"
                                else:
                                    time_status = f"(已過 {abs(diff_weeks):.1f} 週 / {abs(diff_days)} 天)"
                                
                                hover_content = f"<b>{p['專案']} - {config['name']}</b><br>日期: {date_display} {time_status}"
                                hover_texts.append(hover_content)
                                
                                # 靜態文字：若勾選，只顯示日期
                                texts.append(f"{date_display}" if show_schedules else "")

                        if x_vals:
                            mode_setting = 'markers+text' if show_schedules else 'markers'
                            fig.add_trace(go.Scatter(
                                x=x_vals, y=y_vals, mode=mode_setting,
                                marker=dict(color=config['color'], symbol=config['symbol'], size=config.get('size', 10), line=dict(width=2, color='white')),
                                name=config['name'], 
                                text=texts,
                                hovertext=hover_texts,
                                hoverinfo="text",
                                textposition="bottom center"
                            ))
                    
                    # 3. 無資料標記
                    no_data_x, no_data_y, no_data_hover = [], [], []
                    for p in plot_data:
                        if not p['has_data']:
                            no_data_x.append(current_week_str) 
                            no_data_y.append(p['專案'])
                            no_data_hover.append(f"<b>{p['專案']}</b><br>❌ 無有效時間資料")
                    
                    if no_data_x:
                        fig.add_trace(go.Scatter(
                            x=no_data_x, y=no_data_y, mode='markers',
                            marker=dict(color='gray', symbol='circle-x', size=12, line=dict(width=1, color='white')),
                            name='無時間資料',
                            hovertext=no_data_hover, hoverinfo="text"
                        ))

                    # Legend
                    legend_items = [
                        ("🟦 NPDR開案", '#2E86C1'),
                        ("🟧 標準設計 (往DV)", '#F39C12'),
                        ("🟥 標準工程 (往EV)", '#E74C3C'),
                        ("🟩 標準導入 (往Order)", '#2ECC71'),
                        ("⬜ 其他路徑", '#7F8C8D'),
                        ("❌ 無資料", 'gray')
                    ]
                    for name, color in legend_items:
                         fig.add_trace(go.Scatter(x=[None], y=[None], mode='lines', line=dict(color=color, width=6), name=name))
                    
                    fig.add_vline(x=current_week_str, line_width=2, line_dash="dash", line_color="#E74C3C", opacity=0.8)
                    fig.add_annotation(
                        x=current_week_str, y=1.02, yref='paper',
                        text=f"📍 本週 ({current_week_str})", showarrow=False,
                        font=dict(color="#E74C3C", size=12, weight="bold"),
                        bgcolor="rgba(255, 255, 255, 0.8)", bordercolor="#E74C3C"
                    )

                    try:
                        current_week_idx = sorted_weeks.index(current_week_str)
                        start_idx_view = max(0, current_week_idx - 1) 
                        end_idx_view = len(sorted_weeks) - 1
                    except:
                        start_idx_view = 0
                        end_idx_view = len(sorted_weeks) - 1

                    chart_height = max(400, 150 + (len(plot_data) * 45))
                    
                    fig.update_layout(
                        xaxis=dict(
                            title="時間軸 (週次)", type='category', 
                            categoryorder='array', categoryarray=sorted_weeks,
                            tickangle=-45,
                            range=[start_idx_view - 0.5, end_idx_view + 0.5] 
                        ),
                        yaxis=dict(title="專案", autorange="reversed"),
                        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5),
                        margin=dict(l=0, r=0, t=80, b=20),
                        height=chart_height, 
                        hoverlabel=dict(bgcolor="white", font_size=14, font_family="Arial")
                    )

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
    # [區塊 4] & [區塊 5] (折疊收納)
    # =========================================================================
    if not df_chart_source.empty:
        with st.expander("📊 圖表分析 (產品類別 & 市場應用) - 點擊展開", expanded=False):
            row2_col1, row2_col2 = st.columns(2)

            with row2_col1:
                st.subheader("📌 各產品類別營收分佈")
                if total_revenue > 0 and cat_col_name:
                    fig_pie = px.pie(df_chart_source, values=revenue_col, names=cat_col_name, hole=0.4, title=f'各{cat_col_name}營收分佈')
                    fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                    fig_pie.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.1))
                    st.plotly_chart(fig_pie, use_container_width=True)
                elif not cat_col_name:
                    st.info("無 '產品類別' (或 '專案類別') 欄位，無法繪製圓餅圖")
                else:
                    st.info("營收總和為 0")

            with row2_col2:
                st.subheader("🌍 市場 x 應用場景")
                if total_revenue > 0 and '市場' in df_chart_source.columns and '產業應用場景' in df_chart_source.columns:
                    df_market = df_chart_source.groupby(['市場', '產業應用場景'])[revenue_col].sum().reset_index()
                    fig_market = px.bar(df_market, x='市場', y=revenue_col, color='產業應用場景', 
                                        barmode='stack', text_auto='.2s', title='各地區市場應用')
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
        if total_revenue > 0:
            df_chart = df_chart_source.nlargest(10, revenue_col).sort_values(revenue_col, ascending=True)
            fig_bar = px.bar(df_chart, x=revenue_col, y='專案', orientation='h', text_auto='.2s', 
                             color=revenue_col, color_continuous_scale='Blues')
            fig_bar.update_layout(xaxis_title="預估營收", yaxis_title="專案")
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("無營收數據")

    # =========================================================================
    # [區塊 7] 詳細資料檢視 (可編輯模式)
    # =========================================================================
    st.divider()
    st.subheader("📋 詳細資料檢視 (可編輯模式)")
    st.info("💡 提示：您可以直接點擊下方表格修改數值或日期，修改完畢後請點擊「🔄 更新數據」按鈕。")

    column_cfg = {
        "專案": st.column_config.TextColumn("專案", width="medium", disabled=False, required=True, pinned=True)
    }

    edited_df = st.data_editor(
        st.session_state['working_df'], 
        column_config=column_cfg,
        num_rows="dynamic", 
        use_container_width=True
    )

    col_btn1, col_btn2 = st.columns([1, 1])
    
    with col_btn1:
        if st.button("🔄 更新數據 (Update Charts)", type="primary"):
            st.session_state['working_df'] = edited_df
            st.rerun()
            
    with col_btn2:
        csv_buffer = io.StringIO()
        edited_df.to_csv(csv_buffer, index=False)
        csv_data = csv_buffer.getvalue().encode('utf-8-sig')
        
        st.download_button(
            label="💾 存檔 (下載 CSV)",
            data=csv_data,
            file_name="edited_project_data.csv",
            mime="text/csv"
        )
