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
st.set_page_config(page_title="📊 PLC and Tray Monitor", layout="wide")

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
    credentials_dict = st.secrets["gcp"] 
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
    client = gspread.authorize(creds)

    try:
        spreadsheet = client.open(sheet_name)
    except gspread.exceptions.SpreadsheetNotFound:
        spreadsheet = client.create(sheet_name)

    def get_or_create(title):
        try:
            return spreadsheet.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            return spreadsheet.add_worksheet(title=title, rows="100", cols="10")

    plc_sheet = get_or_create("plc_data_1")
    memory_sheet = get_or_create("memory_data_1")
    daily_sheet = get_or_create("daily_data_1")
    triggered_sheet = get_or_create("triggered_daily_count")

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
    return f"{n}{'th' if 11 <= n <= 13 else {1:'st',2:'nd',3:'rd'}.get(n%10,'th')}"

# Helper: format datetime with +1hr correction
def format_custom_datetime(dt):
    dt = dt + pd.Timedelta(hours=1)
    return f"{ordinal(dt.day)} {dt.strftime('%B, %Y %H:%M')}"

def main():
    st.info('Last updated by @aakalkri under the supervision of @didymiod for @enistepe', icon="ℹ️")
    til1, til2, til3 = st.columns([0.7, 0.1, 0.2])
    with til1:
        st.title("📦 Real-Time Tray Monitoring Dashboard")
    with til3:
        if st.button("🔁 Manual Refresh Now"):
            st.rerun()
    st.markdown("---")

    try:
        # Load all sheets
        plc_sheet, memory_sheet, daily_sheet, triggered_sheet = auth_gspread(sheet_name)
        plc_df = load_df(plc_sheet)
        memory_df = load_df(memory_sheet, parse_dates="Most Recent Timestamp")
        daily_df = load_df(daily_sheet)
        counter_df = load_df(triggered_sheet, parse_dates="Date")

        # ✅ Fix 1: Calculate Pct Change immediately
        if not counter_df.empty:
            counter_df['Counter'] = pd.to_numeric(counter_df['Counter'], errors='coerce').fillna(0)
            counter_df['Pct Change'] = counter_df['Counter'].pct_change().fillna(0) * 100

        # --- Metrics & Latest Data Display ---
        cols1, cols2, cols3, cols4, cols5 = st.columns(5)

        with cols1:
            st.subheader("📋 Latest PLC Data")
            if not plc_df.empty:
                plc_df_display = plc_df.copy()
                plc_df_display['Timestamp'] = pd.to_datetime(plc_df_display['Timestamp']) + pd.Timedelta(hours=1)  # ✅ Fix 2
                plc_df_display['Timestamp'] = plc_df_display['Timestamp'].dt.strftime('%d %b, %Y %H:%M')
                st.dataframe(plc_df_display, hide_index=True)
            else:
                st.info("No PLC data found.")

        with cols2:
            st.subheader("📋 Scanned Trays in Memory")
            if not memory_df.empty:
                memory_df_display = memory_df.copy()
                memory_df_display['Most Recent Timestamp'] = pd.to_datetime(memory_df_display['Most Recent Timestamp']) + pd.Timedelta(hours=1)  # ✅ Fix 2
                memory_df_display['Most Recent Timestamp'] = memory_df_display['Most Recent Timestamp'].dt.strftime('%d %b, %Y %H:%M')
                st.dataframe(memory_df_display, hide_index=True)
            else:
                st.info("Scanned Trays in Memory")

        with cols3:
            st.subheader("📋 Scanned Tray Daily Count")
            if not daily_df.empty:
                st.dataframe(daily_df, hide_index=True, use_container_width=True)
            else:
                st.info("No Daily data")

        with cols4:
            st.subheader("📦 Scanned Tray Insights")
            total_trays = memory_df['Tray ID'].nunique() if not memory_df.empty else 0
            st.metric("Unique Trays Scanned", f"{total_trays} Trays", border=True)
            total_appearances = memory_df['Count'].sum() if not memory_df.empty else 0
            st.metric("Total Defective Trays Scanned", f"{int(total_appearances)} Trays", border=True)  # ✅ Fix 3
            latest_time = memory_df['Most Recent Timestamp'].max() if not memory_df.empty else None
            formatted_time = format_custom_datetime(latest_time) if latest_time else "N/A"
            st.metric("Last Scanned Tray Time", formatted_time, border=True)

        with cols5:
            if not counter_df.empty:
                latest_pct = counter_df['Pct Change'].iloc[-1]
                latest_value = int(counter_df['Counter'].iloc[-1])  # ✅ Fix 3
                st.metric(
                    label="Latest PLC Counter Change",
                    value=f"{latest_pct:.1f}%",
                    delta=f"{latest_value} raw triggers",
                    delta_color="inverse"
                )
            else:
                st.info("No PLC counter data yet.")

        # --- 30-Day PLC Counter Graph ---
        st.markdown("---")
        if not counter_df.empty:
            counter_df_30 = counter_df.sort_values('Date').tail(30)
            fig_counter = px.line(
                counter_df_30,
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

        st.markdown("---")
        graph_column_1, graph_column_2 = st.columns([0.6, 0.4])

        with graph_column_1:
            st.markdown("### 📈 Tray Appearances Over Time")
            if not memory_df.empty:
                memory_df = memory_df.sort_values('Most Recent Timestamp')
                memory_df['Corrected Timestamp'] = memory_df['Most Recent Timestamp'] + pd.Timedelta(hours=1)  # ✅ Fix 2
                memory_df['Corrected Timestamp'] = memory_df['Corrected Timestamp'].dt.strftime('%d %b, %Y %H:%M')
                memory_df = memory_df[memory_df['Count'] > 1]

                fig = px.line(
                    memory_df,
                    x='Corrected Timestamp',
                    y='Count',
                    hover_data=['Tray ID'],
                    title='Memory Data Over Time'
                )
                st.plotly_chart(fig)
            else:
                st.info("No memory data available to plot.")

        with graph_column_2:
            st.subheader('Daily scans count')
            if not daily_df.empty:
                daily_df = daily_df.sort_values('Date')
                fig_1 = px.line(
                    daily_df,
                    x='Date',
                    y='Daily Trigger Count',
                    title='Daily Tray Scans'
                )
                fig_1.update_layout(yaxis=dict(range=[0, daily_df['Daily Trigger Count'].max()]))
                st.plotly_chart(fig_1)
            else:
                st.info("No daily count available to plot.")

        st.markdown("---")

        # --- Time Filtering & Top Trays ---
        if "filtered_df" not in st.session_state:
            st.session_state.filtered_df = memory_df.copy()

        time_options = ["All Data", "Last 1 Day", "Last 2 Days", "Last 7 Days", "Last 1 Month", "Custom Range"]
        if "selected_time_filter" not in st.session_state:
            st.session_state.selected_time_filter = "All Data"

        selected_time = st.selectbox("Select Time Range", time_options, key="selected_time_filter")
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
                min_date = memory_df["Most Recent Timestamp"].min()
                max_date = memory_df["Most Recent Timestamp"].max()
                start_date = st.date_input("Start Date", min_value=min_date, value=min_date)
                end_date = st.date_input("End Date", min_value=min_date, value=max_date)
                submitted = st.form_submit_button("Apply Filter")
            if submitted:
                filtered_df = memory_df[
                    (memory_df["Most Recent Timestamp"] >= pd.to_datetime(start_date)) &
                    (memory_df["Most Recent Timestamp"] <= pd.to_datetime(end_date))
                ]
        else:
            filtered_df = memory_df.copy()

        colz1, colz2, colz3, colz4, colz5, colz6 = st.columns(6)
        with colz1:
            st.metric(label='Total Tray Count', value=len(filtered_df['Tray ID'].unique()), border=True)

        top_Trays = filtered_df.sort_values("Count", ascending=False).head(5)
        columns = [colz2, colz3, colz4, colz5, colz6]

        for i, (_, row) in enumerate(top_Trays.iterrows()):
            with columns[i]:
                st.metric(
                    label=f"{i + 1}️⃣ Concern",
                    value=f"{row['Tray ID']}",
                    help=f"Last Seen: {row['Corrected Timestamp']}\n | Total Scans: {row['Count']}",
                    border=True
                )

        column1, column2 = st.columns([0.3, 0.7])
        with column1:
            if not filtered_df.empty:
                st.dataframe(filtered_df, hide_index=True)
        with column2:
            if not filtered_df.empty:
                fig = px.line(
                    filtered_df,
                    x='Most Recent Timestamp',
                    y='Count',
                    hover_data=['Tray ID'],
                    title='Filtered Memory Data Over Time'
                )
                st.plotly_chart(fig)
            else:
                st.info("No data available for the selected time range.")

    except Exception as e:
        ErrorHandler.log_error(e)
        st.error(f"❌ An error occurred: {e}")


if __name__ == "__main__":
    main()






