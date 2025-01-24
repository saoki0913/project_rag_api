import msal
import requests
from pathlib import Path
import json
from functools import cache
import pprint as pp
import ipdb

class SharePointAccessClass:
    # 初期化
    def __init__(self, client_id, client_secret, tenant_id):
        """
        Initialize the SharePointAccessClass
        """
        self.client_id = client_id # アプリケーション(クライアント)ID
        self.client_secret = client_secret # シークレット(値)
        self.tenant_id = tenant_id # ディレクトリ(テナント)ID
        self.authority = f"https://login.microsoftonline.com/{tenant_id}" 
        self.scope = ["https://graph.microsoft.com/.default"]
        self.access_token: None | str = None
        self.get_access_token()


    # Access Tokenを取得する
    def get_access_token(self):
        """
        Get the access token using the client_id, client_secret, and tenant_id
        """
        # Create a confidential client application using msal library
        """msalを使用してアクセストークンを取得します"""
        app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=self.authority,
            client_credential=self.client_secret
        )
        result = app.acquire_token_for_client(scopes=self.scope)
        if "access_token" in result:
            # Save the access token
            self.access_token = result["access_token"]
        else:
            raise Exception("No access token available")
    
    # Graph APIを使用してデータを取得する汎用GETメソッド
    @cache
    def graph_api_get(self, endpoint: str) -> requests.models.Response | None:
        """
        Get data from Graph API using the endpoint
        """
        if self.access_token is not None:
            graph_data = requests.get(
                endpoint,
                headers={'Authorization': 'Bearer ' + self.access_token})
            return graph_data
        else:
            raise Exception("No access token available")
        
        # Graph APIを使用してデータを送信する汎用PUTメソッド
    def graph_api_put(self, endpoint: str, data) -> requests.models.Response | None:
        """
        Post data to Graph API using the endpoint
        """
        if self.access_token is not None:
            graph_data = requests.put(
                url=endpoint,
                headers={'Authorization': 'Bearer ' + self.access_token},
                data=data)
            return graph_data
        else:
            raise Exception("No access token available")


    # Graph APIを使用してデータを削除する汎用DELETEメソッド
    def graph_api_delete(self, endpoint: str) -> requests.models.Response | None:
        """
        Delete data from Graph API using the endpoint
        """
        if self.access_token is not None:
            graph_data = requests.delete(
                endpoint,
                headers={'Authorization': 'Bearer ' + self.access_token})
            return graph_data
        else:
            raise Exception("No access token available")

    # Graph APIを使用してデータを送信する汎用POSTメソッド
    def graph_api_post(self, endpoint: str, data) -> requests.models.Response | None:
        """
        Post data to Graph API using the endpoint
        """
        if self.access_token is not None:
            graph_data = requests.post(
                url=endpoint,
                headers={'Authorization': 'Bearer ' + self.access_token},
                json=data)  # Use json parameter instead of data for POST requests
            return graph_data
        else:
            raise Exception("No access token available")
        

    # サイト一覧を取得する
    def get_sites(self):
        """
        Get Sites in SharePoint
        """
        print("Get Sites in SharePoint")
        endpoints = self.graph_api_get("https://graph.microsoft.com/v1.0/sites")
        # print(endpoints.json())
        return endpoints.json()


    # サイト名からサイトIDを取得する
    def get_site_id(self, site_name):
        """
        Get Site_id  using the site_name
        """
        print(f"Get Site_id using the site_name: {site_name}")
        sites = self.get_sites()
        for site in sites['value']:
            if site['name'] == site_name:
                print(f"site: {site}")
                return site['id']
        return None


    # サイトIDからサイトのフォルダを全て取得する
    def get_folders(self, site_id, folder_id='root'):
        print(f"Get Subfolders in a folder using the folder_id: {folder_id}")
        folders = self.graph_api_get(
            f'https://graph.microsoft.com/v1.0/sites/{site_id}/drive/items/{folder_id}/children')
        if folders is not None:
            return folders.json()
        else:
            return None


    # サイトIDからサイトのフォルダIdを取得する
    def get_folder_id(self, site_id, folder_name, folder_id='root'):
        folders = self.get_folders(site_id, folder_id)
        for folder in folders['value']:
            if folder_name == folder["name"]:
                return folder['id']
        return None


    # サイトIDからサイトのフォルダを取得する
    def get_folder(self, site_id, folder_name, folder_id='root'):
        subfolders = self.get_folders(site_id, folder_id)
        for folder in subfolders['value']:
            if folder_name == folder["name"]:
                return folder
        return None


    # 指定されたサイトIDのサイトから、指定されたディレクトリツリーの最下層のフォルダIDを取得する
    def get_folder_id_from_tree(self, site_id, sharepoint_directories, folder_id='root'):
        # 各ディレクトリを上から順に表示
        for directory in sharepoint_directories:
            print(f"folder_name:= {directory}")
            folder_id = self.get_folder_id(site_id, directory, folder_id)

        print(f"folder_id: {folder_id}")
        return folder_id

    # SharePoint上のフォルダの作成
    def create_folder(self, target_site_name, sharepoint_directory, folder_name):
        """
        Create a folder in SharePoint using the target_site_name, sharepoint_directory, and folder_name
        """
        print("Creating folder...")
        # ターゲットサイトのIDを取得
        target_site_id = self.get_site_id(target_site_name)
        # フォルダIDを取得
        folder_id = self.get_folder_id_from_tree(target_site_id, sharepoint_directory, 'root')

        if folder_id:
            url = f'https://graph.microsoft.com/v1.0/sites/{target_site_id}/drive/items/{folder_id}/children'

            # フォルダを作成
            data = {
                "name": folder_name,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "rename"
            }
            graph_data = self.graph_api_post(url, data).json()
            return graph_data
        else:
            return "Folder not found"
            
        
    # SharePoint上のフォルダの削除
    def delete_folder(self, target_site_name, sharepoint_directory, folder_name):
        """
        Delete a folder in SharePoint using the target_site_name, sharepoint_directory, and folder_name
        """
        print("Deleting folder...")
        # ターゲットサイトのIDを取得
        target_site_id = self.get_site_id(target_site_name)
        # フォルダIDを取得
        folder_id = self.get_folder_id_from_tree(target_site_id, sharepoint_directory, 'root')

        if folder_id:
            # フォルダを削除するためのURLは、/contentではなく、/items/{item-id}の形式である必要があります
            url = f'https://graph.microsoft.com/v1.0/sites/{target_site_id}/drive/items/{folder_id}:/{folder_name}'

            # フォルダの削除
            graph_data = self.graph_api_delete(url)
            if graph_data.status_code == 204:
                print("Folder deleted successfully")
            else:
                print(f"Failed to delete folder: {graph_data.status_code}")
            return graph_data
        else:
            return "Folder not found"
        
    # SharePoint上の指定フォルダ内の一覧取得
    def get_items_in_the_folder(self, target_site_name, sharepoint_directory):
        """
        Get Files in SharePoint using the target_site_name, sharepoint_directory
        """
        print("Get Files in SharePoint")
        # ターゲットサイトのIDを取得
        target_site_id = self.get_site_id(target_site_name)
        # フォルダIDを取得
        folder_id = self.get_folder_id_from_tree(target_site_id, sharepoint_directory, 'root')
       

        if folder_id:
            items = self.graph_api_get(
                f'https://graph.microsoft.com/v1.0/sites/{target_site_id}/drive/items/{folder_id}/children')
            if items is not None:
                return items.json()
            else:
                return None
        else:
            return "Folder not found"

    # SharePoint上の指定フォルダのサブフォルダ一覧を取得する
    def get_subfolders_in_folder(self, target_site_name, folder_name):
        """
        Get subfolders in a specified folder on SharePoint.
        
        Parameters:
            target_site_name (str): The name of the SharePoint site.
            sharepoint_directory (list[str]): A list of folder names representing the path 
                                            to the target folder in SharePoint.
            
        Returns:
            list[dict]: A list of dictionary objects representing each subfolder's metadata.
                        If the folder doesn't exist or has no subfolders, returns an empty list.
        """
        print("Get subfolders in the specified folder in SharePoint")

        # 1. ターゲットサイトIDを取得
        site_id = self.get_site_id(target_site_name)
        if not site_id:
            print(f"Site '{target_site_name}' not found.")
            return []

        # 2. 指定ディレクトリ内のフォルダIDを取得
        folder_id = self.get_folder_id(site_id, folder_name, 'root')
        if not folder_id:
            print("Specified folder not found.")
            return []

        # 3. フォルダ内の子アイテム一覧を取得
        children_endpoint = f'https://graph.microsoft.com/v1.0/sites/{site_id}/drive/items/{folder_id}/children'
        response = self.graph_api_get(children_endpoint)
        if response is None or response.status_code != 200:
            print("Failed to get children from the specified folder.")
            return []

        items_json = response.json()
        if "value" not in items_json:
            return []

        # 4. フォルダ(`folder`キーを持つアイテム)だけを抽出して返す
        subfolders = []
        for item in items_json["value"]:
            # driveItemに folder プロパティがある場合、それはサブフォルダ
            if "folder" in item:
                subfolder = item["name"]
                subfolders.append(subfolder)

        return subfolders
    
    # SharePoint上の指定フォルダの詳細情報取得
    def get_folder_details(self, target_site_name, sharepoint_directory):
        """
        Get Folder Details in SharePoint using the target_site_name, sharepoint_directory
        """
        print("Get Folder Details in SharePoint")
        # ターゲットサイトのIDを取得
        target_site_id = self.get_site_id(target_site_name)
        # フォルダIDを取得
        folder_id = self.get_folder_id_from_tree(target_site_id, sharepoint_directory, 'root')

        if folder_id:
            folder_details = self.graph_api_get(
                f'https://graph.microsoft.com/v1.0/sites/{target_site_id}/drive/items/{folder_id}')
            if folder_details is not None:
                return folder_details.json()
            else:
                return None
        else:
            return "Folder not found"

    # ファイルのアップロード
    def upload_file(self, target_site_name, sharepoint_directory, object_file_path):
        """
        Upload a file to SharePoint using the target_site_name, sharepoint_directory, and object_file_path
        """
        print("Uploading file...")

        # ターゲットサイトのIDを取得
        target_site_id = self.get_site_id(target_site_name)
        # フォルダIDを取得
        folder_id = self.get_folder_id_from_tree(target_site_id, sharepoint_directory, 'root')

        if folder_id:
            # アップロードURLを作成
            url = f'https://graph.microsoft.com/v1.0/sites/{target_site_id}/drive/items/{folder_id}:/{object_file_path.name}:/content'
            # ファイルをアップロード
            with open(object_file_path, 'rb') as f:
                graph_data = self.graph_api_put(url, f)

            # アップロード結果を返す
            return graph_data.json()
        else:
            return "Folder not found"

    # SharePointのファイルのダウンロード
    def download_file(self, target_site_name, sharepoint_directory, object_file_name, download_dir):
        """
        Download a file from SharePoint using the target_site_name, sharepoint_directory, and object_file_path
        """
        print("Downloading file...")
        # ターゲットサイトのIDを取得
        target_site_id = self.get_site_id(target_site_name)
        # フォルダIDを取得
        folder_id = self.get_folder_id_from_tree(target_site_id, sharepoint_directory, 'root')

        if folder_id:
            # ダウンロードURLを作成
            url = f'https://graph.microsoft.com/v1.0/sites/{target_site_id}/drive/items/{folder_id}:/{object_file_name}:/content'

            # ファイルをダウンロード
            graph_data = self.graph_api_get(url)

            # ファイルを保存
            download_file_path = Path(download_dir).joinpath(object_file_name)
            if graph_data.status_code == 200 and graph_data.content:
                with open(download_file_path, 'wb') as f:
                    f.write(graph_data.content)
                return download_file_path
            else:
                return "File not found"
        else:
            return "Folder not found"

    def read_file(self, target_site_name, sharepoint_directory, object_file_name):
        """
        Read a file from SharePoint using the target_site_name, sharepoint_directory, and object_file_path
        """
        print("Reading file...")
        # ターゲットサイトのIDを取得
        target_site_id = self.get_site_id(target_site_name)
        # フォルダIDを取得
        folder_id = self.get_folder_id_from_tree(target_site_id, sharepoint_directory, 'root')

        if folder_id:
            url = f'https://graph.microsoft.com/v1.0/sites/{target_site_id}/drive/items/{folder_id}:/{object_file_name}:/content'

            # ファイルの読み込み
            graph_data = self.graph_api_get(url)

            # ファイルを保存
            if graph_data.status_code == 200 and graph_data.content:
                return graph_data.content
            else:
                return "File not found"
        else:
            return "Folder not found"


    # SharePoint上のファイルの削除
    def delete_file(self, target_site_name, sharepoint_directory, object_file_name):
        """
        Delete a file from SharePoint using the target_site_name, sharepoint_directory, and object_file_path
        """
        print("Deleting file...")
        # ターゲットサイトのIDを取得
        target_site_id = self.get_site_id(target_site_name)
        # フォルダIDを取得
        folder_id = self.get_folder_id_from_tree(target_site_id, sharepoint_directory, 'root')

        if folder_id:
            url = f'https://graph.microsoft.com/v1.0/sites/{target_site_id}/drive/items/{folder_id}:/{object_file_name}'

            # ファイルの削除
            graph_data = self.graph_api_delete(url)
            if graph_data.status_code == 204:
                print("File deleted successfully")
            else:
                print(f"Failed to delete file: {graph_data.status_code}")
            return graph_data
        else:
            return "Folder not found"
