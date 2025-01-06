# Azure AIサービスを利用したRAG 
 
 
## 目次
 
1. [プロジェクト概要](#プロジェクト概要)
2. [前提条件](#前提条件)
3. [環境構築](#環境構築)
4. [使用方法](#使用方法)
 
 
 
## プロジェクト概要
 
RAG（Retrieval-Augmented Generation）は、事前に収集した大量のデータから関連する情報を抽出し、その情報を基にユーザーに適切な応答を生成する技術です。
このプロジェクトでは、AzureのAIサービスを活用し、アップロードされた画像やドキュメントからテキストを抽出して、それを検索ベースでリクエスト内容に関連する情報を返答する仕組みを構築しています。
複雑なレイアウトのPDFファイル等も、セマンティックチャンキング法により高精度に抽出することが可能です。
主な利用シナリオとしては、システム開発における要件定義書や設計書といった資料を取り扱い、これらから必要な情報を素早く引き出せる点が挙げられます。
 
 
 
## 前提条件
 
このプロジェクトを動かすために必要なツールやリソース
 
- **Azure サブスクリプション**
- **Azure Functions Core Tools**
- **Azure Document Intelligence**
- **Azure AI Search**
- **Azure OpenAI**
- **Python 3.10**
- **VSCode**
- **Azure CLI**
 
 
 
## 環境構築
 
```
git clone git@gitlab.com:intelligentforce/azure_rag.git
cd azure_rag
```
 
### 仮想環境の構築と必要なライブラリのインストール
 
```
pyenv local 3.10.15
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
 
### local_settings.jsonで環境変数の設定
それぞれのバリューには適切なものを入力してください
```
{
    "IsEncrypted": false,
    "Values": {
      "AzureWebJobsStorage": "seDevelopmentStorage=true",
      "FUNCTIONS_WORKER_RUNTIME": "python",
      "AZURE_OPENAI_API_KEY":"Your AZURE_OPENAI_API_KEY",
      "AZURE_OPENAI_ENDPOINT":"Your AZURE_OPENAI_ENDPOINT",
      "AZURE_OPENAI_EMBEDDING_API_KEY":"Your AZURE_OPENAI_EMBEDDING_API_KEY",
      "AZURE_OPENAI_EMBEDDING_ENDPOINT":"Your AZURE_OPENAI_EMBEDDING_ENDPOINT",
      "DOCUMENT_INTELLIGENCE_API_KEY":"Your DOCUMENT_INTELLIGENCE_API_KEY",
      "DOCUMENT_INTELLIGENCE_ENDPOINT":"Your DOCUMENT_INTELLIGENCE_ENDPOINT",
      "AZURE_SEARCH_ENDPOINT":"Your AZURE_SEARCH_ENDPOINT",
      "AZURE_SEARCH_ADMIN_KEY":"Your AZURE_SEARCH_ADMIN_KEY"
    },
    "Host": {
      "CORS": "*"
    }
}
```
 
 
 
## 使用方法
 
```
cd rag_api
func start
```
 
上記のコマンドの実行でバックエンドサーバーを立ち上げます。<br>

```
cd ..
cd rag_cliant
npm start
``` 
上記のコマンドの実行でフロントエンドサーバーを立ち上げます。<br>


UIを操作しフィルのアップロードを行う．
"メッセージを入力"の欄から質問を入力すると，アップロードしたファイルの内容を検索して適切な回答が返ってくる．