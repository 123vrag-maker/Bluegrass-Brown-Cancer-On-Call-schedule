import streamlit as st
import pandas as pd
from datetime import date, timedelta
import holidays  
import calendar
import os

# --- INITIAL APP SETUP & STATE CONFIGURATION ---
st.set_page_config(page_title="Physician On-Call Scheduler", layout="wide")
CSV_FILE = "master_schedule.csv"

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

# --- CRITICAL RE-ORDER: FORCE RE-READ DIRECTLY FROM DISK UPFRONT ---
if os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0:
    try:
        # Load file directly as the single source of truth to protect edits across tabs
        df_disk = pd.read_csv(CSV_FILE)
        df_disk["Start Date"] = pd.to_datetime(df_disk["Start Date"]).dt.date
        df_disk["End Date"] = pd.to_datetime(df_disk["End Date"]).dt.date
        st.session_state['schedule'] = df_disk
    except:
        if 'schedule' not in st.session_state:
            st.session_state['schedule'] = pd.DataFrame()
else:
    if 'schedule' not in st.session_state:
        st.session_state['schedule'] = pd.DataFrame()

# --- HIGH PRIORITY INTERCEPT: AUTO-SAVE EDITS BEFORE RENDERING TAB UI ---
if "grid_editor" in st.session_state and st.session_state["grid_editor"]:
    grid_edits = st.session_state["grid_editor"].get("edited_rows", {})
    if grid_edits and not st.session_state['schedule'].empty:
        for row_idx, data_changes in grid_edits.items():
            if "Assigned Physician" in data_changes:
                updated_doctor = data_changes["Assigned Physician"]
                st.session_state['schedule'].at[int(row_idx), "Assigned Physician"] = updated_doctor
        
        # Write directly to the repository file system instantly
        st.session_state['schedule'].to_csv(CSV_FILE, index=False)
        st.toast("✅ Shift changes written permanently to database file!", icon="💾")

# Inject print styles to isolate just the calendar container during physical printing
st.markdown("""
<style>
    @media print {
        body *, .sidebar, button, [data-testid="stSidebar"], [data-testid="stHeader"], .stTabs [role="tablist"] {
            visibility: hidden !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        .print-container, .print-container * {
            visibility: visible !important;
        }
        .print-container {
            position: absolute !important;
            left: 0 !important;
            top: 0 !important;
            width: 100% !important;
        }
        table { page-break-inside: avoid !important; }
    }
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR: MANAGEMENT ---
st.sidebar.header("⚙️ Settings")

# Display core vacation metrics
st.sidebar.markdown("**Current Core Vacation Balances (Max 36):**")
for doc_name, data in st.session_state['team'].items():
    if data['is_core']:
        used = len(data['vacation_days'])
        st.sidebar.write(f"• {doc_name}: **{used} / 36 days used** (Remaining: {36 - used})")

# 1. Advanced Vacation Tracker (36 Days Rule)
st.sidebar.markdown("---")
st.sidebar.subheader("🌴 Log Vacation Days")
selected_doc = st.sidebar.selectbox("Select Physician", options=list(st.session_state['team'].keys()))
vacation_date = st.sidebar.date_input("Select Date", date.today())

us_holidays = holidays.US(years=[date.today().year, date.today().year + 1])
def check_is_holiday(dt):
    return dt in us_holidays or (dt.month, dt.day) in st.session_state['custom_holidays']

if st.sidebar.button("Log Vacation Day"):
    if vacation_date.weekday() >= 5:
        st.sidebar.error("Weekends are automatically excluded from the 36-day cap.")
    elif check_is_holiday(vacation_date):
        st.sidebar.error("Designated holidays are automatically excluded.")
    else:
        current_vacations = st.session_state['team'][selected_doc]['vacation_days']
        if vacation_date not in current_vacations:
            if st.session_state['team'][selected_doc]['is_core'] and len(current_vacations) >= 36:
                st.sidebar.error(f"Cannot log. {selected_doc} has hit the 36-day vacation limit.")
            else:
                st.session_state['team'][selected_doc]['vacation_days'].append(vacation_date)
                st.sidebar.success(f"Logged vacation for {selected_doc}")
        else:
            st.sidebar.warning("This date is already logged.")

# 2. Holiday Management
st.sidebar.markdown("---")
st.sidebar.subheader("🎉 Holiday Management")
custom_holiday_name = st.sidebar.text_input("Holiday Name")
custom_holiday_date = st.sidebar.date_input("Holiday Date", date.today(), key="holiday_picker")

if st.sidebar.button("Add Holiday"):
    if custom_holiday_name:
        key = (custom_holiday_date.month, custom_holiday_date.day)
        st.session_state['custom_holidays'][key] = custom_holiday_name
        st.sidebar.success(f"Added: {custom_holiday_name}")

# --- MAIN APP: GENERATE SHIFTS ---
st.title("📅 On-Call Scheduler")

col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Schedule Start Date (Choose a Friday)", date.today(), key="main_start_date")
with col2:
    num_weeks = st.number_input("Duration (Weeks)", min_value=1, value=4, key="main_duration")

def get_holiday_name(dt):
    if dt in us_holidays:
        return us_holidays.get(dt)
    return st.session_state['custom_holidays'].get((dt.month, dt.day), "Holiday")

if st.button("Generate Master Schedule"):
    core_team = [name for name, data in st.session_state['team'].items() if data.get('is_core', True)]
    
    if len(core_team) < 2:
        st.error("Please ensure you have at least 2 Core Physicians in the system.")
    else:
        schedule_data = []
        current_friday = start_date + timedelta(days=(4 - start_date.weekday()) % 7)
        core_idx = 0
        
        for week in range(int(num_weeks)):
            fri = current_friday
            sat = fri + timedelta(days=1)
            sun = fri + timedelta(days=2)
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
            
            # Smart Failover Logic
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
        st.session_state['schedule'].to_csv(CSV_FILE, index=False)
        st.rerun()

# --- DISPLAY TABS ---
st.markdown("---")

if not st.session_state['schedule'].empty:
    tab1, tab2 = st.tabs(["📝 Interactive Grid Editor", "📆 Visual Monthly Calendar View"])
    
    with tab1:
        st.subheader("Interactive Schedule Grid")
        
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

    with tab2:
        st.subheader("Monthly On-Call Distribution")
        
        st.markdown('<button onclick="window.print()" style="background-color:#2563eb; color:white; border:none; padding:8px 16px; border-radius:4px; font-weight:bold; cursor:pointer; margin-bottom:15px;">🖨️ Print Calendar View</button>', unsafe_allow_html=True)
        st.markdown('<div class="print-container">', unsafe_allow_html=True)
        
        lookup = {}
        for _, row in st.session_state['schedule'].iterrows():
            d_start = row["Start Date"]
            d_end = row["End Date"]
            curr = d_start
            while curr <= d_end:
                lookup[curr] = (row["Assigned Physician"], row["Shift Type"])
                curr += timedelta(days=1)
                
        all_dates = list(lookup.keys())
        if all_dates:
            min_date = min(all_dates)
            max_date = max(all_dates)
            
            start_month = min_date.replace(day=1)
            end_month = max_date.replace(day=1)
            
            current_month = start_month
            while current_month <= end_month:
                st.write(f"### 🗓️ {current_month.strftime('%B %Y')}")
                
                cal = calendar.Calendar(firstweekday=6)
                month_days = cal.monthdatescalendar(current_month.year, current_month.month)
                
                html = "<table style='width:100%; border-collapse:collapse; table-layout: fixed; margin-bottom: 25px;'>"
                html += "<tr style='background-color:#f1f3f5; text-align:center; font-weight:bold;'>"
                for day_name in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
                    html += f"<th style='padding:8px; border:1px solid #dee2e6;'>{day_name}</th>"
                html += "</tr>"
                
                for week_days in month_days:
                    html += "<tr style='height:90px; vertical-align:top;'>"
                    for d in week_days:
                        if d.month != current_month.month:
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
                
                if current_month.month == 12:
                    current_month = current_month.replace(year=current_month.year + 1, month=1)
                else:
                    current_month = current_month.replace(month=current_month.month + 1)
        st.markdown('</div>', unsafe_allow_html=True)
