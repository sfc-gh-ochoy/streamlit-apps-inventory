import streamlit as st
import pandas as pd
from snowflake.snowpark.context import get_active_session

st.set_page_config(layout="wide", page_title="Streamlit App Inventory")

session = get_active_session()

@st.cache_data(ttl=3600, show_spinner=False)
def load_apps(ps_only: bool):
    if ps_only:
        df = session.sql("SELECT * FROM TEMP.OCHOY.STREAMLIT_APPS_PS_ONLY").to_pandas()
    else:
        df = session.sql("SELECT * FROM TEMP.OCHOY.STREAMLIT_APPS_WITH_ORG").to_pandas()
    return df

@st.cache_data(ttl=3600, show_spinner=False)
def load_usage(ps_only: bool):
    if ps_only:
        return session.sql("SELECT * FROM TEMP.OCHOY.STREAMLIT_APP_USAGE_PS_ONLY").to_pandas()
    else:
        return session.sql("SELECT * FROM TEMP.OCHOY.STREAMLIT_APP_USAGE").to_pandas()

def extract_org_leaders(df):
    leaders = set()
    for hierarchy in df['ORG_HIERARCHY'].dropna():
        parts = hierarchy.replace('^', '=>').split('=>')
        leaders.update([p.strip() for p in parts if p.strip()])
    return sorted(list(leaders))

st.sidebar.header("Team Filter")
ps_only = st.sidebar.toggle("PS/SD Apps Only", value=True, help="Show only apps created by Professional Services team")

if ps_only:
    st.title(":snowflake: PS/SD Streamlit App Inventory")
    st.markdown("Browse Streamlit applications created by **Professional Services / Service Delivery** team")
else:
    st.title(":snowflake: Streamlit App Inventory")
    st.markdown("Browse all Streamlit applications in Snowhouse")

with st.spinner("Loading apps (cached for 1 hour)..."):
    df_apps = load_apps(ps_only)

if df_apps.empty:
    st.warning("No Streamlit apps found.")
    st.stop()

df_usage = load_usage(ps_only)

col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader("Apps Created Per Week")
    df_weekly = df_apps.copy()
    df_weekly['WEEK'] = pd.to_datetime(df_weekly['CREATED_ON']).dt.to_period('W').dt.start_time
    one_year_ago = pd.Timestamp.now() - pd.DateOffset(years=1)
    df_weekly = df_weekly[df_weekly['WEEK'] >= one_year_ago]
    weekly_counts = df_weekly.groupby('WEEK').size().reset_index(name='Apps')
    weekly_counts = weekly_counts.set_index('WEEK')
    st.bar_chart(weekly_counts, height=250)

with col_chart2:
    st.subheader("Top 10 Most Used Apps (90 days)")
    if not df_usage.empty:
        top10 = df_usage.nlargest(10, 'EXECUTION_COUNT')[['STREAMLIT_FQN', 'EXECUTION_COUNT', 'UNIQUE_USERS']].copy()
        top10['APP'] = top10['STREAMLIT_FQN'].str.split('.').str[-1]
        top10 = top10.sort_values('EXECUTION_COUNT', ascending=True)
        chart_data = top10.set_index('APP')[['EXECUTION_COUNT']]
        chart_data.columns = ['Executions']
        st.bar_chart(chart_data, height=250, horizontal=True)
    else:
        st.info("No usage data available")

st.markdown("---")

st.sidebar.markdown("---")
st.sidebar.header("Filter Apps")

filter_type = st.sidebar.radio(
    "Filter by",
    options=["Manager", "Organization", "Owner Role", "Creator", "Database"],
    index=0
)

if filter_type == "Manager":
    managers = sorted(df_apps['MANAGER_NAME'].dropna().unique().tolist())
    selected = st.sidebar.selectbox("Select Manager", options=["All"] + managers)
    if selected != "All":
        df_filtered = df_apps[df_apps['MANAGER_NAME'] == selected].copy()
    else:
        df_filtered = df_apps.copy()

elif filter_type == "Organization":
    org_leaders = extract_org_leaders(df_apps)
    selected = st.sidebar.selectbox("Select Organization Leader", options=["All"] + org_leaders)
    if selected != "All":
        df_filtered = df_apps[df_apps['ORG_HIERARCHY'].str.contains(selected, na=False, regex=False)].copy()
    else:
        df_filtered = df_apps.copy()

elif filter_type == "Owner Role":
    options = sorted(df_apps['OWNER_ROLE'].dropna().unique().tolist())
    default_idx = options.index('TECHNICAL_ACCOUNT_MANAGER') if 'TECHNICAL_ACCOUNT_MANAGER' in options else 0
    selected = st.sidebar.selectbox("Select Owner Role", options=options, index=default_idx)
    df_filtered = df_apps[df_apps['OWNER_ROLE'] == selected].copy()

elif filter_type == "Creator":
    creators = sorted(df_apps['CREATED_BY_USER'].dropna().unique().tolist())
    selected = st.sidebar.selectbox("Select Creator", options=["All"] + creators)
    if selected != "All":
        df_filtered = df_apps[df_apps['CREATED_BY_USER'] == selected].copy()
    else:
        df_filtered = df_apps[df_apps['CREATED_BY_USER'].notna()].copy()

else:
    options = sorted(df_apps['DATABASE_NAME'].dropna().unique().tolist())
    selected = st.sidebar.selectbox("Select Database", options=options)
    df_filtered = df_apps[df_apps['DATABASE_NAME'] == selected].copy()

search_term = st.sidebar.text_input("Search within results", placeholder="Search by title, name...")

if search_term:
    search_lower = search_term.lower()
    df_filtered = df_filtered[
        df_filtered['TITLE'].str.lower().str.contains(search_lower, na=False) |
        df_filtered['NAME'].str.lower().str.contains(search_lower, na=False) |
        df_filtered['LOCATION'].str.lower().str.contains(search_lower, na=False)
    ]

st.sidebar.markdown("---")
if ps_only:
    st.sidebar.caption(f"PS/SD apps: {len(df_apps):,}")
else:
    st.sidebar.caption(f"Total apps in account: {len(df_apps):,}")
st.sidebar.caption(f"With creator info: {df_apps['CREATED_BY_USER'].notna().sum():,}")
st.sidebar.caption(f"With org info: {df_apps['ORG_HIERARCHY'].notna().sum():,}")

if st.sidebar.button("Clear Cache & Reload"):
    st.cache_data.clear()
    st.rerun()

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(f"{filter_type}", selected if 'selected' in dir() else "All")
with col2:
    st.metric("Apps Found", len(df_filtered))
with col3:
    with_creator = len(df_filtered[df_filtered['CREATED_BY_USER'].notna()])
    st.metric("With Creator Info", with_creator)

st.markdown("---")

display_df = df_filtered[[
    'TITLE', 'LOCATION', 'LAST_UPDATED_TIME', 
    'CREATED_BY_USER', 'CREATOR_FULL_NAME', 'MANAGER_NAME',
    'OWNER_ROLE', 'DATABASE_NAME'
]].copy()

base_url = "https://app.snowflake.com/sfcogsops/snowhouse_aws_us_west_2/#/streamlit-apps/"
display_df['APP_URL'] = base_url + display_df['LOCATION']
display_df['TITLE'] = display_df['TITLE'].fillna('None').replace('', 'None')

display_df.columns = ['Title', 'Location', 'Last Updated', 'Creator', 'Creator Name', 'Manager', 'Owner Role', 'Database', 'App URL']
display_df = display_df.sort_values('Last Updated', ascending=False, na_position='last')

st.dataframe(
    display_df[['Title', 'App URL', 'Location', 'Last Updated', 'Creator', 'Creator Name', 'Manager', 'Owner Role', 'Database']],
    use_container_width=True,
    hide_index=True,
    column_config={
        "Title": st.column_config.TextColumn("App Title", width="medium"),
        "App URL": st.column_config.LinkColumn("Open App", display_text="Open", width="small"),
        "Location": st.column_config.TextColumn("Location", width="large"),
        "Last Updated": st.column_config.DatetimeColumn("Last Updated", format="YYYY-MM-DD HH:mm"),
        "Creator": st.column_config.TextColumn("Creator", width="small"),
        "Creator Name": st.column_config.TextColumn("Creator Name", width="medium"),
        "Manager": st.column_config.TextColumn("Manager", width="medium"),
        "Owner Role": st.column_config.TextColumn("Owner Role", width="medium"),
        "Database": st.column_config.TextColumn("Database", width="small"),
    }
)

with st.expander("Apps by Database"):
    db_counts = df_filtered['DATABASE_NAME'].value_counts().head(15)
    st.bar_chart(db_counts)

with st.expander("Apps by Manager"):
    mgr_counts = df_filtered['MANAGER_NAME'].value_counts().head(15)
    if not mgr_counts.empty:
        st.bar_chart(mgr_counts)
    else:
        st.info("No manager data available for filtered apps")
