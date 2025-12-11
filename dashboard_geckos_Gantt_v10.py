import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re

# 設定網頁標題與佈局 (Wide Mode)
st.set_page_config(page_title="Geckos Dashboard Pro", layout="wide")

# 標題
st.title("Geckos Project Dashboard (Executive View)")

# 1. 檔案上傳區塊
st.sidebar.header("資料上傳區")
uploaded_file = st.sidebar.file_uploader("請上傳專案總表 (Excel/CSV)", type=["xlsx", "csv"])

# --- 輔助函式：解析季度末 ---
def parse_quarter_date_end(date_str):
    """
    將 '2026Q2' 強制轉換為該季度的「最後一天」。
    Q1 -> 03-31, Q2 -> 06-30, Q3 -> 09-30, Q4 -> 12-31
    """
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

if uploaded_file is not None:
    # 2. 讀取資料
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"檔案讀取失敗: {e}")
        st.stop()

    # --- 資料前處理 ---
    df.columns = df.columns.str.strip() # 去除空白

    # 智慧尋找「營收」欄位
    revenue_col = None
    candidates_priority = [c for c in df.columns if '營收' in c and 'TWD' in c]
    candidates_secondary = [c for c in df.columns if '營收' in c and '等級' not in c]
    
    if candidates_priority: revenue_col = candidates_priority[0]
    elif candidates_secondary: revenue_col = candidates_secondary[0]
    else: revenue_col = '預估營收(TWD)'

    # 轉換營收為數值
    if revenue_col in df.columns:
        if df[revenue_col].dtype == 'object':
            df[revenue_col] = pd.to_numeric(df[revenue_col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        else:
            df[revenue_col] = df[revenue_col].fillna(0)
    else:
        st.error(f"找不到營收欄位，請確認 Excel 欄位名稱。")
        st.stop()

    # 處理客戶欄位
    customer_cols = ['目標客戶1', '目標客戶2', '目標客戶3', '目標客戶4', '目標客戶5']
    all_customers = set()
    for col in customer_cols:
        if col in df.columns:
            all_customers.update(df[col].dropna().unique())
    all_customers = sorted(list(all_customers))

    # --- 側邊欄：Debug 模式與篩選 ---
    st.sidebar.header("系統設定")
    debug_mode = st.sidebar.checkbox("開啟 Debug 數據檢查", value=False)
    
    if debug_mode:
        st.sidebar.info(f"偵測到的營收欄位: {revenue_col}")

    st.sidebar.header("篩選條件")
    cat_filter = st.sidebar.multiselect("專案類別", options=df['專案類別'].unique())
    scene_filter = st.sidebar.multiselect("產業應用場景", options=df['產業應用場景'].unique())
    market_filter = st.sidebar.multiselect("市場", options=df['市場'].unique())
    revenue_grade_filter = st.sidebar.multiselect("營收等級", options=df['營收等級'].unique())
    
    npdr_options = df['NPDR開案時間'].astype(str).unique()
    npdr_filter = st.sidebar.multiselect("NPDR開案時間", options=npdr_options)
    order_start_filter = st.sidebar.multiselect("預計訂單起始點", options=df['預計訂單起始點'].unique())
    customer_filter = st.sidebar.multiselect("目標客戶", options=all_customers)

    # --- 執行篩選 ---
    df_filtered = df.copy()

    if cat_filter: df_filtered = df_filtered[df_filtered['專案類別'].isin(cat_filter)]
    if scene_filter: df_filtered = df_filtered[df_filtered['產業應用場景'].isin(scene_filter)]
    if market_filter: df_filtered = df_filtered[df_filtered['市場'].isin(market_filter)]
    if revenue_grade_filter: df_filtered = df_filtered[df_filtered['營收等級'].isin(revenue_grade_filter)]
    if npdr_filter: df_filtered = df_filtered[df_filtered['NPDR開案時間'].astype(str).isin(npdr_filter)]
    if order_start_filter: df_filtered = df_filtered[df_filtered['預計訂單起始點'].isin(order_start_filter)]
    if customer_filter:
        mask = df_filtered[customer_cols].apply(lambda x: x.isin(customer_filter).any(), axis=1)
        df_filtered = df_filtered[mask]

    # --- KPI 區塊 ---
    st.divider()
    total_revenue = df_filtered[revenue_col].sum()
    project_count = len(df_filtered)
    
    if not df_filtered.empty and total_revenue > 0:
        top_project_row = df_filtered.loc[df_filtered[revenue_col].idxmax()]
        top_contributor_text = top_project_row['專案']
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
    # [區域 1] 專案研發全週期路徑圖 (Roadmap)
    # =========================================================================
    st.subheader("🚀 專案研發全週期路徑圖 (Roadmap)")
    
    if not df_filtered.empty:
        try:
            plot_data = []
            col_map = {'NPDR': 'NPDR開案時間', 'DV': '設計驗證時間', 'EV': '工程驗證時間', 'Order': '預計訂單起始點'}
            available_cols = {k: v for k, v in col_map.items() if v in df_filtered.columns}
            
            all_active_months = set() 

            if available_cols:
                for idx, row in df_filtered.iterrows():
                    dates = {}
                    
                    # (A) 一般日期解析
                    for key in ['NPDR', 'DV', 'EV']:
                        if key in available_cols:
                            dt = pd.to_datetime(row[available_cols[key]], errors='coerce')
                            if pd.notnull(dt): 
                                dates[key] = dt
                                all_active_months.add(dt.strftime("%Y-%m")) 

                    # (B) 訂單日期解析
                    if 'Order' in available_cols:
                        raw_order = row[available_cols['Order']]
                        dt_order = parse_quarter_date_end(raw_order)
                        if pd.isnull(dt_order):
                            dt_order = pd.to_datetime(raw_order, errors='coerce')

                        if pd.notnull(dt_order): 
                            dates['Order'] = dt_order
                            all_active_months.add(dt_order.strftime("%Y-%m"))

                    if dates:
                        sorted_points = sorted(dates.items(), key=lambda x: x[1])
                        plot_data.append({
                            '專案': row['專案'], 
                            'dates': dates, 
                            'sorted_points': sorted_points,
                            'min_month': sorted_points[0][1].strftime("%Y-%m")
                        })

                if plot_data:
                    # 建立智慧時間軸
                    sorted_months = sorted(list(all_active_months))
                    plot_data.sort(key=lambda x: x['min_month'])

                    fig = go.Figure()
                    
                    # --- 顏色定義 (Strict Path Logic) ---
                    # 只有標準路徑才給顏色，其他給灰色
                    def get_line_color(start_node, end_node):
                        if start_node == 'NPDR' and end_node == 'DV': return '#F39C12' # 橘色
                        if start_node == 'DV' and end_node == 'EV':   return '#E74C3C' # 紅色
                        if start_node == 'EV' and end_node == 'Order': return '#2ECC71' # 綠色
                        return '#D7DBDD' # 灰色 (跳躍或缺漏)

                    # --- 1. 畫分段連線 ---
                    for p in plot_data:
                        points = p['sorted_points']
                        if len(points) < 2: continue
                            
                        for i in range(len(points) - 1):
                            start_node, start_date = points[i]
                            end_node, end_date = points[i+1]
                            
                            start_month = start_date.strftime("%Y-%m")
                            end_month = end_date.strftime("%Y-%m")

                            duration_days = (end_date - start_date).days
                            
                            hover_txt = (
                                f"<b>{p['專案']} ({start_node} ➔ {end_node})</b><br>"
                                f"階段耗時: <b>{duration_days}</b> 天 "
                                f"({start_date.strftime('%Y.%m.%d')} - {end_date.strftime('%Y.%m.%d')})"
                            )

                            # 中間錨點補間
                            x_trace = [start_month]
                            try:
                                start_idx = sorted_months.index(start_month)
                                end_idx = sorted_months.index(end_month)
                                if end_idx > start_idx + 1:
                                    intermediates = sorted_months[start_idx+1 : end_idx]
                                    x_trace.extend(intermediates)
                            except:
                                pass
                            x_trace.append(end_month)
                            
                            y_trace = [p['專案']] * len(x_trace)
                            text_trace = [hover_txt] * len(x_trace)

                            # 取得顏色
                            line_color = get_line_color(start_node, end_node)

                            fig.add_trace(go.Scatter(
                                x=x_trace, 
                                y=y_trace,
                                mode='lines+markers',
                                marker=dict(opacity=0, size=10),
                                line=dict(color=line_color, width=6), 
                                text=text_trace, 
                                hovertemplate="%{text}<extra></extra>", 
                                showlegend=False
                            ))
                    
                    # --- 2. 畫顯性節點 ---
                    markers_config = {
                        'NPDR':  {'color': '#2E86C1', 'symbol': 'circle', 'name': 'NPDR 開案'},  # 藍色
                        'DV':    {'color': '#F39C12', 'symbol': 'diamond', 'name': '設計驗證 (DV)'}, # 橘色
                        'EV':    {'color': '#E74C3C', 'symbol': 'square', 'name': '工程驗證 (EV)'},  # 紅色
                        'Order': {'color': '#27AE60', 'symbol': 'star', 'name': '預計訂單 (Order)', 'size': 14} # 綠色
                    }
                    
                    for key, config in markers_config.items():
                        x_vals, y_vals, texts = [], [], []
                        
                        for p in plot_data:
                            if key in p['dates']:
                                dt = p['dates'][key]
                                x_vals.append(dt.strftime("%Y-%m"))
                                y_vals.append(p['專案'])
                                date_display = dt.strftime("%Y.%m.%d")
                                texts.append(f"<b>{p['專案']}</b> - {config['name']}<br>日期: {date_display}")

                        if x_vals:
                            fig.add_trace(go.Scatter(
                                x=x_vals, y=y_vals, mode='markers',
                                marker=dict(color=config['color'], symbol=config['symbol'], size=config.get('size', 10), line=dict(width=1, color='white')),
                                name=config['name'], text=texts, hovertemplate="%{text}<extra></extra>"
                            ))
                    
                    # Legend
                    legend_items = [
                        ("🟦 NPDR開案", '#2E86C1'),
                        ("🟧 標準設計 (NPDR➔DV)", '#F39C12'),
                        ("🟥 標準工程 (DV➔EV)", '#E74C3C'),
                        ("🟩 標準導入 (EV➔Order)", '#2ECC71'),
                        ("⬜ 流程缺失/跳躍", '#D7DBDD')
                    ]
                    for name, color in legend_items:
                         fig.add_trace(go.Scatter(
                            x=[None], y=[None], mode='lines',
                            line=dict(color=color, width=6),
                            name=name
                        ))

                    # 4. 版面設定 (Fix Overlap)
                    fig.update_layout(
                        xaxis=dict(
                            title="時間軸 (自動隱藏無專案月份)", 
                            type='category', 
                            categoryorder='array', 
                            categoryarray=sorted_months,
                            tickangle=-45
                        ),
                        yaxis=dict(title="專案", autorange="reversed"),
                        # 關鍵調整：拉高 Legend 位置，並增加 Margin
                        legend=dict(
                            orientation="h", 
                            y=1.1, # 向上推
                            x=1, 
                            xanchor="right"
                        ),
                        height=max(400, 150 + (len(plot_data) * 45)), # 稍微增加每一行的高度空間
                        margin=dict(l=0, r=0, t=100, b=0), # 增加上邊界，避免 Legend 蓋住第一行資料
                        hoverlabel=dict(bgcolor="white", font_size=14, font_family="Arial")
                    )

                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("篩選後無有效時間資料，無法繪製路徑圖。")
            else:
                st.warning("Excel 中缺少時間欄位 (NPDR, DV, EV, Order)")
        except Exception as e:
            st.error(f"路徑圖錯誤: {e}")
    else:
        st.write("無資料")

    st.divider()

    # =========================================================================
    # [區域 2] 圓餅圖 + 市場圖
    # =========================================================================
    if not df_filtered.empty:
        row2_col1, row2_col2 = st.columns(2)

        with row2_col1:
            st.subheader("📌 專案類別營收佔比")
            if total_revenue > 0:
                fig_pie = px.pie(df_filtered, values=revenue_col, names='專案類別', 
                                 hole=0.4, title='各類別營收分佈')
                fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                fig_pie.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.1))
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("營收總和為 0")

        with row2_col2:
            st.subheader("🌍 市場 x 應用場景")
            if total_revenue > 0:
                df_market = df_filtered.groupby(['市場', '產業應用場景'])[revenue_col].sum().reset_index()
                fig_market = px.bar(df_market, x='市場', y=revenue_col, color='產業應用場景', 
                                    barmode='stack', text_auto='.2s', title='各地區市場應用')
                st.plotly_chart(fig_market, use_container_width=True)
            else:
                st.info("無營收數據")

        # =========================================================================
        # [區域 3] Top 10
        # =========================================================================
        st.subheader("🏆 營收 Top 10 專案")
        if total_revenue > 0:
            df_chart = df_filtered.nlargest(10, revenue_col).sort_values(revenue_col, ascending=True)
            fig_bar = px.bar(df_chart, x=revenue_col, y='專案', orientation='h', text_auto='.2s', 
                             color=revenue_col, color_continuous_scale='Blues')
            fig_bar.update_layout(xaxis_title="預估營收", yaxis_title="專案")
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("無營收數據")

    st.divider()
    st.subheader("📋 詳細資料檢視")
    st.dataframe(df_filtered, use_container_width=True)