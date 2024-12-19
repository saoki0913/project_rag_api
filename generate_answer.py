import azure.functions as func
import openai
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
import os
import logging
import ipdb
import json
from argparse import ArgumentParser
from datetime import datetime
from azure.core.exceptions import ResourceExistsError
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain_community.document_loaders import AzureAIDocumentIntelligenceLoader
from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_community.vectorstores import AzureSearch
from langchain import hub
from langchain.schema import StrOutputParser
from langchain.schema.runnable import RunnablePassthrough
from operator import itemgetter
from langchain.schema.runnable import RunnableMap
from pydantic import BaseModel
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
import urllib.request
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes import SearchIndexerClient


from docx import Document
from io import BytesIO
from fpdf import FPDF
from fastapi import UploadFile, HTTPException
from magic import Magic
from pptx import Presentation

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

def generate_answer(user_question, project_name):
    """
    質問に基づいて応答を生成。
    """
    try:
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
        #一番関連度の高い資料の情報も取得
        answer_data = rag_chain_with_source.invoke(user_question)
        answer = answer_data["answer"]
        documentUrl = answer_data["documents"][0]["documentUrl"]
        documentName = answer_data["documents"][0]["documentName"]
        last_modified = answer_data["documents"][0]["last_modified"]
        
        content={
            "answer": answer,
            "documentUrl": documentUrl,
            "documentName": documentName,
            "last_modified": last_modified,
        }
        return content

    except Exception as e:
        logging.error(f"Error generating answer with prompt: {e}")
        raise

