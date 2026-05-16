import streamlit as st
import pandas as pd
from datetime import date, timedelta
import holidays  # Dynamic holiday tracking

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
st.title("📅 On-Call Scheduler (Shift-Based)")

col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Schedule Start Date (Choose a Friday)", date.today())
with col2:
    num_weeks = st.number_input("Duration (Weeks)", min_value=1, value=4)

us_holidays = holidays.US(years=[start_date.year, start_date.year + 1])

def is_holiday(dt):
    is_us = dt in us_holidays
    is_cust = (dt.month, dt.day) in st.session_state['custom_holidays']
    return is_us or is_cust

def get_holiday_name(dt):
    if dt in us_holidays:
        return us_holidays.get(dt)
    return st.session_state['custom_holidays'].get((dt.month, dt.day), "Holiday")

if st.button("Generate Master Schedule"):
    core_team = [name for name, data in st.session_state['team'].items() if data.get('is_core', True)]
    all_docs = list(st.session_state['team'].keys())
    
    if len(core_team) < 2:
        st.error("Please ensure you have at least 2 Core Physicians in the system.")
    else:
        schedule_data = []
        # Align to the nearest Friday to keep the block logic perfectly consistent
        current_friday = start_date + timedelta(days=(4 - start_date.weekday()) % 7)
        core_idx = 0
        
        for week in range(num_weeks):
            # --- 1. DETERMINE WEEKEND BOUNDARIES (Friday 12 PM to Mon/Tue 8 AM) ---
            fri = current_friday
            sat = fri + timedelta(days=1)
            sun = fri + timedelta(days=2)
            mon = fri + timedelta(days=3)
            tue = fri + timedelta(days=4)
            
            weekend_end_date = mon
            weekend_label = "Regular Weekend"
            
            # Holiday Extension Logic
            if is_holiday(mon):
                weekend_end_date = tue
                weekend_label = f"Long Weekend ({get_holiday_name(mon)})"
            elif is_holiday(fri):
                weekend_label = f"Long Weekend ({get_holiday_name(fri)})"

            # --- 2. ASSIGN WEEKEND CALL ---
            # Baseline automatic rotation picks a Core doc, but the dropdown allows switching to Coverage
            assigned_weekend_doc = core_team[core_idx % len(core_team)]
            
            schedule_data.append({
                "Time Window": f"{fri.strftime('%m/%d')} (12 PM) to {weekend_end_date.strftime('%m/%d')} (8 AM)",
                "Shift Type": f"Weekend / {weekend_label}",
                "Assigned Physician": assigned_weekend_doc
            })
            
            # --- 3. ASSIGN NEXT WEEKDAY BLOCK (Mon/Tue 8 AM to Friday 12 PM) ---
            # Weekdays are automatically locked to the Core team rotation
            assigned_weekday_doc = core_team[(core_idx + 1) % len(core_team)]
            weekday_start = weekend_end_date
            next_friday = fri + timedelta(days=7)
            
            schedule_data.append({
                "Time Window": f"{weekday_start.strftime('%m/%d')} (8 AM) to {next_friday.strftime('%m/%d')} (12 PM)",
                "Shift Type": "Weekday Core Block",
                "Assigned Physician": assigned_weekday_doc
            })
            
            # Advance loop
            core_idx += 1
            current_friday = next_friday

        st.session_state['schedule'] = pd.DataFrame(schedule_data)

# --- DISPLAY ---
st.markdown("---")

if not st.session_state['schedule'].empty:
    st.subheader("📆 Live Interactive Schedule Grid")
    st.info("💡 Weekend shifts alternate between Core docs by default. Double-click any Weekend cell to assign a Coverage physician instead!")
    
    def color_rows(row):
        if "Weekend" in row["Shift Type"]:
            return ['background-color: #f7f9fc; font-weight: bold'] * len(row)
        return [''] * len(row)

    edited_df = st.data_editor(
        st.session_state['schedule'].style.apply(color_rows, axis=1),
        use_container_width=True,
        column_config={
            "Assigned Physician": st.column_config.SelectboxColumn(
                "On-Call Doctor",
                options=list(st.session_state['team'].keys()), # Pulls all names (Core + Coverage)
                required=True
            )
        }
    )
    st.session_state['schedule'] = edited_df
