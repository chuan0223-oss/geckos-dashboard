import streamlit as st
import pandas as pd

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
tab1, tab2 = st.tabs(["⚡ 廠務水氣電與進度矩陣", "📅 待施工排程清單"])

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
