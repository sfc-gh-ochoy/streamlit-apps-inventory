# PS Streamlit App Inventory - Release Notes

**Version:** 1.0  
**Release Date:** February 20, 2026  
**Author:** Oliver Choy

---

## Overview

The PS Streamlit App Inventory is a centralized dashboard for discovering, tracking, and managing Streamlit applications created by the Professional Services / Service Delivery teams. This tool provides visibility into our team's app portfolio, usage metrics, and organizational ownership.

**App URL:** [PS Streamlit App Inventory](https://app.snowflake.com/sfcogsops/snowhouse_aws_us_west_2/#/streamlit-apps/SNOWPUBLIC.STREAMLIT.PS_STREAMLIT_APP_INVENTORY)

---

## Key Features

### 1. PS/SD App Discovery

- **259 PS/SD apps** currently tracked (filtered by Roxanne McKinnon's org hierarchy)
- Toggle between PS/SD-only view and all Snowhouse apps (3,100+)
- Search by app title, name, or location

### 2. Organizational Filtering

Filter apps by multiple dimensions:
- **Organization** - View apps by org leader (e.g., all apps under a specific director)
- **Direct Manager** - See apps created by a manager's direct reports
- **Creator** - Find all apps by a specific team member
- **Database** - Group apps by their database location
- **Category/Status** - Filter by metadata tags

### 3. Usage Analytics

- **Apps Created Per Week** - Trend chart showing app creation velocity over the past year
- **Top 10 Most Used Apps** - Ranked by execution count over the last 90 days
- Click any top app to view detailed metrics (executions, unique users)

### 4. Creator Attribution

- Automatically identifies who created each app using Snowflake's ACCESS_HISTORY
- Maps creators to their management chain via Salesforce org data
- ~49% coverage due to data retention limits (apps older than 1 year may not have creator info)

### 5. App Metadata Management

Team members can enrich app records with:
- **Description** - What the app does (1-2 sentences)
- **Category** - Analytics, Operations, Customer-facing, Internal Tool, Demo, Other
- **Status** - Active, In Development, Deprecated, Archived

**Access Control:** Users can only edit metadata for apps they created or apps created by their direct reports.

### 6. Direct App Access

Each app row includes a "Go to App" link that opens the Streamlit app directly in Snowsight.

---

## Data Refresh

- App inventory refreshes **daily at 6 AM UTC** via automated task
- User sessions cache data for **8 hours** for performance
- Use "Clear Cache & Reload" in the sidebar to force a fresh data pull

---

## Known Limitations

| Limitation | Reason |
|------------|--------|
| ~49% of apps have creator info | ACCESS_HISTORY retention is ~1 year; older apps won't have creator data |
| Some apps missing "Last Updated" | Only tracked for apps modified within the retention window |
| PS count based on org hierarchy | Apps only appear in PS view if the creator is in resolve_org AND under Roxanne McKinnon |

**Note on Data Sources:** We evaluated Snowflake's telemetry data as an alternative source for creator attribution, but found ACCESS_HISTORY to provide more reliable and accurate results. Telemetry data had inconsistencies in tracking the original creator versus subsequent users who modified or executed the app.

---

## Admin Features (Oliver Choy)

### AI Description Generator

An admin-only feature that uses **Cortex AI** to automatically generate app descriptions by analyzing source code:

1. Select any app from the dropdown (not restricted by ownership)
2. Click "Generate AI Description" 
3. Review and edit the generated text
4. Save to the metadata table

**Limitations:**
- Apps deployed via Snowsight's quick-deploy use internal stages that aren't accessible
- Stub/placeholder apps with minimal code cannot be analyzed
- Manual descriptions required for ~30% of apps

---

## Roadmap

Potential future enhancements based on feedback:
- Export functionality (CSV/Excel)
- App health monitoring (error rates, performance)
- Integration with project tracking systems
- Bulk metadata operations

---

## Feedback

Please share feedback, feature requests, or issues with Oliver Choy.
