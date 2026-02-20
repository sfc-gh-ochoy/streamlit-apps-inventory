# Stored Procedures & Database Objects

> **Last Updated**: 2026-02-20
> **Version**: 1.1 (Working)

This document contains the exact DDL for all database objects powering the Streamlit App Inventory. Use this to restore objects if needed.

## Quick Restore

To restore all objects to this working version, run the SQL blocks in this order:
1. Base Table
2. Stored Procedure
3. Views (Inventory → With Org → PS Only)
4. Grants

---

## 1. Base Table: STREAMLIT_APPS_BASE

```sql
CREATE OR REPLACE TABLE TEMP.OCHOY.STREAMLIT_APPS_BASE (
    NAME VARCHAR(16777216),
    DATABASE_NAME VARCHAR(16777216),
    SCHEMA_NAME VARCHAR(16777216),
    LOCATION VARCHAR(16777216),
    TITLE VARCHAR(16777216),
    CREATED_ON TIMESTAMP_LTZ(3),
    OWNER_ROLE VARCHAR(16777216),
    COMMENT VARCHAR(16777216),
    QUERY_WAREHOUSE VARCHAR(16777216),
    URL_ID VARCHAR(16777216),
    LAST_UPDATED_USER_ID VARCHAR(16777216),
    LAST_UPDATED_TIME TIMESTAMP_LTZ(6),
    CREATED_BY_USER VARCHAR(16777216),
    REFRESHED_AT TIMESTAMP_LTZ(9),
    CREATOR_EMAIL VARCHAR(16777216),
    CREATOR_DISPLAY_NAME VARCHAR(16777216)
);
```

### Column Descriptions

| Column | Description |
|--------|-------------|
| NAME | Streamlit app name |
| DATABASE_NAME | Database containing the app |
| SCHEMA_NAME | Schema containing the app |
| LOCATION | Fully qualified name (DATABASE.SCHEMA.NAME) |
| TITLE | User-defined app title |
| CREATED_ON | When the app was created (from SHOW STREAMLITS) |
| OWNER_ROLE | Role that owns the app |
| COMMENT | JSON comment containing lastUpdatedUser/Time |
| QUERY_WAREHOUSE | Warehouse assigned to the app |
| URL_ID | Snowflake URL identifier |
| LAST_UPDATED_USER_ID | User ID who last updated (from comment JSON) |
| LAST_UPDATED_TIME | Last update timestamp (from comment JSON) |
| CREATED_BY_USER | Snowflake username who created the app |
| REFRESHED_AT | When this row was last refreshed |
| CREATOR_EMAIL | Creator's email from ACCOUNT_USAGE.USERS |
| CREATOR_DISPLAY_NAME | Creator's display name from ACCOUNT_USAGE.USERS |

---

## 2. Stored Procedure: REFRESH_STREAMLIT_APPS

This procedure refreshes the base table by:
1. Getting all Streamlit apps via `SHOW STREAMLITS IN ACCOUNT`
2. Finding creators from `ACCESS_HISTORY` (DDL tracking)
3. Falling back to title pattern matching for older apps
4. Joining with `USERS` table for email/display name

### Important Notes

- **ACCESS_HISTORY latency**: Data can take 2-3 hours to appear
- **ACCESS_HISTORY retention**: 365 days, so very old apps may not have creator info
- **Title pattern fallback**: Extracts username from titles like "USERNAME 2026-02-19 12:00pm"
- **Execute as CALLER**: Requires caller to have access to ACCOUNT_USAGE views

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
    
    -- Step 2: Get creator info from ACCESS_HISTORY (first CREATE per app)
    -- Note: ACCESS_HISTORY has ~365 day retention
    CREATE OR REPLACE TEMP TABLE TEMP.OCHOY._tmp_creators_access_history AS
    SELECT 
        object_modified_by_ddl:objectName::STRING AS streamlit_fqn,
        user_name,
        query_start_time
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY
    WHERE object_modified_by_ddl:objectDomain::STRING = ''Streamlit''
      AND object_modified_by_ddl:operationType::STRING = ''CREATE''
    QUALIFY ROW_NUMBER() OVER (PARTITION BY streamlit_fqn ORDER BY query_start_time ASC) = 1;
    
    -- Step 3: Fallback - extract creator from title pattern (USERNAME YYYY-MM-DD...)
    -- This works for apps of any age if they follow the naming convention
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
         created_by_user, refreshed_at, creator_email, creator_display_name)
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

### Manual Refresh

```sql
USE ROLE TECHNICAL_ACCOUNT_MANAGER;
CALL TEMP.OCHOY.REFRESH_STREAMLIT_APPS();
```

---

## 3. Views

### 3.1 STREAMLIT_APPS_INVENTORY

Simple passthrough view over the base table.

```sql
CREATE OR REPLACE VIEW TEMP.OCHOY.STREAMLIT_APPS_INVENTORY AS
SELECT * FROM TEMP.OCHOY.STREAMLIT_APPS_BASE;
```

### 3.2 STREAMLIT_APPS_WITH_ORG

Enriches apps with Salesforce user data and org hierarchy.

**Dependencies**:
- `fivetran.salesforce.user` - Salesforce user data (email, name)
- `temp.ssubramanian.resolve_org` - Org hierarchy data (manager, reporting chain)

```sql
CREATE OR REPLACE VIEW TEMP.OCHOY.STREAMLIT_APPS_WITH_ORG AS
WITH sf_users AS (
    SELECT EMAIL, NAME 
    FROM fivetran.salesforce.user 
    WHERE IS_ACTIVE = true
    QUALIFY ROW_NUMBER() OVER (PARTITION BY LOWER(EMAIL) ORDER BY CREATED_DATE DESC) = 1
),
org_data AS (
    SELECT RESOURCE_NAME, MANAGER_NAME, ORG_HIERARCHY
    FROM temp.ssubramanian.resolve_org
    QUALIFY ROW_NUMBER() OVER (PARTITION BY LOWER(RESOURCE_NAME) ORDER BY RESOURCE_NAME) = 1
)
SELECT 
    i.*,
    COALESCE(i.creator_display_name, u.NAME) AS creator_full_name,
    o.MANAGER_NAME,
    o.ORG_HIERARCHY
FROM TEMP.OCHOY.STREAMLIT_APPS_INVENTORY i
LEFT JOIN sf_users u ON LOWER(u.EMAIL) = LOWER(i.creator_email)
LEFT JOIN org_data o ON LOWER(o.RESOURCE_NAME) = LOWER(COALESCE(i.creator_display_name, u.NAME));
```

### 3.3 STREAMLIT_APPS_PS_ONLY

Filters to apps created by Professional Services team members (under Roxanne McKinnon's org).

**Filter Logic**: Uses `ORG_HIERARCHY LIKE '%Roxanne McKinnon%'` to find all apps where the creator reports up to the PS org leader.

```sql
CREATE OR REPLACE VIEW TEMP.OCHOY.STREAMLIT_APPS_PS_ONLY AS
SELECT a.*
FROM TEMP.OCHOY.STREAMLIT_APPS_WITH_ORG a
WHERE a.ORG_HIERARCHY LIKE '%Roxanne McKinnon%';
```

---

## 4. Grants

```sql
-- Schema access
GRANT USAGE ON DATABASE TEMP TO ROLE PUBLIC;
GRANT USAGE ON SCHEMA TEMP.OCHOY TO ROLE PUBLIC;

-- Data access
GRANT SELECT ON TABLE TEMP.OCHOY.STREAMLIT_APPS_BASE TO ROLE PUBLIC;
GRANT SELECT ON VIEW TEMP.OCHOY.STREAMLIT_APPS_INVENTORY TO ROLE PUBLIC;
GRANT SELECT ON VIEW TEMP.OCHOY.STREAMLIT_APPS_WITH_ORG TO ROLE PUBLIC;
GRANT SELECT ON VIEW TEMP.OCHOY.STREAMLIT_APPS_PS_ONLY TO ROLE PUBLIC;

-- Dependencies (if not already granted)
GRANT USAGE ON DATABASE FIVETRAN TO ROLE PUBLIC;
GRANT USAGE ON SCHEMA FIVETRAN.SALESFORCE TO ROLE PUBLIC;
GRANT SELECT ON TABLE FIVETRAN.SALESFORCE.USER TO ROLE PUBLIC;
GRANT SELECT ON TABLE TEMP.SSUBRAMANIAN.RESOLVE_ORG TO ROLE PUBLIC;
```

---

## 5. Metadata Table: STREAMLIT_APP_METADATA

Stores editable metadata (description, category, status) for apps.

```sql
CREATE TABLE IF NOT EXISTS TEMP.OCHOY.STREAMLIT_APP_METADATA (
    LOCATION VARCHAR(16777216) PRIMARY KEY,
    DESCRIPTION VARCHAR(16777216),
    CATEGORY VARCHAR(100),
    STATUS VARCHAR(50),
    UPDATED_BY VARCHAR(100),
    UPDATED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

GRANT SELECT, INSERT, UPDATE ON TABLE TEMP.OCHOY.STREAMLIT_APP_METADATA TO ROLE PUBLIC;
```

### Valid Values

| Column | Options |
|--------|---------|
| CATEGORY | Analytics, Operations, Customer-facing, Internal Tool, Demo, Other |
| STATUS | Active, In Development, Deprecated, Archived |

---

## 6. Stored Procedure: GENERATE_APP_DESCRIPTION

Uses Cortex AI to analyze Streamlit app source code and generate a 1-2 sentence description.

### How it Works

1. Parses the app location (DATABASE.SCHEMA.NAME)
2. Runs `DESCRIBE STREAMLIT` to get the source stage path
3. Reads the main Python file from the stage
4. Truncates code to ~4000 characters (token limit safety)
5. Calls `SNOWFLAKE.CORTEX.COMPLETE('llama3.1-70b', prompt)` to generate description
6. Returns the generated description (or error message)

### Limitations

- Only reads the main entry file (app.py, streamlit_app.py, etc.)
- Apps with minimal code (<20 chars) will return an error
- Some apps have inaccessible stages (permission issues, special stage types)
- Multi-file apps only analyze the entry point, not imported modules

```sql
CREATE OR REPLACE PROCEDURE TEMP.OCHOY.GENERATE_APP_DESCRIPTION(APP_LOCATION VARCHAR)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'generate_description'
EXECUTE AS CALLER
AS $$
import snowflake.snowpark as snowpark

def generate_description(session: snowpark.Session, app_location: str) -> str:
    try:
        parts = app_location.split('.')
        if len(parts) != 3:
            return f"Error: Invalid location format: {app_location}"
        
        db, schema, name = parts
        
        desc_result = session.sql(f"DESCRIBE STREAMLIT {db}.{schema}.{name}").collect()
        if not desc_result:
            return "Error: Could not describe streamlit app"
        
        row = desc_result[0].as_dict()
        source_stage = row.get('default_version_source_location_uri')
        main_file = row.get('main_file') or 'streamlit_app.py'
        
        if not source_stage or source_stage == 'None':
            return "Error: No source stage found for this app"
        
        stage_path = source_stage.strip().rstrip('/')
        
        try:
            list_result = session.sql(f"LIST {stage_path}/").collect()
        except Exception as e:
            return f"Error: Cannot access stage {stage_path}: {str(e)}"
        
        if not list_result:
            return f"Error: No files found in stage {stage_path}"
        
        try:
            file_path = f"{stage_path}/{main_file}"
            code_result = session.sql(f"SELECT $1 as code FROM {file_path}").collect()
            
            if code_result:
                code_content = '\n'.join([str(row['CODE']) for row in code_result if row['CODE']])
            else:
                return f"Error: Could not read file content from {file_path}"
                
        except Exception as e:
            return f"Error: Failed to read file {main_file}: {str(e)}"
        
        if not code_content or len(code_content.strip()) < 20:
            return f"Error: App has minimal code ({len(code_content.strip())} chars) - cannot generate meaningful description"
        
        truncated_code = code_content[:4000]
        escaped_code = truncated_code.replace("\\", "\\\\").replace("'", "''")
        
        prompt = "Analyze this Streamlit app code and write a 1-2 sentence description of what the app does. Focus on the main purpose and key features. Be concise and professional. Do not start with This app or This Streamlit app. Code: " + escaped_code
        
        try:
            sql = "SELECT SNOWFLAKE.CORTEX.COMPLETE('llama3.1-70b', '" + prompt.replace("'", "''") + "') as description"
            result = session.sql(sql).collect()
            
            if result and result[0]['DESCRIPTION']:
                return result[0]['DESCRIPTION'].strip()
            else:
                return "Error: AI generation returned empty result"
        except Exception as e:
            return f"Error: AI generation failed: {str(e)}"
            
    except Exception as e:
        return f"Error: {str(e)}"
$$;

GRANT USAGE ON PROCEDURE TEMP.OCHOY.GENERATE_APP_DESCRIPTION(VARCHAR) TO ROLE PUBLIC;
```

### Usage

```sql
-- Generate description for a specific app
CALL TEMP.OCHOY.GENERATE_APP_DESCRIPTION('SNOWFLAKE360.MM_ASSESSMENT.MATURITY_ASSESSMENT_V2');

-- Example output:
-- "The Snowflake 360 Maturity Assessment app evaluates an organization's maturity level 
--  across various topics, providing a scorecard and recommendations for improvement."
```

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| Cannot access stage | Permission denied or special stage type | Manual description needed |
| App has minimal code | Stub/placeholder app | Manual description needed |
| No source stage found | App uses non-standard deployment | Manual description needed |
| AI generation failed | Token limit exceeded or API issue | Try again or use manual |

---

## 7. Scheduled Task

Daily refresh at 6 AM UTC.

```sql
CREATE OR REPLACE TASK TEMP.OCHOY.REFRESH_STREAMLIT_INVENTORY
    WAREHOUSE = SNOWHOUSE
    SCHEDULE = 'USING CRON 0 6 * * * UTC'
AS
    CALL TEMP.OCHOY.REFRESH_STREAMLIT_APPS();

-- Enable the task
ALTER TASK TEMP.OCHOY.REFRESH_STREAMLIT_INVENTORY RESUME;
```

---

## Troubleshooting

### Issue: Creator info is missing for recent apps

**Cause**: ACCESS_HISTORY has 2-3 hour latency.

**Solution**: Wait and re-run the refresh procedure, or manually update:

```sql
-- Manually update creator info for apps missing it
WITH creators AS (
    SELECT 
        object_modified_by_ddl:objectName::STRING AS streamlit_fqn,
        user_name
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY
    WHERE object_modified_by_ddl:objectDomain::STRING = 'Streamlit'
      AND object_modified_by_ddl:operationType::STRING = 'CREATE'
    QUALIFY ROW_NUMBER() OVER (PARTITION BY streamlit_fqn ORDER BY query_start_time ASC) = 1
)
UPDATE TEMP.OCHOY.STREAMLIT_APPS_BASE b
SET CREATED_BY_USER = c.user_name,
    CREATOR_EMAIL = u.EMAIL,
    CREATOR_DISPLAY_NAME = u.DISPLAY_NAME
FROM creators c
JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS u ON u.NAME = c.user_name AND u.DELETED_ON IS NULL
WHERE c.streamlit_fqn = b.LOCATION
  AND b.CREATED_BY_USER IS NULL;
```

### Issue: PS app count seems low

**Cause**: Only apps where the creator is in `resolve_org` AND under Roxanne McKinnon's hierarchy will show.

**Check coverage**:
```sql
SELECT 
    COUNT(*) as total_apps,
    SUM(CASE WHEN CREATED_BY_USER IS NOT NULL THEN 1 ELSE 0 END) as with_creator,
    SUM(CASE WHEN ORG_HIERARCHY IS NOT NULL THEN 1 ELSE 0 END) as with_org
FROM TEMP.OCHOY.STREAMLIT_APPS_WITH_ORG;
```

### Issue: Stored procedure returns fewer creators than expected

**Cause**: The procedure runs as CALLER - ensure the executing role has access to:
- `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY`
- `SNOWFLAKE.ACCOUNT_USAGE.USERS`

**Solution**: Run with a role that has ACCOUNTADMIN or GOVERNANCE_VIEWER privileges.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-19 | Initial working version with ACCESS_HISTORY creator detection |
| 1.1 | 2026-02-20 | Added STREAMLIT_APP_METADATA table and GENERATE_APP_DESCRIPTION procedure |
