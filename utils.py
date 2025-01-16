from azure.cosmos import CosmosClient, exceptions
import os

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
        # 想定以降の文字列を抽出
        remaining_part = input_url[len(teams_pattern):]   
        # プロジェクト名部分だけを抽出（"/"が含まれる場合、それ以降を切り捨てる）
        project_name = remaining_part.split("/")[0]   
        # 正規化されたURLを返す
        return f"{teams_pattern}{project_name}"

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
