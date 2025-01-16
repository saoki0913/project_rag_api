import azure.functions as func
import openai
import os
import logging
import ipdb
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain_community.vectorstores import AzureSearch
from langchain import hub
from langchain.schema import StrOutputParser
from langchain.schema.runnable import RunnablePassthrough
from operator import itemgetter
from langchain.schema.runnable import RunnableMap


# 環境変数から設定を取得
openai_embedding_key = os.getenv("AZURE_OPENAI_EMBEDDING_API_KEY")
openai_embedding_endpoint = os.getenv("AZURE_OPENAI_EMBEDDING_ENDPOINT")
openai_embedding_uri = os.getenv("AZURE_OPENAI_EMBEDDING_URI")
azure_search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
azure_search_key = os.getenv("AZURE_SEARCH_ADMIN_KEY")
openai.api_key = os.getenv("AZURE_OPENAI_API_KEY")
openai.azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")


def generate_answer(user_question, project_name, folder_name):
    """
    質問に基づいて応答を生成。
    OData フィルター + ベクトル検索を組み合わせ、
    指定フォルダ配下のドキュメントのみを検索対象にする。
    """
    try:
        index_name = f"{project_name}-index"

        # OData フィルター文の作成
        # 例: folderName eq 'sample'
        filter_condition = None
        if folder_name:
            filter_condition = f"folderName eq '{folder_name}'" if folder_name else None

        # 検索の設定 (ベクトル検索 + OData フィルター)
        # "filter" によりフォルダ名で事前絞り込み
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
        ).as_retriever(
            search_type="similarity",
            search_kwargs={}
        )

        logging.info(f"filter_condition: {filter_condition}")

        # ドキュメント検索 (トップ3件)
        retrieved_docs = retriever.get_relevant_documents(
            user_question,
            filter=filter_condition
        )
        retrieved_docs = retrieved_docs[:3] 
        logging.info(f"retrieved_docs: {retrieved_docs}")

        # LLM (ChatGPT) を使った回答生成
        llm = AzureChatOpenAI(
            openai_api_key=openai.api_key,
            azure_endpoint=openai.azure_endpoint,
            openai_api_version="2023-05-15",
            azure_deployment="gpt-35-turbo",
            temperature=0,
        )

        # ベクトルストアから取り出した document の page_content を連結
        def format_docs(docs):
            return "\n\n".join(doc.page_content for doc in docs)
        
        # 必要なメタデータのみ抽出
        def filter_metadata(docs):
            return [
                {
                    "documentUrl": doc.metadata.get("documentUrl"),
                    "documentName": doc.metadata.get("documentName"),
                    "last_modified": doc.metadata.get("last_modified"),
                }
                for doc in docs
            ]
        
        # RAG用のプロンプト (LangChain prompt hub)
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

        # RAGチェーン (ドキュメント情報とLLM応答をまとめて返す)
        rag_chain_with_source = RunnableMap(
            {"documents": retriever, "question": RunnablePassthrough()}
        ) | {
            "documents": lambda input: filter_metadata(input["documents"]),
            "answer": rag_chain_from_docs,
        }

        # チェーン実行
        answer_data = rag_chain_with_source.invoke(user_question)
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
