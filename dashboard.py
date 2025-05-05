import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import traceback
import time
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# Page config
st.set_page_config(page_title="📊 PLC and Tote Monitor", layout="wide")

# Refresh every 5 minutes (300000 ms)
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
def auth_gspread(creds_path, sheet_name):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # Directly access Streamlit secrets and parse them as JSON
    credentials_dict = st.secrets["gcp"] 
    
    creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_dict, scope)
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

    return plc_sheet, memory_sheet

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
        st.title("📦 Real-Time Tote Monitoring Dashboard")
    with til3:
        # Manual refresh
        if st.button("🔁 Manual Refresh Now"):
            st.rerun()
    st.markdown("---")
    try:
        plc_sheet, memory_sheet = auth_gspread(creds_path, sheet_name)
        plc_df = load_df(plc_sheet)
        memory_df = load_df(memory_sheet, parse_dates="Most Recent Timestamp")
        cols1,cols2,cols3 = st.columns(3)
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
                st.subheader("📋 Scanned Totes in Memory")
                if not memory_df.empty:
                    memory_df_display = memory_df.copy()
                    memory_df_display['Most Recent Timestamp'] = pd.to_datetime(memory_df_display['Most Recent Timestamp']) + pd.Timedelta(hours=1)
                    memory_df_display['Most Recent Timestamp'] = memory_df_display['Most Recent Timestamp'].dt.strftime('%d %b, %Y %H:%M')
                    st.dataframe(memory_df_display, hide_index=True)
                else:
                    st.info("Scanned Totes in Memory")
            with cols3:
                st.subheader("📦 Scanned Tote Insights")
                total_totes = memory_df['Tote ID'].nunique() if not memory_df.empty else 0
                st.metric("Unique Totes Scanned", f"{total_totes} totes", border=True)
                total_appearances = memory_df['Count'].sum() if not memory_df.empty else 0
                st.metric("Total Defective Totes Scanned", f"{int(total_appearances)} totes", border=True)
                latest_time = memory_df['Most Recent Timestamp'].max() if not memory_df.empty else None
                formatted_time = format_custom_datetime(latest_time) if latest_time else "N/A"
                st.metric("Last Scanned Tote Time", formatted_time, border=True)
            

        st.markdown("---")
        st.markdown("### 📈 Tote Appearances Over Time")

        import plotly.express as px

        if not memory_df.empty:
            memory_df = memory_df.sort_values('Most Recent Timestamp')
            memory_df['Corrected Timestamp'] = memory_df['Most Recent Timestamp'] + pd.Timedelta(hours=1)
            memory_df['Corrected Timestamp'] = memory_df['Corrected Timestamp'].dt.strftime('%d %b, %Y %H:%M')
            memory_df = memory_df[memory_df['Count'] > 1]

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
            
        import plotly.express as px

        if not memory_df.empty:
            memory_df = memory_df.sort_values('Most Recent Timestamp')
            memory_df['Corrected Timestamp'] = memory_df['Most Recent Timestamp'] + pd.Timedelta(hours=1)
            memory_df['Corrected Timestamp'] = memory_df['Corrected Timestamp'].dt.strftime('%d %b, %Y %H:%M')
            memory_df = memory_df[memory_df['Count'] > 1]

            fig = px.bar(
                memory_df,
                x='Tote ID',
                y='Count',
                hover_data=['Corrected Timestamp'],  # Show timestamp info on hover
                title='Count of Memory Data per Tote ID'
            )
            st.plotly_chart(fig)
        else:
            st.info("No memory data available to plot.")


        

    except Exception as e:
        ErrorHandler.log_error(e)
        st.error(f"❌ An error occurred: {e}")

if __name__ == "__main__":
    main()
