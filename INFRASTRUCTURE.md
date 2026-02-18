# Streamlit App Inventory Infrastructure

## Overview

This document describes the Snowflake objects that power the Streamlit App Inventory application.

## Database Objects

All objects are located in `TEMP.OCHOY` schema.

| Object | Type | Description |
|--------|------|-------------|
| `STREAMLIT_APPS_BASE` | Table | Base table storing all Streamlit app metadata |
| `STREAMLIT_APPS_INVENTORY` | View | Simple view over the base table |
| `STREAMLIT_APPS_WITH_ORG` | View | Enriched view with org hierarchy data |
| `STREAMLIT_APPS_PS_ONLY` | View | PS/SD team apps only (filtered by department) |
| `REFRESH_STREAMLIT_APPS()` | Procedure | Refreshes the base table |
| `REFRESH_STREAMLIT_INVENTORY` | Task | Daily scheduled refresh (6 AM UTC) |

## Data Flow

```
SHOW STREAMLITS IN ACCOUNT
        │
        ▼
┌─────────────────────────────────────────┐
│  Creator Source 1 (Primary):            │
│  SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY │  (DDL history - 12 month limit)
│                                         │
│  Creator Source 2 (Fallback):           │
│  Title pattern extraction               │  (e.g., "OCHOY 2026-02-18 12:00pm")
│                                         │
│  SNOWFLAKE.ACCOUNT_USAGE.USERS          │  (email, display name)
└─────────────────────────────────────────┘
        │
        ▼
   STREAMLIT_APPS_BASE (table)
        │
        ▼
   STREAMLIT_APPS_INVENTORY (view)
        │
        ▼
┌─────────────────────────────────────────┐
│  fivetran.salesforce.user               │  (Salesforce user data)
│  temp.ssubramanian.resolve_org          │  (org hierarchy)
└─────────────────────────────────────────┘
        │
        ▼
   STREAMLIT_APPS_WITH_ORG (view)
```

## Stored Procedure: REFRESH_STREAMLIT_APPS()

Uses two sources for creator identification:
1. **ACCESS_HISTORY** (DDL tracking) - limited to 12 months retention
2. **Title pattern** - extracts username from titles like "USERNAME YYYY-MM-DD HH:MMam/pm" (no time limit)

```sql
CREATE OR REPLACE PROCEDURE TEMP.OCHOY.REFRESH_STREAMLIT_APPS()
RETURNS STRING
LANGUAGE SQL
EXECUTE AS CALLER
AS
'
BEGIN
    -- Step 1: Get all Streamlit apps from SHOW command
    SHOW STREAMLITS IN ACCOUNT;
    LET qid := LAST_QUERY_ID();
    
    CREATE OR REPLACE TEMP TABLE TEMP.OCHOY._tmp_streamlits AS 
    SELECT 
        "name",
        "database_name",
        "schema_name",
        "database_name" || ''.'' || "schema_name" || ''.'' || "name" AS location,
        "title",
        "created_on",
        "owner" AS owner_role,
        "comment",
        "query_warehouse",
        "url_id",
        TRY_PARSE_JSON("comment"):lastUpdatedUser::STRING AS last_updated_user_id,
        TO_TIMESTAMP_LTZ(TRY_PARSE_JSON("comment"):lastUpdatedTime::NUMBER / 1000) AS last_updated_time
    FROM TABLE(RESULT_SCAN(:qid));
    
    -- Step 2: Get creator info from ACCESS_HISTORY (first CREATE per app) - 12 month limit
    CREATE OR REPLACE TEMP TABLE TEMP.OCHOY._tmp_creators_access_history AS
    SELECT 
        object_modified_by_ddl:objectName::STRING AS streamlit_fqn,
        user_name,
        query_start_time
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY
    WHERE object_modified_by_ddl:objectDomain::STRING = ''Streamlit''
      AND object_modified_by_ddl:operationType::STRING = ''CREATE''
    QUALIFY ROW_NUMBER() OVER (PARTITION BY streamlit_fqn ORDER BY query_start_time ASC) = 1;
    
    -- Step 3: Get creator info from title pattern (USERNAME YYYY-MM-DD...) - no time limit
    CREATE OR REPLACE TEMP TABLE TEMP.OCHOY._tmp_creators_title AS
    SELECT DISTINCT
        s.location AS streamlit_fqn,
        u.NAME AS user_name
    FROM TEMP.OCHOY._tmp_streamlits s
    JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS u 
        ON u.NAME = UPPER(SPLIT_PART(s."title", '' '', 1))
        AND u.DELETED_ON IS NULL
    WHERE s."title" LIKE ''% 202%'';
    
    -- Step 4: Truncate and reload base table with joined data
    TRUNCATE TABLE TEMP.OCHOY.STREAMLIT_APPS_BASE;
    
    INSERT INTO TEMP.OCHOY.STREAMLIT_APPS_BASE
        (name, database_name, schema_name, location, title, created_on, owner_role, comment, 
         query_warehouse, url_id, last_updated_user_id, last_updated_time, 
         created_by_user, created_at_from_history, refreshed_at, creator_email, creator_display_name)
    SELECT 
        s."name",
        s."database_name",
        s."schema_name",
        s.location,
        s."title",
        s."created_on",
        s.owner_role,
        s."comment",
        s."query_warehouse",
        s."url_id",
        s.last_updated_user_id,
        s.last_updated_time,
        COALESCE(c1.user_name, c2.user_name) AS created_by_user,
        c1.query_start_time AS created_at_from_history,
        CURRENT_TIMESTAMP(),
        u.EMAIL AS creator_email,
        u.DISPLAY_NAME AS creator_display_name
    FROM TEMP.OCHOY._tmp_streamlits s
    LEFT JOIN TEMP.OCHOY._tmp_creators_access_history c1 ON c1.streamlit_fqn = s.location
    LEFT JOIN TEMP.OCHOY._tmp_creators_title c2 ON c2.streamlit_fqn = s.location
    LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS u 
        ON u.NAME = COALESCE(c1.user_name, c2.user_name) AND u.DELETED_ON IS NULL;
    
    RETURN ''Refreshed '' || (SELECT COUNT(*) FROM TEMP.OCHOY.STREAMLIT_APPS_BASE) || '' apps'';
END;
';
```

## Views

### STREAMLIT_APPS_INVENTORY

Simple passthrough view:

```sql
CREATE OR REPLACE VIEW TEMP.OCHOY.STREAMLIT_APPS_INVENTORY AS
SELECT * FROM TEMP.OCHOY.STREAMLIT_APPS_BASE;
```

### STREAMLIT_APPS_WITH_ORG

Enriched view joining with Salesforce and org hierarchy:

```sql
CREATE OR REPLACE VIEW TEMP.OCHOY.STREAMLIT_APPS_WITH_ORG AS
SELECT 
    i.*,
    COALESCE(i.creator_display_name, u.NAME) AS creator_full_name,
    o.MANAGER_NAME,
    o.ORG_HIERARCHY
FROM TEMP.OCHOY.STREAMLIT_APPS_INVENTORY i
LEFT JOIN fivetran.salesforce.user u 
    ON LOWER(u.EMAIL) = LOWER(i.creator_email)
    AND u.IS_ACTIVE = true
LEFT JOIN temp.ssubramanian.resolve_org o 
    ON LOWER(o.RESOURCE_NAME) = LOWER(COALESCE(i.creator_display_name, u.NAME));
```

### STREAMLIT_APPS_PS_ONLY

Filtered view showing only apps created by Professional Services (PS/SD) team members:

```sql
CREATE OR REPLACE VIEW TEMP.OCHOY.STREAMLIT_APPS_PS_ONLY AS
SELECT a.*
FROM TEMP.OCHOY.STREAMLIT_APPS_WITH_ORG a
JOIN FIVETRAN.SALESFORCE.USER u 
    ON LOWER(u.EMAIL) = LOWER(a.creator_email)
WHERE u.IS_ACTIVE = true 
  AND u.DEPARTMENT = 'Professional Services';
```

## Task

Daily refresh at 6 AM UTC:

```sql
CREATE OR REPLACE TASK TEMP.OCHOY.REFRESH_STREAMLIT_INVENTORY
    WAREHOUSE = SNOWADHOC
    SCHEDULE = 'USING CRON 0 6 * * * UTC'
AS
    CALL TEMP.OCHOY.REFRESH_STREAMLIT_APPS();

-- Enable the task
ALTER TASK TEMP.OCHOY.REFRESH_STREAMLIT_INVENTORY RESUME;
```

## Base Table Schema

| Column | Type | Description |
|--------|------|-------------|
| name | STRING | Streamlit app name |
| database_name | STRING | Database containing the app |
| schema_name | STRING | Schema containing the app |
| location | STRING | Fully qualified name (db.schema.name) |
| title | STRING | App title |
| created_on | TIMESTAMP_LTZ | Creation timestamp |
| owner_role | STRING | Role that owns the app |
| comment | STRING | JSON comment with lastUpdatedUser/Time |
| query_warehouse | STRING | Warehouse used by the app |
| url_id | STRING | URL identifier |
| last_updated_user_id | STRING | Snowflake user ID from comment |
| last_updated_time | TIMESTAMP_LTZ | Last update time from comment |
| created_by_user | STRING | Snowflake username who created the app |
| created_at_from_history | TIMESTAMP_LTZ | Creation time from ACCESS_HISTORY |
| refreshed_at | TIMESTAMP_LTZ | When the row was last refreshed |
| creator_email | STRING | Creator's email from USERS table |
| creator_display_name | STRING | Creator's display name from USERS table |

## Grants

```sql
-- Allow PUBLIC role to query the data
GRANT USAGE ON DATABASE TEMP TO ROLE PUBLIC;
GRANT USAGE ON SCHEMA TEMP.OCHOY TO ROLE PUBLIC;
GRANT SELECT ON VIEW TEMP.OCHOY.STREAMLIT_APPS_WITH_ORG TO ROLE PUBLIC;
GRANT SELECT ON VIEW TEMP.OCHOY.STREAMLIT_APPS_INVENTORY TO ROLE PUBLIC;
GRANT SELECT ON TABLE TEMP.OCHOY.STREAMLIT_APPS_BASE TO ROLE PUBLIC;

-- Underlying tables for the view
GRANT USAGE ON DATABASE FIVETRAN TO ROLE PUBLIC;
GRANT USAGE ON SCHEMA FIVETRAN.SALESFORCE TO ROLE PUBLIC;
GRANT SELECT ON TABLE FIVETRAN.SALESFORCE.USER TO ROLE PUBLIC;
GRANT SELECT ON TABLE TEMP.SSUBRAMANIAN.RESOLVE_ORG TO ROLE PUBLIC;
```

## Manual Refresh

To manually refresh the data:

```sql
CALL TEMP.OCHOY.REFRESH_STREAMLIT_APPS();
```

## Data Coverage Notes

- **ACCESS_HISTORY** has 365-day retention, so apps created >1 year ago won't have creator info from DDL tracking
- **Title pattern fallback** extracts username from titles like "USERNAME YYYY-MM-DD HH:MMam/pm" - works for apps of any age
- **Org hierarchy** only includes employees in the `resolve_org` table
- Email matching joins Snowflake user email → Salesforce user email → Org chart
