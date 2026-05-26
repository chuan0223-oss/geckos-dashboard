import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# =========================================================================
# ⚙️ 網頁初始化與佈局設定
# =========================================================================
st.set_page_config(page_title="Geckos Customer Dashboard", layout="wide")
st.title("📊 Geckos Customer Dashboard (V7.6)")

st.sidebar.header("📂 資料管理中心")
uploaded_file = st.sidebar.file_uploader("請上傳「客戶產品列表_V2」Excel 檔案", type=["xlsx"])

def get_safe_options(df, col_name):
    if col_name and col_name in df.columns:
        opts = df[col_name].dropna().astype(str).unique().tolist()
        opts = [x for x in opts if x.lower() != 'nan' and x.strip() != '']
        return sorted(opts)
    return []

# =========================================================================
# 🚀 專屬產品 Roadmap 繪圖引擎 (V7.6 優化版)
# =========================================================================
def create_product_roadmap(df_schedule, product_name):
    """提取特定專案的時程，並繪製專屬的水平研發全週期 Roadmap"""
    df_proj = df_schedule[df_schedule['專案'] == product_name]
    if df_proj.empty:
        return None, "查無此產品的時程規劃資料（請確認『產品時程表』中是否有對應的專案名稱）。"
    
    row = df_proj.iloc[0]
    milestones = []
    
    def parse_date(d):
        try:
            return pd.to_datetime(d)
        except:
            return pd.NaT

    # 1. 開案節點
    start_date = parse_date(row.get('開案'))
    if pd.notna(start_date): 
        milestones.append({'name': '開案', 'date': start_date, 'color': '#3498DB', 'symbol': 'triangle-right', 'size': 20})
        
    # 2. NPDR / DV 節點
    npdr_date = parse_date(row.get('NPDR時間'))
    trans_npdr_date = parse_date(row.get('轉NPDR時間'))
    dv_date = parse_date(row.get('設計驗證時間'))
    
    if pd.notna(dv_date):
        milestones.append({'name': '設計驗證 (DV)', 'date': dv_date, 'color': '#F39C12', 'symbol': 'diamond', 'size': 18})
    elif pd.notna(npdr_date):
        milestones.append({'name': 'NPDR', 'date': npdr_date, 'color': '#F39C12', 'symbol': 'diamond', 'size': 18})
    elif pd.notna(trans_npdr_date):
        milestones.append({'name': '轉NPDR', 'date': trans_npdr_date, 'color': '#F39C12', 'symbol': 'diamond', 'size': 18})
        
    # 3. 工程驗證 EV
    ev_date = parse_date(row.get('工程驗證時間'))
    if pd.notna(ev_date): 
        milestones.append({'name': '工程驗證 (EV)', 'date': ev_date, 'color': '#9B59B6', 'symbol': 'square', 'size': 18})
        
    # 4. 預計訂單起始點
    order_date = parse_date(row.get('預計訂單起始點'))
    if pd.notna(order_date): 
        milestones.append({'name': '預計訂單起始點', 'date': order_date, 'color': '#2ECC71', 'symbol': 'star', 'size': 24})
        
    if not milestones:
        return None, "此產品的時程表內缺乏有效的日期資料。"
        
    df_ms = pd.DataFrame(milestones).sort_values('date')
    
    fig = go.Figure()
    
    # 繪製底部連線 (時間軸軌道)
    fig.add_trace(go.Scatter(
        x=df_ms['date'], y=[0] * len(df_ms),
        mode='lines', line=dict(color='#BDC3C7', width=3, dash='dot'),
        showlegend=False, hoverinfo='skip'
    ))
    
    # 繪製各個里程碑節點
    for _, ms in df_ms.iterrows():
        date_str = ms['date'].strftime('%Y-%m-%d')
        fig.add_trace(go.Scatter(
            x=[ms['date']], y=[0],
            mode='markers+text',
            marker=dict(size=ms['size'], color=ms['color'], symbol=ms['symbol'], line=dict(width=2, color='white')),
            text=[f"<b>{ms['name']}</b><br>{date_str}"],
            textposition="top center",
            textfont=dict(size=13, color='#2C3E50'),
            name=ms['name'],
            hovertemplate=f"<b>{ms['name']}</b><br>日期: {date_str}<extra></extra>",
            cliponaxis=False  # [優化 1] 允許文字超越畫布邊界，防止被截斷
        ))
        
    # [優化 2] 將紅色虛線提示改為自動顯示當前上傳解析的日期 (格式: 西元年-月-日)
    today = pd.Timestamp.today()
    upload_date_str = today.strftime('%Y-%m-%d')
    fig.add_vline(
        x=today.timestamp() * 1000, line_dash="dash", line_color="#E74C3C", 
        annotation_text=upload_date_str, annotation_position="bottom right", annotation_font_size=12
    )

    # [優化 1] 自動計算自適應 X 軸範圍，前後各外推 25 天，確保左右邊緣的字體完美顯示
    min_date = df_ms['date'].min()
    max_date = df_ms['date'].max()
    plot_min = min(min_date, today) - pd.Timedelta(days=25)
    plot_max = max(max_date, today) + pd.Timedelta(days=25)

    # 圖表排版與美化
    fig.update_layout(
        xaxis=dict(showgrid=True, gridcolor='#F2F3F4', title="時間推進軸", range=[plot_min, plot_max]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-1, 1.5]),
        height=280,
        margin=dict(l=40, r=40, t=40, b=20),  # 加大左右邊距邊框空間
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
        df_product = pd.read_excel(uploaded_file, sheet_name='產品列表')
        df_client = pd.read_excel(uploaded_file, sheet_name='客戶列表')
        
        try:
            df_schedule = pd.read_excel(uploaded_file, sheet_name='產品時程表')
        except:
            df_schedule = pd.DataFrame()

        df_client['客戶'] = df_client['客戶'].ffill()
        df_client['產業類別'] = df_client['產業類別'].ffill()
        df_client_clean = df_client[['客戶', '產品名稱', '產業類別', '應用類別']].drop_duplicates(subset=['客戶', '產品名稱'], keep='first')
        
        cols_to_drop = ['Lot No.', '數量', '單位']
        df_tracking = df_tracking.drop(columns=[c for c in cols_to_drop if c in df_tracking.columns], errors='ignore')

        prod_cols = ['產品名稱', '產品類別', '開案類別', '供應商/代理商']
        for k_col in ['動能客戶1', '動能客戶2', '動能客戶3']:
            if k_col in df_product.columns:
                prod_cols.append(k_col)
            
        df_main = pd.merge(df_tracking, df_product[prod_cols], on='產品名稱', how='left')
        df_main = pd.merge(df_main, df_client_clean, on=['客戶', '產品名稱'], how='left')

        df_main['送樣或出貨日期'] = pd.to_datetime(df_main['送樣或出貨日期'], errors='coerce')
        df_main['送樣月份'] = df_main['送樣或出貨日期'].dt.strftime('%Y-%m').fillna('未標示')
        df_main['營收'] = pd.to_numeric(df_main['營收'], errors='coerce').fillna(0)
        
        str_cols = ['客戶', '產品名稱', '應用類別', '供應商/代理商', '開案類別', '產業類別', '出樣/出貨', 'Status', '測試結果', '目的', '動能客戶1', '動能客戶2', '動能客戶3']
        for col in str_cols:
            if col in df_main.columns:
                df_main[col] = df_main[col].astype(str).replace('nan', '未標示').str.strip()

    except Exception as e:
        st.error(f"⚠️ 檔案讀取失敗: {e}")
        st.stop()

    # =========================================================================
    # 🧩 區塊 1：篩選條件
    # =========================================================================
    with st.container(border=True):
        st.markdown("##### 🔍 篩選條件")
        filter_row1_col1, filter_row1_col2, filter_row1_col3 = st.columns(3)
        filter_row2_col1, filter_row2_col2, filter_row2_col3 = st.columns(3)
        
        with filter_row1_col1: filter_client = st.multiselect("👤 客戶名稱", options=get_safe_options(df_main, '客戶'))
        with filter_row1_col2: filter_product = st.multiselect("📦 產品名稱", options=get_safe_options(df_main, '產品名稱'))
        with filter_row1_col3: filter_app = st.multiselect("📱 應用類別", options=get_safe_options(df_main, '應用類別'))
        with filter_row2_col1: filter_supplier = st.multiselect("🏭 供應商", options=get_safe_options(df_main, '供應商/代理商'))
        with filter_row2_col2: filter_opentype = st.multiselect("📂 開案類別", options=get_safe_options(df_main, '開案類別'))
        with filter_row2_col3: filter_industry = st.multiselect("🏢 產業類別", options=get_safe_options(df_main, '產業類別'))

    df_filtered = df_main.copy()
    if filter_client: df_filtered = df_filtered[df_filtered['客戶'].isin(filter_client)]
    if filter_product: df_filtered = df_filtered[df_filtered['產品名稱'].isin(filter_product)]
    if filter_app: df_filtered = df_filtered[df_filtered['應用類別'].isin(filter_app)]
    if filter_supplier: df_filtered = df_filtered[df_filtered['供應商/代理商'].isin(filter_supplier)]
    if filter_opentype: df_filtered = df_filtered[df_filtered['開案類別'].isin(filter_opentype)]
    if filter_industry: df_filtered = df_filtered[df_filtered['產業類別'].isin(filter_industry)]

    st.markdown("<br>", unsafe_allow_html=True)

    # =========================================================================
    # 🧩 區塊 2：客戶與產品維度分析
    # =========================================================================
    st.subheader("🧩 客戶與產品維度分析")
    st.caption("💡 操作指南：在左側的【網格卡片牆】上下滾動，點選「🔍 檢視分析」，右側將無縫顯示深度資料。")
    
    col_grid, col_drill = st.columns([1.3, 1.5])
    
    if "active_view" not in st.session_state:
        st.session_state.active_view = None
        st.session_state.active_target = None

    with col_grid:
        view_mode = st.radio("請選擇網格視圖：", ["🏢 顯示客戶", "📦 顯示產品"], horizontal=True, label_visibility="collapsed")
        
        with st.container(height=500, border=False):
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
                    sample_cnt = len(df_p_temp[df_p_temp['出樣/出貨'] == '出樣'])
                    ship_cnt = len(df_p_temp[df_p_temp['出樣/出貨'] == '出貨'])
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
        with st.container(height=545, border=True):
            if st.session_state.active_view == 'client' and st.session_state.active_target:
                target_client = st.session_state.active_target
                st.markdown(f"### 🏢 客戶深度分析：【 {target_client} 】")
                tab1, tab2, tab3 = st.tabs(["📋 客戶資訊", "📦 送樣歷程", "💰 累積營收"])
                df_c = df_filtered[df_filtered['客戶'] == target_client]
                
                with tab1:
                    industry = df_c['產業類別'].replace('未標示', pd.NA).dropna().iloc[0] if not df_c['產業類別'].replace('未標示', pd.NA).dropna().empty else "未標示"
                    st.info(f"**👤 客戶名稱**：{target_client}\n\n**🏢 產業類別**：{industry}")
                    st.markdown("**🎯 開發目的**：")
                    purposes = [p for p in df_c.get('目的', pd.Series()).dropna().unique() if str(p).strip() not in ["", "nan", "未標示"]]
                    if purposes:
                        for i, p in enumerate(purposes, 1): st.write(f"{i}. {p}")
                    else:
                        st.caption("暫無明確開發目的紀錄。")

                with tab2:
                    st.markdown("##### 2. 送樣歷程追蹤")
                    df_sample_c = df_c[df_c['出樣/出貨'] == '出樣']
                    if not df_sample_c.empty:
                        prods_sampled = df_sample_c['產品名稱'].unique()
                        for prod in prods_sampled:
                            prod_samples = df_sample_c[df_sample_c['產品名稱'] == prod].sort_values('送樣或出貨日期')
                            sample_count = len(prod_samples)
                            with st.expander(f"📦 {prod} (累計送樣: {sample_count} 次)"):
                                display_cols = ['送樣或出貨日期', '單號', 'Status', '測試結果']
                                display_cols = [c for c in display_cols if c in prod_samples.columns]
                                st.dataframe(prod_samples[display_cols], use_container_width=True, hide_index=True)
                    else:
                        st.warning("💡 該客戶目前尚無『出樣』紀錄。")

                with tab3:
                    st.markdown("##### 3. 累積營收")
                    total_revenue = df_c['營收'].sum()
                    if total_revenue > 0:
                        st.metric(label="📊 總體營收貢獻金額", value=f"{total_revenue:,.0f} TWD")
                        st.dataframe(df_c[df_c['營收'] > 0][['送樣月份', '產品名稱', '營收']].sort_values('送樣月份'), use_container_width=True, hide_index=True)
                    else:
                        st.info("💡 目前該客戶尚無營收。")

            elif st.session_state.active_view == 'product' and st.session_state.active_target:
                target_prod = st.session_state.active_target
                st.markdown(f"### 📦 產品型號深度分析：【 {target_prod} 】")
                
                tab1, tab2, tab3 = st.tabs(["🔬 產品資訊與動能客戶", "📝 測試結果明細", "🚀 專案研發全週期 Roadmap"])
                df_p = df_filtered[df_filtered['產品名稱'] == target_prod]
                
                with tab1:
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
                            '送樣次數': (x['出樣/出貨'] == '出樣').sum(),
                            '出貨次數': (x['出樣/出貨'] == '出貨').sum(),
                            '最新狀態': x['Status'].iloc[-1] if not x.empty else '未標示'
                        })
                    ).reset_index().rename(columns={'最新狀態': 'Status'})
                    st.dataframe(df_prod_g, use_container_width=True, hide_index=True)

                with tab2:
                    st.markdown("##### 歷次測試結果列表")
                    df_hover = df_p.copy()
                    df_hover['測試結果'] = df_hover['測試結果'].replace('未標示', '無填寫結果')
                    
                    df_test_results = df_hover[['送樣或出貨日期', '客戶', 'Status', '測試結果']].sort_values('送樣或出貨日期', ascending=False)
                    if not df_test_results.empty:
                        st.dataframe(df_test_results, use_container_width=True, hide_index=True)
                    else:
                        st.info("該產品目前尚無相關紀錄。")
                        
                with tab3:
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
                st.markdown("<div style='text-align: center; padding: 180px 20px; color: gray;'>🔍 <b>操作提示</b><br><br>請點擊左側網格卡片上的【🔍 檢視分析】，<br>此處將自動穿透並呈現專屬的深度分析資料。</div>", unsafe_allow_html=True)

    st.divider()

    # =========================================================================
    # 📊 區塊 3：產品送樣次數與時程統計
    # =========================================================================
    st.subheader("📦 產品送樣次數與時程統計")
    df_sample = df_filtered[df_filtered['出樣/出貨'] == '出樣']
    if not df_sample.empty:
        df_sample_agg = df_sample.groupby(['客戶', '產品名稱']).agg(送樣次數=('單號', 'count'), 最後送樣月份=('送樣月份', 'max')).reset_index()
        df_sample_agg['圖表標籤'] = df_sample_agg['送樣次數'].astype(str) + "次 (" + df_sample_agg['最後送樣月份'] + ")"
        fig2 = px.bar(df_sample_agg, x='客戶', y='送樣次數', color='產品名稱', text='圖表標籤', hover_data=['最後送樣月份'], barmode='group', color_discrete_sequence=px.colors.qualitative.Safe)
        fig2.update_traces(textposition='outside', textfont_size=11)
        fig2.update_layout(margin=dict(t=25, b=10), height=400, xaxis_title="客戶名稱", yaxis_title="送樣累計次數")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("💡 當前篩選條件下無任何『出樣』紀錄。")

    st.divider()

    # =========================================================================
    # 📊 區塊 4：客戶營收貢獻度 TOP 10
    # =========================================================================
    st.subheader("🏆 客戶營收貢獻度 TOP 10")
    df_rev_client = df_filtered.groupby('客戶')['營收'].sum().reset_index()
    df_rev_client = df_rev_client[df_rev_client['營收'] > 0].nlargest(10, '營收').sort_values('營收', ascending=True)
    if not df_rev_client.empty:
        fig4 = px.bar(df_rev_client, x='營收', y='客戶', orientation='h', text='營收', color='營收', color_continuous_scale='GnBu')
        fig4.update_traces(texttemplate='%{text:,.0f} TWD', textposition='outside', textfont_size=11)
        fig4.update_layout(margin=dict(t=25, b=10), height=380, showlegend=False, xaxis_title="累計營收金額", yaxis_title="客戶名稱")
        st.plotly_chart(fig4, use_container_width=True)
    else:
        st.info("💡 當前篩選條件下尚無產生實際營收之客戶。")

    st.divider()

    # =========================================================================
    # 📊 區塊 5：產品累積營收趨勢圖
    # =========================================================================
    with st.container():
        st.subheader("📈 產品累積營收趨勢圖")
        df_trend = df_filtered[(df_filtered['送樣月份'].notna()) & (df_filtered['送樣月份'] != '未標示') & (df_filtered['營收'] > 0)].copy()
        if not df_trend.empty:
            all_months = sorted(df_trend['送樣月份'].unique())
            all_products = df_trend['產品名稱'].unique()
            multi_idx = pd.MultiIndex.from_product([all_months, all_products], names=['送樣月份', '產品名稱'])
            df_monthly_rev = df_trend.groupby(['送樣月份', '產品名稱'])['營收'].sum().reset_index()
            df_monthly_rev = df_monthly_rev.set_index(['送樣月份', '產品名稱']).reindex(multi_idx, fill_value=0).reset_index()
            df_monthly_rev['累積營收'] = df_monthly_rev.groupby('產品名稱')['營收'].cumsum()
            df_monthly_rev = df_monthly_rev.sort_values(by='送樣月份')

            fig3 = px.area(df_monthly_rev, x='送樣月份', y='累積營收', color='產品名稱', line_group='產品名稱', markers=True, color_discrete_sequence=px.colors.qualitative.Vivid, hover_data={'營收': ':,.0f'})
            fig3.update_layout(xaxis_title="營收統計月份", yaxis_title="總體累積營收 (TWD)", hovermode="x unified", height=420, margin=dict(t=15, b=10))
            fig3.update_xaxes(type='category')
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("💡 當前篩選範圍內缺乏含有效日期的營收變動紀錄。")

else:
    st.info("👋 歡迎使用 Geckos Customer Dashboard。請先在左側面板上傳最新的「客戶產品列表_V2.xlsx」數據表。")
