import os
import logging
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchFieldDataType,
    # フィールド定義クラス
    SimpleField, # フィルタリングやソートに使用するフィールド
    SearchableField, # リッチな機能の全文検索を実装する場合
    SearchField, # 完全一致の全文検索を実装する場合
    # ベクトル検索実装のためのクラス
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    AzureOpenAIVectorizer,
    # AzureOpenAIVectorizerParameters,
    AzureOpenAIParameters,
    # セマンティック検索実装のためのクラス
    SemanticConfiguration,
    SemanticPrioritizedFields,
    SemanticField,
    SemanticSearch,
    # スコアリングプロファイル実装のためのクラス
    ScoringProfile,
    TextWeights,
    FreshnessScoringFunction,
    FreshnessScoringParameters,
    ScoringFunction,
    ScoringFunctionInterpolation,
)

openai_embedding_key = os.getenv("AZURE_OPENAI_EMBEDDING_API_KEY")
openai_embedding_endpoint = os.getenv("AZURE_OPENAI_EMBEDDING_ENDPOINT")
openai_embedding_uri = os.getenv("AZURE_OPENAI_EMBEDDING_URI")
openai_embedding_model_name = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL_NAME")
azure_search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
azure_search_key = os.getenv("AZURE_SEARCH_ADMIN_KEY")

def create_project_index(project_name:str, spo_url:str):
    """
    プロジェクト名とSPOのURLを入力して,入力に対して新しいインデックスを作成する.
    """
    try:
        project_name = project_name
        spo_url = spo_url
        
        # フィールド定義
        fields = [
            SearchableField(name="site_library_document_Id", type=SearchFieldDataType.String, key=True, sortable=True, stored=True, analyzer_name="keyword",searchable=True),
            SimpleField(name="siteId", type=SearchFieldDataType.String,  stored=True, searchable=True),
            SimpleField(name="libraryId", type=SearchFieldDataType.String,  stored=True, searchable=True),
            SimpleField(name="documentId", type=SearchFieldDataType.String,  stored=True, searchable=True, sortable=True, filterable=True),
            SearchableField(name="documentPath", type=SearchFieldDataType.String,  stored=True, searchable=True, filterable=True),
            SimpleField(name="folderName", type=SearchFieldDataType.String,  stored=True, searchable=False, filterable=True),
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
        vector_search = create_vector_search()
        #semantic_search = create_semantic_search()
        scoring_profiles, default_scoring_profile = create_scoring_profiles()

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
        algorithm_name="vector-for-verification-algorithm",
        vector_search_profile_name="vector_profile",
        vectorizer_name="myVectorizer",
        resource_url=openai_embedding_uri,
        deployment_id=openai_embedding_model_name,
        api_key=openai_embedding_key,
        model_name=openai_embedding_model_name
    ):
    """
    azure-search-documents==11.6.0b4
    """ 
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


# def create_vector_search(
#         algorithm_name="vector-for-verification-algorithm",
#         vector_search_profile_name="vector_profile",
#         vectorizer_name="myVectorizer",
#         resource_url=openai_embedding_uri,
#         deployment_id=openai_embedding_model_name,
#         api_key=openai_embedding_key,
#         model_name=openai_embedding_model_name
#     ):
    """
    azure-search-documents==11.6.0b8
    """
#     # VectorSearch 設定
#     vector_search = VectorSearch(
#         algorithms=[HnswAlgorithmConfiguration(name=algorithm_name)],
#         profiles=[
#             VectorSearchProfile(
#                 name=vector_search_profile_name,
#                 algorithm_configuration_name=algorithm_name,
#                 vectorizer_name=vectorizer_name,
#             )
#         ],
#          vectorizers=[
#             AzureOpenAIVectorizer(
#                 vectorizer_name=vectorizer_name,
#                 parameters=AzureOpenAIVectorizerParameters(
#                     resource_url=resource_url,
#                     deployment_name=deployment_id,
#                     api_key=api_key,
#                     model_name=model_name,
#                 ),
#             )
#         ],
#     )

#     return vector_search

def create_semantic_search(
        semantic_config_name="<任意のコンフィグ名>", 
        title_field_name="<タイトルに当たるフィールド名>", 
        content_field_name="<内容に当たるフィールド名>", 
        keywords_field_name="<キーワードに当たるフィールド名>"
        ):
    # セマンティック検索を実装する場合
    semantic_config = SemanticConfiguration(
        name=semantic_config_name,
        prioritized_fields=SemanticPrioritizedFields(
            title_field=SemanticField(field_name=title_field_name),
            content_fields=[SemanticField(field_name=content_field_name)],
            keywords_fields=[SemanticField(field_name=keywords_field_name)]
        )
    )
    semantic_search = SemanticSearch(configurations=[semantic_config])

    return semantic_search

def create_scoring_profiles(
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


if __name__ == "__main__":

    # 関数を呼び出してindexを作成
    create_project_index(
        project_name="test", spo_url = "test"
    )