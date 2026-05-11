import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

# Allow running as a script: `python app/ingest.py`
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings, openrouter_headers
from app.logging_utils import get_logger

load_dotenv()

logger = get_logger(__name__)

def ingest_documents():
    settings = get_settings()
    documents = []

    # Load PDFs
    for file in os.listdir(settings.data_path):
        if file.lower().endswith(".pdf"):
            pdf_path = os.path.join(settings.data_path, file)
            try:
                loader = PyPDFLoader(pdf_path)
                loaded_docs = loader.load()
                for page_idx, doc in enumerate(loaded_docs):
                    doc.metadata["source"] = pdf_path
                    doc.metadata["file_name"] = file
                    doc.metadata["page_number"] = doc.metadata.get("page", page_idx)
                documents.extend(loaded_docs)
                logger.info("Loaded PDF: %s (%s pages)", file, len(loaded_docs))
            except Exception as e:
                logger.warning("Error loading %s: %s", file, e)

    logger.info("Loaded %s pages", len(documents))
    if not documents:
        raise ValueError("No PDF pages were loaded. Add valid PDF files to the data folder.")

    # Split into chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        add_start_index=True,
    )
    chunks = text_splitter.split_documents(documents)

    logger.info("Created %s chunks", len(chunks))
    if not chunks:
        raise ValueError("No text chunks were created from the loaded PDFs.")

    # Create embeddings
    embeddings = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base,
        default_headers=openrouter_headers(),
    )

    # Store in FAISS
    db = FAISS.from_documents(chunks, embeddings)
    db.save_local(settings.db_path)

    logger.info("Vector DB created successfully")

if __name__ == "__main__":
    ingest_documents()