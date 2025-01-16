import os
import logging
import requests

# LangChain / OpenAI 関連
import openai
from langchain.schema import Document
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
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


def generate_answer(user_question: str, project_name: str, folder_name: str=None):
    try:
        index_name = f"{project_name}-index"

        # folderName が指定されていれば、"folderName eq '...'" の形式でフィルタを構築
        filter_condition = None
        if folder_name != "all":
            filter_condition = f"folderName eq '{folder_name}'"

        # vectorFilterMode
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
            openai_api_version="2023-05-15",
            azure_deployment="gpt-35-turbo",
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
