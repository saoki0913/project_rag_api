
import os
import httpx
from fastapi import  HTTPException
import logging
from azure.search.documents.indexes.models import (
    SplitSkill,
    InputFieldMappingEntry,
    OutputFieldMappingEntry,
    AzureOpenAIEmbeddingSkill,
    SearchIndexerIndexProjections,
    SearchIndexerIndexProjectionSelector,
    SearchIndexerIndexProjectionsParameters,
    IndexProjectionMode,
    SearchIndexerSkillset,
)

openai_embedding_key = os.getenv("AZURE_OPENAI_EMBEDDING_API_KEY")
openai_embedding_endpoint = os.getenv("AZURE_OPENAI_EMBEDDING_ENDPOINT")
openai_embedding_uri = os.getenv("AZURE_OPENAI_EMBEDDING_URI")
openai_embedding_model_name = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL_NAME")
azure_search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
azure_search_key = os.getenv("AZURE_SEARCH_ADMIN_KEY")
azure_ai_service_account_key = os.getenv("AZURE_AI_SERVICE_ACCOUNT_KEY")


async def create_project_skillset(project_name:str, spo_url:str):
    """
    Create a datasource
    """
    try:
        skillset_name = f"{project_name}-skillset"
        index_name = f"{project_name}-index"
        spo_url = spo_url

        # スキルセット定義 
        skillset_payload = {
            "name": skillset_name,
            "skills": [
                # DocumentIntelligenceLayoutSkill
                {
                    "@odata.type": "#Microsoft.Skills.Util.DocumentIntelligenceLayoutSkill",
                    "name": "my_document_intelligence_layout_skill",
                    "description": "use layout model",
                    "context": "/document",
                    "inputs": [
                        {"name": "file_data", "source": "/document/file_data", "inputs": []}
                    ],
                    "outputs": [
                        {"name": "markdown_document", "targetName": "markdownDocument"}
                    ],
                    "outputMode": "oneToMany",
                    "markdownHeaderDepth": "h3",
                },
                # SplitSkill
                {
                    "@odata.type": "#Microsoft.Skills.Text.SplitSkill",
                    "name": "my_text_split_skill",
                    "description": "split a document",
                    "context": "/document/markdownDocument/*",
                    "inputs": [
                        {
                            "name": "text",
                            "source": "/document/markdownDocument/*/content",
                            "inputs": [],
                        }
                    ],
                    "outputs": [{"name": "textItems", "targetName": "chunks"}],
                    "defaultLanguageCode": "ja",
                    "textSplitMode": "pages",
                    "maximumPageLength": 2000,
                    "pageOverlapLength": 500,
                },
                # AzureOpenAIEmbeddingSkill
                {
                    "@odata.type": "#Microsoft.Skills.Text.AzureOpenAIEmbeddingSkill",
                    "name": "my_azure_openai_embedding_skill",
                    "context": "/document/markdownDocument/*/chunks/*",
                    "inputs": [
                        {"name": "text", "source": "/document/markdownDocument/*/chunks/*"}
                    ],
                    "outputs": [{"name": "embedding", "targetName": "vector"}],
                    "resourceUri": openai_embedding_uri,
                    "deploymentId": "text-embedding-ada-002",
                    "apiKey": openai_embedding_key,
                    "modelName": "text-embedding-ada-002",
                    "dimensions": 1536,
                },
            ],
            "cognitiveServices": {
                "@odata.type": "#Microsoft.Azure.Search.CognitiveServicesByKey",
                "key":azure_ai_service_account_key,
                },
            "@odata.etag": '"0x8DD180AC7B87C4D"',
            "indexProjections": {
                "selectors": [
                    {
                        "targetIndexName": index_name,
                        "parentKeyFieldName": "parent_id",
                        "sourceContext": "/document/markdownDocument/*/chunks/*",
                        "mappings": [
                            {"name": "siteId", "source": "/document/metadata_spo_site_id"},
                            {"name": "libraryId", "source": "/document/metadata_spo_library_id"},
                            {"name": "documentId", "source": "/document/metadata_spo_item_id"},
                            {"name": "documentPath", "source": "/document/metadata_spo_item_path"},
                            {"name": "folderName", "source": "/document/folderName"}, 
                            {"name": "documentName", "source": "/document/metadata_spo_item_name"},
                            {"name": "documentUrl", "source": "/document/metadata_spo_item_weburi"},
                            {"name": "last_modified", "source": "/document/metadata_spo_item_last_modified"},
                            {"name": "size", "source": "/document/metadata_spo_item_size"},
                            {"name": "content", "source": "/document/markdownDocument/*/chunks/*"},
                            {"name": "chunk", "source": "/document/markdownDocument/*/chunks/*"},
                            {"name": "header_1", "source": "/document/markdownDocument/*/sections/h1"},
                            {"name": "header_2", "source": "/document/markdownDocument/*/sections/h2"},
                            {"name": "header_3", "source": "/document/markdownDocument/*/sections/h3"},
                            {"name": "content_vector", "source": "/document/markdownDocument/*/chunks/*/vector"},
                        ],
                    }
                ],
                "parameters": {"projectionMode": "skipIndexingParentDocuments"},
            },
        }

        # APIヘッダー
        headers = {
            "Content-Type": "application/json",
            "api-key": azure_search_key,
        }

            # リクエストを送信
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{azure_search_endpoint}/skillsets('{skillset_name}')?api-version=2024-05-01-preview",
                json=skillset_payload,
                headers=headers
            )
            if response.status_code != 201:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"スキルセットの作成に失敗しました: {response.json()}"
                )
        logging.info("Success creating skillset")

    #スキルセット作成に失敗したときにログを表示    
    except Exception as e:
        logging.error(f"Error creating skillset: {e}")

if __name__ == "__main__":

    # 関数を呼び出してスキルセットを作成
    create_project_skillset(
        project_name="test", spo_url = "test"
    )
    