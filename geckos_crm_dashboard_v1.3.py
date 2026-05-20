import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import math

# =========================================================================
# ⚙️ 網頁初始化與佈局設定
# =========================================================================
st.set_page_config(page_title="Geckos Customer Dashboard", layout="wide")
st.title("📊 Geckos Customer Dashboard")

st.sidebar.header("📂 資料管理中心")
uploaded_file = st.sidebar.file_uploader("請上傳「客戶產品列表_V2」Excel 檔案", type=["xlsx"])

def get_safe_options(df, col_name):
    if col_name and col_name in df.columns:
        opts = df[col_name].dropna().astype(str).unique().tolist()
        opts = [x for x in opts if x.lower() != 'nan' and x.strip() != '']
        return sorted(opts)
    return []

# =========================================================================
# 🎨 原生畫布文字雲產生器 (V5.2 修復文字重疊，導入交錯網格與動態高度)
# =========================================================================
def create_scatter_wordcloud(df, name_col, metric_col, title_text, min_font=14, max_font=42):
    """利用蜂巢交錯演算法與動態高度，徹底解決文字重疊問題"""
    if df.empty:
        return None
        
    df_cloud = df.sort_values(metric_col, ascending=False).reset_index(drop=True)
    n = len(df_cloud)
    
    # [V5.2 優化] 嚴格的交錯網格排版 (Staggered Grid)
    cols = 3 if n < 12 else 4  # 限制最大行數，確保橫向有足夠空間
    rows = math.ceil(n / cols)
    
    x_pos, y_pos = [], []
    for i in range(n):
        r = i // cols
        c = i % cols
        # 讓單數列微幅平移，產生蜂巢交錯排版效果，避開上下字體碰撞
        x_offset = 0.5 if r % 2 == 1 else 0.0
        x_pos.append((c * 2) + x_offset)  # X軸間距強制拉開
        y_pos.append(-r)                  # Y軸嚴格分層
        
    df_cloud['x'] = x_pos
    df_cloud['y'] = y_pos
    
    max_val = df_cloud[metric_col].max()
    min_val = df_cloud[metric_col].min()
    
    # 正規化字體大小
    if max_val == min_val:
        df_cloud['font_size'] = (min_font + max_font) / 2
    else:
        df_cloud['font_size'] = min_font + ((df_cloud[metric_col] - min_val) / (max_val - min_val)) * (max_font - min_font)
        
    colors_palette = ["#1A5276", "#2980B9", "#2471A3", "#5499C7", "#117A65", "#16A085", "#1F618D", "#34495E"]
    df_cloud['color'] = [colors_palette[i % len(colors_palette)] for i in range(n)]
        
    # 建立純文字的隱形散點圖
    fig = go.Figure(go.Scatter(
        x=df_cloud['x'], 
        y=df_cloud['y'],
        mode='text',
        text=df_cloud[name_col],
        textfont=dict(size=df_cloud['font_size'], color=df_cloud['color']),
        customdata=df_cloud[[name_col, metric_col]].values,
        hovertemplate="<b>%{customdata[0]}</b><br>數值權重: %{customdata[1]:,.0f}<extra></extra>"
    ))
    
    # [V5.2 優化] 關閉文字裁切，確保邊緣大字不被切斷
    fig.update_traces(cliponaxis=False)
    
    # [V5.2 優化] 動態圖表高度，資料越多，Y軸自動向下生長，保證絕不擠壓
    dynamic_height = max(280, rows * 75 + 80)
    
    fig.update_layout(
        title=dict(text=title_text, font=dict(size=16)),
        # 嚴格鎖定 X 與 Y 軸的可視範圍，配合動態高度完美呈現
        xaxis=dict(showgrid=False, zeroline=False, visible=False, range=[-1, cols * 2]),
        yaxis=dict(showgrid=False, zeroline=False, visible=False, range=[-(rows), 1]),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=10, r=10, t=50, b=10),
        hovermode='closest',
        dragmode=False, # 停用拖曳縮放，保持版面乾淨
        height=dynamic_height
    )
    return fig

# =========================================================================
# 💾 主要資料流程序
# =========================================================================
if uploaded_file is not None:
    try:
        df_tracking = pd.read_excel(uploaded_file, sheet_name='送樣追蹤管理表')
        df_product = pd.read_excel(uploaded_file, sheet_name='產品列表')
        df_client = pd.read_excel(uploaded_file, sheet_name='客戶列表')

        full_client_list = sorted(df_client['客戶'].dropna().unique().tolist())
        full_product_list = sorted(df_product['產品名稱'].dropna().unique().tolist())

        df_client['客戶'] = df_client['客戶'].ffill()
        df_client['產業類別'] = df_client['產業類別'].ffill()
        df_client_clean = df_client[['客戶', '產品名稱', '產業類別', '應用類別']].drop_duplicates(subset=['客戶', '產品名稱'], keep='first')
        
        cols_to_drop = ['Lot No.', '數量', '單位']
        df_tracking = df_tracking.drop(columns=[c for c in cols_to_drop if c in df_tracking.columns], errors='ignore')

        df_main = pd.merge(df_tracking, df_product[['產品名稱', '產品類別', '開案類別', '供應商/代理商']], on='產品名稱', how='left')
        df_main = pd.merge(df_main, df_client_clean, on=['客戶', '產品名稱'], how='left')

        df_main['送樣或出貨日期'] = pd.to_datetime(df_main['送樣或出貨日期'], errors='coerce')
        df_main['送樣月份'] = df_main['送樣或出貨日期'].dt.strftime('%Y-%m').fillna('未標示')
        df_main['營收'] = pd.to_numeric(df_main['營收'], errors='coerce').fillna(0)
        
        str_cols = ['客戶', '產品名稱', '應用類別', '供應商/代理商', '開案類別', '產業類別', '出樣/出貨', 'Status', '測試結果', '目的']
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
    # 🧩 區塊 2：無縫互動探索控制台 (左圖右表)
    # =========================================================================
    st.subheader("🧩 互動探索控制台")
    st.caption("💡 點選左側文字雲中的任何名稱，右側將會立即無縫顯示深度分析資料！")
    
    col_cloud, col_drill = st.columns([1.2, 1.4])
    
    if "active_view" not in st.session_state:
        st.session_state.active_view = None
        st.session_state.active_target = None
    if "last_client_event" not in st.session_state: st.session_state.last_client_event = []
    if "last_prod_event" not in st.session_state: st.session_state.last_prod_event = []

    with col_cloud:
        client_rev = df_filtered.groupby('客戶')['營收'].sum().to_dict()
        df_c_cloud = pd.DataFrame([{"客戶名稱": c, "營收貢獻": client_rev.get(c, 0)} for c in full_client_list])
        fig_client = create_scatter_wordcloud(df_c_cloud, '客戶名稱', '營收貢獻', "👤 客戶營收貢獻度權重分佈")
        
        prod_count = df_filtered.groupby('產品名稱').size().to_dict()
        df_p_cloud = pd.DataFrame([{"產品型號": p, "送樣次數": prod_count.get(p, 0)} for p in full_product_list])
        fig_prod = create_scatter_wordcloud(df_p_cloud, '產品型號', '送樣次數', "📦 產品送樣熱度權重分佈", min_font=14, max_font=46)

        event_client = None
        event_prod = None
        if fig_client is not None:
            event_client = st.plotly_chart(fig_client, use_container_width=True, on_select="rerun", key="cloud_c")
        if fig_prod is not None:
            event_prod = st.plotly_chart(fig_prod, use_container_width=True, on_select="rerun", key="cloud_p")

        cur_client_pts = event_client['selection']['points'] if event_client and event_client.get('selection') else []
        cur_prod_pts = event_prod['selection']['points'] if event_prod and event_prod.get('selection') else []

        if cur_client_pts != st.session_state.last_client_event:
            st.session_state.last_client_event = cur_client_pts
            if cur_client_pts:
                st.session_state.active_view = 'client'
                st.session_state.active_target = cur_client_pts[0]['customdata'][0]
                
        elif cur_prod_pts != st.session_state.last_prod_event:
            st.session_state.last_prod_event = cur_prod_pts
            if cur_prod_pts:
                st.session_state.active_view = 'product'
                st.session_state.active_target = cur_prod_pts[0]['customdata'][0]

    with col_drill:
        with st.container(border=True):
            if st.session_state.active_view == 'client' and st.session_state.active_target:
                target_client = st.session_state.active_target
                st.markdown(f"### 🏢 客戶深度分析：【 {target_client} 】")
                tab1, tab2, tab3 = st.tabs(["📋 客戶資訊", "📦 送樣資訊", "💰 累積營收"])
                df_c = df_filtered[df_filtered['客戶'] == target_client]
                
                with tab1:
                    st.markdown("##### 1. 客戶資訊")
                    industry = df_c['產業類別'].replace('未標示', pd.NA).dropna().iloc[0] if not df_c['產業類別'].replace('未標示', pd.NA).dropna().empty else "未標示"
                    st.info(f"**👤 客戶名稱**：{target_client}\n\n**🏢 產業類別**：{industry}")
                    st.markdown("**🎯 開發目的**：")
                    purposes = [p for p in df_c.get('目的', pd.Series()).dropna().unique() if str(p).strip() not in ["", "nan", "未標示"]]
                    if purposes:
                        for i, p in enumerate(purposes, 1): st.write(f"{i}. {p}")
                    else:
                        st.caption("暫無明確開發目的紀錄。")

                with tab2:
                    st.markdown("##### 2. 送樣資訊")
                    df_sample_c = df_c[df_c['出樣/出貨'] == '出樣']
                    if not df_sample_c.empty:
                        df_sample_g = df_sample_c.groupby('產品名稱').agg(送樣次數=('單號', 'count'), 最後送樣月份=('送樣月份', 'max')).reset_index()
                        status_list = [df_c[df_c['產品名稱'] == p].sort_values('送樣或出貨日期')['Status'].iloc[-1] if not df_c[df_c['產品名稱'] == p].empty else "未標示" for p in df_sample_g['產品名稱']]
                        df_sample_g['Status'] = status_list
                        st.dataframe(df_sample_g, use_container_width=True, hide_index=True)
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
                tab1, tab2 = st.tabs(["🔬 產品資訊", "📝 測試結果明細 (支援滑鼠移入)"])
                df_p = df_filtered[df_filtered['產品名稱'] == target_prod]
                
                with tab1:
                    st.markdown("##### 1. 產品資訊")
                    df_prod_g = df_p.groupby('客戶').agg(送樣次數=('單號', 'count'), 最新狀態=('Status', 'last')).reset_index().rename(columns={'客戶': '送樣客戶', '最新狀態': 'Status'})
                    st.dataframe(df_prod_g, use_container_width=True, hide_index=True)

                with tab2:
                    st.markdown("##### 2. 當滑鼠移到這個產品的節點時會出現測試結果")
                    df_hover = df_p.copy()
                    df_hover['測試結果'] = df_hover['測試結果'].replace('未標示', '無填寫結果')
                    if not df_hover.empty:
                        fig_hover = px.scatter(
                            df_hover, x='送樣月份', y='客戶', color='Status',
                            custom_data=['產品名稱', '客戶', '送樣月份', 'Status', '測試結果']
                        )
                        fig_hover.update_traces(
                            marker=dict(size=18, line=dict(width=1, color='DarkSlateGrey')),
                            hovertemplate="<b>產品:</b> %{customdata[0]}<br><b>客戶:</b> %{customdata[1]}<br><b>月份:</b> %{customdata[2]}<br><b>狀態:</b> %{customdata[3]}<br>📌 <b>測試結果:</b> %{customdata[4]}<extra></extra>"
                        )
                        fig_hover.update_layout(height=320, margin=dict(t=10, b=10))
                        st.plotly_chart(fig_hover, use_container_width=True, key="prod_scatter_hover")
                    else:
                        st.info("該產品目前尚無測試結果紀錄。")
            else:
                st.markdown("<div style='text-align: center; padding: 120px 20px; color: gray;'>🔍 <b>操作提示</b><br><br>請直接點擊左側文字雲中的【客戶名稱】或【產品型號】，此處將自動穿透並呈現該維度的深度分析資料。</div>", unsafe_allow_html=True)

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
