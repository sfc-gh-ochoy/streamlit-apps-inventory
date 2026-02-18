#!/bin/bash

# Deploy Streamlit App Inventory to Snowflake
# Usage: ./deploy.sh [dev|prod]

set -e

ENV="${1:-dev}"

case "$ENV" in
  dev)
    STAGE="@SNOWPUBLIC.STREAMLIT.streamlit_inventory_stage_dev/PS_STREAMLIT_APP_INVENTORY_DEV"
    APP_URL="https://app.snowflake.com/sfcogsops/snowhouse_aws_us_west_2/#/streamlit-apps/SNOWPUBLIC.STREAMLIT.PS_STREAMLIT_APP_INVENTORY_DEV"
    ;;
  prod)
    STAGE="@SNOWPUBLIC.STREAMLIT.streamlit_inventory_stage/PS_STREAMLIT_APP_INVENTORY/versions/live"
    APP_URL="https://app.snowflake.com/sfcogsops/snowhouse_aws_us_west_2/#/streamlit-apps/SNOWPUBLIC.STREAMLIT.PS_STREAMLIT_APP_INVENTORY"
    ;;
  *)
    echo "Usage: ./deploy.sh [dev|prod]"
    exit 1
    ;;
esac

echo "Deploying to $ENV..."
echo "Stage: $STAGE"

snow stage copy streamlit_app.py "$STAGE/" --overwrite
snow stage copy environment.yml "$STAGE/" --overwrite

echo ""
echo "Deployed successfully!"
echo "View app: $APP_URL"
