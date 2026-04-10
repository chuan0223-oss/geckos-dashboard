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
st.set_page_config(page_title="凱鍶 財務預算戰情室 V1.92", layout="wide")

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
# ⬇️ Dashboard 主程式 (Version: V1.92)
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
# 📁 資料上傳與多檔合併預處理
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

            header_idx = -1
            h2 = []
            
            for i in range(min(10, len(df_raw))):
                row_vals = [str(val).replace('\ufeff', '').strip() for val in df_raw.iloc[i].tolist()]
                if '專案' in row_vals or '項目' in row_vals:
                    header_idx = i
                    h2 = row_vals
                    break
            
            if header_idx == -1:
                st.error(f"檔案 {file.name} 解析失敗：無法在表格前 10 行找到 '專案' 或 '項目' 欄位。")
                st.stop()

            if header_idx == 0:
                new_cols = h2
            else:
                h1_raw = df_raw.iloc[header_idx - 1].ffill().tolist()
                h1 = [str(v).replace('\ufeff', '').strip() for v in h1_raw]
                
                new_cols = []
                for c1, c2 in zip(h1, h2):
                    if str(c1).lower() in ['nan', 'none', '<na>', 'nat', '']:
                        new_cols.append(str(c2))
                    else:
                        new_cols.append(f"{c1}_{c2}")
                        
            df_temp = df_raw.iloc[header_idx + 1:].copy()
            df_temp.columns = new_cols
            
            if '項目' in df_temp.columns:
                df_temp = df_temp.rename(columns={'專案': '開案類別', '項目': '專案', '類別': '產品類別'})
                
            if '專案' not in df_temp.columns:
                st.error(f"檔案 {file.name} 欄位重組失敗。目前抓取到的欄位：{list(df_temp.columns)}")
                st.stop()
                
            df_temp = df_temp[df_temp['專案'] != '合計']
            df_temp = df_temp.dropna(subset=['專案'])
            df_temp = df_temp[df_temp['專案'].astype(str).str.strip() != '']
            
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
    # [區塊 1] 篩選條件設定
    # =========================================================================
    st.sidebar.divider()
    st.sidebar.header("⚙️ 參數與篩選")
    
    view_option = st.sidebar.selectbox("🏢 檢視視角", options=["凱鍶+鎧鍶釩", "凱鍶", "鎧鍶釩"])
    
    # --- 1. 月份區間篩選器 ---
    st.sidebar.markdown("#### 📅 月份篩選")
    col_m1, col_m2 = st.sidebar.columns(2)
    start_month = col_m1.number_input("從 (月)", min_value=1, max_value=12, value=1, step=1)
    end_month = col_m2.number_input("至 (月)", min_value=1, max_value=12, value=12, step=1)

    if start_month > end_month:
        st.sidebar.error("起始月份不能大於結束月份！")
        st.stop()
        
    all_months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    selected_months = all_months[start_month-1 : end_month]

    # --- 資料預過濾 ---
    if view_option == "凱鍶":
        df_filtered = df_combined[df_combined['公司別'] == '凱鍶'].copy()
    elif view_option == "鎧鍶釩":
        df_filtered = df_combined[df_combined['公司別'] == '鎧鍶釩'].copy()
    else:
        df_filtered = df_combined.copy()

    # --- 2. 維度篩選器 ---
    st.sidebar.markdown("#### 📌 維度篩選")
    project_options = [x for x in df_filtered['專案'].unique() if pd.notna(x) and str(x).strip() != '']
    project_filter = st.sidebar.multiselect("🏷️ 專案", options=project_options)

    type_options = [x for x in df_filtered['開案類別'].unique() if pd.notna(x) and str(x).strip() != '']
    type_filter = st.sidebar.multiselect("🏷️ 開案類別", options=type_options)

    cat_options = [x for x in df_filtered['產品類別'].unique() if pd.notna(x) and str(x).strip() != '']
    cat_filter = st.sidebar.multiselect("📂 產品類別", options=cat_options)

    if project_filter: df_filtered = df_filtered[df_filtered['專案'].isin(project_filter)]
    if type_filter: df_filtered = df_filtered[df_filtered['開案類別'].isin(type_filter)]
    if cat_filter: df_filtered = df_filtered[df_filtered['產品類別'].isin(cat_filter)]

    # --- 3. RMB 匯率設定 ---
    st.sidebar.markdown("#### 💱 匯率設定")
    rmb_rate = st.sidebar.number_input("RMB 換 TWD 匯率 (僅套用鎧鍶釩)", value=4.40, step=0.05, format="%.2f")

    # --- 數值轉換與 TWD 匯率套用 ---
    base_numeric_cols = ['目標毛利', '目標銷貨成本', 'Total_預算', 'Total_實際']
    for prefix in all_months + ['Q2']: 
        base_numeric_cols.extend([f"{prefix}_預算", f"{prefix}_實際"])

    for col in base_numeric_cols:
        if col in df_filtered.columns:
            df_filtered[col] = df_filtered[col].apply(clean_numeric)
            mask_subsidiary = df_filtered['公司別'] == '鎧鍶釩'
            df_filtered.loc[mask_subsidiary, col] = df_filtered.loc[mask_subsidiary, col] * rmb_rate

    # --- 動態重算 Total 欄位 (根據選擇的月份) ---
    valid_b_cols = [f"{m}_預算" for m in selected_months if f"{m}_預算" in df_filtered.columns]
    valid_a_cols = [f"{m}_實際" for m in selected_months if f"{m}_實際" in df_filtered.columns]
    
    df_filtered['Total_預算'] = df_filtered[valid_b_cols].sum(axis=1) if valid_b_cols else 0
    df_filtered['Total_實際'] = df_filtered[valid_a_cols].sum(axis=1) if valid_a_cols else 0
    df_filtered['Total_達成率'] = np.where(df_filtered['Total_預算'] > 0, df_filtered['Total_實際'] / df_filtered['Total_預算'], 0)

    # =========================================================================
    # [區塊 2] 🎯 財務戰略指標 (V1.92 適度字體版)
    # =========================================================================
    st.divider()
    st.markdown(f"### 🎯 財務戰略指標 ({start_month}月 ~ {end_month}月) - TWD")
    
    total_budget = df_filtered['Total_預算'].sum()
    total_actual = df_filtered['Total_實際'].sum()
    total_gross_margin = df_filtered['目標毛利'].sum() if '目標毛利' in df_filtered.columns else 0
    overall_achieve_rate = (total_actual / total_budget) if total_budget > 0 else 0

    # 字體大小調整：標題 1.0rem，數字 2.2rem (比 V1.91 縮小，比 V1.9 大)
    def make_kpi_card(title, value, color="#2E86C1"):
        return f"""
        <div style="padding: 15px; border-radius: 8px; border-left: 6px solid {color}; background-color: rgba(128, 128, 128, 0.05); margin-bottom: 10px;">
            <p style="margin: 0; font-size: 1.0rem; color: gray;">{title}</p>
            <h1 style="margin: 5px 0 0 0; font-size: 2.2rem; font-weight: 700;">{value}</h1>
        </div>
        """

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1: st.markdown(make_kpi_card("💰 區間總預算 (Budget)", f"${total_budget:,.0f}", "#3498DB"), unsafe_allow_html=True)
    with kpi2: st.markdown(make_kpi_card("📈 區間實際營收 (Actual)", f"${total_actual:,.0f}", "#2ECC71"), unsafe_allow_html=True)
    with kpi3: st.markdown(make_kpi_card("🎯 區間達成率 (%)", f"{overall_achieve_rate:.1%}", "#E74C3C"), unsafe_allow_html=True)
    with kpi4: st.markdown(make_kpi_card("💎 預期總毛利 (全年 Target)", f"${total_gross_margin:,.0f}", "#F1C40F"), unsafe_allow_html=True)

    with st.expander("💡 點此查看指標計算邏輯與資料來源"):
        st.markdown(f"""
        **數據轉換與計算邏輯聲明：**
        目前檢視視角為：**{view_option}** ； 選擇月份區間：**{start_month} 月至 {end_month} 月**。
        * **凱鍶：** 數值不進行匯率轉換。
        * **鎧鍶釩：** 數值依設定匯率 (**1 RMB = {rmb_rate} TWD**) 轉換為新台幣。
        * **區間預算與實際：** 僅加總側邊欄所選定月份之數值，並以此為基礎計算動態達成率。
        """)

    # =========================================================================
    # [區塊 3] 📅 月度趨勢
    # =========================================================================
    st.divider()
    st.markdown("### 📅 月度預算與實際營收趨勢")
    
    trend_data = []
    for m in selected_months:
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
        st.info("所選月份無可用資料。")

    # =========================================================================
    # [區塊 4] 🏆 Top 10 貢獻專案
    # =========================================================================
    st.divider()
    st.markdown("### 🏆 Top 10 預算貢獻專案")
    
    if 'Total_預算' in df_filtered.columns and not df_filtered.empty:
        df_filtered['排序依據'] = df_filtered[['Total_預算', 'Total_實際']].max(axis=1)
        df_top10 = df_filtered.nlargest(10, '排序依據').sort_values('排序依據', ascending=True)
        
        if view_option == "凱鍶+鎧鍶釩":
            df_top10['顯示專案'] = df_top10['專案'] + " (" + df_top10['公司別'] + ")"
        else:
            df_top10['顯示專案'] = df_top10['專案']
            
        def get_achieve_label(b, a, rate):
            if b <= 0 and a > 0:
                return " 🎉 額外營收 (無預算)"
            elif b <= 0 and a <= 0:
                return " -"
            else:
                return f" 達成 {rate:.0%}"
                
        df_top10['顯示標籤'] = df_top10.apply(lambda row: get_achieve_label(row['Total_預算'], row['Total_實際'], row['Total_達成率']), axis=1)
            
        max_val = df_top10['排序依據'].max()
        x_limit = max_val * 1.35 if max_val > 0 else 100
            
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            y=df_top10['顯示專案'], x=df_top10['Total_預算'], orientation='h', 
            name='Total 預算', marker_color='rgba(46, 134, 193, 0.2)', 
            marker_line_color='#2E86C1', marker_line_width=1, hoverinfo='x+name'
        ))
        fig_bar.add_trace(go.Bar(
            y=df_top10['顯示專案'], x=df_top10['Total_實際'], orientation='h', 
            name='Total 實際', marker_color='#17A589', 
            text=df_top10['顯示標籤'], 
            textposition='outside', cliponaxis=False, hoverinfo='x+name'
        ))
        fig_bar.update_layout(
            barmode='overlay', yaxis_title="專案", xaxis=dict(title="金額 (TWD)", range=[0, x_limit]), 
            height=450, margin=dict(l=0, r=50, t=60, b=0), 
            legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5) 
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    # =========================================================================
    # [區塊 5] 📂 產品類別佔比
    # =========================================================================
    st.divider()
    st.markdown("### 📂 產品類別佔比 (預算 vs 實際)")
    col_p1, col_p2 = st.columns(2)
    
    if '產品類別' in df_filtered.columns and not df_filtered.empty:
        df_pie_cat = df_filtered.groupby('產品類別')[['Total_預算', 'Total_實際']].sum().reset_index()
        
        with col_p1:
            fig_pie_b1 = px.pie(df_pie_cat, values='Total_預算', names='產品類別', hole=0.4, title='📊 預算佔比', color_discrete_sequence=px.colors.sequential.Blues_r)
            fig_pie_b1.update_traces(textposition='inside', textinfo='percent+label')
            fig_pie_b1.update_layout(showlegend=False, margin=dict(t=50, b=0, l=0, r=0), height=350, title_x=0.5)
            st.plotly_chart(fig_pie_b1, use_container_width=True)
            
        with col_p2:
            fig_pie_a1 = px.pie(df_pie_cat, values='Total_實際', names='產品類別', hole=0.4, title='💰 實際營收佔比', color_discrete_sequence=px.colors.sequential.Teal_r)
            fig_pie_a1.update_traces(textposition='inside', textinfo='percent+label')
            fig_pie_a1.update_layout(showlegend=False, margin=dict(t=50, b=0, l=0, r=0), height=350, title_x=0.5)
            st.plotly_chart(fig_pie_a1, use_container_width=True)

    # =========================================================================
    # [區塊 6] 📊 開案類別佔比
    # =========================================================================
    st.divider()
    st.markdown("### 📊 開案類別佔比 (預算 vs 實際)")
    col_o1, col_o2 = st.columns(2)
    
    if '開案類別' in df_filtered.columns and not df_filtered.empty:
        df_pie_open = df_filtered.groupby('開案類別')[['Total_預算', 'Total_實際']].sum().reset_index()
        
        with col_o1:
            fig_pie_b2 = px.pie(df_pie_open, values='Total_預算', names='開案類別', hole=0.4, title='📊 預算佔比', color_discrete_sequence=px.colors.sequential.Purples_r)
            fig_pie_b2.update_traces(textposition='inside', textinfo='percent+label')
            fig_pie_b2.update_layout(showlegend=False, margin=dict(t=50, b=0, l=0, r=0), height=350, title_x=0.5)
            st.plotly_chart(fig_pie_b2, use_container_width=True)
            
        with col_o2:
            fig_pie_a2 = px.pie(df_pie_open, values='Total_實際', names='開案類別', hole=0.4, title='💰 實際營收佔比', color_discrete_sequence=px.colors.sequential.Oranges_r)
            fig_pie_a2.update_traces(textposition='inside', textinfo='percent+label')
            fig_pie_a2.update_layout(showlegend=False, margin=dict(t=50, b=0, l=0, r=0), height=350, title_x=0.5)
            st.plotly_chart(fig_pie_a2, use_container_width=True)

else:
    st.info("請於左側欄上傳預算表以啟動 Dashboard。支援同時上傳多份檔案。")
