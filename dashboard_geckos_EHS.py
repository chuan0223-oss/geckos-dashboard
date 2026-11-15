import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import datetime
import math

# 1. 頁面基礎設定
st.set_page_config(page_title="設備移入與廠務管理系統", layout="wide")

# [CSS 注入] 參考 Geckos Dashboard，優化頁籤與卡片視覺
st.markdown("""
    <style>
    div[data-testid="stTabs"] [data-baseweb="tab-list"] {
        display: flex !important;
        flex-wrap: wrap !important;
        gap: 8px !important;
        padding-bottom: 10px !important;
    }
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
    </style>
""", unsafe_allow_html=True)

# 【需求1】修改標題
st.title("🔧 設備評估看板")
st.caption("目前資料源介接：設備規格表.xlsx (第二階段將轉移至 PostgreSQL)")

# 2. 讀取 Excel 作為臨時資料庫
@st.cache_data
def load_data():
    df = pd.read_excel('設備規格表.xlsx')
    # 時間格式處理，避免顯示錯誤
    if '預計入廠日期' in df.columns:
        df['預計入廠日期'] = pd.to_datetime(df['預計入廠日期']).dt.strftime('%Y-%m-%d')
    if '預計一次測施工' in df.columns:
        df['預計一次測施工'] = df['預計一次測施工'].astype(str).str.replace(' 00:00:00', '')
    # 填充空值以便於網頁顯示
    df = df.fillna("")
    return df

df = load_data()

# 3. 頂部戰情指標 (KPI)
# 【需求2】僅保留評估設備總數
st.subheader("📊 廠務進度總覽指標")
st.metric("評估設備總數", f"{len(df)} 台")
st.markdown("---")

# 4. 核心功能區
# 【需求3】取消矩陣，將待施工排程改為卡片呈現
tab1, tab2, tab3 = st.tabs(["🏢 設備總覽 (Cards)", "📅 待施工排程 (Cards)", "🚀 設備交期路徑圖"])

with tab1:
    st.markdown("##### 🧩 設備維度深度檢視")
    # 【需求2】UI 呈現改成立體卡片，僅顯示 設備名稱、交期、預計進廠日期、進度說明
    cols_per_row = 3
    for i in range(0, len(df), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            if i + j < len(df):
                row = df.iloc[i + j]
                with col:
                    with st.container(border=True): # 使用 Streamlit 原生立體邊框容器
                        # 設備名稱
                        st.markdown(f"<div style='font-size:18px; font-weight:bold; color:#2C3E50; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;'>📦 {row.get('設備名稱', '未標示')}</div>", unsafe_allow_html=True)
                        
                        # 交期
                        lead_time = row.get('交期(天)', '')
                        try:
                            if lead_time != "" and not math.isnan(float(lead_time)):
                                lead_time_str = f"{int(float(lead_time))} 天"
                            else:
                                lead_time_str = "未定"
                        except:
                            lead_time_str = str(lead_time)
                            
                        st.markdown(f"<div style='font-size:22px; font-weight:900; color:#2980B9; margin-top:10px;'>{lead_time_str} <span style='font-size:12px;color:gray;'>交期</span></div>", unsafe_allow_html=True)
                        
                        # 預計進廠日期
                        eta = row.get('預計入廠日期', '未定')
                        st.markdown(f"<div style='font-size:14px; font-weight:700; color:#16A085; margin-bottom:10px;'>📅 預計進廠：{eta}</div>", unsafe_allow_html=True)
                        
                        # 進度說明
                        progress = row.get('進度說明', '')
                        progress_str = progress if str(progress).strip() != "" else "無特殊說明"
                        
                        # 修復 SyntaxError: 使用 
 來換行，而不是直接斷行
                        st.info(f"**📝 進度說明**：\n{progress_str}")

with tab2:
    st.markdown("##### 尚未完成一次側施工之設備")
    pending_df = df[df['預計一次測施工'] != '已完成']
    if pending_df.empty:
        st.success("🎉 目前所有列管設備皆已完成一次側施工！")
    else:
        # 【需求3】待施工排程清單也做卡片呈現，並把「進度說明」拿掉
        cols_per_row_2 = 3
        for i in range(0, len(pending_df), cols_per_row_2):
            cols = st.columns(cols_per_row_2)
            for j, col in enumerate(cols):
                if i + j < len(pending_df):
                    row = pending_df.iloc[i + j]
                    with col:
                        with st.container(border=True):
                            st.markdown(f"<div style='font-size:18px; font-weight:bold; color:#2C3E50; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;'>📦 {row.get('設備名稱', '未標示')}</div>", unsafe_allow_html=True)
                            
                            lead_time = row.get('交期(天)', '')
                            try:
                                if lead_time != "" and not math.isnan(float(lead_time)):
                                    lead_time_str = f"{int(float(lead_time))} 天"
                                else:
                                    lead_time_str = "未定"
                            except:
                                lead_time_str = str(lead_time)
                            
                            st.markdown(f"<div style='font-size:14px; color:#555; margin-top:10px;'>⏳ 交期：<b>{lead_time_str}</b></div>", unsafe_allow_html=True)
                            
                            eta = row.get('預計入廠日期', '未定')
                            st.markdown(f"<div style='font-size:14px; color:#555;'>📅 預計進廠：<b>{eta}</b></div>", unsafe_allow_html=True)
                            
                            hookup = row.get('預計一次測施工', '未排定')
                            st.error(f"🔧 預計施工日：**{hookup}**") # 用紅色 error 框凸顯待施工日期
                            # (此處不顯示進度說明)

with tab3:
    st.markdown("##### 🚀 設備交期與施工路徑圖 (Equipment Roadmap)")

    df_roadmap = df.copy()
    df_roadmap['入廠_dt'] = pd.to_datetime(df_roadmap['預計入廠日期'], errors='coerce')
    df_roadmap['施工_dt'] = pd.to_datetime(df_roadmap['預計一次測施工'].astype(str).str.replace('已完成', ''), errors='coerce')
    df_roadmap['評估_dt'] = pd.to_datetime(df_roadmap['請購評估會議日期'].astype(str).str.replace('已完成', ''), errors='coerce')

    df_roadmap = df_roadmap.dropna(subset=['入廠_dt']).sort_values('入廠_dt', ascending=False)
    now = pd.Timestamp.now().normalize()
    max_move_in_date = df_roadmap['入廠_dt'].max()

    fig = go.Figure()

    for idx, row in df_roadmap.iterrows():
        eq_name = str(row['設備名稱'])
        lead_time = row.get('交期(天)', '')
        
        # 【需求4】若有交期天數，則在設備名稱下方附加標註
        try:
            if lead_time != "" and not math.isnan(float(lead_time)):
                display_name = f"{eq_name}<br><span style='font-size:11px;color:gray;'>(設備交期天數: {int(float(lead_time))}天)</span>"
            else:
                display_name = eq_name
        except:
            display_name = eq_name

        dates = {}
        if pd.notnull(row['評估_dt']): dates['評估'] = row['評估_dt']
        if pd.notnull(row['施工_dt']): dates['施工'] = row['施工_dt']
        if pd.notnull(row['入廠_dt']): dates['入廠'] = row['入廠_dt']
        
        if dates:
            sorted_points = sorted(dates.items(), key=lambda x: x[1])
            x_vals = [p[1] for p in sorted_points]
            y_vals = [display_name] * len(x_vals) # 使用新的帶有交期天數的名稱
            
            fig.add_trace(go.Scatter(
                x=x_vals, y=y_vals, 
                mode='lines', 
                line=dict(color='#7F8C8D', width=4), 
                showlegend=False, 
                hoverinfo="skip"
            ))

            node_configs = {
                '評估': {'color': '#2E86C1', 'symbol': 'circle', 'size': 12},
                '施工': {'color': '#F39C12', 'symbol': 'diamond', 'size': 14},
                '入廠': {'color': '#27AE60', 'symbol': 'star', 'size': 18}
            }
            
            for node_name, dt in sorted_points:
                conf = node_configs[node_name]
                days_diff = (dt - now).days
                status_text = f"剩 {days_diff} 天" if days_diff >= 0 else f"已過 {abs(days_diff)} 天"
                t_pos = "top center" if node_name == '施工' else "bottom center"
                
                fig.add_trace(go.Scatter(
                    x=[dt], y=[display_name], # 對應 Y 軸名稱
                    mode='markers+text',
                    marker=dict(color=conf['color'], symbol=conf['symbol'], size=conf['size'], line=dict(width=2, color='white')),
                    text=[dt.strftime('%m/%d')],
                    textposition=t_pos,
                    hovertext=f"<b>{eq_name}</b><br>{node_name}: {dt.strftime('%Y-%m-%d')}<br>({status_text})",
                    hoverinfo="text",
                    showlegend=False
                ))

    # 圖例
    legend_items = [
        {'name': '評估會議', 'color': '#2E86C1', 'symbol': 'circle', 'size': 10},
        {'name': '一次側施工', 'color': '#F39C12', 'symbol': 'diamond', 'size': 10},
        {'name': '設備入廠', 'color': '#27AE60', 'symbol': 'star', 'size': 14}
    ]
    for item in legend_items:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode='markers',
            marker=dict(color=item['color'], symbol=item['symbol'], size=item['size']),
            name=item['name'], showlegend=True
        ))

    # 垂直標示線
    fig.add_vline(x=now, line_width=2, line_dash="dash", line_color="#E74C3C")
    fig.add_annotation(
        x=now, y=1.05, yref='paper', text=f"📍 本日 ({now.strftime('%Y-%m-%d')})", 
        showarrow=False, font=dict(color="#E74C3C", weight="bold"), bgcolor="rgba(255,255,255,0.8)"
    )
    
    if pd.notnull(max_move_in_date):
        fig.add_vline(x=max_move_in_date, line_width=2, line_dash="dash", line_color="#1E8449")
        fig.add_annotation(
            x=max_move_in_date, y=1.05, yref='paper', text=f"🏁 NCP系列產線設備完成日 ({max_move_in_date.strftime('%Y-%m-%d')})", 
            showarrow=False, font=dict(color="#1E8449", weight="bold"), bgcolor="rgba(255,255,255,0.8)"
        )

    # 調整圖表高度（因為 Y 軸文字變兩行，稍微增加行距高度）
    fig.update_layout(
        xaxis=dict(title="時間軸 (日期)", type='date', tickformat="%Y-%m-%d"),
        yaxis=dict(title="設備名稱", autorange="reversed"), 
        height=max(400, 150 + (len(df_roadmap) * 60)), # 將每一行的高度從50拉到60以容納兩行字
        margin=dict(l=0, r=0, t=60, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )

    st.plotly_chart(fig, use_container_width=True)
