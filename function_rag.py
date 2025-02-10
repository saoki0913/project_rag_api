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

#import mylibraly
from generate_answer import generate_answer, generate_answer_all
from utils import check_spo_url, get_spo_url_by_project_name, get_site_info_by_url, fetch_folders, delete_project_resources, fetch_subfolders
from SharePoint import SharePointAccessClass
from indexing_service import ProjectIndexingService

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
# SPO
client_id = os.getenv("SPO_APPLICATION_ID")
client_secret = os.getenv("SPO_APPLICATION_SECRET")
tenant_id = os.getenv("SPO_TENANT_ID")

# SPOクラスの初期化
sharepoint = SharePointAccessClass(client_id, client_secret, tenant_id)

# indexingクラスの初期化
search_indexing = ProjectIndexingService()

# FastAPI アプリケーションの初期化
app = FastAPI()

# リクエストボディのスキーマ定義
class AnswerRequest(BaseModel):
    user_question: str
    project_name: str
    folder_name:str = None  # オプション項目（指定がない場合はNone）
    subfolder_name:str = None  # オプション項目（指定がない場合はNone）
    conversation_id: str = None  # オプション項目（指定がない場合はNone）

class RegisterProjectRequest(BaseModel):
    project_name: str
    spo_url: str
    include_root_files:bool

class DeleteProjectRequest(BaseModel):
    project_name: str

class GetSpoFoldersRequest(BaseModel):
    project_name: str

class GetSpoSubFoldersRequest(BaseModel):
    project_name: str
    folder_name: str

# クライアントの初期化
index_client = SearchIndexClient(azure_search_endpoint, AzureKeyCredential(azure_search_key))
indexer_client = SearchIndexerClient(azure_search_endpoint, AzureKeyCredential(azure_search_key))

# Cosmos DB クライアントの初期化
cosmos_client = CosmosClient(cosmos_endpoint, cosmos_key)
database = cosmos_client.get_database_client(cosmos_database_name)
container = database.get_container_client(cosmos_container_name)

@app.post("/get_spo_folders")
async def get_spo_folders(request:GetSpoFoldersRequest):
    """
    SPOのURLから、それに対応したサイト名を検索し、そのサイト内のフォルダ一覧を返すエンドポイント。
    """
    try:
        # サイトIDを取得
        project_name = request.project_name
        spo_url = await get_spo_url_by_project_name(project_name)
        sites_data = sharepoint.get_sites()

        # サイト一覧から 'webUrl' が target_url に一致するサイトを検索
        matching_site = get_site_info_by_url(sites_data, spo_url)
        site_name = matching_site["name"]
        site_id = sharepoint.get_site_id(site_name)

        logging.info(f"サイト '{site_name}' のIDを取得しました")
        if not site_id:
            logging.error(f"サイト '{site_name}' が見つかりませんでした")
            raise HTTPException(status_code=404, detail=f"サイト '{site_name}' が見つかりませんでした")       

        # フォルダ一覧を取得
        root_folder="root"
        folder_list = fetch_folders(sharepoint, site_id, root_folder)

        return JSONResponse(content={"folders": folder_list})
    
    except Exception as e:
        logging.error(f"フォルダ一覧取得エラー: {e}")
        raise HTTPException(status_code=500, detail="フォルダ一覧の取得中にエラーが発生しました")

@app.post("/get_spo_subfolders")
async def get_spo_subfolders(request:GetSpoSubFoldersRequest):
    """
    SPOのURLから、それに対応したサイト名を検索し、そのサイト内のフォルダ一覧を返すエンドポイント。
    """
    try:
        # サイトIDを取得
        project_name = request.project_name
        folder_name = request.folder_name
        spo_url = await get_spo_url_by_project_name(project_name)
        sites_data = sharepoint.get_sites()

        # サイト一覧から 'webUrl' が target_url に一致するサイトを検索
        matching_site = get_site_info_by_url(sites_data, spo_url)
        site_name = matching_site["name"]
        subfolder_list = sharepoint.get_subfolders_in_folder(site_name, folder_name)
        return JSONResponse(content={"subfolders": subfolder_list})
    
    except Exception as e:
        logging.error(f"フォルダ一覧取得エラー: {e}")
        raise HTTPException(status_code=500, detail="フォルダ一覧の取得中にエラーが発生しました")   
    

@app.post("/resist_project")
async def resist_project(request: RegisterProjectRequest):
    """
    ユーザーの入力からプロジェクトを登録し，対応するインデックスを作成．
    """
    try:
        project_name = request.project_name
        spo_url = request.spo_url
        include_root_files = request.include_root_files
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
            await search_indexing.create_project_data_source(project_name, spo_url)

            # indexの作成
            index = search_indexing.create_project_index(project_name)
            index_client.delete_index(index)
            index_client.create_or_update_index(index) # 指定したインデックス名が既存の場合上書きする

            # # Skillsetの作成
            # skillset = create_project_skillset(project_name, spo_url)
            # indexer_client.create_or_update_skillset(skillset)

            # 非同期でskillset作成
            await search_indexing.create_project_skillset_layout(project_name)

            # indexerの作成
            if include_root_files == True:
                indexer = search_indexing.create_project_indexer(project_name)
            else:
                indexer = search_indexing.create_project_folder_indexer(project_name)
            
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
        # 登録エラーが発生した場合には、プロジェクトに関する要素をすべて削除する
        delete_project_resources(
                project_name,
                indexer_client,
                index_client,
                container
            )
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
        delete_project_resources(
                project_name,
                indexer_client,
                index_client,
                container
            )

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
        folder_name = request.folder_name
        subfolder_name = request.subfolder_name
        project_name = project_name.lower() #プロジェクト名を小文字に変換

        # プロジェクトが選択されていないときはすべてのプロジェクトを検索して回答する．
        if project_name == "project_all":
            answer = generate_answer_all(user_question, container)
        else:
            answer = generate_answer(user_question, project_name, folder_name, subfolder_name)
        logging.info("質問への回答に成功しました")       
        return JSONResponse(answer)
    
    except Exception as e:
        logging.error(f"回答生成エラー: {e}")
        raise HTTPException(status_code=500, detail="回答の生成に失敗")


