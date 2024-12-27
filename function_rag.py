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
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes import SearchIndexerClient
from azure.cosmos import CosmosClient, exceptions
import ipdb

#import mylibraly
from create_index import create_project_index
from create_skillset_documentintelligence import create_project_skillset
from create_indexer import create_project_indexer
from create_datasource import create_project_data_source
from generate_answer import generate_answer
from generate_answer_all import generate_answer_all
from utils import check_spo_url

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


# FastAPI アプリケーションの初期化
app = FastAPI()

# リクエストボディのスキーマ定義
class AnswerRequest(BaseModel):
    user_question: str
    project_name: str
    conversation_id: str = None  # オプション項目（指定がない場合はNone）

class RegisterProjectRequest(BaseModel):
    project_name: str
    spo_url: str

class DeleteProjectRequest(BaseModel):
    project_name: str

# クライアントの初期化
index_client = SearchIndexClient(azure_search_endpoint, AzureKeyCredential(azure_search_key))
indexer_client = SearchIndexerClient(azure_search_endpoint, AzureKeyCredential(azure_search_key))

# Cosmos DB クライアントの初期化
cosmos_client = CosmosClient(cosmos_endpoint, cosmos_key)
database = cosmos_client.get_database_client(cosmos_database_name)
container = database.get_container_client(cosmos_container_name)


@app.post("/resist_project")
async def resist_project(request: RegisterProjectRequest):
    """
    ユーザーの入力からプロジェクトを登録し，対応するインデックスを作成．
    """
    try:
        project_name = request.project_name
        spo_url = request.spo_url
        spo_url = await check_spo_url(spo_url)

        #index, indexerの名前
        project_name = project_name.lower() #プロジェクト名を小文字に変換
        index_name = f"{project_name}-index"
        indexer_name = f"{project_name}-indexer"
    
        # インデックス名を取得してリストに保管
        indexs = []
        indexs = list(index_client.list_index_names())

        if index_name in indexs:
            # 既存インデックスの場合はインデクサーのみ実行
            logging.warning(f"インデックス '{index_name}' は既に存在します。インデクサーのみ実行します。")
            indexer_client.run_indexer(indexer_name)  # インデクサーを実行
        else:
            # 新規インデックスを作成
            logging.info(f"新規インデックス '{index_name}' を作成します。")
           
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

            # Cosmos DB にプロジェクトを保存
            container.upsert_item({
                "id": str(uuid.uuid4()),  # 一意の ID を生成
                "project_name": project_name,
                "spo_url": spo_url
            }) 

        logging.info("プロジェクト登録とインデックス作成に成功しました")
        return JSONResponse(content={"message": "プロジェクト登録とインデックス作成成功"})
    
    except ResourceExistsError:
        logging.warning(f"インデックス '{project_name}' は既に存在します")
        return JSONResponse(content={"message": f"プロジェクト '{project_name}' 登録済み"})
    except Exception as e:
        logging.error(f"プロジェクト登録エラー: {e}")
        raise HTTPException(status_code=500, detail="プロジェクト登録中にエラーが発生しました")

@app.get("/projects")
async def get_projects():
    """
    登録されたプロジェクト一覧を返すエンドポイント。
    """
    try:
        projects = list(container.read_all_items())
        logging.info("プロジェクトの取得に成功しました")
        return JSONResponse(content={"projects": projects})
    except Exception as e:
        logging.error(f"プロジェクト一覧取得エラー: {e}")
        raise HTTPException(status_code=500, detail="プロジェクト一覧の取得中にエラーが発生しました")
    
@app.delete("/delete_project")
async def delete_item_by_project_name(request:DeleteProjectRequest):
    """
    指定された project_name に基づいてアイテムを削除するエンドポイント.
    """
    try:
        project_name = request.project_name
        project_name = project_name.lower() #プロジェクト名を小文字に変換

        #index, Skillset, datasource ,indexerの名前
        index_name = f"{project_name}-index"
        data_source_name = f"{project_name}-datasource"
        skillset_name = f"{project_name}-skillset"
        indexer_name = f"{project_name}-indexer"
    
        #index, Skillset, datasource ,indexerの削除
        indexer_client.delete_indexer(indexer_name)
        indexer_client.delete_skillset(skillset_name)
        indexer_client.delete_data_source_connection(data_source_name)
        index_client.delete_index(index_name)

        # クエリで project_name に一致するアイテムを検索
        query = "SELECT * FROM Projects p WHERE p.project_name = @project_name"
        parameters = [{"name": "@project_name", "value": project_name}]
        item = list(container.query_items(query=query, parameters=parameters, enable_cross_partition_query=True))
        if not item:
            logging.warning(f"'{project_name}' に一致するプロジェクトが見つかりません。")
            return

        # 検索結果からアイテムを削除   
        container.delete_item(item=item[0]["id"], partition_key=item[0]["project_name"])
        logging.info(f"プロジェクト '{project_name}' を削除しました。")

    except exceptions.CosmosHttpResponseError as e:
        logging.error(f"プロジェクト削除エラー: {e}")
    except Exception as ex:
        print(f"プロジェクト削除中に予期せぬエラーが発生しました: {ex}")

@app.post("/answer")
async def answer(request: AnswerRequest):
    """
    質問に対する応答を生成し、フロントエンドに返す。
    """
    try:
        user_question = request.user_question
        project_name = request.project_name
        project_name = project_name.lower() #プロジェクト名を小文字に変換

        # プロジェクトが選択されていないときはすべてのプロジェクトを検索して回答する．
        if project_name == "all":
            answer = generate_answer_all(user_question, container)
        else:
            answer = generate_answer(user_question, project_name)
        logging.info("質問への回答に成功しました")       
        return JSONResponse(answer)
    
    except Exception as e:
        logging.error(f"回答生成エラー: {e}")
        raise HTTPException(status_code=500, detail="回答の生成に失敗")

