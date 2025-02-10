import os
import logging
import requests
import ipdb

# LangChain / OpenAI 関連
import openai
from langchain.schema import Document
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain_community.vectorstores import AzureSearch
from langchain import hub
from langchain.schema import StrOutputParser
from langchain.schema.runnable import RunnablePassthrough, RunnableMap
from operator import itemgetter

# 環境変数等の取得
openai_embedding_key = os.getenv("AZURE_OPENAI_EMBEDDING_API_KEY")
openai_embedding_endpoint = os.getenv("AZURE_OPENAI_EMBEDDING_ENDPOINT")
azure_search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT") 
azure_search_key = os.getenv("AZURE_SEARCH_ADMIN_KEY")
openai.api_key = os.getenv("AZURE_OPENAI_API_KEY")
openai.azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
service_name = "srch-rag-dev-001"


def vector_search_with_filter(
    service_name: str, 
    index_name: str, 
    api_key: str, 
    user_query: str, 
    filter_condition: str, 
    vector_filter_mode: str = "preFilter",  # preFilter設定
    top: int = 3
):
    """
    REST API を直接呼び出して、ベクトル検索 + フィルターを実行し、
    ドキュメント (LangChain の Document) のリストを返す。
    """

    # 1. ユーザークエリをベクトル化 
    embedding_model = AzureOpenAIEmbeddings(
        azure_deployment="text-embedding-ada-002",
        openai_api_version="2023-05-15",
        openai_api_key=openai_embedding_key,
        azure_endpoint=openai_embedding_endpoint,
    )
    user_vector = embedding_model.embed_query(user_query)

    #  2. REST API 用 JSON ボディを構築 
    body = {
        "select": "folderName, content, documentUrl, documentName, last_modified", # 取得するフィールド名を指定する
        "filter": filter_condition,        # OData フィルター 
        "vectorFilterMode": vector_filter_mode,
        "vectorQueries": [
            {
                "kind": "vector",
                "fields": "content_vector",  # インデックスで定義したベクトルフィールド
                "vector": user_vector,
                "k": top
            }
        ]
    }

    url = f"https://{service_name}.search.windows.net/indexes/{index_name}/docs/search?api-version=2024-07-01"
    headers = {
        "Content-Type": "application/json",
        "api-key": api_key
    }

    # 3. リクエスト送信 
    response = requests.post(url, headers=headers, json=body)
    response.raise_for_status()

    # 4. 結果をパースして LangChain の Document に変換 
    result_json = response.json()
    docs = []
    for item in result_json.get("value", []):
        doc_content = item.get("content", "")
        metadata = {
            "documentUrl": item.get("documentUrl", ""),
            "documentName": item.get("documentName", ""),
            "last_modified": item.get("last_modified", ""),
            "folderName": item.get("folderName", "")
        }
        docs.append(Document(page_content=doc_content, metadata=metadata))

    return docs

def build_filter_condition(folder_name: str, subfolder_name: str) -> str | None:
    """
    folder_name と subfolder_name の組み合わせに応じて、
    OData フィルタ文字列 (folderName, subfolderName) を生成する。
    folder_name = "FOLDER_ALL" フィルタリングなし (None)
    それ以外の場合:
        subfolder_name = "SUBFOLDER_ALL" フォルダ名のみフィルタリング："folderName eq 'xxx'"
        subfolder_name != "SUBFOLDER_ALL" フォルダ名とサブフォルダ名でフィルタリング："folderName eq 'xxx' and subfolderName eq 'yyy'"
    """
    # folder_name が "FOLDER_ALL" の場合 
    if folder_name == "FOLDER_ALL":
        return None

    # folder_name が FOLDER_ALL 以外の場合
    if subfolder_name == "SUBFOLDER_ALL":
        # folderName のみフィルタリング
        return f"folderName eq '{folder_name}'"
    else:
        # folderName と subfolderName の両方でフィルタリング
        return f"folderName eq '{folder_name}' and subfolderName eq '{subfolder_name}'"

def generate_answer(user_question: str, project_name: str, folder_name: str=None, subfolder_name:str=None):
    """
    指定したプロジェクトに対して、フォルダ名でのフィルタリング機能を追加したベクトル検索を実行し、ユーザーの質問に対する回答を生成する 
    """
    try:
        index_name = f"{project_name}-index"
        # ipdb.set_trace()

        # 条件に応じてフィルタリングを構成
        filter_condition = build_filter_condition(folder_name, subfolder_name)
        # vectorFilterModeを用いてベクトル検索にfolderName, subfolderNameでのフィルタリングを追加
        retrieved_docs = vector_search_with_filter(
            service_name=service_name,
            index_name=index_name,
            api_key=azure_search_key,
            user_query=user_question,
            filter_condition=filter_condition,
            vector_filter_mode="preFilter",
            top=3
        )

        logging.info(f"retrieved_docs: {retrieved_docs}")

        # LLM の設定
        llm = AzureChatOpenAI(
            openai_api_key=openai.api_key,
            azure_endpoint=openai.azure_endpoint,
            openai_api_version="2024-08-01-preview",
            azure_deployment="gpt-4o",
            temperature=0,
        )

        # ドキュメント本文を結合
        def format_docs(docs):
            return "\n\n".join(
                doc.page_content if isinstance(doc, Document) else doc.get("content", "")
                for doc in docs
            )

        # メタデータ抽出
        def filter_metadata(docs):
            return [
                {
                    "documentUrl": doc.metadata.get("documentUrl"),
                    "documentName": doc.metadata.get("documentName"),
                    "last_modified": doc.metadata.get("last_modified"),
                }
                for doc in docs
            ]

        # RAG 用のプロンプトを取得
        prompt = hub.pull("rlm/rag-prompt")
        ipdb.set_trace()

        # RAG チェーン構築
        rag_chain_from_docs = (
            {
                "context": lambda input: format_docs(input["documents"]),
                "question": itemgetter("question"),
            }
            | prompt
            | llm
            | StrOutputParser()
        )

        # RAG チェーン実行
        rag_chain_with_source = RunnableMap(
            {
                "documents": lambda _: retrieved_docs,
                "question": lambda _: user_question
            }
        ) | {
            "documents": lambda input: filter_metadata(input["documents"]),
            "answer": rag_chain_from_docs,
        }

        # チェーン実行
        answer_data = rag_chain_with_source.invoke({})
        answer = answer_data["answer"]

        # 上位ドキュメントの情報をまとめる
        documents_info = answer_data["documents"]
        documentUrl_list, documentName_list, last_modified_list = [], [], []

        if documents_info:
            # 最初の1件を追加
            documentUrl_list.append(documents_info[0]["documentUrl"])
            documentName_list.append(documents_info[0]["documentName"])
            last_modified_list.append(documents_info[0]["last_modified"])

            # 以降、URL が重複しなければ追加
            for i in range(len(documents_info) - 1):
                if documents_info[i]["documentUrl"] != documents_info[i+1]["documentUrl"]:
                    documentUrl_list.append(documents_info[i+1]["documentUrl"])
                    documentName_list.append(documents_info[i+1]["documentName"])
                    last_modified_list.append(documents_info[i+1]["last_modified"])

        content = {
            "answer": answer,
            "documentUrl": documentUrl_list,
            "documentName": documentName_list,
            "last_modified": last_modified_list,
        }
        return content

    except Exception as e:
        logging.error(f"Error generating answer with prompt: {e}")
        raise


def generate_answer_all(user_question, container):
    """
    プロジェクト名が"ALL"の時、すべてのプロジェクトを検索対象としてベクトル検索を実行する。
    ベクトル検索の結果から、検索スコア上位3件をもとに、LLMを介して質問に対する回答を生成。
    """
    try:
        # クエリを実行して project_name を抽出
        project_names = []
        retrieved_docs_list = []
        query = "SELECT c.project_name FROM c"  # 必要なフィールドのみ取得
        for item in container.query_items(query=query, enable_cross_partition_query=True):
            project_names.append(item["project_name"])  # project_name をリストに追加
        
        # すべてプロジェクトに関してベクトル検索を実行
        for project_name in project_names:
            index_name = f"{project_name}-index"
            retriever = AzureSearch(
                azure_search_endpoint=azure_search_endpoint,
                azure_search_key=azure_search_key,
                index_name=index_name,
                embedding_function=AzureOpenAIEmbeddings(
                    azure_deployment="text-embedding-ada-002",
                    openai_api_version="2023-05-15",
                    openai_api_key=openai_embedding_key,
                    azure_endpoint=openai_embedding_endpoint,
                ).embed_query,
            ).as_retriever(search_type="similarity")

            retrieved_docs = retriever.get_relevant_documents(user_question)[:3]
            logging.info(f"retrieved_docs: {retrieved_docs}")

            # retrieved_docs の要素を展開して追加
            for doc in retrieved_docs:
                retrieved_docs_list.append(doc)

        # @search.score が大きい順に並べ替え
        retrieved_docs_list = sorted(
            retrieved_docs_list,
            key=lambda x: x.metadata.get('@search.score', 0),  # @search.score を基準にソート
            reverse=True  # 降順にソート
        )
        #検索結果を上位三件に絞る
        retrieved_docs_list = retrieved_docs_list[:3]
        logging.info(f"retrieved_docs sorted by @search.score: {retrieved_docs_list}")

        llm = AzureChatOpenAI(
            openai_api_key=openai.api_key,
            azure_endpoint=openai.azure_endpoint,
            openai_api_version="2024-08-01-preview",
            azure_deployment="gpt-4o",
            temperature=0,
        )

        # ベクトルストアから取り出したdocumentからpage_contentの内容だけを抽出し、連結.
        def format_docs(docs):
            return "\n\n".join(doc.page_content for doc in docs)
        
        # 必要なフィールドのみ抽出
        def filter_metadata(docs):
            return [
                {
                    "documentUrl": doc.metadata.get("documentUrl"),
                    "documentName": doc.metadata.get("documentName"),
                    "last_modified": doc.metadata.get("last_modified"),
                }
                for doc in docs
            ]
        
        # Use a prompt for RAG that is checked into the LangChain prompt hub (https://smith.langchain.com/hub/rlm/rag-prompt?organizationId=989ad331-949f-4bac-9694-660074a208a7)
        prompt = hub.pull("rlm/rag-prompt")
        
        rag_chain_from_docs = (
            {
                "context": lambda input: format_docs(input['documents']),
                "question": itemgetter("question"),
            }
            | prompt
            | llm
            | StrOutputParser()
        )

        rag_chain_with_source = RunnableMap(
            {"documents": retriever, "question": RunnablePassthrough()}
        ) | {
            "documents": lambda input: filter_metadata(input["documents"]),
            "answer": rag_chain_from_docs,
        }

        # 会話の回答生成
        #関連度の高い資料の情報も取得
        answer_data = rag_chain_with_source.invoke(user_question)
        answer = answer_data["answer"]
        documentUrl_list, documentName_list, last_modified_list = [], [], []

        #最も関連度の高い資料をリストに追加
        documentUrl_list.append(answer_data["documents"][0]["documentUrl"])
        documentName_list.append(answer_data["documents"][0]["documentName"])
        last_modified_list.append(answer_data["documents"][0]["last_modified"])

        for i in range(2):
            # 異なる関連ドキュメントが存在する場合はリストに追加
            if answer_data["documents"][i]["documentUrl"] != answer_data["documents"][i+1]["documentUrl"]:
                documentUrl_list.append(answer_data["documents"][i+1]["documentUrl"])
                documentName_list.append(answer_data["documents"][i+1]["documentName"])
                last_modified_list.append(answer_data["documents"][i+1]["last_modified"])
        
        content={
            "answer": answer,
            "documentUrl": documentUrl_list,
            "documentName": documentName_list,
            "last_modified": last_modified_list,
        }
        return content

    except Exception as e:
        logging.error(f"Error generating answer with prompt: {e}")
        raise