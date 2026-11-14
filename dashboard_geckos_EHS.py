import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import datetime

# 1. 頁面基礎設定
st.set_page_config(page_title="設備移入與廠務管理系統", layout="wide")

st.title("🔧 設備評估與廠務水氣電看板 (Prototype)")
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
st.subheader("📊 廠務進度總覽指標")
col1, col2, col3, col4 = st.columns(4)
col1.metric("列管設備總數", f"{len(df)} 台")
# 簡單篩選出需要 380V 的設備數量
power_380v = len(df[df['電壓規格'].astype(str).str.contains('380V')])
col2.metric("需 380V 動力電評估", f"{power_380v} 台", "需確認配電盤負載")
# 篩選一次側已完成
completed_hookup = len(df[df['預計一次測施工'] == '已完成'])
col3.metric("一次側施工已完成", f"{completed_hookup} 台", "等待設備入廠")
col4.metric("進度異常/待確認", f"{len(df) - completed_hookup} 台", "需緊盯交期", delta_color="inverse")

st.markdown("---")

# 4. 核心功能區：互動式資料編輯與進度追蹤
tab1, tab2, tab3 = st.tabs(["⚡ 廠務水氣電與進度矩陣", "📅 待施工排程清單", "🚀 設備交期路徑圖"])

with tab1:
    st.markdown("##### 設備規格檢核表")
    st.info("💡 **高層展示亮點**：這不僅是報表，使用者可以直接在下方表格雙擊修改「進度說明」或「交期」，未來可一鍵儲存回資料庫。也能隨時擴充『廢水排放』或『樓板載重』等欄位。")
    
    # 運用 st.data_editor 讓主管直接體驗系統的「互動性」
    edited_df = st.data_editor(
        df,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "交期(天)": st.column_config.NumberColumn("交期(天)"),
            "預計入廠日期": st.column_config.TextColumn("預計入廠日期 (YYYY-MM-DD)"),
            "預計一次測施工": st.column_config.TextColumn("預計一次側施工 (日期或狀態)"),
            "進度說明": st.column_config.TextColumn("進度說明 (支援長文本)", width="large")
        }
    )

with tab2:
    st.markdown("##### 尚未完成一次側施工之設備 (交期預警)")
    # 過濾出還沒完成施工的資料，方便開會追蹤
    pending_df = df[df['預計一次測施工'] != '已完成']
    st.dataframe(
        pending_df[['設備名稱', '預計入廠日期', '預計一次測施工', '進度說明']], 
        use_container_width=True
    )

with tab3:
    st.markdown("##### 🚀 設備交期與施工路徑圖 (Equipment Roadmap)")
    st.info("💡 視覺化呈現每台設備從「一次側施工」到「入廠」的時程，並自動計算距離今天還有幾天。")

    # 1. 準備繪圖資料
    df_roadmap = df.copy()
    # 轉換日期格式以便計算
    df_roadmap['入廠_dt'] = pd.to_datetime(df_roadmap['預計入廠日期'], errors='coerce')
    df_roadmap['施工_dt'] = pd.to_datetime(df_roadmap['預計一次測施工'].astype(str).str.replace('已完成', ''), errors='coerce')
    df_roadmap['評估_dt'] = pd.to_datetime(df_roadmap['請購評估會議日期'].astype(str).str.replace('已完成', ''), errors='coerce')

    # 過濾出至少有入廠日期的設備
    df_roadmap = df_roadmap.dropna(subset=['入廠_dt']).sort_values('入廠_dt', ascending=False)
    now = pd.Timestamp.now().normalize()

    fig = go.Figure()

    # 2. 逐一繪製每台設備的時間軸
    for idx, row in df_roadmap.iterrows():
        eq_name = row['設備名稱']
        dates = {}
        
        # 蒐集有效日期
        if pd.notnull(row['評估_dt']): dates['評估'] = row['評估_dt']
        if pd.notnull(row['施工_dt']): dates['施工'] = row['施工_dt']
        if pd.notnull(row['入廠_dt']): dates['入廠'] = row['入廠_dt']
        
        if dates:
            # 依時間先後排序
            sorted_points = sorted(dates.items(), key=lambda x: x[1])
            x_vals = [p[1] for p in sorted_points]
            y_vals = [eq_name] * len(x_vals)
            
            # 畫底線 (連接各節點)
            fig.add_trace(go.Scatter(
                x=x_vals, y=y_vals, 
                mode='lines', 
                line=dict(color='#7F8C8D', width=4), 
                showlegend=False, 
                hoverinfo="skip"
            ))

            # 畫節點與標籤
            node_configs = {
                '評估': {'color': '#2E86C1', 'symbol': 'circle', 'size': 12},
                '施工': {'color': '#F39C12', 'symbol': 'diamond', 'size': 14},
                '入廠': {'color': '#27AE60', 'symbol': 'star', 'size': 18}
            }
            
            for node_name, dt in sorted_points:
                conf = node_configs[node_name]
                days_diff = (dt - now).days
                status_text = f"剩 {days_diff} 天" if days_diff >= 0 else f"已過 {abs(days_diff)} 天"
                
                fig.add_trace(go.Scatter(
                    x=[dt], y=[eq_name],
                    mode='markers+text',
                    marker=dict(color=conf['color'], symbol=conf['symbol'], size=conf['size'], line=dict(width=2, color='white')),
                    text=[dt.strftime('%m/%d')],
                    textposition="bottom center",
                    hovertext=f"<b>{eq_name}</b><br>{node_name}: {dt.strftime('%Y-%m-%d')}<br>({status_text})",
                    hoverinfo="text",
                    showlegend=False
                ))

    # 3. 補上圖例 (Legend)
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

    # 4. 畫上「今日」的垂直虛線
    fig.add_vline(x=now, line_width=2, line_dash="dash", line_color="#E74C3C")
    fig.add_annotation(
        x=now, y=1.05, yref='paper', text=f"📍 本日 ({now.strftime('%Y-%m-%d')})", 
        showarrow=False, font=dict(color="#E74C3C", weight="bold"), bgcolor="rgba(255,255,255,0.8)"
    )

    # 5. 排版與顯示
    fig.update_layout(
        xaxis=dict(title="時間軸 (日期)", type='date', tickformat="%Y-%m-%d"),
        yaxis=dict(title="設備名稱", autorange="reversed"), # 反轉Y軸讓第一筆在最上面
        height=max(400, 150 + (len(df_roadmap) * 50)),
        margin=dict(l=0, r=0, t=60, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )

    st.plotly_chart(fig, use_container_width=True)
