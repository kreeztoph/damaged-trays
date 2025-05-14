import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import traceback
import time
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import plotly.express as px

# Reset manual_refresh after rerun
if "manual_refresh" in st.session_state and st.session_state.manual_refresh:
    st.session_state.manual_refresh = False

# Page config
st.set_page_config(page_title="📊 PLC and Tote Monitor", layout="wide")

if "manual_refresh" not in st.session_state:
    st.session_state.manual_refresh = False

# Only auto-refresh if manual refresh not just triggered
if not st.session_state.manual_refresh:
    count = st_autorefresh(interval=300000, limit=None, key="auto-refresh")

# Google Sheets config
sheet_name = "Data Monitor ENIS"

# Error logging
class ErrorHandler:
    LOG_FILE = "error_log.txt"

    @staticmethod
    def log_error(error):
        with open(ErrorHandler.LOG_FILE, "a") as f:
            f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {str(error)}\n")
            f.write(traceback.format_exc() + "\n")

# Google Sheets authentication and loading
def auth_gspread(sheet_name):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # Directly access Streamlit secrets and parse them as JSON
    credentials_dict = st.secrets["gcp"] 
    
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
    client = gspread.authorize(creds)

    try:
        spreadsheet = client.open(sheet_name)
    except gspread.exceptions.SpreadsheetNotFound:
        spreadsheet = client.create(sheet_name)

    try:
        plc_sheet = spreadsheet.worksheet("plc_data")
    except gspread.exceptions.WorksheetNotFound:
        plc_sheet = spreadsheet.add_worksheet(title="plc_data", rows="100", cols="10")

    try:
        memory_sheet = spreadsheet.worksheet("memory_data")
    except gspread.exceptions.WorksheetNotFound:
        memory_sheet = spreadsheet.add_worksheet(title="memory_data", rows="100", cols="10")

    try:
        daily_sheet = spreadsheet.worksheet("daily_data")
    except gspread.exceptions.WorksheetNotFound:
        daily_sheet = spreadsheet.add_worksheet(title="daily_data", rows="100", cols="10")

    return plc_sheet, memory_sheet , daily_sheet

# Load data from Google Sheets
def load_df(sheet, parse_dates=None):
    data = sheet.get_all_records()
    if data:
        df = pd.DataFrame(data)
        if parse_dates and parse_dates in df.columns:
            df[parse_dates] = pd.to_datetime(df[parse_dates])
        return df
    else:
        return pd.DataFrame()

# Helper: ordinal date suffix
def ordinal(n):
    return f"{n}{'th' if 11 <= n <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"

# Helper: format datetime with +1hr correction
def format_custom_datetime(dt):
    dt = dt + pd.Timedelta(hours=1)
    return f"{ordinal(dt.day)} {dt.strftime('%B, %Y %H:%M')}"

# Main app
def main():
    til1,til2, til3 = st.columns([0.7,0.1,0.2])
    with til1:
        st.title("📦 Real-Time Tray Monitoring Dashboard")
    with til3:
        # Manual refresh
        if st.button("🔁 Manual Refresh Now"):
            st.rerun()
    st.markdown("---")
    try:
        plc_sheet, memory_sheet , daily_sheet = auth_gspread(creds_path, sheet_name)
        plc_df = load_df(plc_sheet)
        memory_df = load_df(memory_sheet, parse_dates="Most Recent Timestamp")
        daily_df = load_df(daily_sheet)
        cols1,cols2,cols3,cols4 = st.columns(4)
        with cols1:
            st.subheader("📋 Latest PLC Data")
            if not plc_df.empty:
                plc_df_display = plc_df.copy()
                plc_df_display['Timestamp'] = pd.to_datetime(plc_df_display['Timestamp']) + pd.Timedelta(hours=1)
                plc_df_display['Timestamp'] = plc_df_display['Timestamp'].dt.strftime('%d %b, %Y %H:%M')
                st.dataframe(plc_df_display, hide_index=True)
            else:
                st.info("No PLC data found.")
            
            with cols2:
                st.subheader("📋 Scanned Trays in Memory")
                if not memory_df.empty:
                    memory_df_display = memory_df.copy()
                    memory_df_display['Most Recent Timestamp'] = pd.to_datetime(memory_df_display['Most Recent Timestamp']) + pd.Timedelta(hours=1)
                    memory_df_display['Most Recent Timestamp'] = memory_df_display['Most Recent Timestamp'].dt.strftime('%d %b, %Y %H:%M')
                    st.dataframe(memory_df_display, hide_index=True)
                else:
                    st.info("Scanned Trays in Memory")
            with cols3:
                st.subheader("📋 Scanned Tray Daily Count")
                if not daily_df.empty:
                    daily_df_display = daily_df.copy()
                    st.dataframe(daily_df_display, hide_index=True,use_container_width=True)
                else:
                    st.info("No Daily data")
            with cols4:
                st.subheader("📦 Scanned Tray Insights")
                total_totes = memory_df['Tote ID'].nunique() if not memory_df.empty else 0
                st.metric("Unique Trays Scanned", f"{total_totes} Trays", border=True)
                total_appearances = memory_df['Count'].sum() if not memory_df.empty else 0
                st.metric("Total Defective Trays Scanned", f"{int(total_appearances)} Trays", border=True)
                latest_time = memory_df['Most Recent Timestamp'].max() if not memory_df.empty else None
                formatted_time = format_custom_datetime(latest_time) if latest_time else "N/A"
                st.metric("Last Scanned Tray Time", formatted_time, border=True)
            

        st.markdown("---")
        st.markdown("### 📈 Tray Appearances Over Time")

        import plotly.express as px
        memory_df = memory_df.sort_values('Most Recent Timestamp')
        memory_df['Corrected Timestamp'] = memory_df['Most Recent Timestamp'] + pd.Timedelta(hours=1)
        memory_df['Corrected Timestamp'] = memory_df['Corrected Timestamp'].dt.strftime('%d %b, %Y %H:%M')
        memory_df = memory_df[memory_df['Count'] > 1]
        if not memory_df.empty:
            fig = px.line(
                memory_df,
                x='Corrected Timestamp',
                y='Count',
                hover_data=['Tote ID'],  # Add Tote ID to the hover
                title='Memory Data Over Time'
            )
            st.plotly_chart(fig)
        else:
            st.info("No memory data available to plot.")

                # Initialize session state for filtered data
        if "filtered_df" not in st.session_state:
            st.session_state.filtered_df = memory_df.copy()

        # Time Filter Selection
        time_options = ["All Data", "Last 1 Day", "Last 2 Days", "Last 7 Days", "Last 1 Month", "Custom Range"]
        # Initialize session state for selected filter
        if "selected_time_filter" not in st.session_state:
            st.session_state.selected_time_filter = "All Data"

        # Time Filter Selection
        time_options = ["All Data", "Last 1 Day", "Last 2 Days", "Last 7 Days", "Last 1 Month", "Custom Range"]
        selected_time = st.selectbox("Select Time Range", time_options, key="selected_time_filter")

        # Define time filtering logic (without page reload)
        now = pd.Timestamp.now()

        if selected_time == "Last 1 Day":
            filtered_df = memory_df[memory_df["Most Recent Timestamp"] >= now - pd.Timedelta(days=1)]
        elif selected_time == "Last 2 Days":
            filtered_df = memory_df[memory_df["Most Recent Timestamp"] >= now - pd.Timedelta(days=2)]
        elif selected_time == "Last 7 Days":
            filtered_df = memory_df[memory_df["Most Recent Timestamp"] >= now - pd.Timedelta(days=7)]
        elif selected_time == "Last 1 Month":
            filtered_df = memory_df[memory_df["Most Recent Timestamp"] >= now - pd.Timedelta(days=30)]
        elif selected_time == "Custom Range":
            with st.form("Custom Range Selection"):
                st.write("### Select Date Range")

                # Get min/max values from the dataset
                min_date = memory_df["Most Recent Timestamp"].min()
                max_date = memory_df["Most Recent Timestamp"].max()

                # Date selection inputs within the form
                start_date = st.date_input("Start Date", min_value=min_date, value=min_date)
                end_date = st.date_input("End Date", min_value=min_date, value=max_date)

                # Submit button for applying the filter
                submitted = st.form_submit_button("Apply Filter")

            # Filter data only after form submission
            if submitted:
                filtered_df = memory_df[
                    (memory_df["Most Recent Timestamp"] >= pd.to_datetime(start_date)) & 
                    (memory_df["Most Recent Timestamp"] <= pd.to_datetime(end_date))
                ]

        else:  # "All Data" selected
            filtered_df = memory_df.copy()
        colz1,colz2,colz3,colz4,colz5,colz6 = st.columns(6)
        with colz1:
            st.metric(label='Total Tray Count',value=len(filtered_df['Tote ID'].unique()),border=True)
        # Sort the dataframe by count in descending order
        top_totes = filtered_df.sort_values("Count", ascending=False).head(5)

        # Assign each concern to a column
        columns = [colz2, colz3, colz4, colz5, colz6]

        for i, (_, row) in enumerate(top_totes.iterrows()):
            with columns[i]:  # Dynamically place each metric in its column
                st.metric(
                    label=f"{i + 1}️⃣ Concern",  # Rank indicator
                    value=f"{row['Tote ID']}",  # Tray ID
                    help=f"Last Seen: {row['Corrected Timestamp']}\n | Total Scans: {row['Count']}",  # Hover details
                    border=True
                )

        column1,column2 = st.columns([0.3,0.7])
        with column1:
            # Display filtered results
                if not filtered_df.empty:
                    st.dataframe(filtered_df, hide_index=True)
        with column2:
            # Use the filtered data for visualization
            if not filtered_df.empty:
                fig = px.line(
                    filtered_df,
                    x='Most Recent Timestamp',
                    y='Count',
                    hover_data=['Tote ID'],
                    title='Filtered Memory Data Over Time'
                )
                st.plotly_chart(fig)
            else:
                st.info("No data available for the selected time range.")
    except Exception as e:
        ErrorHandler.log_error(e)
        st.error(f"❌ An error occurred: {e}")


        

    except Exception as e:
        ErrorHandler.log_error(e)
        st.error(f"❌ An error occurred: {e}")

if __name__ == "__main__":
    main()
