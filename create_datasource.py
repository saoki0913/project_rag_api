import os
import httpx
from fastapi import  HTTPException
import logging
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient, SearchIndexerClient
from azure.search.documents.models import VectorizableTextQuery
from azure.search.documents.indexes.models import (

    SearchIndexerDataContainer,
    SearchIndexerDataSourceConnection,
    SqlIntegratedChangeTrackingPolicy
)

azure_search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
azure_search_key = os.getenv("AZURE_SEARCH_ADMIN_KEY")
ApplicationId = os.getenv("SPO_APPLICATION_ID")
ApplicationSecret = os.getenv("SPO_APPLICATION_SECRET")
TenantId = os.getenv("SPO_TENANT_ID")


# Datasource の作成 (非同期)   
async def create_project_data_source(project_name:str, spo_url:str):
    """
    Create a datasource
    """
    try:
        data_source_name = f"{project_name}-datasource"
        spo_url = spo_url
        sharepoint_connection_string = f"SharePointOnlineEndpoint={spo_url};ApplicationId={ApplicationId};ApplicationSecret={ApplicationSecret};TenantId={TenantId};" #社内用 URL version
        # https://intelligentforce0401.sharepoint.com/sites/Test/Shared%20Documents/Forms/AllItems.aspx?id=%2Fsites%2FTest%2FShared%20Documents%2Ftest&viewid=d0948e95%2D5e9a%2D43cc%2D8630%2D6006ca74a7e3
        # sharepoint_connection_string = f"SharePointOnlineEndpoint=https://intelligentforce0401.sharepoint.com/sites/{project_name};ApplicationId={ApplicationId};ApplicationSecret={ApplicationSecret};TenantId={TenantId};" #社内用
        # sharepoint_connection_string = f"SharePointOnlineEndpoint={spo_url};ApplicationId={ApplicationId};ApplicationSecret={ApplicationSecret};TenantId={TenantId};" #社外用
        # Datasource の作成 (非同期)       
        data_source_payload = {
            "name": data_source_name,
            "type": "sharepoint",
            "credentials": {
                "connectionString": sharepoint_connection_string
            },
            "container": {
                "name": "defaultSiteLibrary"
            }
        }

        headers = {
            "Content-Type": "application/json",
            "api-key": azure_search_key,
        }

        # リクエストを送信
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{azure_search_endpoint}/datasources?api-version=2024-05-01-preview",
                json=data_source_payload,
                headers=headers
            )
            if response.status_code != 201:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"データソースの作成に失敗しました: {response.json()}"
                )
        logging.info("Success creating datasource")

    #データソース作成に失敗したときにログを表示
    except Exception as e:
        logging.error(f"Error creating datasource: {e}")

if __name__ == "__main__":

    # 関数を呼び出してデータソースを作成
    create_project_data_source(
        project_name="test", spo_url = "test"
    )