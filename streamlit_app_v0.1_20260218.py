import streamlit as st
import pandas as pd
from snowflake.snowpark.context import get_active_session

st.set_page_config(layout="wide", page_title="Streamlit App Inventory")

session = get_active_session()

@st.cache_data(ttl=3600, show_spinner=False)
def load_all_apps():
    df = session.sql("SELECT * FROM TEMP.OCHOY.STREAMLIT_APPS_WITH_ORG").to_pandas()
    return df

def extract_org_leaders(df):
    leaders = set()
    for hierarchy in df['ORG_HIERARCHY'].dropna():
        parts = hierarchy.replace('^', '=>').split('=>')
        leaders.update([p.strip() for p in parts if p.strip()])
    return sorted(list(leaders))

st.title(":snowflake: Streamlit App Inventory")
st.markdown("Browse Streamlit applications in Snowhouse")

with st.spinner("Loading apps (cached for 1 hour)..."):
    df_apps = load_all_apps()

if df_apps.empty:
    st.warning("No Streamlit apps found.")
    st.stop()

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

display_df.columns = ['Title', 'Location', 'Last Updated', 'Creator', 'Creator Name', 'Manager', 'Owner Role', 'Database']
display_df = display_df.sort_values('Last Updated', ascending=False, na_position='last')

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Title": st.column_config.TextColumn("App Title", width="medium"),
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
