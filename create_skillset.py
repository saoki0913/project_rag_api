
import os
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

def create_project_skillset(project_name:str, spo_url:str):
    """
    Create a skillset
    """  
    spo_url = spo_url
    index_name = f"{project_name}-index"
    skillset_name = f"{project_name}-skillset"

    # テキストのchunking
    split_skill = SplitSkill(  
        name="my_text_split_skill",
        description="split a document",
        text_split_mode="pages",  
        context="/document",  
        maximum_page_length=1000,  
        page_overlap_length=250,
        default_language_code="ja",
        inputs=[  
            InputFieldMappingEntry(name="text", source="/document/content"),  
        ],  
        outputs=[  
            OutputFieldMappingEntry(name="textItems", target_name="chunks")  
        ]
    )

    # ベクトル化
    embedding_skill = AzureOpenAIEmbeddingSkill( 
        name="my_azure_openai_embedding_skill", 
        description="Skill to generate embeddings via Azure OpenAI",  
        context="/document/chunks/*",  
        resource_uri=openai_embedding_uri,  
        deployment_id=openai_embedding_model_name,  
        model_name=openai_embedding_model_name,
        dimensions=1536,
        api_key=openai_embedding_key,  
        inputs=[  
            InputFieldMappingEntry(name="text", source="/document/chunks/*"),  
        ],  
        outputs=[
            OutputFieldMappingEntry(name="embedding", target_name="vector")  
        ]
    )

    # スキルセットの結果をインデックスにマッピングする
    index_projections = SearchIndexerIndexProjections(  
        selectors=[  
            SearchIndexerIndexProjectionSelector(  
                target_index_name=index_name,  
                parent_key_field_name="parent_id",  
                source_context="/document/chunks/*",  
                mappings=[
                    InputFieldMappingEntry(name="siteId", source="/document/metadata_spo_site_id"),  
                    InputFieldMappingEntry(name="libraryId", source="/document/metadata_spo_library_id"),  
                    InputFieldMappingEntry(name="documentId", source="/document/metadata_spo_item_id"),  
                    InputFieldMappingEntry(name="documentPath", source="/document/metadata_spo_item_path"),
                    InputFieldMappingEntry(name="documentName", source="/document/metadata_spo_item_name"),
                    InputFieldMappingEntry(name="documentUrl", source="/document/metadata_spo_item_weburi"), 
                    InputFieldMappingEntry(name="last_modified", source="/document/metadata_spo_item_last_modified"), 
                    InputFieldMappingEntry(name="size", source="/document/metadata_spo_item_size"), 
                    InputFieldMappingEntry(name="content", source="/document/content"), 
                    InputFieldMappingEntry(name="chunk", source="/document/chunks/*"),
                    InputFieldMappingEntry(name="content_vector", source="/document/chunks/*/vector")
                ]
            )
        ],  
        parameters=SearchIndexerIndexProjectionsParameters(  
            projection_mode=IndexProjectionMode.SKIP_INDEXING_PARENT_DOCUMENTS  
        )  
    )

    skills = [split_skill, embedding_skill]

    return SearchIndexerSkillset(  
        name=skillset_name,  
        description="Skillset to chunk documents and generating embeddings",  
        skills=skills,  
        index_projections=index_projections
    )