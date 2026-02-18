# Streamlit App Inventory

A Streamlit dashboard to browse and filter all Streamlit applications in Snowhouse.

## Features

- View all Streamlit apps in the account with metadata
- Filter by Manager, Organization, Owner Role, Creator, or Database
- Search within filtered results
- Charts showing app distribution by database and manager

## Data Sources

- `SHOW STREAMLITS IN ACCOUNT` - App listing
- `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY` - Creator user (DDL history)
- `SNOWFLAKE.ACCOUNT_USAGE.USERS` - Creator email/display name
- `fivetran.salesforce.user` - Salesforce user data
- `temp.ssubramanian.resolve_org` - Org hierarchy

Data is refreshed daily at 6 AM UTC via a scheduled task.

## Deployment

Requires [Snowflake CLI](https://docs.snowflake.com/en/developer-guide/snowflake-cli-v2/index).

**Deploy to DEV (for testing):**
```bash
./deploy.sh dev
```

**Deploy to PROD:**
```bash
./deploy.sh prod
```

## URLs

- **Prod:** [PS_STREAMLIT_APP_INVENTORY](https://app.snowflake.com/sfcogsops/snowhouse_aws_us_west_2/#/streamlit-apps/SNOWPUBLIC.STREAMLIT.PS_STREAMLIT_APP_INVENTORY)
- **Dev:** [PS_STREAMLIT_APP_INVENTORY_DEV](https://app.snowflake.com/sfcogsops/snowhouse_aws_us_west_2/#/streamlit-apps/SNOWPUBLIC.STREAMLIT.PS_STREAMLIT_APP_INVENTORY_DEV)

## Manual Data Refresh

```sql
CALL TEMP.OCHOY.REFRESH_STREAMLIT_APPS();
```

## Documentation

See [INFRASTRUCTURE.md](INFRASTRUCTURE.md) for details on the stored procedure, views, task, and grants.
