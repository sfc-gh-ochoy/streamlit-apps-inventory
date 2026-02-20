import streamlit as st
import pandas as pd
from snowflake.snowpark.context import get_active_session

st.set_page_config(layout="wide", page_title="Streamlit App Inventory")

session = get_active_session()
current_user = session.sql("SELECT CURRENT_USER()").collect()[0][0]

CATEGORIES = ["", "Analytics", "Operations", "Customer-facing", "Internal Tool", "Demo", "Other"]
STATUSES = ["", "Active", "In Development", "Deprecated", "Archived"]

@st.cache_data(ttl=28800, show_spinner=False)
def load_apps(ps_only: bool):
    if ps_only:
        df = session.sql("SELECT * FROM TEMP.OCHOY.STREAMLIT_APPS_PS_ONLY_MAT").to_pandas()
    else:
        df = session.sql("SELECT * FROM TEMP.OCHOY.STREAMLIT_APPS_WITH_ORG_MAT").to_pandas()
    return df

@st.cache_data(ttl=28800, show_spinner=False)
def load_usage(ps_only: bool):
    if ps_only:
        return session.sql("SELECT * FROM TEMP.OCHOY.STREAMLIT_APP_USAGE_PS_ONLY").to_pandas()
    else:
        return session.sql("SELECT * FROM TEMP.OCHOY.STREAMLIT_APP_USAGE").to_pandas()

@st.cache_data(ttl=60, show_spinner=False)
def load_metadata():
    return session.sql("SELECT * FROM TEMP.OCHOY.STREAMLIT_APP_METADATA").to_pandas()

@st.cache_data(ttl=3600, show_spinner=False)
def get_user_display_name(username: str):
    result = session.sql(f"SELECT DISPLAY_NAME FROM SNOWFLAKE.ACCOUNT_USAGE.USERS WHERE NAME = '{username}' AND DELETED_ON IS NULL LIMIT 1").to_pandas()
    if not result.empty:
        return result['DISPLAY_NAME'].values[0]
    return None

def save_metadata(location, description, category, status):
    session.sql(f"""
        MERGE INTO TEMP.OCHOY.STREAMLIT_APP_METADATA t
        USING (SELECT '{location}' AS LOCATION) s
        ON t.LOCATION = s.LOCATION
        WHEN MATCHED THEN UPDATE SET 
            DESCRIPTION = '{description.replace("'", "''")}',
            CATEGORY = '{category}',
            STATUS = '{status}',
            UPDATED_BY = '{current_user}',
            UPDATED_AT = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT (LOCATION, DESCRIPTION, CATEGORY, STATUS, UPDATED_BY, UPDATED_AT)
            VALUES ('{location}', '{description.replace("'", "''")}', '{category}', '{status}', '{current_user}', CURRENT_TIMESTAMP())
    """).collect()
    st.cache_data.clear()

current_user_display_name = get_user_display_name(current_user)

def can_edit(app_row):
    if pd.isna(app_row.get('CREATED_BY_USER')) and pd.isna(app_row.get('ORG_HIERARCHY')):
        return False
    if app_row.get('CREATED_BY_USER') == current_user:
        return True
    org_hierarchy = app_row.get('ORG_HIERARCHY', '') or ''
    if org_hierarchy and current_user in org_hierarchy:
        return True
    if current_user_display_name and org_hierarchy and current_user_display_name in org_hierarchy:
        return True
    return False

def extract_org_leaders(df):
    leaders = set()
    for hierarchy in df['ORG_HIERARCHY'].dropna():
        parts = hierarchy.replace('^', '=>').split('=>')
        leaders.update([p.strip() for p in parts if p.strip()])
    return sorted(list(leaders))

with st.sidebar.expander("Team Filter", expanded=True):
    ps_only = st.toggle("PS/SD Apps Only", value=True, help="Show only apps created by Professional Services team")

if ps_only:
    st.title(":snowflake: PS/SD Streamlit App Inventory")
    st.markdown("Browse Streamlit applications created by **Professional Services / Service Delivery** team")
else:
    st.title(":snowflake: Streamlit App Inventory")
    st.markdown("Browse all Streamlit applications in Snowhouse")

with st.spinner("Loading apps (cached for 1 hour)..."):
    df_apps = load_apps(ps_only)
    df_metadata = load_metadata()

if not df_metadata.empty:
    df_apps = df_apps.merge(df_metadata[['LOCATION', 'DESCRIPTION', 'CATEGORY', 'STATUS']], on='LOCATION', how='left')
else:
    df_apps['DESCRIPTION'] = None
    df_apps['CATEGORY'] = None
    df_apps['STATUS'] = None

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
        
        top10_sorted = top10.sort_values('EXECUTION_COUNT', ascending=False)
        selected_top_app = st.selectbox(
            "Select app for details",
            options=[""] + top10_sorted['STREAMLIT_FQN'].tolist(),
            format_func=lambda x: "Click to select an app..." if x == "" else f"{x.split('.')[-1]} ({top10_sorted[top10_sorted['STREAMLIT_FQN']==x]['EXECUTION_COUNT'].values[0]:,} runs)"
        )
    else:
        st.info("No usage data available")
        selected_top_app = ""

st.markdown("---")

with st.sidebar.expander("Filter Apps", expanded=True):
    filter_type = st.radio(
        "Filter by",
        options=["Organization", "Direct Manager", "Owner Role", "Creator", "Database", "Category", "Status"],
        index=0
    )

    if filter_type == "Organization":
        org_leaders = extract_org_leaders(df_apps)
        selected = st.selectbox("Select Organization Leader", options=["All"] + org_leaders)
        if selected != "All":
            df_filtered = df_apps[df_apps['ORG_HIERARCHY'].str.contains(selected, na=False, regex=False)].copy()
        else:
            df_filtered = df_apps.copy()

    elif filter_type == "Direct Manager":
        managers = sorted(df_apps['MANAGER_NAME'].dropna().unique().tolist())
        selected = st.selectbox("Select Direct Manager", options=["All"] + managers)
        if selected != "All":
            df_filtered = df_apps[df_apps['MANAGER_NAME'] == selected].copy()
        else:
            df_filtered = df_apps.copy()

    elif filter_type == "Owner Role":
        options = sorted(df_apps['OWNER_ROLE'].dropna().unique().tolist())
        default_idx = options.index('TECHNICAL_ACCOUNT_MANAGER') if 'TECHNICAL_ACCOUNT_MANAGER' in options else 0
        selected = st.selectbox("Select Owner Role", options=options, index=default_idx)
        df_filtered = df_apps[df_apps['OWNER_ROLE'] == selected].copy()

    elif filter_type == "Creator":
        creators = sorted(df_apps['CREATED_BY_USER'].dropna().unique().tolist())
        selected = st.selectbox("Select Creator", options=["All"] + creators)
        if selected != "All":
            df_filtered = df_apps[df_apps['CREATED_BY_USER'] == selected].copy()
        else:
            df_filtered = df_apps[df_apps['CREATED_BY_USER'].notna()].copy()

    elif filter_type == "Category":
        categories = [c for c in CATEGORIES if c] + ["Uncategorized"]
        selected = st.selectbox("Select Category", options=["All"] + categories)
        if selected == "All":
            df_filtered = df_apps.copy()
        elif selected == "Uncategorized":
            df_filtered = df_apps[df_apps['CATEGORY'].isna() | (df_apps['CATEGORY'] == '')].copy()
        else:
            df_filtered = df_apps[df_apps['CATEGORY'] == selected].copy()

    elif filter_type == "Status":
        statuses = [s for s in STATUSES if s] + ["Not Set"]
        selected = st.selectbox("Select Status", options=["All"] + statuses)
        if selected == "All":
            df_filtered = df_apps.copy()
        elif selected == "Not Set":
            df_filtered = df_apps[df_apps['STATUS'].isna() | (df_apps['STATUS'] == '')].copy()
        else:
            df_filtered = df_apps[df_apps['STATUS'] == selected].copy()

    else:
        options = sorted(df_apps['DATABASE_NAME'].dropna().unique().tolist())
        selected = st.selectbox("Select Database", options=options)
        df_filtered = df_apps[df_apps['DATABASE_NAME'] == selected].copy()

    search_term = st.text_input("Search within results", placeholder="Search by title, name...")

if search_term:
    search_lower = search_term.lower()
    df_filtered = df_filtered[
        df_filtered['TITLE'].str.lower().str.contains(search_lower, na=False) |
        df_filtered['NAME'].str.lower().str.contains(search_lower, na=False) |
        df_filtered['LOCATION'].str.lower().str.contains(search_lower, na=False)
    ]

if selected_top_app:
    df_filtered = df_apps[df_apps['LOCATION'] == selected_top_app].copy()

with st.sidebar.expander("Stats & Actions", expanded=False):
    if ps_only:
        st.caption(f"PS/SD apps: {len(df_apps):,}")
    else:
        st.caption(f"Total apps in account: {len(df_apps):,}")
    st.caption(f"With creator info: {df_apps['CREATED_BY_USER'].notna().sum():,}")
    st.caption(f"With org info: {df_apps['ORG_HIERARCHY'].notna().sum():,}")

    if st.button("Clear Cache & Reload"):
        st.cache_data.clear()
        st.rerun()

col1, col2, col3 = st.columns(3)
if selected_top_app:
    app_usage = df_usage[df_usage['STREAMLIT_FQN'] == selected_top_app]
    with col1:
        st.metric("Selected App", selected_top_app.split('.')[-1])
    with col2:
        st.metric("Executions (90d)", f"{app_usage['EXECUTION_COUNT'].values[0]:,}" if not app_usage.empty else "N/A")
    with col3:
        st.metric("Unique Users", f"{app_usage['UNIQUE_USERS'].values[0]:,}" if not app_usage.empty else "N/A")
else:
    with col1:
        st.metric(f"{filter_type}", selected if 'selected' in dir() else "All")
    with col2:
        st.metric("Apps Found", len(df_filtered))
    with col3:
        with_creator = len(df_filtered[df_filtered['CREATED_BY_USER'].notna()])
        st.metric("With Creator Info", with_creator)

st.markdown("---")

with st.expander("ℹ️ About this data", expanded=False):
    st.markdown("""
**Data Sources:**
- App list from `SHOW STREAMLITS IN ACCOUNT`
- Creator info from `ACCOUNT_USAGE.ACCESS_HISTORY` (tracks who first created each app)
- Org hierarchy from `ACCOUNT_USAGE.USERS` (maps creators to their management chain)
- Usage metrics from `ACCOUNT_USAGE.QUERY_HISTORY` (EXECUTE_STREAMLIT events)

**Known Limitations:**
- **Last Updated**: Only populated for apps modified within the ACCESS_HISTORY retention window (~1 year). Older apps may show blank.
- **Creator**: Coverage is ~49% due to ACCESS_HISTORY retention limits. Apps created before the retention window won't have creator data.
- Telemetry data was evaluated but ACCESS_HISTORY provides more reliable creator attribution.
    """)

df_filtered['CAN_EDIT'] = df_filtered.apply(can_edit, axis=1)

display_df = df_filtered[[
    'TITLE', 'NAME', 'LOCATION', 'LAST_UPDATED_TIME', 
    'CREATED_BY_USER', 'CREATOR_FULL_NAME', 'MANAGER_NAME',
    'OWNER_ROLE', 'DATABASE_NAME', 'CATEGORY', 'STATUS', 'DESCRIPTION', 'CAN_EDIT'
]].copy()

base_url = "https://app.snowflake.com/sfcogsops/snowhouse_aws_us_west_2/#/streamlit-apps/"
display_df['APP_URL'] = base_url + display_df['LOCATION']
display_df['TITLE'] = display_df.apply(lambda row: row['TITLE'] if row['TITLE'] and row['TITLE'].strip() else row['NAME'], axis=1)
display_df['Edit'] = display_df['CAN_EDIT'].apply(lambda x: '✏️' if x else '')
display_df['LINK_TEXT'] = 'Go to App'
display_df = display_df.drop(columns=['NAME', 'CAN_EDIT'])

display_df.columns = ['Title', 'Location', 'Last Updated', 'Creator', 'Creator Name', 'Manager', 'Owner Role', 'Database', 'Category', 'Status', 'Description', 'App URL', 'Edit', 'Link Text']
display_df = display_df.sort_values('Last Updated', ascending=False, na_position='last')

st.dataframe(
    display_df[['Edit', 'Title', 'Description', 'App URL', 'Last Updated', 'Creator', 'Creator Name', 'Manager', 'Status']],
    use_container_width=True,
    hide_index=True,
    column_config={
        "Edit": st.column_config.TextColumn("", width="small"),
        "Title": st.column_config.TextColumn("App Title", width="medium"),
        "Description": st.column_config.TextColumn("Description", width="medium"),
        "App URL": st.column_config.LinkColumn("Link", display_text="Go to App", width="small"),
        "Last Updated": st.column_config.DatetimeColumn("Last Updated", format="YYYY-MM-DD HH:mm"),
        "Creator": st.column_config.TextColumn("Creator", width="small"),
        "Creator Name": st.column_config.TextColumn("Creator Name", width="medium"),
        "Manager": st.column_config.TextColumn("Manager", width="medium"),
        "Status": st.column_config.TextColumn("Status", width="small"),
    }
)

editable_apps = display_df[display_df['Edit'] == '✏️']['Location'].tolist()
if editable_apps:
    st.markdown("---")
    edit_app_location = st.selectbox(
        "✏️ Select app to edit metadata",
        options=[""] + editable_apps,
        format_func=lambda x: "Select an app..." if x == "" else x
    )
    
    if edit_app_location:
        app_row = df_filtered[df_filtered['LOCATION'] == edit_app_location].iloc[0]
        app_display = display_df[display_df['Location'] == edit_app_location].iloc[0]
        
        with st.container(border=True):
            st.subheader(f"📝 Edit Metadata: {app_display['Title']}")
            
            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.caption("**Location**")
                st.write(edit_app_location)
            with col_info2:
                st.caption("**Creator**")
                st.write(f"{app_display['Creator Name'] or app_display['Creator'] or 'Unknown'}")
            with col_info3:
                st.caption("**Last Updated**")
                st.write(f"{app_display['Last Updated']}")
            
            st.markdown("---")
            
            current_desc = app_row.get('DESCRIPTION', '') or ''
            current_cat = app_row.get('CATEGORY', '') or ''
            current_status = app_row.get('STATUS', '') or ''
            
            new_desc = st.text_area("Description", value=current_desc, placeholder="What does this app do?", key="edit_desc")
            col_cat, col_status = st.columns(2)
            with col_cat:
                cat_idx = CATEGORIES.index(current_cat) if current_cat in CATEGORIES else 0
                new_cat = st.selectbox("Category", options=CATEGORIES, index=cat_idx, key="edit_cat")
            with col_status:
                status_idx = STATUSES.index(current_status) if current_status in STATUSES else 0
                new_status = st.selectbox("Status", options=STATUSES, index=status_idx, key="edit_status")
            
            if st.button("Save Metadata", type="primary", key="save_btn"):
                save_metadata(edit_app_location, new_desc, new_cat, new_status)
                st.success("Metadata saved!")
                st.rerun()

with st.expander("Apps by Database"):
    db_counts = df_filtered['DATABASE_NAME'].value_counts().head(15)
    st.bar_chart(db_counts)

with st.expander("Apps by Manager"):
    mgr_counts = df_filtered['MANAGER_NAME'].value_counts().head(15)
    if not mgr_counts.empty:
        st.bar_chart(mgr_counts)
    else:
        st.info("No manager data available for filtered apps")

if current_user == 'OCHOY':
    st.markdown("---")
    st.subheader("Admin: AI Description Generator")
    
    all_app_locations = sorted(df_filtered['LOCATION'].tolist())
    ai_selected_app = st.selectbox(
        "Select app to generate description",
        options=[""] + all_app_locations,
        format_func=lambda x: "Select an app..." if x == "" else x,
        key="ai_app_select"
    )
    
    if ai_selected_app:
        current_meta = df_metadata[df_metadata['LOCATION'] == ai_selected_app]
        existing_desc = current_meta['DESCRIPTION'].values[0] if len(current_meta) > 0 and pd.notna(current_meta['DESCRIPTION'].values[0]) else None
        
        if existing_desc:
            st.info(f"**Current description:** {existing_desc}")
        
        if st.button("Generate AI Description", type="primary", key="gen_ai_btn"):
            with st.spinner("Analyzing app code with Cortex AI..."):
                result = session.call("TEMP.OCHOY.GENERATE_APP_DESCRIPTION", ai_selected_app)
            
            if result.startswith("Error:"):
                st.error(result)
            else:
                st.session_state['generated_desc'] = result
                st.session_state['ai_gen_app'] = ai_selected_app
        
        if 'generated_desc' in st.session_state and st.session_state.get('ai_gen_app') == ai_selected_app:
            st.success("Description generated!")
            final_desc = st.text_area(
                "Generated description (edit if needed):",
                value=st.session_state['generated_desc'],
                key="ai_desc_edit"
            )
            
            col_save, col_clear = st.columns(2)
            with col_save:
                if st.button("Save Description", type="primary", key="save_ai_desc"):
                    existing_cat = current_meta['CATEGORY'].values[0] if len(current_meta) > 0 and pd.notna(current_meta['CATEGORY'].values[0]) else ''
                    existing_status = current_meta['STATUS'].values[0] if len(current_meta) > 0 and pd.notna(current_meta['STATUS'].values[0]) else ''
                    save_metadata(ai_selected_app, final_desc, existing_cat or '', existing_status or '')
                    del st.session_state['generated_desc']
                    del st.session_state['ai_gen_app']
                    st.success("Description saved!")
                    st.rerun()
            with col_clear:
                if st.button("Discard", key="discard_ai"):
                    del st.session_state['generated_desc']
                    del st.session_state['ai_gen_app']
                    st.rerun()
