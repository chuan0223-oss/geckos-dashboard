import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import datetime
import re

# =========================================================================
# ⚙️ 設定網頁標題與佈局 (Wide Mode)
# =========================================================================
st.set_page_config(page_title="凱鍶 財務預算戰情室 V1.7", layout="wide")

# =========================================================================
# 🔐 [資安強化] 身分驗證
# =========================================================================
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password" not in st.secrets:
        st.error("⚠️ 系統設定錯誤：未檢測到密碼設定檔 (.streamlit/secrets.toml)。")
        return False

    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    st.title("🔒 預算戰情室 安全登入")
    st.markdown("##### 本系統包含敏感財務預算資料，請輸入授權密碼。")
    st.text_input("Password", type="password", on_change=password_entered, key="password")
    
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        if "password" not in st.session_state: 
             st.error("❌ 密碼錯誤，請重新輸入。")
    return False

# 暫時註解密碼驗證方便本地測試
# if not check_password():
#     st.stop()

# =========================================================================
# ⬇️ Dashboard 主程式 (Version: V1.7)
# =========================================================================
st.title("📊 2026 年度預算戰情室 (Budget vs. Actual)")

def clean_numeric(val):
    if pd.isna(val): return 0.0
    val_str = str(val).strip().replace(',', '')
    if val_str == '-' or val_str == '': return 0.0
    try: return float(val_str)
    except: return 0.0

def clean_percent(val):
    if pd.isna(val): return 0.0
    val_str = str(val).strip().replace('%', '').replace(',', '')
    if val_str == '-' or val_str == '': return 0.0
    try: return float(val_str) / 100.0
    except: return 0.0

# =========================================================================
# 📁 資料上傳與多檔合併預處理 (V1.7 智慧防呆版)
# =========================================================================
st.sidebar.header("📂 資料上傳區")
uploaded_files = st.sidebar.file_uploader("請上傳年度預算表 (可多選 CSV/Excel)", type=["csv", "xlsx"], accept_multiple_files=True)

if uploaded_files:
    df_list = []
    
    for file in uploaded_files:
        try:
            if file.name.endswith('.csv'):
                df_raw = pd.read_csv(file, header=None, encoding='utf-8-sig')
            else:
                df_raw = pd.read_excel(file, header=None)

            # --- 動態智慧掃描表頭位置 ---
            header_idx = -1
            h2 = []
            
            # 掃描前 10 行尋找特徵關鍵字
            for i in range(min(10, len(df_raw))):
                # 強制移除 BOM (\ufeff) 與頭尾空白
                row_vals = [str(val).replace('\ufeff', '').strip() for val in df_raw.iloc[i].tolist()]
                if '專案' in row_vals or '項目' in row_vals:
                    header_idx = i
                    h2 = row_vals
                    break
            
            if header_idx == -1:
                st.error(f"檔案 {file.name} 解析失敗：無法在表格前 10 行找到 '專案' 或 '項目' 欄位。")
                st.stop()

            # 組合新欄位名稱
            if header_idx == 0:
                # 只有單層表頭的防呆機制
                new_cols = h2
            else:
                # 抓取主表頭的前一行作為月份/Total
                h1_raw = df_raw.iloc[header_idx - 1].ffill().astype(str)
                h1 = [v.replace('\ufeff', '').strip() for v in h1_raw]
                
                new_cols = []
                for c1, c2 in zip(h1, h2):
                    # 考慮不同 Pandas 版本處理 NaN 的字串結果
                    if c1.lower() in ['nan', 'none', '<na>', 'nat', '']:
                        new_cols.append(c2)
                    else:
                        new_cols.append(f"{c1}_{c2}")
                        
            # 擷取資料區塊
            df_temp = df_raw.iloc[header_idx + 1:].copy()
            df_temp.columns = new_cols
            
            # --- 欄位校正與清理 ---
            if '項目' in df_temp.columns:
                df_temp = df_temp.rename(columns={'專案': '開案類別', '項目': '專案', '類別': '產品類別'})
                
            # 二次確認專案欄位存在
            if '專案' not in df_temp.columns:
                st.error(f"檔案 {file.name} 欄位重組失敗。目前抓取到的欄位：{list(df_temp.columns)}")
                st.stop()
                
            # 清除空值列與合計列
            df_temp = df_temp[df_temp['專案'] != '合計']
            df_temp = df_temp.dropna(subset=['專案'])
            df_temp = df_temp[df_temp['專案'].astype(str).str.strip() != '']
            
            # 自動標記公司別
            if "鎧鍶釩" in file.name:
                df_temp['公司別'] = '鎧鍶釩'
            elif "凱鍶" in file.name:
                df_temp['公司別'] = '凱鍶'
            else:
                df_temp['公司別'] = '其他'
                
            df_list.append(df_temp)
            
        except Exception as e:
            st.error(f"檔案 {file.name} 讀取或解析失敗: {str(e)}")
            st.stop()

    if not df_list:
        st.stop()
        
    df_combined = pd.concat(df_list, ignore_index=True)

    # =========================================================================
    # 篩選條件設定
    # =========================================================================
    st.sidebar.divider()
    st.sidebar.header("⚙️ 參數與篩選")
    
    view_option = st.sidebar.selectbox("🏢 檢視視角", options=["凱鍶+鎧鍶釩", "凱鍶", "鎧鍶釩"])
    rmb_rate = st.sidebar.number_input("💱 RMB 換 TWD 匯率 (僅套用於鎧鍶釩)", value=4.40, step=0.05, format="%.2f")

    if view_option == "凱鍶":
        df_filtered = df_combined[df_combined['公司別'] == '凱鍶'].copy()
    elif view_option == "鎧鍶釩":
        df_filtered = df_combined[df_combined['公司別'] == '鎧鍶釩'].copy()
    else:
        df_filtered = df_combined.copy()

    cat_options = [x for x in df_filtered['產品類別'].unique() if pd.notna(x) and str(x).strip() != '']
    cat_filter = st.sidebar.multiselect("📂 產品類別", options=cat_options)

    type_options = [x for x in df_filtered['開案類別'].unique() if pd.notna(x) and str(x).strip() != '']
    type_filter = st.sidebar.multiselect("🏷️ 開案類別", options=type_options)

    if cat_filter: df_filtered = df_filtered[df_filtered['產品類別'].isin(cat_filter)]
    if type_filter: df_filtered = df_filtered[df_filtered['開案類別'].isin(type_filter)]

    base_numeric_cols = ['目標毛利', '目標銷貨成本', 'Total_預算', 'Total_實際']
    month_prefixes = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec', 'Q2']
    for prefix in month_prefixes: base_numeric_cols.extend([f"{prefix}_預算", f"{prefix}_實際"])

    for col in base_numeric_cols:
        if col in df_filtered.columns:
            df_filtered[col] = df_filtered[col].apply(clean_numeric)
            mask_subsidiary = df_filtered['公司別'] == '鎧鍶釩'
            df_filtered.loc[mask_subsidiary, col] = df_filtered.loc[mask_subsidiary, col] * rmb_rate

    percent_cols = ['預期毛利率', 'Total_達成率'] + [f"{prefix}_達成率" for prefix in month_prefixes]
    for col in percent_cols:
        if col in df_filtered.columns:
            df_filtered[col] = df_filtered[col].apply(clean_percent)

    # =========================================================================
    # 🎯 年度財務戰略指標 (單位：TWD)
    # =========================================================================
    st.divider()
    st.markdown("### 🎯 年度財務戰略指標 (單位：TWD)")
    
    total_budget = df_filtered['Total_預算'].sum() if 'Total_預算' in df_filtered.columns else 0
    total_actual = df_filtered['Total_實際'].sum() if 'Total_實際' in df_filtered.columns else 0
    total_gross_margin = df_filtered['目標毛利'].sum() if '目標毛利' in df_filtered.columns else 0
    overall_achieve_rate = (total_actual / total_budget) if total_budget > 0 else 0

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("💰 全年總預算 (Budget)", f"${total_budget:,.0f}", help="加總當下篩選條件之總預算。鎧鍶釩數值已乘匯率轉換為 TWD。")
    kpi2.metric("📈 累計實際營收 (Actual)", f"${total_actual:,.0f}", help="加總當下篩選條件之實際營收。鎧鍶釩數值已乘匯率轉換為 TWD。")
    kpi3.metric("🎯 整體達成率 (YTD %)", f"{overall_achieve_rate:.1%}", help="(累計實際營收 TWD) ÷ (全年總預算 TWD) × 100%")
    kpi4.metric("💎 預期總毛利 (Gross Margin)", f"${total_gross_margin:,.0f}", help="加總當下篩選條件之目標毛利。鎧鍶釩數值已乘匯率轉換為 TWD。")

    with st.expander("💡 點此查看指標計算邏輯與資料來源"):
        st.markdown(f"""
        **數據轉換邏輯聲明：**
        目前檢視視角為：**{view_option}**
        
        * **凱鍶：** 系統判定為 TWD 基準，數值**不進行**匯率轉換。
        * **鎧鍶釩：** 系統判定為 RMB 基準，財務數值已自動根據設定匯率 (**1 RMB = {rmb_rate} TWD**) 轉換為新台幣。
        """)

    # =========================================================================
    # 📅 月度預算與實際營收趨勢
    # =========================================================================
    st.divider()
    st.markdown("### 📅 月度預算與實際營收趨勢")
    
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    trend_data = []

    for m in months:
        b_col = f"{m}_預算"
        a_col = f"{m}_實際"
        if b_col in df_filtered.columns and a_col in df_filtered.columns:
            m_budget = df_filtered[b_col].sum()
            m_actual = df_filtered[a_col].sum()
            m_rate = (m_actual / m_budget) if m_budget > 0 else 0
            trend_data.append({'Month': m, 'Budget': m_budget, 'Actual': m_actual, 'Achieve_Rate': m_rate})

    df_trend = pd.DataFrame(trend_data) if trend_data else pd.DataFrame()

    if not df_trend.empty:
        fig_trend = go.Figure()
        fig_trend.add_trace(go.Bar(x=df_trend['Month'], y=df_trend['Budget'], name='預算 (Budget)', marker_color='#EBF5FB', marker_line_color='#2E86C1', marker_line_width=1.5, opacity=0.8, yaxis='y1'))
        fig_trend.add_trace(go.Bar(x=df_trend['Month'], y=df_trend['Actual'], name='實際 (Actual)', marker_color='#2E86C1', yaxis='y1'))
        fig_trend.add_trace(go.Scatter(x=df_trend['Month'], y=df_trend['Achieve_Rate'], name='達成率 (%)', mode='lines+markers+text', marker=dict(color='#E74C3C', size=8), line=dict(width=3, dash='dot'), text=[f"{val:.0%}" for val in df_trend['Achieve_Rate']], textposition='top center', yaxis='y2'))

        fig_trend.update_layout(barmode='group', yaxis=dict(title='金額 (TWD)', showgrid=True, gridcolor='#E5E8E8'), yaxis2=dict(title='達成率', overlaying='y', side='right', tickformat='.0%', range=[0, max(1.2, df_trend['Achieve_Rate'].max() * 1.1) if not df_trend.empty else 1.2]), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), margin=dict(l=0, r=0, t=60, b=0), height=400, hovermode="x unified")
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("尚無完整的月份資料可供繪製趨勢圖。")

    # =========================================================================
    # 🏆 Top 10 預算貢獻專案
    # =========================================================================
    st.divider()
    col_chart1, col_chart2 = st.columns([1.5, 1])

    with col_chart1:
        st.markdown("### 🏆 Top 10 預算貢獻專案")
        if 'Total_預算' in df_filtered.columns and not df_filtered.empty:
            df_top10 = df_filtered.nlargest(10, 'Total_預算').sort_values('Total_預算', ascending=True)
            
            if view_option == "凱鍶+鎧鍶釩":
                df_top10['顯示專案'] = df_top10['專案'] + " (" + df_top10['公司別'] + ")"
            else:
                df_top10['顯示專案'] = df_top10['專案']
                
            max_val = df_top10['Total_預算'].max()
            x_limit = max_val * 1.25 if max_val > 0 else 100
                
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                y=df_top10['顯示專案'], x=df_top10['Total_預算'], orientation='h', 
                name='Total 預算', marker_color='rgba(46, 134, 193, 0.2)', 
                marker_line_color='#2E86C1', marker_line_width=1,
                hoverinfo='x+name'
            ))
            fig_bar.add_trace(go.Bar(
                y=df_top10['顯示專案'], x=df_top10['Total_實際'], orientation='h', 
                name='Total 實際', marker_color='#17A589', 
                text=[f" 達成 {r:.0%}" for r in df_top10['Total_達成率']], 
                textposition='outside',
                cliponaxis=False,
                hoverinfo='x+name'
            ))
            fig_bar.update_layout(
                barmode='overlay', 
                yaxis_title="專案", 
                xaxis=dict(title="金額 (TWD)", range=[0, x_limit]), 
                height=400, 
                margin=dict(l=0, r=50, t=80, b=0), 
                legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5) 
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    with col_chart2:
        st.markdown("### 📂 產品類別預算佔比")
        if '產品類別' in df_filtered.columns and not df_filtered.empty:
            df_pie = df_filtered.groupby('產品類別')['Total_預算'].sum().reset_index()
            fig_pie = px.pie(df_pie, values='Total_預算', names='產品類別', hole=0.4, color_discrete_sequence=px.colors.sequential.Teal)
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            fig_pie.update_layout(showlegend=False, margin=dict(t=80, b=0, l=0, r=0), height=400)
            st.plotly_chart(fig_pie, use_container_width=True)

    # =========================================================================
    # 🗓️ 全年預算 vs 實際累積軌跡 (YTD)
    # =========================================================================
    st.divider()
    st.markdown("### 🗓️ 全年預算 vs 實際累積軌跡 (YTD)")
    if not df_trend.empty:
        df_cum = df_trend.copy()
        df_cum['Cum_Budget'] = df_cum['Budget'].cumsum()
        df_cum['Cum_Actual'] = df_cum['Actual'].cumsum()

        fig_cum = go.Figure()
        fig_cum.add_trace(go.Scatter(x=df_cum['Month'], y=df_cum['Cum_Budget'], name='累計預算路徑', mode='lines+markers', line=dict(color='#3498DB', width=3)))
        fig_cum.add_trace(go.Scatter(x=df_cum['Month'], y=df_cum['Cum_Actual'], name='累計實際路徑', mode='lines+markers', line=dict(color='#2ECC71', width=3), fill='tonexty', fillcolor='rgba(46, 204, 113, 0.1)'))
        
        fig_cum.update_layout(yaxis_title="累計金額 (TWD)", xaxis_title="月份", height=400, margin=dict(l=0, r=0, t=60, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1), hovermode="x unified")
        st.plotly_chart(fig_cum, use_container_width=True)

else:
    st.info("請於左側欄上傳預算表以啟動 Dashboard。支援同時上傳多份檔案。")
