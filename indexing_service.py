import os
import logging
import httpx
from datetime import datetime, timedelta
from fastapi import HTTPException
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchIndexerSkillset,
    SearchFieldDataType,
    # フィールド定義クラス
    SimpleField, 
    SearchableField, 
    SearchField, 
    # ベクトル検索実装のためのクラス
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    AzureOpenAIVectorizer,
    AzureOpenAIParameters,
    # スコアリングプロファイル実装のためのクラス
    ScoringProfile,
    FreshnessScoringFunction,
    FreshnessScoringParameters,
    ScoringFunctionInterpolation,
    # skillset
    SplitSkill,
    InputFieldMappingEntry,
    OutputFieldMappingEntry,
    AzureOpenAIEmbeddingSkill,
    SearchIndexerIndexProjections,
    SearchIndexerIndexProjectionSelector,
    SearchIndexerIndexProjectionsParameters,
    IndexProjectionMode,
    SearchIndexerSkillset,
    InputFieldMappingEntry,
    OutputFieldMappingEntry,
    AzureOpenAIEmbeddingSkill,
    #indexer
    SearchIndexer,
    IndexingSchedule,
    IndexingParameters,
    FieldMapping,
    FieldMappingFunction,
)

class ProjectIndexingService:
    def __init__(self):
        self.azure_search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
        self.azure_search_key = os.getenv("AZURE_SEARCH_ADMIN_KEY")
        self.openai_embedding_key = os.getenv("AZURE_OPENAI_EMBEDDING_API_KEY")
        self.openai_embedding_uri = os.getenv("AZURE_OPENAI_EMBEDDING_URI")
        self.openai_embedding_endpoint = os.getenv("AZURE_OPENAI_EMBEDDING_ENDPOINT")
        self.openai_embedding_model_name = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL_NAME")
        self.ApplicationId = os.getenv("SPO_APPLICATION_ID")
        self.ApplicationSecret = os.getenv("SPO_APPLICATION_SECRET")
        self.TenantId = os.getenv("SPO_TENANT_ID")
        self.azure_ai_service_account_key = os.getenv("AZURE_AI_SERVICE_ACCOUNT_KEY")

    def create_project_index(self, project_name:str):
        """
        プロジェクト名とSPOのURLを入力して,入力に対して新しいインデックスを作成する.
        """
        try:
            project_name = project_name
            
            # フィールド定義
            fields = [
                SearchableField(name="site_library_document_Id", type=SearchFieldDataType.String, key=True, sortable=True, stored=True, analyzer_name="keyword",searchable=True),
                SimpleField(name="siteId", type=SearchFieldDataType.String,  stored=True, searchable=True),
                SimpleField(name="libraryId", type=SearchFieldDataType.String,  stored=True, searchable=True),
                SimpleField(name="documentId", type=SearchFieldDataType.String,  stored=True, searchable=True, sortable=True, filterable=True),
                SearchableField(name="documentPath", type=SearchFieldDataType.String,  stored=True, searchable=True, filterable=True),
                SimpleField(name="folderName", type=SearchFieldDataType.String,  stored=True, searchable=False, filterable=True),
                SimpleField(name="subfolderName", type=SearchFieldDataType.String,  stored=True, searchable=False, filterable=True),
                SearchableField(name="documentName", type=SearchFieldDataType.String, stored=True, searchable=True, filterable=True),
                SearchableField(name="documentUrl", type=SearchFieldDataType.String, stored=True, searchable=True, filterable=True),
                SimpleField(name="last_modified", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True, stored=True),
                SimpleField(name="size", type=SearchFieldDataType.Int64, filterable=True, sortable=True, stored=True),
                SearchableField(name="parent_id", type=SearchFieldDataType.String,  stored=True, searchable=True, filterable=True),
                SearchableField(name="header_1", type=SearchFieldDataType.String,  stored=True, searchable=True),
                SearchableField(name="header_2", type=SearchFieldDataType.String,  stored=True, searchable=True),
                SearchableField(name="header_3", type=SearchFieldDataType.String, stored=True, searchable=True),
                SearchableField(name="content", type=SearchFieldDataType.String, stored=True, searchable=True),
                SearchableField(name="chunk", type=SearchFieldDataType.String, stored=True, searchable=True),
                SearchField(name="content_vector", 
                            type=SearchFieldDataType.Collection(SearchFieldDataType.Single), 
                            vector_search_dimensions=1536, 
                            vector_search_profile_name="vector_profile"), 
            ]

            # 高度な検索の実装
            vector_search = self.create_vector_search()
            #semantic_search = create_semantic_search()
            scoring_profiles, default_scoring_profile = self.create_scoring_profiles()

            logging.info("Success creating index")

            return SearchIndex(
                name=f"{project_name}-index",
                fields = fields,
                vector_search = vector_search, # 任意
                # semantic_search = semantic_search, # 任意
                scoring_profiles = scoring_profiles, # 任意
                default_scoring_profile = default_scoring_profile, # 任意
            )


        #index作成に失敗したときにログを表示
        except Exception as e:
            logging.error(f"Error creating index: {e}")


    def create_vector_search(
            self,
            algorithm_name="vector-for-verification-algorithm",
            vector_search_profile_name="vector_profile",
            vectorizer_name="myVectorizer"
        ):
        """
        azure-search-documents==11.6.0b4
        """        
        resource_url = self.openai_embedding_uri
        deployment_id = self.openai_embedding_model_name
        api_key = self.openai_embedding_key
        model_name = self.openai_embedding_model_name

        # VectorSearch 設定
        vector_search = VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name=algorithm_name)],
            profiles=[
                VectorSearchProfile(
                    name=vector_search_profile_name,
                    algorithm_configuration_name=algorithm_name,
                    vectorizer=vectorizer_name,
                )
            ],
            vectorizers=[
                AzureOpenAIVectorizer(
                    name=vectorizer_name,
                    azure_open_ai_parameters=AzureOpenAIParameters(
                        resource_uri=resource_url,
                        deployment_id=deployment_id,
                        api_key=api_key,
                        model_name=model_name,
                    ),
                )
            ],
        )

        return vector_search
   
    def create_scoring_profiles(
            self,
            function_aggregation = "sum", # "average"、"minimum"、"maximum"、"firstMatching"などもある
            scoring_profile_name = "boostLastModified",
            freshness_field_name="last_modified",
            freshness_boost=10,
            boosting_duration="P365D",  # ISO 8601 形式の期間
            ):
        # スコアリングプロファイルの作成
        scoring_profiles = []
        default_scoring_profile = None

        # FreshnessScoringFunctionの作成
        freshness_scoring_function = FreshnessScoringFunction(
            field_name=freshness_field_name,
            boost=freshness_boost,
            parameters=FreshnessScoringParameters(boosting_duration=boosting_duration),
            interpolation=ScoringFunctionInterpolation.QUADRATIC,  # "quadratic" を指定
        )

        # ScoringProfileの作成
        scoring_profile = ScoringProfile(
            name=scoring_profile_name,
            function_aggregation=function_aggregation,
            functions=[freshness_scoring_function],  # Freshness関数を登録
        )

        scoring_profiles.append(scoring_profile)
        default_scoring_profile = scoring_profile_name

        return scoring_profiles, default_scoring_profile
    
    # Datasource の作成 (非同期)   
    async def create_project_data_source(self, project_name:str, spo_url:str):
        """
        Create a datasource
        """
        try:
            data_source_name = f"{project_name}-datasource"
            spo_url = spo_url
            sharepoint_connection_string = f"SharePointOnlineEndpoint={spo_url};ApplicationId={self.ApplicationId};ApplicationSecret={self.ApplicationSecret};TenantId={self.TenantId};" #社内用 URL version
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
                "api-key": self.azure_search_key,
            }

            # リクエストを送信
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.azure_search_endpoint}/datasources?api-version=2024-05-01-preview",
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

    
    async def create_project_skillset_layout(self, project_name:str):
        """
        Create a skillset
        """
        try:
            skillset_name = f"{project_name}-skillset"
            index_name = f"{project_name}-index"

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
                        "resourceUri": self.openai_embedding_uri,
                        "deploymentId": "text-embedding-ada-002",
                        "apiKey": self.openai_embedding_key,
                        "modelName": "text-embedding-ada-002",
                        "dimensions": 1536,
                    },
                ],
                "cognitiveServices": {
                    "@odata.type": "#Microsoft.Azure.Search.CognitiveServicesByKey",
                    "key":self.azure_ai_service_account_key,
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
                                {"name": "subfolderName", "source": "/document/subfolderName"}, 
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
                "api-key": self.azure_search_key,
            }

                # リクエストを送信
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.azure_search_endpoint}/skillsets('{skillset_name}')?api-version=2024-05-01-preview",
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

    
    def create_project_skillset(self, project_name:str):
        """
        Create a skillset
        """  
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
            resource_uri=self.openai_embedding_uri,  
            deployment_id=self.openai_embedding_model_name,  
            model_name=self.openai_embedding_model_name,
            dimensions=1536,
            api_key=self.openai_embedding_key,  
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
    

    def create_project_indexer(self, project_name:str):
        """
        Create a indexer
        """
        try:
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

            folder_field_mappings_function = FieldMappingFunction(
                name="extractTokenAtPosition",
                parameters={
                    "delimiter": "/",
                    "position": 4
                }
            )

            folder_field_mappings = FieldMapping(
                source_field_name="metadata_spo_item_path",
                target_field_name="folderName",
                mapping_function=folder_field_mappings_function
            )

            subfolder_field_mappings_function = FieldMappingFunction(
                name="extractTokenAtPosition",
                parameters={
                    "delimiter": "/",
                    "position": 4
                }
            )

            subfolder_field_mappings = FieldMapping(
                source_field_name="metadata_spo_item_path",
                target_field_name="subfolderName",
                mapping_function=subfolder_field_mappings_function
            )

            field_mappings = [folder_field_mappings, subfolder_field_mappings]

            indexer = SearchIndexer(  
                name=indexer_name,  
                description="Indexer to index documents and generate embeddings",  
                skillset_name=skillset_name,
                schedule=schedule,  
                target_index_name=index_name,  
                data_source_name=data_source_name,
                parameters=indexer_parameters,
                field_mappings=field_mappings
            ) 

            logging.info("Success creating indexer")
            return indexer 
        
        except Exception as e:
            logging.error(f"Error creating indexer: {e}")


    def create_project_folder_indexer(self, project_name:str):
        """
        Create a indexer
        """
        try:
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

            folder_field_mappings_function = FieldMappingFunction(
                name="extractTokenAtPosition",
                parameters={
                    "delimiter": "/",
                    "position": 4
                }
            )

            folder_field_mappings = FieldMapping(
                source_field_name="metadata_spo_item_path",
                target_field_name="folderName",
                mapping_function=folder_field_mappings_function
            )

            subfolder_field_mappings_function = FieldMappingFunction(
                name="extractTokenAtPosition",
                parameters={
                    "delimiter": "/",
                    "position": 5
                }
            )

            subfolder_field_mappings = FieldMapping(
                source_field_name="metadata_spo_item_path",
                target_field_name="subfolderName",
                mapping_function=subfolder_field_mappings_function
            )

            field_mappings = [folder_field_mappings, subfolder_field_mappings]

            indexer = SearchIndexer(  
                name=indexer_name,  
                description="Indexer to index documents and generate embeddings",  
                skillset_name=skillset_name,
                schedule=schedule,  
                target_index_name=index_name,  
                data_source_name=data_source_name,
                parameters=indexer_parameters,
                field_mappings=field_mappings
            ) 

            logging.info("Success creating indexer")
            return indexer 
        
        except Exception as e:
            logging.error(f"Error creating indexer: {e}")