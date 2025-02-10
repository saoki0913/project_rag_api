from azure.cosmos import CosmosClient
import os
import logging
from SharePoint import SharePointAccessClass

# 環境変数から設定を取得
cosmos_endpoint = os.getenv("COSMOS_DB_ENDPOINT")
cosmos_key = os.getenv("COSMOS_DB_KEY")
cosmos_database_name = "ProjectDatabase"
cosmos_container_name = "Projects"
client_id = os.getenv("SPO_APPLICATION_ID")
client_secret = os.getenv("SPO_APPLICATION_SECRET")
tenant_id = os.getenv("SPO_TENANT_ID")

# Cosmos DB クライアントの初期化
cosmos_client = CosmosClient(cosmos_endpoint, cosmos_key)
database = cosmos_client.get_database_client(cosmos_database_name)
container = database.get_container_client(cosmos_container_name)

# SPOクラスの初期化
sharepoint = SharePointAccessClass(client_id, client_secret, tenant_id)

async def check_spo_url(input_url: str) -> str:
    """
    入力されたSPOのURLを想定される形式に修正する。

    Args:
        input_url (str): ユーザーからの入力URL。

    Returns:
        str: 修正されたURL（想定している形式に修正）。
    """
    # 想定しているSPO URLの基本形式
    spo_pattern = r"https://intelligentforce0401.sharepoint.com/sites/"
    teams_pattern = r"https://intelligentforce0401.sharepoint.com/:f:/r/sites/"
    # https://intelligentforce0401.sharepoint.com/:f:/r/sites/AI/
    
    # 入力が想定している形式で始まるかチェック
    if input_url.startswith(spo_pattern):
        # 想定以降の文字列を抽出
        remaining_part = input_url[len(spo_pattern):]
        # プロジェクト名部分だけを抽出（"/"が含まれる場合、それ以降を切り捨てる）
        project_name = remaining_part.split("/")[0]
        # 正規化されたURLを返す
        return f"{spo_pattern}{project_name}"
    
    elif input_url.startswith(teams_pattern):
        remaining_part = input_url[len(teams_pattern):]   
        project_name = remaining_part.split("/")[0]   
        return f"{spo_pattern}{project_name}"

    else:
        # 想定外の入力の場合は空文字列やエラーを返す
        return "Invalid SPO URL"
    

async def get_spo_url_by_project_name(project_name):
    """
    指定された project_name に一致する spo_url を取得する
    """
    try:
        # クエリを作成
        query = "SELECT c.spo_url FROM c WHERE c.project_name = @project_name"
        parameters = [{"name": "@project_name", "value": project_name.lower()}]  # 小文字で一致させる
        
        # クエリを実行
        results = list(container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True  # パーティションキーをまたぐクエリを許可
        ))

        # 結果を確認
        if results:
            spo_url = results[0].get("spo_url", "").strip()  # 最初の結果の spo_url を取得
            print(f"Found spo_url: {spo_url}")
            return spo_url
        else:
            print(f"No project found with name: {project_name}")
            return None
    except Exception as e:
        print(f"Error while fetching spo_url: {e}")
        return None

def get_site_info_by_url(sites_data, spo_url):
    return next((site for site in sites_data.get("value", []) if site.get("webUrl") == spo_url), None)

def fetch_folders(sharepoint, site_id, root_folder):
    """
    指定されたSharePointサイトのフォルダ一覧を取得する。

    Args:
        sharepoint (SharePointAccessClass): SharePointアクセスクラスのインスタンス。
        site_id (str): 対象のSharePointサイトのID。
        root_folder (str): フォルダ階層の開始ポイント（デフォルトは"root"）。

    Returns:
        list: フォルダ名のリスト。

    Raises:
        Exception: フォルダの取得中にエラーが発生した場合。
    """
    try:
        folder_list = []
        folders = sharepoint.get_folders(site_id, root_folder)  # 指定フォルダ以下を取得
        if folders and "value" in folders:
            folder_list = [folder['name'] for folder in folders["value"]]
            logging.info(f"フォルダ一覧取得成功: {folder_list}")
        else:
            logging.warning("フォルダが見つかりませんでした")

        return folder_list

    except Exception as e:
        logging.error(f"フォルダ一覧取得エラー: {e}")
        raise

def fetch_subfolders(sharepoint, site_id, root_folder):
    """
    指定されたSharePointサイトのフォルダ一覧を取得する。

    Args:
        sharepoint (SharePointAccessClass): SharePointアクセスクラスのインスタンス。
        site_id (str): 対象のSharePointサイトのID。
        root_folder (str): フォルダ階層の開始ポイント（デフォルトは"root"）。

    Returns:
        list: フォルダ名のリスト。

    Raises:
        Exception: フォルダの取得中にエラーが発生した場合。
    """
    try:
        folder_list = []
        folders = sharepoint.get_folders(site_id, root_folder)  # 指定フォルダ以下を取得
        if folders and "value" in folders:
            folder_list = [folder['name'] for folder in folders["value"]]
            logging.info(f"フォルダ一覧取得成功: {folder_list}")
        else:
            logging.warning("フォルダが見つかりませんでした")

        return folder_list

    except Exception as e:
        logging.error(f"フォルダ一覧取得エラー: {e}")
        raise

def delete_project_resources(
    project_name: str,
    indexer_client,
    index_client,
    container
):
    """
    指定した project_name に関連する Azure Cognitive Search の
    Index, Skillset, Data Source, Indexer と Cosmos DB のアイテムを削除します。

    Parameters
    ----------
    project_name : str
        削除対象プロジェクトの名前。
    indexer_client : 
        Azure Search Indexer クライアント。
    index_client :
        Azure Search Index クライアント。
    container :
        Cosmos DB コンテナーオブジェクト。
    """
    # プロジェクト名を小文字に変換
    project_name = project_name.lower()

    # index, Skillset, datasource ,indexer の名前を組み立て
    index_name = f"{project_name}-index"
    data_source_name = f"{project_name}-datasource"
    skillset_name = f"{project_name}-skillset"
    indexer_name = f"{project_name}-indexer"

    # indexer, skillset, datasource, index の削除
    try:
        indexer_client.delete_indexer(indexer_name)
        logging.info(f"Deleted indexer '{indexer_name}'.")
    except Exception as e:
        logging.warning(f"Failed to delete indexer '{indexer_name}': {e}")

    try:
        indexer_client.delete_skillset(skillset_name)
        logging.info(f"Deleted skillset '{skillset_name}'.")
    except Exception as e:
        logging.warning(f"Failed to delete skillset '{skillset_name}': {e}")

    try:
        indexer_client.delete_data_source_connection(data_source_name)
        logging.info(f"Deleted data source '{data_source_name}'.")
    except Exception as e:
        logging.warning(f"Failed to delete data source '{data_source_name}': {e}")

    try:
        index_client.delete_index(index_name)
        logging.info(f"Deleted index '{index_name}'.")
    except Exception as e:
        logging.warning(f"Failed to delete index '{index_name}': {e}")

    # クエリで project_name に一致するアイテムを検索
    query = "SELECT * FROM Projects p WHERE p.project_name = @project_name"
    parameters = [{"name": "@project_name", "value": project_name}]

    items = list(container.query_items(
        query=query,
        parameters=parameters,
        enable_cross_partition_query=True
    ))

    # 一致するアイテムがなければ警告ログ
    if not items:
        logging.warning(f"'{project_name}' に一致するプロジェクトが見つかりません。")
        return

    # 検索結果からアイテムを削除
    try:
        container.delete_item(
            item=items[0]["id"],
            partition_key=items[0]["project_name"]
        )
        logging.info(f"プロジェクト '{project_name}' を削除しました。")
    except Exception as e:
        logging.error(f"Failed to delete project '{project_name}' from Cosmos DB: {e}")
