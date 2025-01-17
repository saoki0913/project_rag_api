import os
import logging
from datetime import datetime, timedelta
from azure.search.documents.indexes.models import (
    SearchIndexer,
    IndexingSchedule,
    IndexingParameters,
    IndexingParametersConfiguration ,
    FieldMapping,
    FieldMappingFunction,
    BlobIndexerImageAction
)

openai_embedding_key = os.getenv("AZURE_OPENAI_EMBEDDING_API_KEY")
openai_embedding_endpoint = os.getenv("AZURE_OPENAI_EMBEDDING_ENDPOINT")
openai_embedding_uri = os.getenv("AZURE_OPENAI_EMBEDDING_URI")
openai_embedding_model_name = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL_NAME")
azure_search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
azure_search_key = os.getenv("AZURE_SEARCH_ADMIN_KEY")

def create_project_indexer(project_name:str, spo_url:str):
    """
    Create a indexer
    """
    try:
        spo_url = spo_url

        # Create an indexer for project
        index_name = f"{project_name}-index" 
        indexer_name = f"{project_name}-indexer" 
        skillset_name = f"{project_name}-skillset" 
        data_source_name = f"{project_name}-datasource"  

        #インデクサーのスケジュールを設定（1日1回、現在時刻から開始）
        schedule = IndexingSchedule(
            interval=timedelta(days=1),  # 1日1回実行
            start_time=datetime.utcnow()  # 現在のUTC時刻から開始
        )

        #fileデータをスキルセットに送る設定
        indexer_parameters = IndexingParameters(
            max_failed_items=-1,
            max_failed_items_per_batch=-1,
            configuration={
            "dataToExtract": "contentAndMetadata",
            "imageAction": "none",
            "indexStorageMetadataOnlyForOversizedDocuments": True,
            "failOnUnsupportedContentType": False,
            "allowSkillsetToReadFileData": True
        }
        )

        field_mappings_function = FieldMappingFunction(
            name="extractTokenAtPosition",
            parameters={
                "delimiter": "/",
                "position": 4
            }
        )

        field_mappings = FieldMapping(
            source_field_name="metadata_spo_item_path",
            target_field_name="folderName",
            mapping_function=field_mappings_function
        )


        indexer = SearchIndexer(  
            name=indexer_name,  
            description="Indexer to index documents and generate embeddings",  
            skillset_name=skillset_name,
            schedule=schedule,  
            target_index_name=index_name,  
            data_source_name=data_source_name,
            parameters=indexer_parameters,
            field_mappings=[field_mappings]
        ) 

        logging.info("Success creating indexer")
        return indexer 
    
    except Exception as e:
        logging.error(f"Error creating indexer: {e}")


if __name__ == "__main__":

    # 関数を呼び出してインデクサーを作成
    create_project_indexer(
        project_name="test", spo_url = "test"
    )