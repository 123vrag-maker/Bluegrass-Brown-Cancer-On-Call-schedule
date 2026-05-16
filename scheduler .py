import streamlit as st
import pandas as pd
from datetime import date, timedelta
import holidays  # Dynamic holiday tracking
import calendar

# --- CONFIGURATION ---
st.set_page_config(page_title="Physician On-Call Scheduler", layout="wide")

# Initialize Session State with Core Team vs Coverage distinction
if 'team' not in st.session_state:
    st.session_state['team'] = {
        'Dr. CoreOne': {'vacation_used': 0, 'vacation_days': [], 'is_core': True},
        'Dr. CoreTwo': {'vacation_used': 0, 'vacation_days': [], 'is_core': True},
        'Dr. CoverageAlpha': {'vacation_used': 0, 'vacation_days': [], 'is_core': False},
    }

if 'custom_holidays' not in st.session_state:
    st.session_state['custom_holidays'] = {}

if 'schedule' not in st.session_state:
    st.session_state['schedule'] = pd.DataFrame()

# --- SIDEBAR: MANAGEMENT ---
st.sidebar.header("⚙️ Settings")

# 1. Personnel Management
st.sidebar.subheader("👤 Manage Roster")
new_member = st.sidebar.text_input("Physician Name")
is_core_member = st.sidebar.checkbox("Is Core Team Member?", value=True)

if st.sidebar.button("Add Physician"):
    if new_member and new_member not in st.session_state['team']:
        st.session_state['team'][new_member] = {'vacation_used': 0, 'vacation_days': [], 'is_core': is_core_member}
        st.success(f"Added {new_member}!")

# 2. Holiday Management
st.sidebar.markdown("---")
st.sidebar.subheader("🎉 Holiday Management")
custom_holiday_name = st.sidebar.text_input("Holiday Name")
custom_holiday_date = st.sidebar.date_input("Holiday Date", date.today())

if st.sidebar.button("Add Holiday"):
    if custom_holiday_name:
        key = (custom_holiday_date.month, custom_holiday_date.day)
        st.session_state['custom_holidays'][key] = custom_holiday_name
        st.sidebar.success(f"Added: {custom_holiday_name}")

# --- MAIN APP: GENERATE SHIFTS ---
st.title("📅 On-Call Scheduler")

col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Schedule Start Date (Choose a Friday)", date.today())
with col2:
    num_weeks = st.number_input("Duration (Weeks)", min_value=1, value=4)

us_holidays = holidays.US(years=[start_date.year, start_date.year + 1])

def is_holiday(dt):
    return dt in us_holidays or (dt.month, dt.day) in st.session_state['custom_holidays']

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
        # Align to nearest Friday
        current_friday = start_date + timedelta(days=(4 - start_date.weekday()) % 7)
        core_idx = 0
        
        for week in range(num_weeks):
            fri = current_friday
            sat = fri + timedelta(days=1)
            sun = fri + timedelta(days=2)
            mon = fri + timedelta(days=3)
            tue = fri + timedelta(days=4)
            
            weekend_end_date = mon
            weekend_label = "Regular Weekend"
            
            if is_holiday(mon):
                weekend_end_date = tue
                weekend_label = f"Long Weekend ({get_holiday_name(mon)})"
            elif is_holiday(fri):
                weekend_label = f"Long Weekend ({get_holiday_name(fri)})"

            assigned_weekend_doc = core_team[core_idx % len(core_team)]
            
            schedule_data.append({
                "Start Date": fri,
                "End Date": weekend_end_date - timedelta(days=1), # For mapping back to calendar days
                "Time Window": f"{fri.strftime('%m/%d')} (12 PM) to {weekend_end_date.strftime('%m/%d')} (8 AM)",
                "Shift Type": f"Weekend / {weekend_label}",
                "Assigned Physician": assigned_weekend_doc
            })
            
            assigned_weekday_doc = core_team[(core_idx + 1) % len(core_team)]
            weekday_start = weekend_end_date
            next_friday = fri + timedelta(days=7)
            
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

# --- DISPLAY ---
st.markdown("---")

if not st.session_state['schedule'].empty:
    
    # Create Tabs to switch easily between Spreadsheet view and Calendar view
    tab1, tab2 = st.tabs(["📝 Interactive Grid Editor", "📆 Visual Monthly Calendar View"])
    
    with tab1:
        st.subheader("Interactive Schedule Grid")
        st.info("💡 Make assignments here via the dropdown menus. The visual calendar view in the next tab will update instantly!")
        
        def color_rows(row):
            if "Weekend" in row["Shift Type"]:
                return ['background-color: #f7f9fc; font-weight: bold'] * len(row)
            return [''] * len(row)

        # Clean display columns for the editor
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
        # Sync edits back to master dataframe
        st.session_state['schedule']["Assigned Physician"] = edited_df["Assigned Physician"]

    with tab2:
        st.subheader("Monthly On-Call Distribution")
        
        # Build a day-by-day mapping lookup dictionary from our current state matrix
        lookup = {}
        for _, row in st.session_state['schedule'].iterrows():
            d_start = row["Start Date"]
            d_end = row["End Date"]
            curr = d_start
            while curr <= d_end:
                lookup[curr] = (row["Assigned Physician"], row["Shift Type"])
                curr += timedelta(days=1)
                
        # Determine the months we need to draw based on our schedule bounds
        all_dates = list(lookup.keys())
        if all_dates:
            min_date = min(all_dates)
            max_date = max(all_dates)
            
            start_month = min_date.replace(day=1)
            end_month = max_date.replace(day=1)
            
            current_month = start_month
            while current_month <= end_month:
                st.write(f"### 🗓️ {current_month.strftime('%B %Y')}")
                
                # Render clean HTML Calendar grid
                cal = calendar.Calendar(firstweekday=6) # Sunday start
                month_days = cal.monthdatescalendar(current_month.year, current_month.month)
                
                # HTML Table Header
                html = "<table style='width:100%; border-collapse:collapse; table-layout: fixed;'>"
                html += "<tr style='background-color:#f1f3f5; text-align:center; font-weight:bold;'>"
                for day_name in ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]:
                    html += f"<th style='padding:8px; border:1px solid #dee2e6;'>{day_name}</th>"
                html += "</tr>"
                
                for week_days in month_days:
                    html += "<tr style='height:90px; vertical-align:top;'>"
                    for d in week_days:
                        # Out of month styling
                        if d.month != current_month.month:
                            html += "<td style='border:1px solid #dee2e6; background-color:#fafafa; color:#adb5bd; padding:6px;'></td>"
                        else:
                            bg = "#ffffff"
                            content = ""
                            
                            if d in lookup:
                                doc, stype = lookup[d]
                                content = f"<div style='font-weight:600; font-size:13px; color:#1e293b; margin-top:4px;'>{doc}</div>"
                                if "Weekend" in stype:
                                    bg = "#edf2f7" # Light blue/grey block for weekend shifts
                                    content += "<div style='font-size:10px; color:#64748b;'>Weekend</div>"
                                else:
                                    content += "<div style='font-size:10px; color:#94a3b8;'>Weekday</div>"
                                    
                            if is_holiday(d):
                                bg = "#ffe3e3" # Pink tint for holidays
                                content += f"<div style='font-size:10px; color:#dc2626; font-weight:bold;'>{get_holiday_name(d)}</div>"
                                
                            html += f"<td style='border:1px solid #dee2e6; background-color:{bg}; padding:6px;'>"
                            html += f"<span style='font-size:12px; font-weight:bold; color:#475569;'>{d.day}</span>"
                            html += content
                            html += "</td>"
                    html += "</tr>"
                html += "</table><br>"
                st.markdown(html, unsafe_allow_html=True)
                
                # Advance to next month
                if current_month.month == 12:
                    current_month = current_month.replace(year=current_month.year + 1, month=1)
                else:
                    current_month = current_month.replace(month=current_month.month + 1)
