import streamlit as st
import pandas as pd
from datetime import date, timedelta
import holidays  # Dynamic holiday tracking

# --- CONFIGURATION ---
st.set_page_config(page_title="Team On-Call Scheduler", layout="wide")

# Initialize Session State
if 'team' not in st.session_state:
    st.session_state['team'] = {
        'Dr. Vijay Raghavan': {'vacation_used': 0, 'vacation_days': []},
        'Dr.Iltaf Khan':   {'vacation_used': 0, 'vacation_days': []},
        'Dr.Rohit Kumar': {'vacation_used': 0, 'vacation_days': []},
        'Dr.Abigail Chan': {'vacation_used': 0, 'vacation_days': []}
    }

# Initialize custom company holidays list
if 'custom_holidays' not in st.session_state:
    st.session_state['custom_holidays'] = {}

if 'schedule' not in st.session_state:
    st.session_state['schedule'] = pd.DataFrame()

# --- SIDEBAR: MANAGEMENT ---
st.sidebar.header("⚙️ Settings")

# 1. Team Management
new_member = st.sidebar.text_input("Add Team Member")
if st.sidebar.button("Add Member"):
    if new_member and new_member not in st.session_state['team']:
        st.session_state['team'][new_member] = {'vacation_used': 0, 'vacation_days': []}
        st.success(f"Added {new_member}!")

# 2. Permanent & Custom Holiday Management
st.sidebar.markdown("---")
st.sidebar.subheader("🎉 Holiday Management")
st.sidebar.write("Standard US holidays apply automatically and roll over annually.")

custom_holiday_name = st.sidebar.text_input("Custom Holiday Name (e.g., Company Day)")
custom_holiday_date = st.sidebar.date_input("Holiday Date (Any Year)", date.today())

if st.sidebar.button("Add/Update Holiday"):
    if custom_holiday_name:
        # Store by Month and Day so it repeats every year automatically
        key = (custom_holiday_date.month, custom_holiday_date.day)
        st.session_state['custom_holidays'][key] = custom_holiday_name
        st.sidebar.success(f"Added permanent holiday: {custom_holiday_name}")

# Show current custom holidays
if st.session_state['custom_holidays']:
    st.sidebar.markdown("**Custom Annual Holidays:**")
    for (m, d), name in list(st.session_state['custom_holidays'].items()):
        st.sidebar.text(f"• {name} ({m}/{d})")
        if st.sidebar.button(f"Remove {name}", key=f"del_{m}_{d}"):
            del st.session_state['custom_holidays'][(m, d)]
            st.rerun()

# 3. Vacation Logger
st.sidebar.markdown("---")
st.sidebar.subheader("🌴 Log Vacation")
vacation_user = st.sidebar.selectbox("Select Person", list(st.session_state['team'].keys()))
vacation_date = st.sidebar.date_input("Vacation Date", min_value=date.today())

if st.sidebar.button("Book Vacation"):
    user_record = st.session_state['team'][vacation_user]
    if vacation_date not in user_record['vacation_days']:
        user_record['vacation_days'].append(vacation_date)
        user_record['vacation_used'] += 1
        st.sidebar.success(f"Booked off for {vacation_user}")

# --- MAIN APP: GENERATE SCHEDULE ---
st.title("📅 On-Call Scheduler")

col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Schedule Start Date", date.today())
with col2:
    num_weeks = st.number_input("Duration (Weeks)", min_value=1, value=4)

# Load standard US holidays dynamically for the relevant years
us_holidays = holidays.US(years=[start_date.year, start_date.year + 1])

if st.button("Generate Schedule"):
    team_list = list(st.session_state['team'].keys())
    
    if not team_list:
        st.error("Please add team members first!")
    else:
        schedule_data = []
        current_date = start_date
        week_idx = 0
        
        for _ in range(num_weeks * 7):
            # Check Day Type (Weekend vs Holiday vs Weekday)
            is_us_holiday = current_date in us_holidays
            custom_key = (current_date.month, current_date.day)
            is_custom_holiday = custom_key in st.session_state['custom_holidays']
            
            day_label = "Weekday"
            if current_date.weekday() >= 5:
                day_label = "Weekend"
            if is_us_holiday:
                day_label = f"Holiday ({us_holidays.get(current_date)})"
            elif is_custom_holiday:
                day_label = f"Holiday ({st.session_state['custom_holidays'][custom_key]})"
            
            # Rotation Logic (Skipping people on vacation)
            assigned_person = team_list[week_idx % len(team_list)]
            attempts = 0
            while current_date in st.session_state['team'][assigned_person]['vacation_days'] and attempts < len(team_list):
                 week_idx += 1
                 assigned_person = team_list[week_idx % len(team_list)]
                 attempts += 1
            
            if attempts >= len(team_list):
                assigned_person = "UNCOVERED (Everyone away)"
            
            schedule_data.append({
                "Date": current_date,
                "Day": current_date.strftime("%A"),
                "Type": day_label,
                "On-Call": assigned_person
            })
            
            week_idx += 1
            current_date += timedelta(days=1)

        st.session_state['schedule'] = pd.DataFrame(schedule_data)

# --- DISPLAY ---
st.markdown("---")

if not st.session_state['schedule'].empty:
    st.subheader("📆 Schedule View")
    
    # Highlight Weekends and Holidays dynamically
    def highlight_days(row):
        if "Holiday" in row.Type:
            return ['background-color: #ffccd5'] * len(row)  # Light Red/Pink for holidays
        elif row.Type == 'Weekend':
            return ['background-color: #ffeba1'] * len(row)  # Yellow for weekends
        return [''] * len(row)

    st.dataframe(
        st.session_state['schedule'].style.apply(highlight_days, axis=1), 
        use_container_width=True
    )

# Vacation Stats
st.subheader("📊 Vacation Tracker")
stats = []
for name, data in st.session_state['team'].items():
    stats.append({"Name": name, "Days Used": data['vacation_used']})
st.table(pd.DataFrame(stats))
