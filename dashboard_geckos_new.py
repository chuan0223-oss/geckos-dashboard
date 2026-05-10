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
st.set_page_config(page_title="凱鍶 財務預算戰情室 V2.22", layout="wide")

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
# ⬇️ Dashboard 主程式 (Version: V2.22 - 名稱精確校正版)
# =========================================================================
st.title("📊 2026 年度預算戰情室 (Budget vs. Actual)")

# --- 終極數字清洗器 ---
def clean_numeric(val):
    if pd.isna(val): return 0.0
    val_str = re.sub(r'[\s,]', '', str(val))
    if val_str == '-' or val_str == '': return 0.0
    
    if val_str.startswith('(') and val_str.endswith(')'):
        val_str = '-' + val_str[1:-1]
        
    try: return float(val_str)
    except: return 0.0

def clean_percent(val):
    if pd.isna(val): return 0.0
    val_str = re.sub(r'[\s,]', '', str(val))
    if val_str == '-' or val_str == '': return 0.0
    
    if val_str.startswith('(') and val_str.endswith(')'):
        val_str = '-' + val_str[1:-1]
        
    try: 
        if '%' in val_str:
            return float(val_str.replace('%', '')) / 100.0
        return float(val_str)
    except: return 0.0

FINANCIAL_KEYWORDS = ['合計', '銷貨收入', '營業收入', '銷貨成本', '營業成本', '毛利', '邊際貢獻', '營業費用', '損益', '本期損益', '營業淨利', '稅前淨利', '稅後淨利']

def is_financial_row(proj_name):
    """ 智慧關鍵字雷達 """
    for kw in FINANCIAL_KEYWORDS:
        if kw in proj_name:
            return True
    return False

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
                if '專案' in row_vals or '項目' in row_vals or '產品名稱' in row_vals:
                    header_idx = i
                    h2 = row_vals
                    break
            
            if header_idx == -1:
                st.error(f"檔案 {file.name} 解析失敗：無法找到表頭。")
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
            
            if 'Sep_實際成本率' in df_temp.columns and 'Sep_預算' not in df_temp.columns:
                df_temp = df_temp.rename(columns={'Sep_實際成本率': 'Sep_預算'})
            
            if '項目' in df_temp.columns and '專案' in df_temp.columns:
                df_temp = df_temp.rename(columns={'專案': '開案類別'})
                
            rename_dict = {}
            if '項目' in df_temp.columns: rename_dict['項目'] = '專案'
            if '產品名稱' in df_temp.columns: rename_dict['產品名稱'] = '專案'
            if '開案' in df_temp.columns: rename_dict['開案'] = '開案類別'
            if '類別' in df_temp.columns: rename_dict['類別'] = '產品類別'
            
            if rename_dict:
                df_temp = df_temp.rename(columns=rename_dict)
                
            df_temp = df_temp.dropna(subset=['專案'])
            df_temp['專案'] = df_temp['專案'].astype(str).str.strip()
            
            if "鎧鍶釩" in file.name:
                df_temp['公司別'] = '鎧鍶釩'
            elif "凱鍶" in file.name or "鎧鍶" in file.name:
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

    df_combined['專案_Clean'] = df_combined['專案'].astype(str).str.strip()
    mask_financial = df_combined['專案_Clean'].apply(is_financial_row)
    
    df_proj_all = df_combined[~mask_financial].copy()
    df_fin_all = df_combined[mask_financial].copy()

    # =========================================================================
    # [區塊 1] 篩選條件設定
    # =========================================================================
    st.sidebar.divider()
    st.sidebar.header("⚙️ 參數與篩選")
    
    view_option = st.sidebar.selectbox("🏢 檢視視角 (圖表連動)", options=["凱鍶+鎧鍶釩", "凱鍶", "鎧鍶釩"])
    
    st.sidebar.markdown("#### 📅 月份篩選")
    col_m1, col_m2 = st.sidebar.columns(2)
    start_month = col_m1.number_input("從 (月)", min_value=1, max_value=12, value=1, step=1)
    end_month = col_m2.number_input("至 (月)", min_value=1, max_value=12, value=12, step=1)

    if start_month > end_month:
        st.sidebar.error("起始月份不能大於結束月份！")
        st.stop()
        
    all_months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    selected_months = all_months[start_month-1 : end_month]

    st.sidebar.markdown("#### 📌 維度篩選")
    project_options = [x for x in df_proj_all['專案'].unique() if pd.notna(x) and str(x).strip() != '']
    project_filter = st.sidebar.multiselect("🏷️ 專案", options=project_options)

    type_options = [x for x in df_proj_all['開案類別'].unique() if pd.notna(x) and str(x).strip() != '']
    type_filter = st.sidebar.multiselect("🏷️ 開案類別", options=type_options)

    cat_options = [x for x in df_proj_all['產品類別'].unique() if pd.notna(x) and str(x).strip() != '']
    cat_filter = st.sidebar.multiselect("📂 產品類別", options=cat_options)

    if project_filter: df_proj_all = df_proj_all[df_proj_all['專案'].isin(project_filter)]
    if type_filter: df_proj_all = df_proj_all[df_proj_all['開案類別'].isin(type_filter)]
    if cat_filter: df_proj_all = df_proj_all[df_proj_all['產品類別'].isin(cat_filter)]

    st.sidebar.markdown("#### 💱 匯率設定")
    rmb_rate = st.sidebar.number_input("RMB 換 TWD 匯率 (僅套用鎧鍶釩)", value=4.60, step=0.05, format="%.2f")

    # =========================================================================
    # 💎 數據轉型與基礎計算
    # =========================================================================
    cols_to_clean = ['目標邊際貢獻', '目標銷貨成本', '目標成本率']
    for prefix in all_months + ['Total']: 
        cols_to_clean.extend([f"{prefix}_預算", f"{prefix}_實際", f"{prefix}_實際成本", f"{prefix}_實際CMR"])
    
    for col in cols_to_clean:
        if col in df_proj_all.columns:
            if col in ['目標成本率'] or col.endswith('實際CMR'):
                df_proj_all[col] = df_proj_all[col].apply(clean_percent).astype(float)
            else:
                df_proj_all[col] = df_proj_all[col].apply(clean_numeric).astype(float)
                
    for col in cols_to_clean:
        if col in df_fin_all.columns:
            if col in ['目標成本率'] or col.endswith('實際CMR'):
                df_fin_all[col] = df_fin_all[col].apply(clean_percent).astype(float)
            else:
                df_fin_all[col] = df_fin_all[col].apply(clean_numeric).astype(float)

    # =========================================================================
    # [區塊 2] 🎯 財務戰略指標 
    # =========================================================================
    st.divider()
    st.markdown(f"### 🎯 財務戰略指標 ({start_month}月 ~ {end_month}月)")

    def get_raw_metrics(df_p):
        b_cols = [f"{m}_預算" for m in selected_months if f"{m}_預算" in df_p.columns]
        a_cols = [f"{m}_實際" for m in selected_months if f"{m}_實際" in df_p.columns]
        ac_cols = [f"{m}_實際成本" for m in selected_months if f"{m}_實際成本" in df_p.columns]
        
        bud = df_p[b_cols].sum().sum() if b_cols else 0
        act = df_p[a_cols].sum().sum() if a_cols else 0
        act_cost = df_p[ac_cols].sum().sum() if ac_cols else 0
            
        return bud, act, act_cost, len(ac_cols) > 0

    p_bud, p_act, p_act_cost, p_has_cost = get_raw_metrics(df_proj_all[df_proj_all['公司別'] == '凱鍶'])
    s_bud, s_act, s_act_cost, s_has_cost = get_raw_metrics(df_proj_all[df_proj_all['公司別'] == '鎧鍶釩'])

    g_bud = p_bud + (s_bud * rmb_rate)
    g_act = p_act + (s_act * rmb_rate)
    g_act_cost = p_act_cost + (s_act_cost * rmb_rate)
    g_has_cost = p_has_cost or s_has_cost

    def calculate_rates(bud, act, act_cost, has_cost):
        rate = act / bud if bud > 0 else 0
        if act > 0 and has_cost:
            act_cmr = (act - act_cost) / act
        else:
            act_cmr = 0.0
        return rate, act_cmr

    p_rate, p_act_cmr = calculate_rates(p_bud, p_act, p_act_cost, p_has_cost)
    s_rate, s_act_cmr = calculate_rates(s_bud, s_act, s_act_cost, s_has_cost)
    g_rate, g_act_cmr = calculate_rates(g_bud, g_act, g_act_cost, g_has_cost)

    # 固定的公司目標 CMR
    p_target_cmr = 0.40  # 凱鍶 40%
    s_target_cmr = 0.10  # 鎧鍶釩 10%

    def make_kpi_card(title, value, color="#2E86C1"):
        return f"""
        <div style="padding: 10px; border-radius: 8px; border-left: 6px solid {color}; background-color: rgba(128, 128, 128, 0.05); margin-bottom: 10px; display: flex; flex-direction: column; justify-content: space-between; height: 100%;">
            <p style="margin: 0; font-size: 0.9rem; color: gray;">{title}</p>
            <h1 style="margin: 5px 0 0 0; font-size: 1.8rem; font-weight: 700; color: #2C3E50;">{value}</h1>
            <div style='margin-top: 5px; font-size: 0.85rem; color: transparent;'>-</div>
        </div>
        """

    st.markdown("##### 🏢 集團合併 (凱鍶 + 鎧鍶釩) - 單位：TWD")
    kg1, kg2, kg3, kg4 = st.columns(4)
    with kg1: st.markdown(make_kpi_card("💰 區間總預算", f"${g_bud:,.0f}", "#3498DB"), unsafe_allow_html=True)
    with kg2: st.markdown(make_kpi_card("📈 區間實際營收", f"${g_act:,.0f}", "#2ECC71"), unsafe_allow_html=True)
    with kg3: st.markdown(make_kpi_card("🎯 區間達成率", f"{g_rate:.1%}", "#E74C3C"), unsafe_allow_html=True)
    with kg4: st.markdown(make_kpi_card("📊 實際 CMR", f"{g_act_cmr:.1%}", "#9B59B6"), unsafe_allow_html=True)

    st.markdown("##### 🇹🇼 凱鍶總公司 - 單位：TWD")
    kp1, kp2, kp3, kp4, kp5 = st.columns(5)
    with kp1: st.markdown(make_kpi_card("💰 區間總預算", f"${p_bud:,.0f}", "#3498DB"), unsafe_allow_html=True)
    with kp2: st.markdown(make_kpi_card("📈 區間實際營收", f"${p_act:,.0f}", "#2ECC71"), unsafe_allow_html=True)
    with kp3: st.markdown(make_kpi_card("🎯 區間達成率", f"{p_rate:.1%}", "#E74C3C"), unsafe_allow_html=True)
    with kp4: st.markdown(make_kpi_card("🎯 目標 CMR", f"{p_target_cmr:.1%}", "#F39C12"), unsafe_allow_html=True)
    with kp5: st.markdown(make_kpi_card("📊 實際 CMR", f"{p_act_cmr:.1%}", "#9B59B6"), unsafe_allow_html=True)

    st.markdown("##### 🇨🇳 鎧鍶釩子公司 - 單位：CNY")
    ks1, ks2, ks3, ks4, ks5 = st.columns(5)
    with ks1: st.markdown(make_kpi_card("💰 區間總預算", f"¥{s_bud:,.0f}", "#3498DB"), unsafe_allow_html=True)
    with ks2: st.markdown(make_kpi_card("📈 區間實際營收", f"¥{s_act:,.0f}", "#2ECC71"), unsafe_allow_html=True)
    with ks3: st.markdown(make_kpi_card("🎯 區間達成率", f"{s_rate:.1%}", "#E74C3C"), unsafe_allow_html=True)
    with ks4: st.markdown(make_kpi_card("🎯 目標 CMR", f"{s_target_cmr:.1%}", "#F39C12"), unsafe_allow_html=True)
    with ks5: st.markdown(make_kpi_card("📊 實際 CMR", f"{s_act_cmr:.1%}", "#9B59B6"), unsafe_allow_html=True)

    # =========================================================================
    # 🔀 圖表資料準備 (依照檢視視角動態轉換幣別)
    # =========================================================================
    if view_option == "凱鍶":
        df_view_proj = df_proj_all[df_proj_all['公司別'] == '凱鍶'].copy()
        curr_sym = "TWD"
    elif view_option == "鎧鍶釩":
        df_view_proj = df_proj_all[df_proj_all['公司別'] == '鎧鍶釩'].copy()
        curr_sym = "CNY"
    else:
        df_view_proj = df_proj_all.copy()
        curr_sym = "TWD"
        mask_sub = df_view_proj['公司別'] == '鎧鍶釩'
        if mask_sub.any():
            for col in cols_to_clean:
                if col not in ['目標成本率'] and not col.endswith('實際CMR') and col in df_view_proj.columns:
                    df_view_proj.loc[mask_sub, col] = df_view_proj.loc[mask_sub, col] * float(rmb_rate)

    v_b_cols = [f"{m}_預算" for m in selected_months if f"{m}_預算" in df_view_proj.columns]
    v_a_cols = [f"{m}_實際" for m in selected_months if f"{m}_實際" in df_view_proj.columns]
    v_ac_cols = [f"{m}_實際成本" for m in selected_months if f"{m}_實際成本" in df_view_proj.columns]
    
    df_view_proj['Total_預算'] = df_view_proj[v_b_cols].sum(axis=1) if v_b_cols else 0
    df_view_proj['Total_實際'] = df_view_proj[v_a_cols].sum(axis=1) if v_a_cols else 0
    df_view_proj['Total_實際成本'] = df_view_proj[v_ac_cols].sum(axis=1) if v_ac_cols else 0
    df_view_proj['Total_達成率'] = np.where(df_view_proj['Total_預算'] > 0, df_view_proj['Total_實際'] / df_view_proj['Total_預算'], 0)
    
    df_view_proj['實際CMR_動態'] = np.where(df_view_proj['Total_實際'] > 0, (df_view_proj['Total_實際'] - df_view_proj['Total_實際成本']) / df_view_proj['Total_實際'], 0)

    # =========================================================================
    # 📌 預先準備 Top 10 專案名單 
    # =========================================================================
    if 'Total_預算' in df_view_proj.columns and not df_view_proj.empty:
        df_view_proj['排序依據'] = df_view_proj[['Total_預算', 'Total_實際']].max(axis=1)
        df_top10 = df_view_proj.nlargest(10, '排序依據').sort_values('排序依據', ascending=True)
        if view_option == "凱鍶+鎧鍶釩":
            df_top10['顯示專案'] = df_top10['專案'] + " (" + df_top10['公司別'] + ")"
        else:
            df_top10['顯示專案'] = df_top10['專案']
            
        # 寫入固定的公司目標 CMR 供圖表使用
        df_top10['目標CMR'] = np.where(df_top10['公司別'] == '凱鍶', p_target_cmr, np.where(df_top10['公司別'] == '鎧鍶釩', s_target_cmr, 0))
    else:
        df_top10 = pd.DataFrame()

    # =========================================================================
    # [區塊 3] 📅 月度專案預算與營收趨勢
    # =========================================================================
    st.divider()
    st.markdown(f"### 📅 月度專案預算與營收趨勢 - 視角：{view_option}")
    
    trend_data = []
    for m in selected_months:
        b_col = f"{m}_預算"
        a_col = f"{m}_實際"
        if b_col in df_view_proj.columns and a_col in df_view_proj.columns:
            m_budget = df_view_proj[b_col].sum()
            m_actual = df_view_proj[a_col].sum()
            m_rate = (m_actual / m_budget) if m_budget > 0 else 0
            trend_data.append({'Month': m, 'Budget': m_budget, 'Actual': m_actual, 'Achieve_Rate': m_rate})

    df_trend = pd.DataFrame(trend_data) if trend_data else pd.DataFrame()

    if not df_trend.empty:
        fig_trend = go.Figure()
        fig_trend.add_trace(go.Bar(x=df_trend['Month'], y=df_trend['Budget'], name='預算 (Budget)', marker_color='#EBF5FB', marker_line_color='#2E86C1', marker_line_width=1.5, opacity=0.8, yaxis='y1'))
        fig_trend.add_trace(go.Bar(x=df_trend['Month'], y=df_trend['Actual'], name='實際 (Actual)', marker_color='#2E86C1', yaxis='y1'))
        fig_trend.add_trace(go.Scatter(x=df_trend['Month'], y=df_trend['Achieve_Rate'], name='達成率 (%)', mode='lines+markers+text', marker=dict(color='#E74C3C', size=8), line=dict(width=3, dash='dot'), text=[f"{val:.0%}" for val in df_trend['Achieve_Rate']], textposition='top center', yaxis='y2'))

        fig_trend.update_layout(barmode='group', yaxis=dict(title=f'金額 ({curr_sym})', showgrid=True, gridcolor='#E5E8E8'), yaxis2=dict(title='達成率', overlaying='y', side='right', tickformat='.0%', range=[0, max(1.2, df_trend['Achieve_Rate'].max() * 1.1) if not df_trend.empty else 1.2]), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), margin=dict(l=0, r=0, t=60, b=0), height=400, hovermode="x unified")
        st.plotly_chart(fig_trend, use_container_width=True)

    # =========================================================================
    # [區塊 4] 🎯 Top 10 目標邊際貢獻率(CMR)標靶圖 
    # =========================================================================
    st.divider()
    st.markdown(f"### 🎯 Top 10 邊際貢獻率(CMR)標靶圖 - 視角：{view_option}")
    
    if not df_top10.empty:
        df_cmr = df_top10.copy()
        cmr_colors = ['#2ECC71' if act >= exp else '#E74C3C' for act, exp in zip(df_cmr['實際CMR_動態'], df_cmr['目標CMR'])]
        
        fig_cmr = go.Figure()

        fig_cmr.add_trace(go.Bar(
            y=df_cmr['顯示專案'], x=df_cmr['目標CMR'], orientation='h', name='目標範圍 (背景)',
            marker_color='rgba(220, 224, 228, 0.4)', hoverinfo='none'
        ))

        fig_cmr.add_trace(go.Bar(
            y=df_cmr['顯示專案'], x=df_cmr['實際CMR_動態'], orientation='h', name='實際 CMR',
            marker_color=cmr_colors, width=0.45,
            text=[f"<b>{val:.1%}</b>" if val != 0 else "" for val in df_cmr['實際CMR_動態']],
            textposition='inside', insidetextanchor='end',         
            textfont=dict(color='white', size=22), cliponaxis=False, hoverinfo='x+name'
        ))

        fig_cmr.add_trace(go.Scatter(
            y=df_cmr['顯示專案'], x=df_cmr['目標CMR'], mode='markers', name='目標 CMR (底線)',
            marker=dict(symbol='line-ns', size=24, color='#2C3E50', line=dict(width=3, color='#2C3E50')), 
            hoverinfo='x+name'
        ))

        fig_cmr.update_layout(
            barmode='overlay', 
            yaxis=dict(title=dict(text="專案", font=dict(size=16, color='black')), tickfont=dict(size=15, color='black')),
            xaxis=dict(title=dict(text="CMR 邊際貢獻率", font=dict(size=15, color='black')), tickformat=".0%", tickfont=dict(size=14, color='black')),
            height=600, margin=dict(l=0, r=50, t=60, b=0), 
            legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5, font=dict(size=15)) 
        )
        st.plotly_chart(fig_cmr, use_container_width=True)

    # =========================================================================
    # [區塊 5] 🏆 Top 10 預算貢獻專案 
    # =========================================================================
    st.divider()
    st.markdown(f"### 🏆 Top 10 預算貢獻專案 - 視角：{view_option}")
    
    if not df_top10.empty:
        def get_achieve_label(b, a, rate):
            if b <= 0 and a > 0: return " 🎉 額外營收 (無預算)"
            elif b <= 0 and a <= 0: return " -"
            else: return f" 達成 {rate:.0%}"
                
        df_top10['顯示標籤'] = df_top10.apply(lambda row: get_achieve_label(row['Total_預算'], row['Total_實際'], row['Total_達成率']), axis=1)
            
        max_val = df_top10['排序依據'].max()
        x_limit = max_val * 1.35 if max_val > 0 else 100
            
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            y=df_top10['顯示專案'], x=df_top10['Total_預算'], orientation='h', 
            name='Total 預算', marker_color='rgba(46, 134, 193, 0.2)', marker_line_color='#2E86C1', marker_line_width=1, hoverinfo='x+name'
        ))
        fig_bar.add_trace(go.Bar(
            y=df_top10['顯示專案'], x=df_top10['Total_實際'], orientation='h', 
            name='Total 實際', marker_color='#17A589', text=df_top10['顯示標籤'], textposition='outside', cliponaxis=False, hoverinfo='x+name'
        ))
        fig_bar.update_layout(
            barmode='overlay', yaxis_title="專案", xaxis=dict(title=f"金額 ({curr_sym})", range=[0, x_limit]), 
            height=450, margin=dict(l=0, r=50, t=60, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="center", x=0.5) 
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    # =========================================================================
    # [區塊 6] 📂 產品類別佔比 
    # =========================================================================
    st.divider()
    st.markdown("### 📂 產品類別佔比 (預算 vs 實際)")
    col_p1, col_p2 = st.columns(2)
    
    if '產品類別' in df_view_proj.columns and not df_view_proj.empty:
        df_pie_cat = df_view_proj.groupby('產品類別')[['Total_預算', 'Total_實際']].sum().reset_index()
        with col_p1:
            fig_pie_b1 = px.pie(df_pie_cat, values='Total_預算', names='產品類別', hole=0.4, title='📊 預算佔比', color_discrete_sequence=px.colors.sequential.Blues_r)
            fig_pie_b1.update_traces(textposition='inside', textinfo='percent+label')
            fig_pie_b1.update_layout(showlegend=False, margin=dict(t=50, b=20, l=30, r=30), height=350, title_x=0.5)
            st.plotly_chart(fig_pie_b1, use_container_width=True)
        with col_p2:
            fig_pie_a1 = px.pie(df_pie_cat, values='Total_實際', names='產品類別', hole=0.4, title='💰 實際營收佔比', color_discrete_sequence=px.colors.sequential.Teal_r)
            fig_pie_a1.update_traces(textposition='inside', textinfo='percent+label')
            fig_pie_a1.update_layout(showlegend=False, margin=dict(t=50, b=20, l=30, r=30), height=350, title_x=0.5)
            st.plotly_chart(fig_pie_a1, use_container_width=True)

    # =========================================================================
    # [區塊 7] 📊 開案類別佔比 
    # =========================================================================
    st.divider()
    st.markdown("### 📊 開案類別佔比 (預算 vs 實際)")
    col_o1, col_o2 = st.columns(2)
    
    if '開案類別' in df_view_proj.columns and not df_view_proj.empty:
        df_pie_open = df_view_proj.groupby('開案類別')[['Total_預算', 'Total_實際']].sum().reset_index()
        with col_o1:
            fig_pie_b2 = px.pie(df_pie_open, values='Total_預算', names='開案類別', hole=0.4, title='📊 預算佔比', color_discrete_sequence=px.colors.sequential.Purples_r)
            fig_pie_b2.update_traces(textposition='inside', textinfo='percent+label')
            fig_pie_b2.update_layout(showlegend=False, margin=dict(t=50, b=20, l=30, r=30), height=350, title_x=0.5)
            st.plotly_chart(fig_pie_b2, use_container_width=True)
        with col_o2:
            fig_pie_a2 = px.pie(df_pie_open, values='Total_實際', names='開案類別', hole=0.4, title='💰 實際營收佔比', color_discrete_sequence=px.colors.sequential.Oranges_r)
            fig_pie_a2.update_traces(textposition='inside', textinfo='percent+label')
            fig_pie_a2.update_layout(showlegend=False, margin=dict(t=50, b=20, l=30, r=30), height=350, title_x=0.5)
            st.plotly_chart(fig_pie_a2, use_container_width=True)

else:
    st.info("請於左側欄上傳預算表以啟動 Dashboard。支援同時上傳多份檔案。")
