import azure.functions as func
import openai
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import os
import logging
import uuid
from azure.core.exceptions import ResourceExistsError
from pydantic import BaseModel
from azure.core.credentials import AzureKeyCredential
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes import SearchIndexerClient
from azure.cosmos import CosmosClient

import uvicorn
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings
from fastapi.middleware.cors import CORSMiddleware
from fastapi_azure_auth import SingleTenantAzureAuthorizationCodeBearer
from pydantic import AnyHttpUrl, computed_field
from fastapi import FastAPI, Security



#import mylibraly
from create_index import create_project_index
from create_skillset_documentintelligence import create_project_skillset
from create_indexer import create_project_indexer
from create_datasource import create_project_data_source
from generate_answer import generate_answer

# 環境変数から設定を取得
intelligence_key = os.getenv("DOCUMENT_INTELLIGENCE_API_KEY")
intelligence_endpoint = os.getenv("DOCUMENT_INTELLIGENCE_ENDPOINT")
openai_embedding_key = os.getenv("AZURE_OPENAI_EMBEDDING_API_KEY")
openai_embedding_endpoint = os.getenv("AZURE_OPENAI_EMBEDDING_ENDPOINT")
openai_embedding_uri = os.getenv("AZURE_OPENAI_EMBEDDING_URI")
azure_search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
azure_search_key = os.getenv("AZURE_SEARCH_ADMIN_KEY")
openai.api_key = os.getenv("AZURE_OPENAI_API_KEY")
openai.azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")  
cosmos_endpoint = os.getenv("COSMOS_DB_ENDPOINT")
cosmos_key = os.getenv("COSMOS_DB_KEY")
cosmos_database_name = "ProjectDatabase"
cosmos_container_name = "Projects"

class Settings(BaseSettings):
    BACKEND_CORS_ORIGINS: list[str | AnyHttpUrl] = ['http://localhost:7071']
    OPENAPI_CLIENT_ID: str = ""
    APP_CLIENT_ID: str = ""
    TENANT_ID: str = ""
    SCOPE_DESCRIPTION: str = "user_impersonation"
   
    @computed_field
    @property
    def SCOPE_NAME(self) -> str:
        return f'api://{self.APP_CLIENT_ID}/{self.SCOPE_DESCRIPTION}'

    @computed_field
    @property
    def SCOPES(self) -> dict:
        return {
            self.SCOPE_NAME: self.SCOPE_DESCRIPTION,
        }

    class Config:
        env_file = 'local.settings.json'
        env_file_encoding = 'utf-8'
        case_sensitive = True

settings = Settings()

# FastAPI アプリケーションの初期化
app = FastAPI(
    swagger_ui_oauth2_redirect_url='/oauth2-redirect',
    swagger_ui_init_oauth={
        'usePkceWithAuthorizationCodeGrant': True,
        'clientId': settings.OPENAPI_CLIENT_ID,
    },
)

if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

azure_scheme = SingleTenantAzureAuthorizationCodeBearer(
    app_client_id=settings.APP_CLIENT_ID,
    tenant_id=settings.TENANT_ID,
    scopes=settings.SCOPES,
)


# リクエストボディのスキーマ定義
class AnswerRequest(BaseModel):
    user_question: str
    project_name: str
    conversation_id: str = None  # オプション項目（指定がない場合はNone）

class RegisterProjectRequest(BaseModel):
    project_name: str
    spo_url: str

# Cosmos DB クライアントの初期化
cosmos_client = CosmosClient(cosmos_endpoint, cosmos_key)
database = cosmos_client.get_database_client(cosmos_database_name)
container = database.get_container_client(cosmos_container_name)


@app.post("/resist_project", dependencies=[Security(azure_scheme)])
async def resist_project(request: RegisterProjectRequest):
    """
    ユーザーの入力からプロジェクトを登録し，対応するインデックスを作成．
    """
    try:
        # クライアントの初期化
        index_client = SearchIndexClient(azure_search_endpoint, AzureKeyCredential(azure_search_key))
        indexer_client = SearchIndexerClient(azure_search_endpoint, AzureKeyCredential(azure_search_key))

        project_name = request.project_name
        spo_url = request.spo_url

        #index, Skillset, datasource ,indexerの名前
        project_name = project_name.lower() #プロジェクト名を小文字に変換
        index_name = f"{project_name}-index"
        data_source_name = f"{project_name}-datasource"
        skillset_name = f"{project_name}-skillset"
        indexer_name = f"{project_name}-indexer"
    
        # インデックス名を取得してリストに保管
        indexs = []
        indexs = list(index_client.list_index_names())

        if index_name in indexs:
            # 既存インデックスの場合はインデクサーのみ実行
            logging.info(f"インデックス '{index_name}' は既に存在します。インデクサーのみ実行します。")
            indexer_client.run_indexer(indexer_name)  # インデクサーを実行
        else:
            # 新規インデックスを作成
            logging.info(f"新規インデックス '{index_name}' を作成します。")

            # Cosmos DB にプロジェクトを保存
            container.upsert_item({
                "id": str(uuid.uuid4()),  # 一意の ID を生成
                "project_name": project_name,
                "spo_url": spo_url
            })
                       
            # 非同期でdatasource作成
            await create_project_data_source(project_name, spo_url)

            # indexの作成
            index = create_project_index(project_name, spo_url)
            index_client.delete_index(index)
            index_client.create_or_update_index(index) # 指定したインデックス名が既存の場合上書きする

            # # Skillsetの作成
            # skillset = create_project_skillset(project_name, spo_url)
            # indexer_client.create_or_update_skillset(skillset)

            # 非同期でskillset作成
            await create_project_skillset(project_name, spo_url)

            # indexerの作成
            indexer = create_project_indexer(project_name, spo_url)
            indexer_client.create_or_update_indexer(indexer) 

        return JSONResponse(content={"message": "プロジェクト登録とインデックス作成成功"})
    except ResourceExistsError:
        logging.warning(f"インデックス '{project_name}' は既に存在します")
        return JSONResponse(content={"message": f"プロジェクト '{project_name}' 登録済み"})
    except Exception as e:
        logging.error(f"プロジェクト登録エラー: {e}")
        raise HTTPException(status_code=500, detail="プロジェクト登録中にエラーが発生しました")

@app.get("/projects", dependencies=[Security(azure_scheme)])
async def get_projects():
    """
    登録されたプロジェクト一覧を返すエンドポイント。
    """
    try:
        projects = list(container.read_all_items())
        return JSONResponse(content={"projects": projects})
    except Exception as e:
        logging.error(f"プロジェクト一覧取得エラー: {e}")
        raise HTTPException(status_code=500, detail="プロジェクト一覧の取得中にエラーが発生しました")

@app.post("/answer", dependencies=[Security(azure_scheme)])
async def answer(request: AnswerRequest):
    """
    質問に対する応答を生成し、フロントエンドに返す。
    """
    try:
        user_question = request.user_question
        project_name = request.project_name
        project_name = project_name.lower() #プロジェクト名を小文字に変換
        answer = generate_answer(user_question, project_name)       
        return JSONResponse(answer)
    except Exception as e:
        logging.error(f"Error generating answer: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate answer")

