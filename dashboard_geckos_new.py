import streamlit as st
import pandas as pd
import plotly.express as px

# 設定網頁標題與佈局
st.set_page_config(page_title="Geckos Dashboard", layout="wide")

# 標題
st.title("Geckos Project Dashboard")

# 1. 檔案上傳區塊
st.sidebar.header("資料上傳區")
uploaded_file = st.sidebar.file_uploader("請上傳專案總表 (Excel/CSV)", type=["xlsx", "csv"])

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
    # 確保營收欄位是數字
    revenue_col = '預估營收(TWD)'
    # 如果找不到預設名稱，嘗試尋找類似名稱
    if revenue_col not in df.columns:
        possible_cols = [c for c in df.columns if '營收' in c and 'TWD' in c]
        if possible_cols:
            revenue_col = possible_cols[0]

    # 清洗營收數據 (轉為數值)
    if df[revenue_col].dtype == 'object':
        df[revenue_col] = pd.to_numeric(df[revenue_col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    else:
        df[revenue_col] = df[revenue_col].fillna(0)

    # 處理「目標客戶」：將 1-5 欄位合併以便篩選
    customer_cols = ['目標客戶1', '目標客戶2', '目標客戶3', '目標客戶4', '目標客戶5']
    all_customers = set()
    for col in customer_cols:
        if col in df.columns:
            all_customers.update(df[col].dropna().unique())
    all_customers = sorted(list(all_customers))

    # --- 側邊欄篩選條件 ---
    st.sidebar.header("篩選條件")

    # 建立各個篩選器
    cat_filter = st.sidebar.multiselect("專案類別", options=df['專案類別'].unique())
    scene_filter = st.sidebar.multiselect("產業應用場景", options=df['產業應用場景'].unique())
    market_filter = st.sidebar.multiselect("市場", options=df['市場'].unique())
    revenue_grade_filter = st.sidebar.multiselect("營收等級", options=df['營收等級'].unique())
    customer_filter = st.sidebar.multiselect("目標客戶", options=all_customers)
    
    # NPDR 與 訂單起始點
    npdr_options = df['NPDR開案時間'].astype(str).unique()
    npdr_filter = st.sidebar.multiselect("NPDR開案時間", options=npdr_options)
    
    order_start_filter = st.sidebar.multiselect("預計訂單起始點", options=df['預計訂單起始點'].unique())

    # --- 執行篩選邏輯 ---
    df_filtered = df.copy()

    if cat_filter:
        df_filtered = df_filtered[df_filtered['專案類別'].isin(cat_filter)]
    if scene_filter:
        df_filtered = df_filtered[df_filtered['產業應用場景'].isin(scene_filter)]
    if market_filter:
        df_filtered = df_filtered[df_filtered['市場'].isin(market_filter)]
    if revenue_grade_filter:
        df_filtered = df_filtered[df_filtered['營收等級'].isin(revenue_grade_filter)]
    if npdr_filter:
        df_filtered = df_filtered[df_filtered['NPDR開案時間'].astype(str).isin(npdr_filter)]
    if order_start_filter:
        df_filtered = df_filtered[df_filtered['預計訂單起始點'].isin(order_start_filter)]
    
    if customer_filter:
        mask = df_filtered[customer_cols].apply(lambda x: x.isin(customer_filter).any(), axis=1)
        df_filtered = df_filtered[mask]

    # --- 儀表板關鍵指標 (KPIs) ---
    st.divider()
    
    total_revenue = df_filtered[revenue_col].sum()
    project_count = len(df_filtered)
    
    # 營收貢獻王邏輯
    if not df_filtered.empty and total_revenue > 0:
        top_project_row = df_filtered.loc[df_filtered[revenue_col].idxmax()]
        top_project_name = top_project_row['專案']
        top_project_rev = top_project_row[revenue_col]
        top_contributor_text = f"{top_project_name}"
    else:
        top_contributor_text = "無資料"
        top_project_rev = 0

    # KPI 顯示
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric(label="💰 預估總營收 (TWD)", value=f"{total_revenue:,.0f}")
    kpi2.metric(label="👑 營收貢獻王", value=top_contributor_text, delta=f"{top_project_rev:,.0f}")
    kpi3.metric(label="📊 篩選後專案數", value=project_count)

    st.divider()

    # --- 圖表區塊 ---
    if not df_filtered.empty:
        
        # 第一列圖表：類別佔比 & 訂單時程
        row1_col1, row1_col2 = st.columns(2)

        with row1_col1:
            st.subheader("📌 專案類別營收佔比")
            # [新增圖表 1] 圓餅圖：專案類別
            fig_pie = px.pie(df_filtered, values=revenue_col, names='專案類別', 
                             hole=0.4, # 甜甜圈圖樣式
                             title='各類別營收分佈')
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)

        with row1_col2:
            st.subheader("📅 預計訂單時程趨勢")
            # [新增圖表 2] 長條圖：預計訂單起始點 (排序後)
            # 先聚合資料並排序
            df_time = df_filtered.groupby('預計訂單起始點')[revenue_col].sum().reset_index()
            df_time = df_time.sort_values('預計訂單起始點') # 讓時間軸正確排序 (Q1, Q2, Q3...)
            
            fig_time = px.bar(df_time, x='預計訂單起始點', y=revenue_col,
                              text_auto='.2s', color=revenue_col, color_continuous_scale='Greens')
            fig_time.update_layout(xaxis_title="時間 (Quarter)", yaxis_title="預估營收")
            st.plotly_chart(fig_time, use_container_width=True)

        # 第二列圖表：市場分析 & 專案排行
        row2_col1, row2_col2 = st.columns(2)

        with row2_col1:
            st.subheader("🌍 市場 x 應用場景 交叉分析")
            # [新增圖表 3] 堆疊長條圖：市場 + 應用場景
            df_market = df_filtered.groupby(['市場', '產業應用場景'])[revenue_col].sum().reset_index()
            
            fig_market = px.bar(df_market, x='市場', y=revenue_col, color='產業應用場景',
                                title='各地區市場之應用場景分佈',
                                text_auto='.2s', barmode='stack')
            st.plotly_chart(fig_market, use_container_width=True)

        with row2_col2:
            st.subheader("🏆 專案營收 Top 10")
            # [原有圖表優化]
            df_chart = df_filtered.nlargest(10, revenue_col).sort_values(revenue_col, ascending=True)
            fig_bar = px.bar(df_chart, x=revenue_col, y='專案', orientation='h', text_auto='.2s',
                             color=revenue_col, color_continuous_scale='Blues')
            fig_bar.update_layout(xaxis_title="預估營收", yaxis_title="專案名稱")
            st.plotly_chart(fig_bar, use_container_width=True)

    else:
        st.warning("⚠️ 目前篩選條件下無資料，請調整左側篩選器。")

    st.divider()

    # --- 詳細資料表格 ---
    st.subheader("📋 詳細資料檢視")
    st.dataframe(df_filtered, use_container_width=True)

else:
    # 歡迎畫面
    st.info("👋 歡迎使用 Geckos Dashboard！請從左側上傳專案 Excel 檔案以開始分析。")