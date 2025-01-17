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
            openai_api_version="2023-05-15",
            azure_deployment="gpt-35-turbo",
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