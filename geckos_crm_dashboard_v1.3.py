import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# =========================================================================
# ⚙️ 網頁初始化與佈局設定
# =========================================================================
st.set_page_config(page_title="Geckos CRM Dashboard", layout="wide")

# =========================================================================
# ⬇️ 核心數據載入與清洗處理
# =========================================================================
st.title("📊 Geckos CRM 戰情室 (V1.3 - 修正資料關聯膨脹)")

# 檔案上傳保留於側邊欄
st.sidebar.header("📂 資料管理中心")
uploaded_file = st.sidebar.file_uploader("請上傳「客戶產品列表_V2」Excel 檔案", type=["xlsx"])

def get_safe_options(df, col_name):
    """安全地從指定的 DataFrame 欄位取得不含空值的排序唯一值清單"""
    if col_name and col_name in df.columns:
        opts = df[col_name].dropna().astype(str).unique().tolist()
        opts = [x for x in opts if x.lower() != 'nan' and x.strip() != '']
        return sorted(opts)
    return []

if uploaded_file is not None:
    try:
        # 同步讀取三個核心資料表
        df_tracking = pd.read_excel(uploaded_file, sheet_name='送樣追蹤管理表')
        df_product = pd.read_excel(uploaded_file, sheet_name='產品列表')
        df_client = pd.read_excel(uploaded_file, sheet_name='客戶列表')

        # [UI/UX 防護] 處理 Excel 因合併儲存格匯出時產生的斷層空值 (NaN)
        df_client['客戶'] = df_client['客戶'].ffill()
        df_client['產業類別'] = df_client['產業類別'].ffill()
        
        # 🔥【V1.3 重要修正】在關聯前，先將客戶列表依據「客戶+產品名稱」進行去重
        # 避免因為一個客戶同個產品有多行備註，導致主表 Merge 時營收翻倍
        df_client_clean = df_client[['客戶', '產品名稱', '產業類別', '應用類別']].drop_duplicates(subset=['客戶', '產品名稱'], keep='first')
        
        # 依據架構共識，排除忽略之非必要統計欄位
        cols_to_drop = ['Lot No.', '數量', '單位']
        df_tracking = df_tracking.drop(columns=[c for c in cols_to_drop if c in df_tracking.columns], errors='ignore')

        # [資料庫多維度關聯整合]
        # 1. 關聯產品列表屬性
        df_main = pd.merge(
            df_tracking, 
            df_product[['產品名稱', '產品類別', '開案類別', '供應商/代理商']], 
            on='產品名稱', 
            how='left'
        )
        # 2. 關聯客戶列表屬性 (透過已去重的 df_client_clean 進行雙鍵複合關聯)
        df_main = pd.merge(
            df_main, 
            df_client_clean, 
            on=['客戶', '產品名稱'], 
            how='left'
        )

        # 數值與時間欄位格式標準化
        df_main['送樣或出貨日期'] = pd.to_datetime(df_main['送樣或出貨日期'], errors='coerce')
        df_main['送樣月份'] = df_main['送樣或出貨日期'].dt.to_period('M').astype(str)
        df_main['營收'] = pd.to_numeric(df_main['營收'], errors='coerce').fillna(0)
        
        # 填補未歸類字串，避免前端篩選器顯示錯誤
        str_cols = ['客戶', '產品名稱', '應用類別', '供應商/代理商', '開案類別', '產業類別', '出樣/出貨']
        for col in str_cols:
            if col in df_main.columns:
                df_main[col] = df_main[col].astype(str).replace('nan', '未標示')

    except Exception as e:
        st.error(f"⚠️ 檔案讀取或資料庫多維關聯失敗: {e}")
        st.stop()

    # =========================================================================
    # 🧩 [區塊 1] 橫向多維度篩選器
    # =========================================================================
    with st.container(border=True):
        st.markdown("##### 🔍 橫向多元關鍵指標篩選控制台")
        
        filter_row1_col1, filter_row1_col2, filter_row1_col3 = st.columns(3)
        filter_row2_col1, filter_row2_col2, filter_row2_col3 = st.columns(3)
        
        with filter_row1_col1:
            filter_client = st.multiselect("👤 客戶名稱", options=get_safe_options(df_main, '客戶'))
        with filter_row1_col2:
            filter_product = st.multiselect("📦 產品名稱", options=get_safe_options(df_main, '產品名稱'))
        with filter_row1_col3:
            filter_app = st.multiselect("📱 應用類別", options=get_safe_options(df_main, '應用類別'))
            
        with filter_row2_col1:
            filter_supplier = st.multiselect("🏭 供應商", options=get_safe_options(df_main, '供應商/代理商'))
        with filter_row2_col2:
            filter_opentype = st.multiselect("📂 開案類別", options=get_safe_options(df_main, '開案類別'))
        with filter_row2_col3:
            filter_industry = st.multiselect("🏢 產業類別", options=get_safe_options(df_main, '產業類別'))

    # 全域資料過濾邏輯連動
    df_filtered = df_main.copy()
    if filter_client: df_filtered = df_filtered[df_filtered['客戶'].isin(filter_client)]
    if filter_product: df_filtered = df_filtered[df_filtered['產品名稱'].isin(filter_product)]
    if filter_app: df_filtered = df_filtered[df_filtered['應用類別'].isin(filter_app)]
    if filter_supplier: df_filtered = df_filtered[df_filtered['供應商/代理商'].isin(filter_supplier)]
    if filter_opentype: df_filtered = df_filtered[df_filtered['開案類別'].isin(filter_opentype)]
    if filter_industry: df_filtered = df_filtered[df_filtered['產業類別'].isin(filter_industry)]

    st.markdown("<br>", unsafe_allow_html=True)

    # =========================================================================
    # 📊 數據視覺化圖表配置排列
    # =========================================================================
    
    graph_col_left, graph_col_right = st.columns([1.2, 1])

    # [區塊 2] 送樣次數統計圖表 (長條圖)
    with graph_col_left:
        st.subheader("📦 產品送樣次數與最新時程統計")
        df_sample = df_filtered[df_filtered['出樣/出貨'] == '出樣']
        if not df_sample.empty:
            df_sample_agg = df_sample.groupby(['客戶', '產品名稱']).agg(
                送樣次數=('單號', 'count'),
                最後送樣月份=('送樣月份', 'max')
            ).reset_index()
            
            df_sample_agg['圖表標籤'] = df_sample_agg['送樣次數'].astype(str) + "次 (" + df_sample_agg['最後送樣月份'] + ")"

            fig2 = px.bar(
                df_sample_agg, 
                x='客戶', 
                y='送樣次數', 
                color='產品名稱',
                text='圖表標籤',
                hover_data=['最後送樣月份'],
                barmode='group',
                color_discrete_sequence=px.colors.qualitative.Safe
            )
            fig2.update_traces(textposition='outside', textfont_size=11)
            fig2.update_layout(margin=dict(t=20, b=10), height=380, xaxis_title="客戶名稱", yaxis_title="送樣累計次數")
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("💡 當前篩選條件下無任何『出樣』紀錄。")

    # [區塊 4] 客戶 TOP10 (依照營收排名)
    with graph_col_right:
        st.subheader("🏆 客戶營收贡献度 TOP 10")
        df_rev_client = df_filtered.groupby('客戶')['營收'].sum().reset_index()
        df_rev_client = df_rev_client[df_rev_client['營收'] > 0].nlargest(10, '營收').sort_values('營收', ascending=True)

        if not df_rev_client.empty:
            fig4 = px.bar(
                df_rev_client, 
                x='營收', 
                y='客戶', 
                orientation='h',
                text='營收',
                color='營收',
                color_continuous_scale='GnBu'
            )
            fig4.update_traces(texttemplate='%{text:,.0f} TWD', textposition='outside', textfont_size=11)
            fig4.update_layout(margin=dict(t=20, b=10), height=380, showlegend=False, xaxis_title="累計營收金額", yaxis_title="客戶名稱")
            st.plotly_chart(fig4, use_container_width=True)
        else:
            st.info("💡 當前篩選條件下尚無產生實際營收之客戶。")

    st.divider()

    # [區塊 3] 累積營收圖表 (堆疊面積圖)
    with st.container():
        st.subheader("📈 企業整體與產品別累積營收趨勢 (堆疊視覺版)")
        df_trend = df_filtered[(df_filtered['送樣月份'] != 'NaT') & (df_filtered['營收'] > 0)].copy()
        
        if not df_trend.empty:
            all_months = sorted(df_trend['送樣月份'].unique())
            all_products = df_trend['產品名稱'].unique()
            
            multi_idx = pd.MultiIndex.from_product([all_months, all_products], names=['送樣月份', '產品名稱'])
            df_monthly_rev = df_trend.groupby(['送樣月份', '產品名稱'])['營收'].sum().reset_index()
            df_monthly_rev = df_monthly_rev.set_index(['送樣月份', '產品名稱']).reindex(multi_idx, fill_value=0).reset_index()
            
            df_monthly_rev['累積營收'] = df_monthly_rev.groupby('產品名稱')['營收'].cumsum()
            df_monthly_rev = df_monthly_rev.sort_values(by='送樣月份')

            fig3 = px.area(
                df_monthly_rev, 
                x='送樣月份', 
                y='累積營收', 
                color='產品名稱',
                line_group='產品名稱',
                markers=True,
                color_discrete_sequence=px.colors.qualitative.Vivid,
                hover_data={'營收': ':,.0f'}
            )
            fig3.update_layout(
                xaxis_title="營收統計月份", 
                yaxis_title="總體累積營收 (TWD)",
                hovermode="x unified",
                height=420,
                margin=dict(t=15, b=10)
            )
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("💡 當前篩選範圍內缺乏含有效日期的營收變動紀錄。")

else:
    st.info("👋 歡迎使用 Geckos CRM 系統。請先在左側面板上傳最新的「客戶產品列表_V2.xlsx」數據表。")