import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import traceback
import time
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import plotly.express as px

# --- TEMP PATCH FLAG ---
TEMP_PATCH = True   # 🔧 set to False once backend is fixed
PATCHED_VALUE = 18618

# Reset manual_refresh after rerun
if "manual_refresh" in st.session_state and st.session_state.manual_refresh:
    st.session_state.manual_refresh = False

# Page config
st.set_page_config(page_title="📊 PLC and Tray Monitor", layout="wide")

if "manual_refresh" not in st.session_state:
    st.session_state.manual_refresh = False

# Only auto-refresh if manual refresh not just triggered
if not st.session_state.manual_refresh:
    count = st_autorefresh(interval=1800000, limit=None, key="auto-refresh")

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
    credentials_dict = st.secrets["gcp"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
    client = gspread.authorize(creds)

    try:
        spreadsheet = client.open(sheet_name)
    except gspread.exceptions.SpreadsheetNotFound:
        spreadsheet = client.create(sheet_name)

    try:
        plc_sheet = spreadsheet.worksheet("plc_data_1")
    except gspread.exceptions.WorksheetNotFound:
        plc_sheet = spreadsheet.add_worksheet(title="plc_data_1", rows="100", cols="10")

    try:
        memory_sheet = spreadsheet.worksheet("memory_data_1")
    except gspread.exceptions.WorksheetNotFound:
        memory_sheet = spreadsheet.add_worksheet(title="memory_data_1", rows="100", cols="10")

    try:
        daily_sheet = spreadsheet.worksheet("daily_data_1")
    except gspread.exceptions.WorksheetNotFound:
        daily_sheet = spreadsheet.add_worksheet(title="daily_data_1", rows="100", cols="10")

    try:
        triggered_sheet = spreadsheet.worksheet("triggered_daily_count")
    except gspread.exceptions.WorksheetNotFound:
        triggered_sheet = spreadsheet.add_worksheet(title="triggered_daily_count", rows="100", cols="10")

    return plc_sheet, memory_sheet, daily_sheet, triggered_sheet

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
    st.info('Last updated by @aakalkri under the supervision of @didymiod for @enistepe', icon="ℹ️")
    til1, til2, til3 = st.columns([0.7, 0.1, 0.2])
    with til1:
        st.title("📦 Real-Time Tray Monitoring Dashboard")
    with til3:
        # Manual refresh
        if st.button("🔁 Manual Refresh Now"):
            st.rerun()
    st.markdown("---")

    try:
        plc_sheet, memory_sheet, daily_sheet, triggered_sheet = auth_gspread(sheet_name)
        plc_df = load_df(plc_sheet)
        memory_df = load_df(memory_sheet, parse_dates="Most Recent Timestamp")
        daily_df = load_df(daily_sheet)
        counter_df = load_df(triggered_sheet, parse_dates="Date")

        cols1, cols2, cols3, cols4, cols5 = st.columns(5)

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
                st.info("No scanned trays in memory.")

        with cols3:
            st.subheader("📋 Scanned Tray Daily Count")
            if not daily_df.empty:
                st.dataframe(daily_df, hide_index=True, use_container_width=True)
            else:
                st.info("No Daily data")

        with cols4:
            st.subheader("📦 Scanned Tray Insights")
            total_Trays = memory_df['Tray ID'].nunique() if not memory_df.empty else 0
            st.metric("Unique Trays Scanned", f"{total_Trays} Trays", border=True)
            total_appearances = memory_df['Count'].sum() if not memory_df.empty else 0
            st.metric("Total Defective Trays Scanned", f"{int(total_appearances)} Trays", border=True)
            latest_time = memory_df['Most Recent Timestamp'].max() if not memory_df.empty else None
            formatted_time = format_custom_datetime(latest_time) if latest_time else "N/A"
            st.metric("Last Scanned Tray Time", formatted_time, border=True)

        with cols5:
            st.subheader("📊 PLC Counter Insights")
            if not counter_df.empty:
                try:
                    counter_df['Counter'] = pd.to_numeric(counter_df['Counter'], errors='coerce').fillna(0)

                    if TEMP_PATCH:
                        counter_df.loc[counter_df.index[-1], 'Counter'] = PATCHED_VALUE  # 🔧 apply patch

                    counter_df['Pct Change'] = counter_df['Counter'].pct_change().fillna(0) * 100

                    latest_pct = counter_df['Pct Change'].iloc[-1]
                    latest_value = int(counter_df['Counter'].iloc[-1])

                    label = "Latest PLC Counter Change"
                    if TEMP_PATCH:
                        label += " (patched)"

                    st.metric(
                        label=label,
                        value=f"{latest_pct:.1f}%",
                        delta=f"{latest_value} raw triggers",
                        delta_color="inverse"
                    )
                except Exception as e:
                    ErrorHandler.log_error(e)
                    st.warning("⚠️ Could not calculate PLC counter metrics.")
            else:
                st.metric(
                    label="Latest PLC Counter Change (patched)" if TEMP_PATCH else "Latest PLC Counter Change",
                    value="N/A",
                    delta=f"{PATCHED_VALUE} raw triggers (temp)" if TEMP_PATCH else "N/A",
                    delta_color="off"
                )

        st.markdown("---")
        st.markdown("### 📊 30-Day PLC Daily Counter (% Change from Previous Day)")

        if not counter_df.empty:
            counter_df['Date'] = pd.to_datetime(counter_df['Date'])
            counter_df = counter_df.sort_values('Date').tail(30)

            counter_df['Counter'] = pd.to_numeric(counter_df['Counter'], errors='coerce').fillna(0)

            if TEMP_PATCH:
                counter_df.loc[counter_df.index[-1], 'Counter'] = PATCHED_VALUE  # 🔧 apply patch

            counter_df['Pct Change'] = counter_df['Counter'].pct_change().fillna(0) * 100

            fig_counter = px.line(
                counter_df,
                x='Date',
                y='Pct Change',
                title="Daily Counter % Change from Previous Day (Last 30 Days)",
                markers=True,
                text='Counter'
            )

            fig_counter.update_layout(
                yaxis=dict(title="Percentage Change (%)"),
                xaxis_title="Date",
                template="plotly_white"
            )

            st.plotly_chart(fig_counter, use_container_width=True)
        else:
            st.info("No PLC daily counter data available yet. It will appear once updated.")

    except Exception as e:
        ErrorHandler.log_error(e)
        st.error(f"❌ An error occurred: {e}")


if __name__ == "__main__":
    main()








