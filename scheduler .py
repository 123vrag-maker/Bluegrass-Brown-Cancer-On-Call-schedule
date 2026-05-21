import streamlit as st
import pandas as pd
from datetime import date, timedelta
import holidays  
import calendar
import json

# --- INITIAL APP SETUP & STATE CONFIGURATION ---
st.set_page_config(page_title="Physician On-Call Scheduler", layout="wide")

# Pre-populate your stable hospital roster structure layout
if 'team' not in st.session_state:
    st.session_state['team'] = {
        'Dr. Vijay Raghavan': {'vacation_days': [], 'is_core': True},
        'Dr. Iltaf Khan': {'vacation_days': [], 'is_core': True},
        'Dr. Rohit Kumar': {'vacation_days': [], 'is_core': False},
        'Dr. Abigail Chan': {'vacation_days': [], 'is_core': False}
    }

if 'custom_holidays' not in st.session_state:
    st.session_state['custom_holidays'] = {}

if 'schedule' not in st.session_state:
    st.session_state['schedule'] = pd.DataFrame()

# Infinite Calendar Setup
if 'cal_month' not in st.session_state:
    st.session_state['cal_month'] = date.today().month
    st.session_state['cal_year'] = date.today().year

# --- FIXED PRINT CSS ---
# Instead of hiding the whole body, we precisely target only Streamlit's UI menus
st.markdown("""
<style>
    @media print {
        /* Hide sidebars, top headers, tab navigation, and buttons */
        [data-testid="stSidebar"], 
        header[data-testid="stHeader"], 
        .stTabs [role="tablist"],
        [data-testid="stToolbar"],
        button {
            display: none !important;
        }
        
        /* Force the main container to take up the full printed page */
        .main .block-container {
            max-width: 100% !important;
            padding: 0 !important;
            margin: 0 !important;
        }
        
        /* Ensure table rows do not break across physical pages */
        tr { page-break-inside: avoid !important; }
        table { page-break-inside: avoid !important; }
    }
</style>
""", unsafe_allow_html=True)

# --- BACKUP & RESTORE UTILITIES ---
def generate_backup_file():
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
            
    export_data = {'team': {}, 'custom_holidays': {}, 'schedule': schedule_data}
    
    for doc, info in st.session_state['team'].items():
        export_data['team'][doc] = {
            'vacation_days': [d.isoformat() for d in info['vacation_days']],
            'is_core': info['is_core']
        }
    for k, v in st.session_state['custom_holidays'].items():
        export_data['custom_holidays'][f"{k[0]:02d}-{k[1]:02d}"] = v
        
    return json.dumps(export_data, indent=4)

def process_uploaded_backup(uploaded_file):
    try:
        data = json.load(uploaded_file)
        
        team = {}
        for doc, info in data.get('team', {}).items():
            v_days = [date.fromisoformat(d) for d in info.get('vacation_days', [])]
            team[doc] = {'vacation_days': v_days, 'is_core': info.get('is_core', True)}
        st.session_state['team'] = team
        
        hols = {}
        for k, v in data.get('custom_holidays', {}).items():
            m, d = map(int, k.split('-'))
            hols[(m, d)] = v
        st.session_state['custom_holidays'] = hols
        
        sched_list = data.get('schedule', [])
        if sched_list:
            df = pd.DataFrame(sched_list)
            df["Start Date"] = pd.to_datetime(df["Start Date"]).dt.date
            df["End Date"] = pd.to_datetime(df["End Date"]).dt.date
            st.session_state['schedule'] = df
        else:
            st.session_state['schedule'] = pd.DataFrame()
            
        st.success("✅ System successfully restored from backup!")
    except Exception as e:
        st.error("Error reading backup file. Please ensure it is a valid schedule JSON.")

# --- SIDEBAR: MANAGEMENT ---
st.sidebar.header("⚙️ Settings & Storage")

# Backup & Restore UI
st.sidebar.markdown("---")
st.sidebar.subheader("💾 Cloud Backup Manager")
st.sidebar.caption("Streamlit cloud servers reset periodically. Download your file to save changes permanently. Upload it here if the schedule clears.")

st.sidebar.download_button(
    label="⬇️ Download Master Backup File",
    data=generate_backup_file(),
    file_name=f"BBCC_Schedule_Backup_{date.today().strftime('%Y_%m_%d')}.json",
    mime="application/json"
)

uploaded_backup = st.sidebar.file_uploader("⬆️ Restore from Backup", type=['json'])
if uploaded_backup is not None:
    if st.sidebar.button("Apply Uploaded Backup"):
        process_uploaded_backup(uploaded_backup)
        st.rerun()

# Manage Away Dates
st.sidebar.markdown("---")
st.sidebar.subheader("🌴 Manage Away Dates")
selected_doc = st.sidebar.selectbox("Select Physician", options=list(st.session_state['team'].keys()))

date_range = st.sidebar.date_input("Select Date(s)", value=())
if st.sidebar.button("➕ Log Away Date(s)"):
    if isinstance(date_range, tuple) or isinstance(date_range, list):
        if len(date_range) == 2:
            start_d, end_d = date_range[0], date_range[1]
            delta = end_d - start_d
            for i in range(delta.days + 1):
                day = start_d + timedelta(days=i)
                if day not in st.session_state['team'][selected_doc]['vacation_days']:
                    st.session_state['team'][selected_doc]['vacation_days'].append(day)
            st.sidebar.success("Block logged. Remember to Download Backup!")
        elif len(date_range) == 1:
            day = date_range[0]
            if day not in st.session_state['team'][selected_doc]['vacation_days']:
                st.session_state['team'][selected_doc]['vacation_days'].append(day)
                st.sidebar.success("Date logged. Remember to Download Backup!")
    else:
        if date_range not in st.session_state['team'][selected_doc]['vacation_days']:
            st.session_state['team'][selected_doc]['vacation_days'].append(date_range)
            st.sidebar.success("Date logged. Remember to Download Backup!")

current_vacations = st.session_state['team'][selected_doc].get('vacation_days', [])
if current_vacations:
    current_vacations.sort()
    dates_to_remove = st.sidebar.multiselect(
        "Remove logged dates:", 
        options=current_vacations,
        format_func=lambda x: x.strftime('%m/%d/%Y')
    )
    if st.sidebar.button("❌ Remove Selected"):
        for d in dates_to_remove:
            st.session_state['team'][selected_doc]['vacation_days'].remove(d)
        st.sidebar.success("Dates removed. Remember to Download Backup!")
        st.rerun()

# --- MAIN APP: GENERATE SHIFTS ---
st.title("📅 On-Call Scheduler")

col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Schedule Start Date (Choose a Friday)", date.today(), key="main_start_date")
with col2:
    num_weeks = st.number_input("Duration (Weeks)", min_value=1, value=4, key="main_duration")

us_holidays = holidays.US(years=[date.today().year, date.today().year + 1])
def check_is_holiday(dt):
    return dt in us_holidays or (dt.month, dt.day) in st.session_state['custom_holidays']

def get_holiday_name(dt):
    if dt in us_holidays:
        return us_holidays.get(dt)
    return st.session_state['custom_holidays'].get((dt.month, dt.day), "Holiday")

if st.button("Generate Master Schedule"):
    # Set calendar to snap to the month of the generated schedule automatically
    st.session_state['cal_month'] = start_date.month
    st.session_state['cal_year'] = start_date.year

    core_team = [name for name, data in st.session_state['team'].items() if data.get('is_core', True)]
    
    if len(core_team) < 2:
        st.error("Please ensure you have at least 2 Core Physicians in the system.")
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

            assigned_weekend_doc = core_team[core_idx % len(core_team)]
            
            schedule_data.append({
                "Start Date": fri,
                "End Date": weekend_end_date - timedelta(days=1),
                "Time Window": f"{fri.strftime('%m/%d')} (12 PM) to {weekend_end_date.strftime('%m/%d')} (8 AM)",
                "Shift Type": f"Weekend / {weekend_label}",
                "Assigned Physician": assigned_weekend_doc
            })
            
            primary_weekday_doc = core_team[(core_idx + 1) % len(core_team)]
            weekday_start = weekend_end_date
            next_friday = fri + timedelta(days=7)
            
            is_on_vacation = False
            current_check = weekday_start
            while current_check < next_friday:
                if current_check in st.session_state['team'][primary_weekday_doc]['vacation_days']:
                    is_on_vacation = True
                    break
                current_check += timedelta(days=1)
            
            if is_on_vacation:
                alternatives = [doc for doc in core_team if doc != primary_weekday_doc]
                assigned_weekday_doc = alternatives[0] if alternatives else primary_weekday_doc
            else:
                assigned_weekday_doc = primary_weekday_doc
            
            schedule_data.append({
                "Start Date": weekday_start,
                "End Date": next_friday - timedelta(days=1),
                "Time Window": f"{weekday_start.strftime('%m/%d')} (8 AM) to {next_friday.strftime('%m/%d')} (12 PM)",
                "Shift Type": "Weekday Core Block",
                "Assigned Physician": assigned_weekday_doc
            })
            
            core_idx += 1
            current_friday = next_friday

        st.session_state['schedule'] = pd.DataFrame(schedule_data)
        st.rerun()

# --- DISPLAY CONFIGURATION ---
st.markdown("---")

if not st.session_state['schedule'].empty:

    tab1, tab2 = st.tabs(["📝 Interactive Grid Editor", "📆 Visual Monthly Calendar View"])
    
    with tab1:
        st.subheader("Interactive Schedule Grid")
        st.caption("Instructions: Make your edits in the grid. **When finished, click 'Download Master Backup File' in the sidebar to permanently save your changes.**")
        
        def color_rows(row):
            if "Weekend" in row["Shift Type"]:
                return ['background-color: #f7f9fc; font-weight: bold'] * len(row)
            return [''] * len(row)

        display_df = st.session_state['schedule'][["Time Window", "Shift Type", "Assigned Physician"]]
        
        edited_df = st.data_editor(
            display_df.style.apply(color_rows, axis=1),
            use_container_width=True,
            column_config={
                "Assigned Physician": st.column_config.SelectboxColumn(
                    "On-Call Doctor",
                    options=list(st.session_state['team'].keys()),
                    required=True
                )
            },
            key="grid_editor"
        )
        
        # Apply structural edits immediately to memory
        if "grid_editor" in st.session_state:
            grid_changes = st.session_state["grid_editor"].get("edited_rows", {})
            if grid_changes:
                for r_idx, v_changes in grid_changes.items():
                    if "Assigned Physician" in v_changes:
                        st.session_state['schedule'].at[int(r_idx), "Assigned Physician"] = v_changes["Assigned Physician"]

    with tab2:
        st.subheader("Monthly On-Call Distribution")
        st.caption("🖨️ **To Print:** Press `Ctrl + P` (Windows) or `Cmd + P` (Mac) to open your system print dialog. The document is automatically styled to only print the calendar below.")
        
        # --- FIXED CALENDAR PAGINATION ---
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
            d_start = row["Start Date"]
            d_end = row["End Date"]
            curr = d_start
            while curr <= d_end:
                lookup[curr] = (row["Assigned Physician"], row["Shift Type"])
                curr += timedelta(days=1)
                
        # Render the specific selected month
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
            html += "<tr style='height:90px; vertical-align:top;'>"
            for d in week_days:
                if d.month != curr_month:
                    html += "<td style='border:1px solid #dee2e6; background-color:#fafafa; color:#adb5bd; padding:6px;'></td>"
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
                        
                    html += f"<td style='border:1px solid #dee2e6; background-color:{bg}; padding:6px;'>"
                    html += f"<span style='font-size:12px; font-weight:bold; color:#475569;'>{d.day}</span>"
                    html += content
                    html += "</td>"
            html += "</tr>"
        html += "</table>"
        st.markdown(html, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)
