"""
專案名稱: 通用專案管理系統 (General Project Management System)
檔案名稱: pms_v5_2.py
版本號碼: v5.2 (雲端原生 + 智慧資料清洗遷移版)
版更紀錄: 
  - v5.1: 內建一鍵遷移工具
  - v5.2: 完美解決 Pandas 讀取 SQLite 時 NaN 型態衝突問題，自動清洗空日期與空整數，並加入資料庫交易復原 (Rollback) 機制。
"""

import streamlit as st
import pandas as pd
import psycopg2
import sqlite3
import os
from datetime import datetime, date
import warnings

warnings.filterwarnings('ignore', category=UserWarning)

st.set_page_config(page_title="專案管理系統 (v5.2)", page_icon="☁️", layout="wide")

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .section-header { font-size: 18px; font-weight: 600; color: #1f2937; margin-top: 25px; border-bottom: 2px solid #e5e7eb; padding-bottom: 5px; display: flex; justify-content: space-between;}
    .task-page-title { font-size: 28px; font-weight: bold; color: #1f2937; margin-bottom: 5px; }
    .back-btn-container { margin-bottom: 20px; }
    .section-progress { color: #10B981; font-size: 16px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

if 'view_mode' not in st.session_state:
    st.session_state.view_mode = 'list'
if 'active_task_id' not in st.session_state:
    st.session_state.active_task_id = None
if 'table_counter' not in st.session_state:
    st.session_state.table_counter = 0

# ==========================================
# 0. 建立 PostgreSQL 資料庫連線
# ==========================================
def get_db_connection():
    if "SUPABASE_DB_URL" not in st.secrets:
        st.error("⚠️ 系統錯誤：找不到雲端資料庫連線字串！請至 Streamlit Cloud 的 Secrets 設定 `SUPABASE_DB_URL`。")
        st.stop()
    try:
        return psycopg2.connect(st.secrets["SUPABASE_DB_URL"])
    except Exception as e:
        st.error(f"⚠️ 無法連線至 Supabase 資料庫，錯誤訊息：{e}")
        st.stop()

# ==========================================
# 1. 資料庫初始化
# ==========================================
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS projects (project_name TEXT PRIMARY KEY, target_date DATE)')
    c.execute('CREATE TABLE IF NOT EXISTS departments (dept_name TEXT PRIMARY KEY)')
    c.execute('CREATE TABLE IF NOT EXISTS assignees (name TEXT PRIMARY KEY)') 
    c.execute('CREATE TABLE IF NOT EXISTS sections (id SERIAL PRIMARY KEY, project_name TEXT, section_name TEXT)')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            project_name TEXT,
            section_name TEXT,
            is_done BOOLEAN,
            task_name TEXT,
            department TEXT,
            assignee TEXT,
            collaborator TEXT,
            due_date DATE,
            description TEXT,
            parent_id INTEGER
        )
    ''')
    conn.commit()
    c.close()
    conn.close()

init_db()
conn = get_db_connection()

# ==========================================
# 2. 側邊欄與全域讀取
# ==========================================
project_list = []
dept_list = []
assignee_list = []

try:
    project_list = pd.read_sql_query("SELECT project_name FROM projects", conn)['project_name'].tolist()
    dept_list = pd.read_sql_query("SELECT dept_name FROM departments", conn)['dept_name'].tolist()
    assignee_list = pd.read_sql_query("SELECT name FROM assignees", conn)['name'].tolist()
except Exception:
    conn.rollback() # 防止交易失敗卡住

with st.sidebar:
    st.header("👤 工作區導覽")
    current_project = st.selectbox("📂 選擇當前專案", project_list) if project_list else None
    
    if 'prev_project' not in st.session_state:
        st.session_state.prev_project = current_project
    if st.session_state.prev_project != current_project:
        st.session_state.view_mode = 'list'
        st.session_state.prev_project = current_project

    st.markdown("---")
    st.caption("☁️ **系統狀態**\n\n🟢 Supabase 雲端資料庫連線正常")

if not current_project and project_list:
    current_project = project_list[0]


# ==========================================
# 3. 讀取與處理子任務階層資料
# ==========================================
if current_project:
    try:
        df_all_tasks = pd.read_sql_query(f"SELECT * FROM tasks WHERE project_name = '{current_project}'", conn)
        df_all_tasks['is_done'] = df_all_tasks['is_done'].fillna(False).astype(bool)
    except Exception:
        conn.rollback()
        df_all_tasks = pd.DataFrame()

    if not df_all_tasks.empty:
        df_children_temp = df_all_tasks[df_all_tasks['parent_id'].notna()]
        sub_counts = df_children_temp.groupby('parent_id').size()
        df_all_tasks['sub_count'] = df_all_tasks['id'].map(sub_counts)
        
        def make_display_name(row):
            name = row['task_name']
            if pd.isna(row['parent_id']) and pd.notna(row['sub_count']) and row['sub_count'] > 0:
                return f"{name} 📦 ({int(row['sub_count'])} 子任務)"
            return name
            
        def make_search_name(row):
            dept = row['department'] if row['department'] else "未定"
            assign = row['assignee'] if row['assignee'] else "未指派"
            if pd.isna(row['parent_id']):
                return f"[{dept} | {assign}] {row['display_name']}"
            else:
                return f"[{dept} | {assign}]  ↳ {row['task_name']} (隸屬子任務)"

        df_all_tasks['display_name'] = df_all_tasks.apply(make_display_name, axis=1)
        df_all_tasks['search_name'] = df_all_tasks.apply(make_search_name, axis=1) 
        
        df_parents = df_all_tasks[df_all_tasks['parent_id'].isna()].copy()
        df_children = df_all_tasks[df_all_tasks['parent_id'].notna()].copy()
    else:
        df_parents = pd.DataFrame(columns=['id', 'section_name', 'is_done', 'task_name', 'display_name', 'search_name', 'department', 'assignee', 'collaborator', 'due_date'])
        df_children = pd.DataFrame()
else:
    df_all_tasks = pd.DataFrame()
    df_parents = pd.DataFrame()
    df_children = pd.DataFrame()


# ==========================================
# 4. 畫面路由 (Routing)
# ==========================================
tab_list, tab_settings = st.tabs(["📋 專案工作區", "⚙️ 專案維護與設定"])

with tab_list:
    if not current_project:
        st.info("💡 目前尚無專案。如果您有舊版的 `pm_system_v4.db` 檔案已上傳至 GitHub，請至隔壁頁籤「⚙️ 專案維護與設定」執行一鍵遷移！")
    else:
        if st.session_state.view_mode == 'list':
            st.title(f"📋 {current_project}")
            
            try:
                target_date_val = pd.read_sql_query(f"SELECT target_date FROM projects WHERE project_name='{current_project}'", conn).iloc[0, 0]
            except:
                conn.rollback()
                target_date_val = date.today()

            if isinstance(target_date_val, str):
                target_date_val = datetime.strptime(target_date_val, '%Y-%m-%d').date()
            elif isinstance(target_date_val, pd.Timestamp):
                target_date_val = target_date_val.date()
            
            days_left = (target_date_val - date.today()).days if target_date_val else 0
            
            total_tasks = len(df_all_tasks)
            completed_tasks = df_all_tasks['is_done'].sum() if not df_all_tasks.empty else 0
            progress_pct = int((completed_tasks / total_tasks * 100)) if total_tasks > 0 else 0
            
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("⏳ 距離上線倒數", f"{days_left} 天")
            kpi2.metric("🎯 總任務數 (含子任務)", f"{total_tasks} 項")
            kpi3.metric("✅ 專案整體完成度", f"{progress_pct} %")
            st.divider()
            
            if not df_all_tasks.empty:
                st.markdown("### 🔍 任務工作站 (編輯詳情)")
                task_options = dict(zip(df_all_tasks['id'], df_all_tasks['search_name']))
                col_search, col_btn = st.columns([4, 1])
                selected_to_edit = col_search.selectbox(
                    "選擇任務進入全螢幕編輯頁面", 
                    options=list(task_options.keys()), 
                    format_func=lambda x: task_options[x],
                    index=None,
                    placeholder="🔍 搜尋部門、人員、主任務或子任務名稱..."
                )
                
                if selected_to_edit:
                    selected_row = df_all_tasks[df_all_tasks['id'] == selected_to_edit].iloc[0]
                    if pd.notna(selected_row['parent_id']):
                        st.session_state.active_task_id = int(selected_row['parent_id'])
                    else:
                        st.session_state.active_task_id = int(selected_to_edit)
                    st.session_state.view_mode = 'detail'
                    st.rerun()
            
            st.divider()

            try:
                sections = pd.read_sql_query(f"SELECT section_name FROM sections WHERE project_name='{current_project}'", conn)['section_name'].tolist()
            except:
                conn.rollback()
                sections = []
            
            column_config = {
                "id": None, 
                "is_done": st.column_config.CheckboxColumn("✅", width="small"),
                "display_name": st.column_config.TextColumn("任務名稱", required=True, width="large"),
                "section_name": st.column_config.SelectboxColumn("隸屬區段", options=sections, width="medium"),
                "department": st.column_config.SelectboxColumn("負責部門", options=dept_list, width="medium"),
                "assignee": st.column_config.SelectboxColumn("指派對象", options=assignee_list, width="medium"),
                "due_date": st.column_config.DateColumn("截止日期", width="small"),
                "delete_flag": st.column_config.CheckboxColumn("🗑️ 刪除", width="small")
            }

            with st.expander("➕ 新增區段 (Add Section)"):
                new_section = st.text_input("區段名稱", key="new_sec_input")
                if st.button("建立區段") and new_section and new_section not in sections:
                    c = conn.cursor()
                    c.execute("INSERT INTO sections (project_name, section_name) VALUES (%s, %s)", (current_project, new_section))
                    conn.commit()
                    c.close()
                    st.rerun()
            
            for sec in sections:
                sec_tasks = df_all_tasks[df_all_tasks['section_name'] == sec] if not df_all_tasks.empty else pd.DataFrame()
                sec_total = len(sec_tasks)
                sec_done = sec_tasks['is_done'].sum() if not sec_tasks.empty else 0
                sec_pct = int((sec_done / sec_total * 100)) if sec_total > 0 else 0
                
                st.markdown(f"""
                    <div class='section-header'>
                        <div>🔽 {sec}</div>
                        <div class='section-progress'>✅ {sec_pct}% 完成</div>
                    </div>
                """, unsafe_allow_html=True)
                
                df_sec = df_parents[df_parents['section_name'] == sec].copy() if not df_parents.empty else pd.DataFrame()
                if not df_sec.empty:
                    df_sec['due_date'] = pd.to_datetime(df_sec['due_date'], errors='coerce').dt.date
                    df_sec['delete_flag'] = False 
                
                cols_order = ['id', 'is_done', 'display_name', 'section_name', 'department', 'assignee', 'due_date', 'delete_flag']
                df_sec_display = df_sec[cols_order].reset_index(drop=True) if not df_sec.empty else pd.DataFrame(columns=cols_order)
                
                editor_key = f"autosave_{sec}_{st.session_state.table_counter}"
                
                if not df_sec_display.empty:
                    edited_df = st.data_editor(
                        df_sec_display, 
                        column_config=column_config, 
                        use_container_width=True, 
                        num_rows="fixed", 
                        hide_index=True, 
                        key=editor_key
                    )
                    
                    if editor_key in st.session_state:
                        changes = st.session_state[editor_key]
                        if changes.get("edited_rows"):
                            c = conn.cursor()
                            for r_idx, cols_dict in changes.get("edited_rows", {}).items():
                                r_id = int(df_sec_display.iloc[int(r_idx)]['id'])
                                u_row = edited_df.iloc[int(r_idx)]
                                
                                if u_row.get('delete_flag') == True:
                                    c.execute("DELETE FROM tasks WHERE id = %s OR parent_id = %s", (r_id, r_id))
                                    continue 
                                
                                raw_display = str(u_row['display_name'])
                                t_name = raw_display.split(" 📦")[0].strip() 
                                if not t_name: 
                                    t_name = str(df_sec_display.iloc[int(r_idx)]['display_name']).split(" 📦")[0].strip() 
                                    
                                d_done = True if u_row['is_done'] else False
                                new_sec = str(u_row['section_name']).strip() if pd.notna(u_row['section_name']) else sec
                                d_dept = str(u_row['department']).strip() if pd.notna(u_row['department']) else ""
                                d_assig = str(u_row['assignee']).strip() if pd.notna(u_row['assignee']) else ""
                                d_due = u_row['due_date']
                                d_due_str = str(d_due)[:10] if pd.notna(d_due) and str(d_due).strip() not in ["", "NaT", "None", "nan"] else None
                                
                                c.execute("""UPDATE tasks SET is_done=%s, task_name=%s, section_name=%s, department=%s, assignee=%s, due_date=%s WHERE id=%s""", 
                                          (d_done, t_name, new_sec, d_dept, d_assig, d_due_str, r_id))
                                
                                if new_sec != sec:
                                    c.execute("UPDATE tasks SET section_name=%s WHERE parent_id=%s", (new_sec, r_id))
                                    
                            conn.commit()
                            c.close()
                            st.session_state.table_counter += 1
                            st.rerun()
                else:
                    st.caption("此區段目前無任務。")

                with st.form(f"add_task_form_{sec}", clear_on_submit=True):
                    col1, col2 = st.columns([5, 1])
                    new_t_name = col1.text_input(f"新增任務至 {sec}", label_visibility="collapsed", placeholder="➕ 輸入新任務名稱 (按 Enter 快速儲存)...")
                    if col2.form_submit_button("新增任務", use_container_width=True):
                        if new_t_name and new_t_name.strip() != "":
                            c = conn.cursor()
                            c.execute("""INSERT INTO tasks (project_name, section_name, is_done, task_name, department, assignee, due_date) 
                                         VALUES (%s, %s, False, %s, '', '', NULL)""", (current_project, sec, new_t_name.strip()))
                            conn.commit()
                            c.close()
                            st.session_state.table_counter += 1
                            st.rerun()

        elif st.session_state.view_mode == 'detail':
            st.markdown("<div class='back-btn-container'>", unsafe_allow_html=True)
            if st.button("⬅️ 返回專案清單"):
                st.session_state.view_mode = 'list'
                st.session_state.active_task_id = None
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

            active_id = st.session_state.active_task_id
            try:
                task_df = pd.read_sql_query(f"SELECT * FROM tasks WHERE id = '{active_id}'", conn)
            except:
                conn.rollback()
                task_df = pd.DataFrame()
            
            if task_df.empty:
                st.error("找不到此任務，可能已被刪除。")
                if st.button("回首頁"):
                    st.session_state.view_mode = 'list'
                    st.rerun()
            else:
                task = task_df.iloc[0]
                try:
                    sections = pd.read_sql_query(f"SELECT section_name FROM sections WHERE project_name='{current_project}'", conn)['section_name'].tolist()
                except:
                    conn.rollback()
                    sections = []
                
                st.markdown(f"<div class='task-page-title'>📝 任務編輯工作站</div>", unsafe_allow_html=True)
                st.divider()

                col_main_edit, col_sub_edit = st.columns([1, 1])
                
                with col_main_edit:
                    with st.container(border=True):
                        st.markdown("#### 基本設定")
                        with st.form("full_edit_form"):
                            edit_name = st.text_input("任務名稱", value=task['task_name'])
                            
                            c_sec, c_date = st.columns(2)
                            s_idx = sections.index(task['section_name']) if task['section_name'] in sections else 0
                            edit_section = c_sec.selectbox("隸屬區段", options=sections, index=s_idx)
                            edit_date = c_date.date_input("截止日期", value=pd.to_datetime(task['due_date']) if pd.notna(task['due_date']) else None)
                            
                            c1, c2 = st.columns(2)
                            d_idx = dept_list.index(task['department']) if task['department'] in dept_list else None
                            edit_dept = c1.selectbox("負責部門", options=dept_list, index=d_idx, placeholder="選擇部門...")
                            a_idx = assignee_list.index(task['assignee']) if task['assignee'] in assignee_list else None
                            edit_assignee = c2.selectbox("指派對象", options=assignee_list, index=a_idx, placeholder="選擇人員...")
                            
                            edit_collab = st.text_input("🤝 協作對象 (非指派者)", value=task['collaborator'] if pd.notna(task['collaborator']) else "")
                            edit_desc = st.text_area("任務描述", value=task['description'] if pd.notna(task['description']) else "", height=150)
                            
                            st.markdown(" ")
                            if st.form_submit_button("💾 儲存任務變更", type="primary", use_container_width=True):
                                c = conn.cursor()
                                c.execute("""UPDATE tasks SET task_name=%s, section_name=%s, department=%s, assignee=%s, collaborator=%s, due_date=%s, description=%s WHERE id=%s""", 
                                          (edit_name, edit_section, edit_dept if edit_dept else '', edit_assignee if edit_assignee else '', edit_collab, edit_date, edit_desc, int(active_id)))
                                if edit_section != task['section_name']:
                                    c.execute("UPDATE tasks SET section_name=%s WHERE parent_id=%s", (edit_section, int(active_id)))
                                conn.commit()
                                c.close()
                                st.success("變更已儲存！")
                                st.rerun()
                                
                        if st.button("🗑️ 刪除此任務 (包含所有子任務)", use_container_width=True):
                            c = conn.cursor()
                            c.execute("DELETE FROM tasks WHERE id = %s OR parent_id = %s", (int(active_id), int(active_id)))
                            conn.commit()
                            c.close()
                            st.session_state.view_mode = 'list'
                            st.session_state.active_task_id = None
                            st.rerun()

                with col_sub_edit:
                    with st.container(border=True):
                        st.markdown("#### 📑 子任務清單")
                        sub_df = df_children[df_children['parent_id'] == active_id].copy() if not df_children.empty else pd.DataFrame()
                        
                        with st.form("subtask_manage_form"):
                            if not sub_df.empty:
                                sub_df['is_done'] = sub_df['is_done'].astype(bool)
                                edited_subs = st.data_editor(
                                    sub_df[['id', 'is_done', 'task_name', 'assignee']], 
                                    column_config={
                                        "id": None, 
                                        "is_done": st.column_config.CheckboxColumn("✅", width="small"), 
                                        "task_name": st.column_config.TextColumn("子任務名稱", required=True), 
                                        "assignee": st.column_config.SelectboxColumn("指派給", options=assignee_list)
                                    },
                                    use_container_width=True, hide_index=True, num_rows="dynamic"
                                )
                            else:
                                st.caption("目前無子任務。")
                                edited_subs = pd.DataFrame()
                                
                            st.write("➕ **快速新增子任務**")
                            c_sub1, c_sub2 = st.columns([2, 1])
                            new_sub_name = c_sub1.text_input("新子任務名稱", label_visibility="collapsed", placeholder="輸入子任務名稱...")
                            new_sub_assignee = c_sub2.selectbox("新子任務指派", options=assignee_list, index=None, label_visibility="collapsed", placeholder="選擇指派...")
                            
                            if st.form_submit_button("💾 更新子任務狀態", use_container_width=True):
                                c = conn.cursor()
                                if new_sub_name:
                                    c.execute("""INSERT INTO tasks (project_name, section_name, is_done, task_name, department, assignee, parent_id) 
                                                 VALUES (%s, %s, False, %s, %s, %s, %s)""", 
                                              (task['project_name'], task['section_name'], new_sub_name, task['department'], new_sub_assignee if new_sub_assignee else '', int(active_id)))
                                
                                if not edited_subs.empty:
                                    current_sub_ids = [int(x) for x in edited_subs['id'].dropna().tolist()]
                                    old_sub_ids = sub_df['id'].dropna().tolist()
                                    for did in [x for x in old_sub_ids if x not in current_sub_ids]:
                                        c.execute("DELETE FROM tasks WHERE id = %s", (did,))
                                    
                                    for _, s_row in edited_subs.iterrows():
                                        if pd.notna(s_row.get('id')):
                                            c.execute("UPDATE tasks SET is_done=%s, task_name=%s, assignee=%s WHERE id=%s", 
                                                      (bool(s_row.get('is_done', False)), s_row['task_name'], s_row['assignee'] if pd.notna(s_row['assignee']) else '', int(s_row['id'])))
                                        elif pd.notna(s_row.get('task_name')):
                                            c.execute("""INSERT INTO tasks (project_name, section_name, is_done, task_name, department, assignee, parent_id) 
                                                         VALUES (%s, %s, %s, %s, %s, %s, %s)""", 
                                                      (task['project_name'], task['section_name'], bool(s_row.get('is_done',False)), s_row['task_name'], task['department'], s_row.get('assignee','') if pd.notna(s_row.get('assignee')) else '', int(active_id)))
                                conn.commit()
                                c.close()
                                st.rerun()

# ----------------- Tab 2: 專案維護與設定 (含一鍵資料遷移工具) -----------------
with tab_settings:
    col_set1, col_set2 = st.columns(2)
    
    with col_set1:
        st.subheader("🏢 動態部門管理")
        try:
            df_dept = pd.read_sql_query("SELECT * FROM departments", conn)
        except:
            conn.rollback()
            df_dept = pd.DataFrame(columns=['dept_name'])

        with st.form("dept_form"):
            edited_dept = st.data_editor(df_dept, num_rows="dynamic", use_container_width=True, hide_index=True, column_config={"dept_name": st.column_config.TextColumn("部門名稱", required=True)})
            if st.form_submit_button("更新部門清單"):
                c = conn.cursor()
                c.execute("DELETE FROM departments")
                for _, r in edited_dept.dropna(subset=['dept_name']).iterrows():
                    c.execute("INSERT INTO departments (dept_name) VALUES (%s)", (r['dept_name'],))
                conn.commit()
                c.close()
                st.rerun()
                
        st.markdown("---")
        
        st.subheader("🧑‍🤝‍🧑 指派人員名單管理")
        try:
            df_assignee = pd.read_sql_query("SELECT * FROM assignees", conn)
        except:
            conn.rollback()
            df_assignee = pd.DataFrame(columns=['name'])

        with st.form("assignee_form"):
            edited_assignee = st.data_editor(df_assignee, num_rows="dynamic", use_container_width=True, hide_index=True, column_config={"name": st.column_config.TextColumn("人員姓名", required=True)})
            if st.form_submit_button("更新人員名單"):
                c = conn.cursor()
                c.execute("DELETE FROM assignees")
                for _, r in edited_assignee.dropna(subset=['name']).iterrows():
                    c.execute("INSERT INTO assignees (name) VALUES (%s)", (r['name'],))
                conn.commit()
                c.close()
                st.rerun()
                
        # 🟢 內建一鍵遷移工具 (已完美加入 NaN 清洗防護)
        st.markdown("---")
        st.subheader("📦 本地舊資料無痛遷移工具")
        st.caption("如果您已將舊的 `pm_system_v4.db` 檔案上傳至 GitHub，點擊下方按鈕即可一鍵將所有歷史資料匯入至 Supabase 雲端！")
        
        if st.button("🚀 開始一鍵匯入舊資料至 Supabase", type="primary"):
            old_db_path = 'pm_system_v4.db'
            if not os.path.exists(old_db_path):
                st.error("❌ 找不到 `pm_system_v4.db` 檔案！請確認是否已將檔案上傳至 GitHub 專案根目錄。")
            else:
                try:
                    sqlite_conn = sqlite3.connect(old_db_path)
                    pg_c = conn.cursor()
                    
                    # 1. 遷移 projects
                    df_p = pd.read_sql("SELECT * FROM projects", sqlite_conn)
                    for _, row in df_p.iterrows():
                        t_date = row['target_date']
                        if pd.isna(t_date) or str(t_date).strip() in ['', 'nan', 'NaT', 'None']:
                            t_date = None
                        pg_c.execute("INSERT INTO projects (project_name, target_date) VALUES (%s, %s) ON CONFLICT (project_name) DO NOTHING", (row['project_name'], t_date))
                    
                    # 2. 遷移 departments
                    df_d = pd.read_sql("SELECT * FROM departments", sqlite_conn)
                    for _, row in df_d.iterrows():
                        pg_c.execute("INSERT INTO departments (dept_name) VALUES (%s) ON CONFLICT (dept_name) DO NOTHING", (row['dept_name'],))
                        
                    # 3. 遷移 assignees
                    try:
                        df_a = pd.read_sql("SELECT * FROM assignees", sqlite_conn)
                        for _, row in df_a.iterrows():
                            pg_c.execute("INSERT INTO assignees (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (row['name'],))
                    except:
                        pass
                        
                    # 4. 遷移 sections
                    df_s = pd.read_sql("SELECT * FROM sections", sqlite_conn)
                    for _, row in df_s.iterrows():
                        pg_c.execute("INSERT INTO sections (project_name, section_name) VALUES (%s, %s)", (row['project_name'], row['section_name']))
                        
                    # 5. 遷移 tasks (精準資料清洗，防止 NaN 污染)
                    df_t = pd.read_sql("SELECT * FROM tasks", sqlite_conn)
                    for _, row in df_t.iterrows():
                        # 清洗 due_date
                        due_val = row['due_date']
                        if pd.isna(due_val) or str(due_val).strip() in ['', 'nan', 'NaT', 'None']:
                            due_val = None
                        else:
                            due_val = str(due_val)[:10]

                        # 清洗 parent_id
                        p_id = row['parent_id']
                        if pd.isna(p_id) or str(p_id).strip() in ['', 'nan', 'NaT', 'None']:
                            p_id = None
                        else:
                            p_id = int(p_id)

                        # 清洗文字欄位
                        t_name = row['task_name'] if pd.notna(row['task_name']) else ''
                        dept = row['department'] if pd.notna(row['department']) else ''
                        assign = row['assignee'] if pd.notna(row['assignee']) else ''
                        collab = row['collaborator'] if pd.notna(row['collaborator']) else ''
                        desc = row['description'] if pd.notna(row['description']) else ''
                        is_d = bool(row['is_done']) if pd.notna(row['is_done']) else False

                        pg_c.execute("""INSERT INTO tasks (project_name, section_name, is_done, task_name, department, assignee, collaborator, due_date, description, parent_id) 
                                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", 
                                     (row['project_name'], row['section_name'], is_d, t_name, dept, assign, collab, due_val, desc, p_id))
                    
                    conn.commit()
                    pg_c.close()
                    sqlite_conn.close()
                    st.success("🎉 歷史資料成功全數遷移至 Supabase 雲端！請重新整理網頁。")
                    st.rerun()
                except Exception as ex:
                    conn.rollback()
                    st.error(f"❌ 遷移過程發生錯誤：{ex}")

    with col_set2:
        if current_project:
            st.subheader("📑 當前專案區段管理")
            try:
                df_sections = pd.read_sql_query(f"SELECT id, section_name FROM sections WHERE project_name='{current_project}'", conn)
            except:
                conn.rollback()
                df_sections = pd.DataFrame(columns=['id', 'section_name'])

            with st.form("section_form"):
                edited_sections = st.data_editor(df_sections, num_rows="dynamic", use_container_width=True, hide_index=True, column_config={"id": None, "section_name": st.column_config.TextColumn("區段名稱", required=True)})
                if st.form_submit_button("更新區段名稱"):
                    c = conn.cursor()
                    c.execute("DELETE FROM sections WHERE project_name=%s", (current_project,))
                    for _, r in edited_sections.dropna(subset=['section_name']).iterrows():
                        c.execute("INSERT INTO sections (project_name, section_name) VALUES (%s, %s)", (current_project, r['section_name']))
                    conn.commit()
                    c.close()
                    st.rerun()
                    
            st.markdown("---")
                    
            st.subheader("🛠️ 當前專案維護")
            try:
                current_target = pd.read_sql_query(f"SELECT target_date FROM projects WHERE project_name='{current_project}'", conn).iloc[0, 0]
            except:
                conn.rollback()
                current_target = str(date.today())

            with st.form("project_edit_form"):
                update_proj_name = st.text_input("專案名稱", value=current_project)
                if isinstance(current_target, str):
                    current_target_val = datetime.strptime(current_target, '%Y-%m-%d').date()
                elif isinstance(current_target, pd.Timestamp):
                    current_target_val = current_target.date()
                else:
                    current_target_val = date.today()
                    
                update_proj_date = st.date_input("目標上線日", value=current_target_val)
                
                col_u1, col_u2 = st.columns(2)
                if col_u1.form_submit_button("💾 儲存更新", type="primary"):
                    c = conn.cursor()
                    if update_proj_name != current_project:
                        c.execute("UPDATE projects SET project_name=%s, target_date=%s WHERE project_name=%s", (update_proj_name, update_proj_date, current_project))
                        c.execute("UPDATE sections SET project_name=%s WHERE project_name=%s", (update_proj_name, current_project))
                        c.execute("UPDATE tasks SET project_name=%s WHERE project_name=%s", (update_proj_name, current_project))
                    else:
                        c.execute("UPDATE projects SET target_date=%s WHERE project_name=%s", (update_proj_date, current_project))
                    conn.commit()
                    c.close()
                    st.rerun()
                    
                if col_u2.form_submit_button("🗑️ 刪除專案"):
                    c = conn.cursor()
                    c.execute("DELETE FROM projects WHERE project_name=%s", (current_project,))
                    c.execute("DELETE FROM sections WHERE project_name=%s", (current_project,))
                    c.execute("DELETE FROM tasks WHERE project_name=%s", (current_project,))
                    conn.commit()
                    c.close()
                    st.rerun()

        st.markdown("---")
        
        st.subheader("📂 建立新專案")
        with st.form("new_project_form"):
            new_proj_name = st.text_input("新專案名稱")
            new_proj_date = st.date_input("預計完成日")
            if st.form_submit_button("➕ 建立專案"):
                if new_proj_name and new_proj_name not in project_list:
                    c = conn.cursor()
                    c.execute("INSERT INTO projects (project_name, target_date) VALUES (%s, %s)", (new_proj_name, new_proj_date))
                    conn.commit()
                    c.close()
                    st.rerun()

conn.close()
