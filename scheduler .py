import streamlit as st
import pandas as pd
from datetime import date, timedelta
import holidays  
import calendar
import json
from github import Github

# --- INITIAL APP SETUP & STATE CONFIGURATION ---
st.set_page_config(page_title="Physician On-Call Scheduler", layout="wide")
DATA_FILE = "BBCC_master_data.json"

# --- SECURE GITHUB DATABASE CONNECTION ---
def load_data_from_github():
    try:
        g = Github(st.secrets["GITHUB_TOKEN"])
        repo = g.get_repo(st.secrets["GITHUB_REPO"])
        file_content = repo.get_contents(DATA_FILE)
        data = json.loads(file_content.decoded_content.decode("utf-8"))
        return data
    except Exception:
        return None

def save_data_to_github(data_dict):
    try:
        g = Github(st.secrets["GITHUB_TOKEN"])
        repo = g.get_repo(st.secrets["GITHUB_REPO"])
        content_str = json.dumps(data_dict, indent=4)
        
        try:
            file_content = repo.get_contents(DATA_FILE)
            repo.update_file(DATA_FILE, "Update on-call schedule", content_str, file_content.sha)
        except Exception:
            repo.create_file(DATA_FILE, "Initialize on-call schedule", content_str)
        return True
    except Exception as e:
        st.error(f"Cloud write blocked. Error: {e}")
        return False

# --- LOAD SYSTEM STATE ONCE ---
if 'system_loaded' not in st.session_state:
    st.session_state['team'] = {
        'Dr. Vijay Raghavan': {'is_core': True},
        'Dr. CoreTwo': {'is_core': True},
        'Dr. CoverageAlpha': {'is_core': False},
        'Dr. CoverageBeta': {'is_core': False}
    }
    st.session_state['custom_holidays'] = {}
    st.session_state['schedule'] = pd.DataFrame()

    db_data = load_data_from_github()
    if db_data:
        hols = {}
        for k, v in db_data.get('custom_holidays', {}).items():
            m, d = map(int, k.split('-'))
            hols[(m, d)] = v
        st.session_state['custom_holidays'] = hols
        
        sched_list = db_data.get('schedule', [])
        if sched_list:
            df = pd.DataFrame(sched_list)
            df["Start Date"] = pd.to_datetime(df["Start Date"]).dt.date
            df["End Date"] = pd.to_datetime(df["End Date"]).dt.date
            st.session_state['schedule'] = df
            
    st.session_state['system_loaded'] = True
    st.session_state['cal_month'] = date.today().month
    st.session_state['cal_year'] = date.today().year

def trigger_cloud_save():
    schedule_data = []
    if not st.session_state['schedule'].empty:
        for _, row in st.session_state['schedule'].iterrows():
            schedule_data.append({
                "Start Date": row["Start Date"].isoformat() if isinstance(row["Start Date"], date) else row["Start Date"],
                "End Date": row["End Date"].isoformat() if isinstance(row["End Date"], date) else row["End Date"],
                "Time Window": row["Time Window"],
                "Shift Type": row["Shift Type"],
                "Assigned Physician": row["Assigned Physician"]
            })
            
    export_data = {'team': st.session_state['team'], 'custom_holidays': {}, 'schedule': schedule_data}
    for k, v in st.session_state['custom_holidays'].items():
        export_data['custom_holidays'][f"{k[0]:02d}-{k[1]:02d}"] = v
        
    return save_data_to_github(export_data)

# --- GLOBAL STYLING & PRINT COMPRESSION ---
st.markdown("""
<style>
    @media print {
        @page { size: landscape; margin: 10mm; }
        [data-testid="stSidebar"], header[data-testid="stHeader"], .stTabs [role="tablist"], [data-testid="stToolbar"], button { display: none !important; }
        .main .block-container { max-width: 100% !important; padding: 0 !important; margin: 0 !important; }
        table { width: 100% !important; page-break-inside: auto !important; }
        tr { page-break-inside: avoid !important; page-break-after: auto !important; }
        .print-container { zoom: 0.75; -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
    }
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR: MANAGEMENT ---
st.sidebar.header("⚙️ Roster Settings")

st.sidebar.markdown("---")
st.sidebar.subheader("🎉 Add Custom Holidays")
st.sidebar.caption("These will highlight red on the calendar.")
custom_holiday_name = st.sidebar.text_input("Holiday Name")
custom_holiday_date = st.sidebar.date_input("Holiday Date", date.today(), key="holiday_picker")

if st.sidebar.button("Add Holiday"):
    if custom_holiday_name:
        key = (custom_holiday_date.month, custom_holiday_date.day)
        st.session_state['custom_holidays'][key] = custom_holiday_name
        if trigger_cloud_save():
            st.sidebar.success(f"Added: {custom_holiday_name}")

# --- MAIN APP: GENERATE SHIFTS ---
st.title("📅 On-Call Scheduler")

col1, col2 = st.columns(2)
with col1:
    st.markdown("**1. Choose Your Launch Date:**")
    start_date = st.date_input("Schedule Start Date (Choose a Friday)", date.today(), label_visibility="collapsed", key="main_start_date")
with col2:
    st.markdown("**2. How many weeks to generate?**")
    num_weeks = st.number_input("Duration (Weeks)", min_value=1, value=4, label_visibility="collapsed", key="main_duration")

us_holidays = holidays.US(years=[date.today().year, date.today().year + 1])
def check_is_holiday(dt): return dt in us_holidays or (dt.month, dt.day) in st.session_state['custom_holidays']
def get_holiday_name(dt): return us_holidays.get(dt) if dt in us_holidays else st.session_state['custom_holidays'].get((dt.month, dt.day), "Holiday")

if st.button("Generate Master Schedule", type="secondary"):
    st.session_state['cal_month'] = start_date.month
    st.session_state['cal_year'] = start_date.year

    core_physicians_only = [name for name, specs in st.session_state['team'].items() if specs['is_core']]
    
    if len(core_physicians_only) < 2:
        st.error("Please ensure you have at least 2 Core Physicians configured.")
    else:
        schedule_data = []
        current_friday = start_date + timedelta(days=(4 - start_date.weekday()) % 7)
        core_idx = 0
        
        for week in range(int(num_weeks)):
            fri = current_friday
            mon = fri + timedelta(days=3)
            tue = fri + timedelta(days=4)
            
            weekend_end_date = mon
            weekend_label = "Regular Weekend"
            
            if check_is_holiday(mon):
                weekend_end_date = tue
                weekend_label = f"Long Weekend ({get_holiday_name(mon)})"
            elif check_is_holiday(fri):
                weekend_label = f"Long Weekend ({get_holiday_name(fri)})"

            # FIXED: Assign the SAME physician to the entire 7-day stretch
            assigned_doc = core_physicians_only[core_idx % len(core_physicians_only)]
            
            schedule_data.append({
                "Start Date": fri,
                "End Date": weekend_end_date - timedelta(days=1),
                "Time Window": f"{fri.strftime('%m/%d')} (12 PM) to {weekend_end_date.strftime('%m/%d')} (8 AM)",
                "Shift Type": f"Weekend / {weekend_label}",
                "Assigned Physician": assigned_doc
            })
            
            weekday_start = weekend_end_date
            next_friday = fri + timedelta(days=7)
            
            schedule_data.append({
                "Start Date": weekday_start,
                "End Date": next_friday - timedelta(days=1),
                "Time Window": f"{weekday_start.strftime('%m/%d')} (8 AM) to {next_friday.strftime('%m/%d')} (12 PM)",
                "Shift Type": "Weekday Core Block",
                "Assigned Physician": assigned_doc
            })
            
            core_idx += 1 # Move to the other physician for the next week
            current_friday = next_friday

        st.session_state['schedule'] = pd.DataFrame(schedule_data)
        if trigger_cloud_save():
            st.rerun()

# --- DISPLAY TABS ---
st.markdown("---")

if not st.session_state['schedule'].empty:

    tab1, tab2 = st.tabs(["📝 Interactive Grid Editor", "📆 Visual Monthly Calendar View"])
    
    with tab1:
        st.subheader("Interactive Schedule Grid")
        st.caption("Instructions: Make your adjustments inside the spreadsheet columns. **When finished, click the blue LOCK button below to sync modifications live.**")
        
        def color_rows(row): 
            if "Weekend" in row["Shift Type"]: return ['background-color: #f7f9fc; font-weight: bold'] * len(row)
            return [''] * len(row)

        display_df = st.session_state['schedule'][["Time Window", "Shift Type", "Assigned Physician"]]
        
        edited_df = st.data_editor(
            display_df.style.apply(color_rows, axis=1),
            use_container_width=True,
            height=600,
            column_config={
                "Assigned Physician": st.column_config.SelectboxColumn(
                    "On-Call Doctor",
                    options=list(st.session_state['team'].keys()),
                    required=True
                )
            },
            key="grid_editor"
        )
        
        if st.button("💾 LOCK IN & SYNC GRID EDITS", type="primary"):
            st.session_state['schedule']["Assigned Physician"] = edited_df["Assigned Physician"]
            if trigger_cloud_save():
                st.success("Changes Locked and Synced Live to Database! Physicians will now see this updated information.")
                st.rerun()

    with tab2:
        st.subheader("Monthly On-Call Distribution")
        st.caption("🖨️ **To Print:** Press `Ctrl + P` (Windows) or `Cmd + P` (Mac). Layout scales landscape automatically.")
        
        nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
        with nav_col1:
            if st.button("⬅️ Previous Month"):
                if st.session_state['cal_month'] == 1:
                    st.session_state['cal_month'] = 12
                    st.session_state['cal_year'] -= 1
                else:
                    st.session_state['cal_month'] -= 1
                st.rerun()
        with nav_col3:
            if st.button("Next Month ➡️"):
                if st.session_state['cal_month'] == 12:
                    st.session_state['cal_month'] = 1
                    st.session_state['cal_year'] += 1
                else:
                    st.session_state['cal_month'] += 1
                st.rerun()

        st.markdown('<div class="print-container">', unsafe_allow_html=True)
        
        lookup = {}
        for _, row in st.session_state['schedule'].iterrows():
            d_start = pd.to_datetime(row["Start Date"]).date()
            d_end = pd.to_datetime(row["End Date"]).date()
            curr = d_start
            while curr <= d_end:
                lookup[curr] = (row["Assigned Physician"], row["Shift Type"])
                curr += timedelta(days=1)
                
        curr_year = st.session_state['cal_year']
        curr_month = st.session_state['cal_month']
        target_date = date(curr_year, curr_month, 1)
        
        st.write(f"### 🗓️ {target_date.strftime('%B %Y')}")
        
        cal = calendar.Calendar(firstweekday=6)
        month_days = cal.monthdatescalendar(curr_year, curr_month)
        
        html = "<table style='width:100%; border-collapse:collapse; table-layout: fixed; margin-bottom: 25px;'>"
        html += "<tr style='background-color:#f1f3f5; text-align:center; font-weight:bold;'>"
        for day_name in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
            html += f"<th style='padding:8px; border:1px solid #dee2e6;'>{day_name}</th>"
        html += "</tr>"
        
        for week_days in month_days:
            html += "<tr style='vertical-align:top;'>"
            for d in week_days:
                if d.month != curr_month:
                    html += "<td style='border:1px solid #dee2e6; background-color:#fafafa; color:#adb5bd; padding:6px; min-height:80px;'></td>"
                else:
                    bg = "#ffffff"
                    content = ""
                    
                    if d in lookup:
                        doc, stype = lookup[d]
                        content = f"<div style='font-weight:600; font-size:13px; color:#1e293b; margin-top:4px;'>{doc}</div>"
                        if "Weekend" in stype:
                            bg = "#edf2f7"
                            content += "<div style='font-size:10px; color:#64748b;'>Weekend</div>"
                        else:
                            content += "<div style='font-size:10px; color:#94a3b8;'>Weekday</div>"
                            
                    if check_is_holiday(d):
                        bg = "#ffe3e3"
                        content += f"<div style='font-size:10px; color:#dc2626; font-weight:bold;'>{get_holiday_name(d)}</div>"
                        
                    html += f"<td style='border:1px solid #dee2e6; background-color:{bg}; padding:6px; min-height:80px;'>"
                    html += f"<span style='font-size:12px; font-weight:bold; color:#475569;'>{d.day}</span>"
                    html += content
                    html += "</td>"
            html += "</tr>"
        html += "</table>"
        st.markdown(html, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)
