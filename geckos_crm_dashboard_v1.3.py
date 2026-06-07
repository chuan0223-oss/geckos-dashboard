import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# =========================================================================
# ⚙️ 網頁初始化、佈局與 CSS 注入
# =========================================================================
st.set_page_config(page_title="Geckos Customer Dashboard", layout="wide")

# 注入極致的 CSS：自動換行展開所有 Tabs，消滅隱藏與捲動的痛點！
st.markdown("""
    <style>
    /* 1. 設定右側資料面板固定不動 */
    div[data-testid="column"]:nth-of-type(2) {
        position: sticky !important;
        top: 60px !important;
        z-index: 100 !important;
        align-self: flex-start;
    }
    
    /* 2. 徹底打破 Streamlit 單行隱藏限制，改為自動換行 (Wrap) 展開所有頁籤 */
    div[data-testid="stTabs"] [data-baseweb="tab-list"] {
        display: flex !important;
        flex-wrap: wrap !important;
        gap: 8px !important;
        padding-bottom: 10px !important;
    }
    
    /* 3. 將每個頁籤做成類似按鈕的膠囊狀，讓換行排版時更美觀直覺 */
    div[data-testid="stTabs"] [data-baseweb="tab"] {
        flex: 0 0 auto !important;
        white-space: nowrap !important;
        background-color: rgba(242, 243, 244, 0.4) !important;
        border-radius: 6px !important;
        padding-left: 14px !important;
        padding-right: 14px !important;
        border-bottom: 2px solid transparent !important;
    }
    
    div[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {
        background-color: rgba(52, 152, 219, 0.1) !important;
        border-bottom: 2px solid #3498DB !important;
    }

    /* 4. 隱藏原生的左右滾動箭頭 (現在全展開了，不再需要箭頭) */
    div[data-testid="stTabs"] > div > div > button {
        display: none !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📊 Geckos Customer Relationship Managemen")

# =========================================================================
# 📂 左側側邊欄：資料上傳與篩選條件
# =========================================================================
st.sidebar.header("📂 資料管理中心")
uploaded_file = st.sidebar.file_uploader("請上傳最新的 Excel 檔案", type=["xlsx"])

def get_safe_options(df, col_name):
    if col_name and col_name in df.columns:
        opts = df[col_name].dropna().astype(str).unique().tolist()
        opts = [x for x in opts if x.lower() != 'nan' and x.strip() != '']
        return sorted(opts)
    return []

# =========================================================================
# 🚀 專屬產品 Roadmap 繪圖引擎
# =========================================================================
def create_product_roadmap(df_schedule, product_name):
    if '產品名稱' in df_schedule.columns:
        df_proj = df_schedule[df_schedule['產品名稱'] == product_name]
    elif '專案' in df_schedule.columns:
        df_proj = df_schedule[df_schedule['專案'] == product_name]
    else:
        return None, "時程表缺乏有效的產品/專案名稱欄位。"

    if df_proj.empty:
        return None, "查無此產品的時程規劃資料。"
    
    row = df_proj.iloc[0]
    milestones = []
    
    def parse_date(d):
        try:
            return pd.to_datetime(d)
        except:
            return pd.NaT

    start_date = parse_date(row.get('開案'))
    if pd.notna(start_date): milestones.append({'name': '開案', 'date': start_date, 'color': '#3498DB', 'symbol': 'triangle-right', 'size': 20})
        
    trans_npdr_date = parse_date(row.get('轉NPDR時間'))
    if pd.notna(trans_npdr_date): milestones.append({'name': '轉NPDR', 'date': trans_npdr_date, 'color': '#E67E22', 'symbol': 'hexagon', 'size': 18})

    npdr_date = parse_date(row.get('NPDR時間'))
    if pd.notna(npdr_date): milestones.append({'name': 'NPDR', 'date': npdr_date, 'color': '#D35400', 'symbol': 'pentagon', 'size': 18})

    dv_date = parse_date(row.get('設計驗證時間'))
    if pd.notna(dv_date): milestones.append({'name': '設計驗證(DV)', 'date': dv_date, 'color': '#F39C12', 'symbol': 'diamond', 'size': 18})
        
    ev_date = parse_date(row.get('工程驗證時間'))
    if pd.notna(ev_date): milestones.append({'name': '工程驗證(EV)', 'date': ev_date, 'color': '#9B59B6', 'symbol': 'square', 'size': 18})
        
    order_date = parse_date(row.get('預計訂單起始點'))
    if pd.notna(order_date): milestones.append({'name': '訂單起始', 'date': order_date, 'color': '#2ECC71', 'symbol': 'star', 'size': 24})
        
    if not milestones:
        return None, "此產品的時程表內缺乏有效的日期資料。"
        
    df_ms = pd.DataFrame(milestones).sort_values('date')
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df_ms['date'], y=[0] * len(df_ms),
        mode='lines', line=dict(color='#BDC3C7', width=3, dash='dot'),
        showlegend=False, hoverinfo='skip'
    ))
    
    for idx, ms in df_ms.reset_index(drop=True).iterrows():
        date_str = ms['date'].strftime('%Y-%m-%d')
        text_pos = "top center" if idx % 2 == 0 else "bottom center"
        
        fig.add_trace(go.Scatter(
            x=[ms['date']], y=[0],
            mode='markers+text',
            marker=dict(size=ms['size'], color=ms['color'], symbol=ms['symbol'], line=dict(width=2, color='white')),
            text=[f"<b>{ms['name']}</b><br>{date_str}"],
            textposition=text_pos,
            textfont=dict(size=12, color='#2C3E50'),
            name=ms['name'],
            hovertemplate=f"<b>{ms['name']}</b><br>日期: {date_str}<extra></extra>",
            cliponaxis=False  
        ))
        
    today = pd.Timestamp.today()
    upload_date_str = today.strftime('%Y-%m-%d')
    fig.add_vline(
        x=today.timestamp() * 1000, line_dash="dash", line_color="#E74C3C", 
        annotation_text=f"載入: {upload_date_str}", annotation_position="bottom right", annotation_font_size=12
    )

    min_date = df_ms['date'].min()
    max_date = df_ms['date'].max()
    plot_min = min(min_date, today) - pd.Timedelta(days=30)
    plot_max = max(max_date, today) + pd.Timedelta(days=30)

    fig.update_layout(
        xaxis=dict(showgrid=True, gridcolor='#F2F3F4', title="", range=[plot_min, plot_max]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.8, 0.8]), 
        height=280,
        margin=dict(l=40, r=40, t=30, b=30), 
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        showlegend=False
    )
    return fig, None

# =========================================================================
# 💾 主要資料流程序
# =========================================================================
if uploaded_file is not None:
    try:
        df_tracking = pd.read_excel(uploaded_file, sheet_name='送樣追蹤管理表')
        df_client = pd.read_excel(uploaded_file, sheet_name='客戶列表')
        df_schedule = pd.read_excel(uploaded_file, sheet_name='產品時程表')
        df_product = df_schedule.copy()

        if '產品名稱' in df_tracking.columns: df_tracking['產品名稱'] = df_tracking['產品名稱'].astype(str).str.strip()
        if '產品名稱' in df_product.columns: df_product['產品名稱'] = df_product['產品名稱'].astype(str).str.strip()
        if '產品名稱' in df_client.columns: df_client['產品名稱'] = df_client['產品名稱'].astype(str).str.strip()
        if '客戶' in df_tracking.columns: df_tracking['客戶'] = df_tracking['客戶'].astype(str).str.strip()
        if '客戶' in df_client.columns: df_client['客戶'] = df_client['客戶'].astype(str).str.strip()

        for col in ['客戶', '產品名稱', '產業類別', '應用類別', '目的']:
            if col not in df_client.columns:
                df_client[col] = '未標示'
                
        df_client['客戶'] = df_client['客戶'].ffill()
        df_client['產業類別'] = df_client['產業類別'].ffill()
        df_client_clean = df_client[['客戶', '產品名稱', '產業類別', '應用類別', '目的']].drop_duplicates(subset=['客戶', '產品名稱'], keep='first')
        
        df_client_clean = df_client_clean.rename(columns={'目的': '開發目的'})
        
        cols_to_drop = ['Lot No.', '數量', '單位']
        df_tracking = df_tracking.drop(columns=[c for c in cols_to_drop if c in df_tracking.columns], errors='ignore')

        prod_cols = ['產品名稱']
        for c in ['產品類別', '開案類別', '供應商/代理商', '動能客戶1', '動能客戶2', '動能客戶3']:
            if c in df_product.columns:
                prod_cols.append(c)
            
        df_main = pd.merge(df_tracking, df_product[prod_cols], on='產品名稱', how='left')
        df_main = pd.merge(df_main, df_client_clean, on=['客戶', '產品名稱'], how='left')

        df_main['送樣或出貨日期'] = pd.to_datetime(df_main['送樣或出貨日期'], errors='coerce')
        # 將送樣月份轉換為 'YYYY-MM' 的字串格式
        df_main['送樣月份'] = df_main['送樣或出貨日期'].dt.strftime('%Y-%m').fillna('未標示')
        df_main['營收'] = pd.to_numeric(df_main.get('營收', pd.Series([0]*len(df_main))), errors='coerce').fillna(0)
        
        str_cols = ['客戶', '產品名稱', '應用類別', '供應商/代理商', '開案類別', '產業類別', '出樣/出貨', 'Status', '測試結果', '目的', '開發目的', '動能客戶1', '動能客戶2', '動能客戶3']
        for col in str_cols:
            if col in df_main.columns:
                df_main[col] = df_main[col].astype(str).replace('nan', '未標示').str.strip()

    except Exception as e:
        st.error(f"⚠️ 檔案讀取失敗: {e}\n請確認上傳的 Excel 檔案格式。")
        st.stop()

    # =========================================================================
    # 🧩 區塊 1：側邊欄全局篩選條件
    # =========================================================================
    st.sidebar.markdown("---")
    st.sidebar.markdown("##### 🔍 篩選條件")
    filter_client = st.sidebar.multiselect("👤 客戶名稱", options=get_safe_options(df_main, '客戶'))
    filter_product = st.sidebar.multiselect("📦 產品名稱", options=get_safe_options(df_main, '產品名稱'))
    filter_app = st.sidebar.multiselect("📱 應用類別", options=get_safe_options(df_main, '應用類別'))
    filter_supplier = st.sidebar.multiselect("🏭 供應商", options=get_safe_options(df_main, '供應商/代理商'))
    filter_opentype = st.sidebar.multiselect("📂 開案類別", options=get_safe_options(df_main, '開案類別'))
    filter_industry = st.sidebar.multiselect("🏢 產業類別", options=get_safe_options(df_main, '產業類別'))

    df_filtered = df_main.copy()
    if filter_client: df_filtered = df_filtered[df_filtered['客戶'].isin(filter_client)]
    if filter_product: df_filtered = df_filtered[df_filtered['產品名稱'].isin(filter_product)]
    if filter_app: df_filtered = df_filtered[df_filtered['應用類別'].isin(filter_app)]
    if filter_supplier: df_filtered = df_filtered[df_filtered['供應商/代理商'].isin(filter_supplier)]
    if filter_opentype: df_filtered = df_filtered[df_filtered['開案類別'].isin(filter_opentype)]
    if filter_industry: df_filtered = df_filtered[df_filtered['產業類別'].isin(filter_industry)]

    # =========================================================================
    # 🧩 區塊 2：客戶與產品維度分析
    # =========================================================================
    st.subheader("🧩 客戶與產品維度分析")
    st.caption("💡 操作指南：在左側網格卡片尋找目標並點選「🔍 檢視分析」，右側面板將自動鎖定顯示。**所有的功能頁籤已全展開為多行矩陣，方便您一眼點選！**")
    
    col_grid, col_drill = st.columns([1.2, 1.6])
    
    if "active_view" not in st.session_state:
        st.session_state.active_view = None
        st.session_state.active_target = None

    with col_grid:
        view_mode = st.radio("請選擇網格視圖：", ["🏢 顯示客戶", "📦 顯示產品"], horizontal=True, label_visibility="collapsed")
        
        with st.container(height=700, border=False):
            if view_mode == "🏢 顯示客戶":
                filtered_clients = df_filtered['客戶'].dropna().unique().tolist()
                client_rev = df_filtered.groupby('客戶')['營收'].sum().to_dict()
                sorted_clients = sorted([{"name": c, "val": client_rev.get(c, 0)} for c in filtered_clients], key=lambda x: x["val"], reverse=True)
                
                if not sorted_clients:
                    st.info("查無符合條件的客戶。")
                else:
                    cols_per_row = 2
                    for i in range(0, len(sorted_clients), cols_per_row):
                        row_cols = st.columns(cols_per_row)
                        for j, col in enumerate(row_cols):
                            if i + j < len(sorted_clients):
                                c_data = sorted_clients[i + j]
                                with col:
                                    with st.container(border=True):
                                        st.markdown(f"<div style='font-size:16px; font-weight:bold; color:#2C3E50; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;' title='{c_data['name']}'>🏢 {c_data['name']}</div>", unsafe_allow_html=True)
                                        st.markdown(f"<div style='font-size:22px; font-weight:900; color:#2980B9; margin-bottom:10px;'>{c_data['val']:,.0f} <span style='font-size:12px;color:gray;'>TWD</span></div>", unsafe_allow_html=True)
                                        if st.button("🔍 檢視分析", key=f"btn_c_{c_data['name']}", use_container_width=True):
                                            st.session_state.active_view = 'client'
                                            st.session_state.active_target = c_data['name']
                                            st.rerun()
                                        
            elif view_mode == "📦 顯示產品":
                filtered_products = df_filtered['產品名稱'].dropna().unique().tolist()
                prod_stats = []
                for p in filtered_products:
                    df_p_temp = df_filtered[df_filtered['產品名稱'] == p]
                    sample_cnt = df_p_temp['出樣/出貨'].str.contains('出樣|出样', na=False).sum()
                    ship_cnt = df_p_temp['出樣/出貨'].str.contains('出貨|出货', na=False).sum()
                    prod_stats.append({"name": p, "sample": sample_cnt, "ship": ship_cnt})
                
                sorted_prods = sorted(prod_stats, key=lambda x: (x["sample"], x["ship"]), reverse=True)
                
                if not sorted_prods:
                    st.info("查無符合條件的產品。")
                else:
                    cols_per_row = 2
                    for i in range(0, len(sorted_prods), cols_per_row):
                        row_cols = st.columns(cols_per_row)
                        for j, col in enumerate(row_cols):
                            if i + j < len(sorted_prods):
                                p_data = sorted_prods[i + j]
                                with col:
                                    with st.container(border=True):
                                        st.markdown(f"<div style='font-size:16px; font-weight:bold; color:#2C3E50; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;' title='{p_data['name']}'>📦 {p_data['name']}</div>", unsafe_allow_html=True)
                                        st.markdown(f"<div style='font-size:19px; font-weight:900; color:#16A085; margin-bottom:2px;'>{p_data['sample']} <span style='font-size:12px;color:gray;'>次送樣</span></div>", unsafe_allow_html=True)
                                        st.markdown(f"<div style='font-size:16px; font-weight:700; color:#D35400; margin-bottom:10px;'>{p_data['ship']} <span style='font-size:12px;color:gray;'>次出貨</span></div>", unsafe_allow_html=True)
                                        if st.button("🔍 檢視分析", key=f"btn_p_{p_data['name']}", use_container_width=True):
                                            st.session_state.active_view = 'product'
                                            st.session_state.active_target = p_data['name']
                                            st.rerun()

    # --- 右側：無縫連動深度穿透面板 ---
    with col_drill:
        with st.container(border=True):
            
            # =====================================================
            # 視圖 A：顯示客戶
            # =====================================================
            if st.session_state.active_view == 'client' and st.session_state.active_target:
                target_client = st.session_state.active_target
                st.markdown(f"### 🏢 客戶深度分析：【 {target_client} 】")
                tab1, tab2, tab3 = st.tabs(["📋 客戶資訊", "📦 送樣歷程", "💰 累積營收"])
                df_c = df_filtered[df_filtered['客戶'] == target_client]
                
                with tab1:
                    industry = df_c['產業類別'].iloc[0] if not df_c['產業類別'].empty else "未標示"
                    sent_products = [p for p in df_c['產品名稱'].unique() if str(p) not in ['nan', '未標示', '']]
                    products_str = "、".join(sent_products) if sent_products else "暫無送樣產品紀錄"
                    
                    st.info(f"**👤 客戶名稱**：{target_client}\n\n**🏢 產業類別**：{industry}\n\n**📦 曾測試/採用產品**：{products_str}")
                    
                    st.markdown("**🎯 開發目的**：")
                    purposes = [p for p in df_c.get('開發目的', pd.Series(dtype=str)).unique() if str(p).strip() not in ["", "nan", "未標示", "None"]]
                    if purposes:
                        for i, p in enumerate(purposes, 1): st.write(f"{i}. {p}")
                    else:
                        st.caption("暫無明確開發目的紀錄。")

                with tab2:
                    st.markdown("##### 📊 本客戶各產品送樣次數分佈")
                    df_sample_c = df_c[df_c['出樣/出貨'].str.contains('出樣|出样', na=False)]
                    if not df_sample_c.empty:
                        df_sample_size_c = df_sample_c.groupby('產品名稱').size().reset_index(name='送樣次數')
                        df_sample_max_c = df_sample_c.groupby('產品名稱')['送樣月份'].max().reset_index(name='最後送樣月份')
                        df_sample_agg_c = pd.merge(df_sample_size_c, df_sample_max_c, on='產品名稱')
                        
                        df_sample_agg_c['圖表標籤'] = df_sample_agg_c['送樣次數'].astype(str) + "次 (" + df_sample_agg_c['最後送樣月份'] + ")"
                        fig_c_sample = px.bar(df_sample_agg_c, x='產品名稱', y='送樣次數', text='圖表標籤', hover_data=['最後送樣月份'], color_discrete_sequence=['#16A085'])
                        fig_c_sample.update_traces(textposition='outside', textfont_size=11)
                        
                        max_y_c = df_sample_agg_c['送樣次數'].max()
                        fig_c_sample.update_yaxes(range=[0, max_y_c * 1.3 + 0.5])
                        fig_c_sample.update_layout(margin=dict(t=40, b=10), height=300, yaxis_title="送樣次數", xaxis_title="")
                        st.plotly_chart(fig_c_sample, use_container_width=True, key=f"bar_c_{target_client}")
                        
                        st.markdown("---")
                        st.markdown("##### 📝 送樣歷程追蹤明細")
                        prods_sampled = df_sample_c['產品名稱'].unique()
                        for prod in prods_sampled:
                            prod_samples = df_sample_c[df_sample_c['產品名稱'] == prod].sort_values('送樣或出貨日期')
                            sample_count = len(prod_samples)
                            with st.expander(f"📦 {prod} (累計送樣: {sample_count} 次)"):
                                display_cols = [c for c in ['送樣或出貨日期', '單號', 'Status', '測試結果'] if c in prod_samples.columns]
                                disp_df = prod_samples[display_cols].copy()
                                if '送樣或出貨日期' in disp_df.columns:
                                    disp_df['送樣或出貨日期'] = pd.to_datetime(disp_df['送樣或出貨日期']).dt.strftime('%Y-%m-%d')
                                st.dataframe(disp_df, use_container_width=True, hide_index=True)
                    else:
                        st.warning("💡 該客戶目前尚無『出樣』紀錄。")

                with tab3:
                    total_revenue = df_c['營收'].sum()
                    if total_revenue > 0:
                        st.metric(label="📊 總體營收貢獻金額", value=f"{total_revenue:,.0f} TWD")
                        
                        st.markdown("##### 📈 每月產品營收貢獻分佈")
                        df_rev_c = df_c[df_c['營收'] > 0]
                        df_rev_structure_c = df_rev_c.groupby(['送樣月份', '產品名稱'])['營收'].sum().reset_index()
                        df_rev_structure_c = df_rev_structure_c.rename(columns={'送樣月份': '出貨月份'}).sort_values('出貨月份')
                        
                        fig_c_rev = px.bar(
                            df_rev_structure_c, 
                            x='出貨月份', 
                            y='營收', 
                            text='營收',
                            color='產品名稱',
                            barmode='group',
                            color_discrete_sequence=px.colors.qualitative.Set3
                        )
                        fig_c_rev.update_traces(texttemplate='%{text:,.0f}', textposition='outside', textfont_size=11)
                        fig_c_rev.update_xaxes(type='category')
                        max_y_c_rev = df_rev_structure_c['營收'].max()
                        fig_c_rev.update_yaxes(range=[0, max_y_c_rev * 1.3])
                        fig_c_rev.update_layout(margin=dict(t=40, b=10), height=350, xaxis_title="出貨月份", yaxis_title="累計營收 (TWD)")
                        st.plotly_chart(fig_c_rev, use_container_width=True, key=f"rev_c_time_{target_client}")
                        
                        st.markdown("---")
                        st.markdown("##### 📝 營收明細列表")
                        df_c_rev_table = df_c[df_c['營收'] > 0][['送樣月份', '產品名稱', '營收']].sort_values('送樣月份')
                        df_c_rev_table = df_c_rev_table.rename(columns={'送樣月份': '出貨月份'})
                        st.dataframe(df_c_rev_table, use_container_width=True, hide_index=True)
                    else:
                        st.info("💡 目前該客戶尚無營收。")

            # =====================================================
            # 視圖 B：顯示產品
            # =====================================================
            elif st.session_state.active_view == 'product' and st.session_state.active_target:
                target_prod = st.session_state.active_target
                st.markdown(f"### 📦 產品型號深度分析：【 {target_prod} 】")
                
                tab1, tab2, tab3, tab4, tab5 = st.tabs(["🔬 產品資訊與動能客戶", "📝 測試結果明細", "🏆 客戶Top10", "📅 每月營收分佈", "🚀 專案研發 Roadmap"])
                df_p = df_filtered[df_filtered['產品名稱'] == target_prod]
                
                with tab1:
                    df_p_schedule = df_schedule[df_schedule['產品名稱'] == target_prod] if '產品名稱' in df_schedule.columns else pd.DataFrame()
                    p_cat = df_p_schedule['產品類別'].iloc[0] if not df_p_schedule.empty and pd.notna(df_p_schedule['產品類別'].iloc[0]) else '未標示'
                    p_open = df_p_schedule['開案類別'].iloc[0] if not df_p_schedule.empty and pd.notna(df_p_schedule['開案類別'].iloc[0]) else '未標示'
                    p_sup = df_p_schedule['供應商/代理商'].iloc[0] if not df_p_schedule.empty and pd.notna(df_p_schedule['供應商/代理商'].iloc[0]) else '未標示'
                    
                    st.info(f"**🏷️ 產品類別**：{p_cat} ｜ **📂 開案類別**：{p_open} ｜ **🏭 供應商/代理商**：{p_sup}")
                    
                    k_list = []
                    for k_col in ['動能客戶1', '動能客戶2', '動能客戶3']:
                        if k_col in df_p.columns:
                            valid_vals = [str(x) for x in df_p[k_col].unique() if str(x).strip() not in ['nan', 'None', '', '未標示']]
                            for v in valid_vals:
                                if v not in k_list:
                                    k_list.append(v)
                    
                    if k_list:
                        st.success(f"**🔥 動能客戶**： {', '.join(k_list)}")
                    else:
                        st.success("**🔥 動能客戶**： 暫無紀錄")
                    
                    st.markdown("##### 產品各客戶指標統計")
                    df_prod_g = df_p.groupby('客戶').apply(
                        lambda x: pd.Series({
                            '送樣次數': x['出樣/出貨'].str.contains('出樣|出样', na=False).sum(),
                            '出貨次數': x['出樣/出貨'].str.contains('出貨|出货', na=False).sum(),
                            '最新狀態': x['Status'].iloc[-1] if not x.empty else '未標示'
                        })
                    ).reset_index().rename(columns={'最新狀態': 'Status'})
                    st.dataframe(df_prod_g, use_container_width=True, hide_index=True)

                with tab2:
                    st.markdown("##### 📊 本產品各客戶送樣次數分佈")
                    df_sample_p = df_p[df_p['出樣/出貨'].str.contains('出樣|出样', na=False)]
                    if not df_sample_p.empty:
                        df_sample_size_p = df_sample_p.groupby('客戶').size().reset_index(name='送樣次數')
                        df_sample_max_p = df_sample_p.groupby('客戶')['送樣月份'].max().reset_index(name='最後送樣月份')
                        df_sample_agg_p = pd.merge(df_sample_size_p, df_sample_max_p, on='客戶')
                        
                        df_sample_agg_p['圖表標籤'] = df_sample_agg_p['送樣次數'].astype(str) + "次 (" + df_sample_agg_p['最後送樣月份'] + ")"
                        fig_p_sample = px.bar(df_sample_agg_p, x='客戶', y='送樣次數', text='圖表標籤', hover_data=['最後送樣月份'], color_discrete_sequence=['#3498DB'])
                        fig_p_sample.update_traces(textposition='outside', textfont_size=11)
                        
                        max_y_p = df_sample_agg_p['送樣次數'].max()
                        fig_p_sample.update_yaxes(range=[0, max_y_p * 1.3 + 0.5])
                        fig_p_sample.update_layout(margin=dict(t=40, b=10), height=300, yaxis_title="送樣次數", xaxis_title="")
                        st.plotly_chart(fig_p_sample, use_container_width=True, key=f"bar_{target_prod}")
                    else:
                        st.info("本產品目前尚無『出樣』紀錄可繪製圖表。")
                        
                    st.markdown("---")
                    st.markdown("##### 📝 歷次測試結果列表")
                    df_hover = df_p.copy()
                    df_hover['測試結果'] = df_hover['測試結果'].replace('未標示', '無填寫結果')
                    
                    if '送樣或出貨日期' in df_hover.columns:
                        df_hover['送樣或出貨日期'] = pd.to_datetime(df_hover['送樣或出貨日期']).dt.strftime('%Y-%m-%d')
                        
                    df_test_results = df_hover[['送樣或出貨日期', '客戶', 'Status', '測試結果']].sort_values('送樣或出貨日期', ascending=False)
                    if not df_test_results.empty:
                        st.dataframe(df_test_results, use_container_width=True, hide_index=True)
                    else:
                        st.info("該產品目前尚無相關紀錄。")
                        
                with tab3:
                    st.markdown(f"##### 🏆 {target_prod} 客戶營收貢獻度 TOP 10")
                    df_rev_client_p = df_p.groupby('客戶')['營收'].sum().reset_index()
                    df_rev_client_p = df_rev_client_p[df_rev_client_p['營收'] > 0].nlargest(10, '營收').sort_values('營收', ascending=True)
                    if not df_rev_client_p.empty:
                        fig_p_rev = px.bar(df_rev_client_p, x='營收', y='客戶', orientation='h', text='營收', color='營收', color_continuous_scale='GnBu')
                        fig_p_rev.update_traces(texttemplate='%{text:,.0f} TWD', textposition='outside', textfont_size=11)
                        
                        max_x_p = df_rev_client_p['營收'].max()
                        fig_p_rev.update_xaxes(range=[0, max_x_p * 1.3])
                        fig_p_rev.update_layout(margin=dict(t=40, b=10, r=40), height=350, showlegend=False, xaxis_title="累計營收金額", yaxis_title="客戶名稱")
                        st.plotly_chart(fig_p_rev, use_container_width=True, key=f"rev_{target_prod}")
                    else:
                        st.info("💡 目前該產品尚無產生實際營收之客戶。")

                with tab4:
                    st.markdown(f"##### 📅 {target_prod} 每月客戶營收分佈")
                    df_rev_time_p = df_p[df_p['營收'] > 0]
                    if not df_rev_time_p.empty:
                        df_rev_structure_p = df_rev_time_p.groupby(['送樣月份', '客戶'])['營收'].sum().reset_index()
                        df_rev_structure_p = df_rev_structure_p.rename(columns={'送樣月份': '出貨月份'}).sort_values('出貨月份')
                        
                        fig_p_rev_time = px.bar(
                            df_rev_structure_p,
                            x='出貨月份',
                            y='營收',
                            text='營收',
                            color='客戶',
                            barmode='group',
                            color_discrete_sequence=px.colors.qualitative.Set3
                        )
                        fig_p_rev_time.update_traces(texttemplate='%{text:,.0f}', textposition='outside', textfont_size=11)
                        fig_p_rev_time.update_xaxes(type='category')
                        max_y_p_rev = df_rev_structure_p['營收'].max()
                        fig_p_rev_time.update_yaxes(range=[0, max_y_p_rev * 1.3])
                        fig_p_rev_time.update_layout(margin=dict(t=40, b=10), height=350, xaxis_title="出貨月份", yaxis_title="營收金額 (TWD)")
                        st.plotly_chart(fig_p_rev_time, use_container_width=True, key=f"rev_time_{target_prod}")
                    else:
                        st.info("💡 目前該產品尚無產生實際營收之客戶。")

                with tab5:
                    st.markdown(f"##### 🎯 {target_prod} 關鍵里程碑")
                    if not df_schedule.empty:
                        fig, error_msg = create_product_roadmap(df_schedule, target_prod)
                        if fig:
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.info(error_msg)
                    else:
                        st.warning("⚠️ 系統未能載入「產品時程表」，請確認上傳的 Excel 檔案包含此 Sheet。")
                        
            else:
                st.markdown("<div style='text-align: center; padding: 180px 20px; color: gray;'>🔍 <b>操作提示</b><br><br>請點擊左側網格卡片上的【🔍 檢視分析】，<br>此處將自動鎖定並呈獻專屬的深度分析資料。</div>", unsafe_allow_html=True)

else:
    st.info("👋 歡迎使用 GGeckos Customer Relationship Managemen。請先在左側面板上傳最新的 Excel 數據表。")
