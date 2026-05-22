import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

# Allow running as a script: `python app/ingest.py`
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings, openrouter_headers
from app.db_utils import vector_db_ready
from app.logging_utils import get_logger

load_dotenv()

logger = get_logger(__name__)


def _docstore_items(vectorstore: FAISS) -> list[tuple[str, Any]]:
    docstore = getattr(vectorstore, "docstore", None)
    store = getattr(docstore, "_dict", None)
    if not isinstance(store, dict):
        return []
    return list(store.items())


def _file_signature(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"file_size": stat.st_size, "file_mtime_ns": stat.st_mtime_ns}


def _indexed_file_signatures(vectorstore: FAISS) -> dict[str, dict[str, int | None]]:
    indexed: dict[str, dict[str, int | None]] = {}
    for _, doc in _docstore_items(vectorstore):
        metadata = getattr(doc, "metadata", {}) or {}
        file_name = metadata.get("file_name")
        if not file_name:
            source = metadata.get("source")
            file_name = Path(str(source)).name if source else None
        if not file_name or file_name in indexed:
            continue
        indexed[str(file_name)] = {
            "file_size": metadata.get("file_size"),
            "file_mtime_ns": metadata.get("file_mtime_ns"),
        }
    return indexed


def _delete_file_documents(vectorstore: FAISS, file_name: str) -> None:
    ids_to_delete = [
        doc_id
        for doc_id, doc in _docstore_items(vectorstore)
        if (getattr(doc, "metadata", {}) or {}).get("file_name") == file_name
    ]
    if ids_to_delete:
        vectorstore.delete(ids_to_delete)


def ingest_documents():
    settings = get_settings()
    data_path = Path(settings.data_path)
    if not data_path.exists():
        raise ValueError(f"Data folder does not exist: {settings.data_path}")

    documents = []
    embeddings = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base,
        default_headers=openrouter_headers(),
    )

    vectorstore = None
    indexed_signatures: dict[str, dict[str, int | None]] = {}
    if vector_db_ready(settings.db_path):
        vectorstore = FAISS.load_local(
            settings.db_path, embeddings, allow_dangerous_deserialization=True
        )
        indexed_signatures = _indexed_file_signatures(vectorstore)

    # Load PDFs
    for pdf_path in sorted(data_path.iterdir()):
        if not pdf_path.is_file() or not pdf_path.name.lower().endswith(".pdf"):
            continue

        signature = _file_signature(pdf_path)
        indexed_signature = indexed_signatures.get(pdf_path.name)
        if indexed_signature == signature:
            logger.info("Skipping existing file: %s", pdf_path.name)
            continue

        if indexed_signature and vectorstore is not None:
            logger.info("Indexing new file: %s (changed since last index)", pdf_path.name)
            _delete_file_documents(vectorstore, pdf_path.name)
        else:
            logger.info("Indexing new file: %s", pdf_path.name)

        try:
            loader = PyPDFLoader(str(pdf_path))
            loaded_docs = loader.load()
            for page_idx, doc in enumerate(loaded_docs):
                doc.metadata["source"] = str(pdf_path)
                doc.metadata["file_name"] = pdf_path.name
                doc.metadata["page_number"] = doc.metadata.get("page", page_idx)
                doc.metadata.update(signature)
            documents.extend(loaded_docs)
            logger.info("Loaded PDF: %s (%s pages)", pdf_path.name, len(loaded_docs))
        except Exception as e:
            logger.warning("Error loading %s: %s", pdf_path.name, e)

    logger.info("Loaded %s pages", len(documents))
    if not documents:
        if vectorstore is not None:
            logger.info("No new or changed PDF files found. Existing vector DB preserved.")
            return
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

    # Store in FAISS
    if vectorstore is not None:
        vectorstore.add_documents(chunks)
        db = vectorstore
    else:
        db = FAISS.from_documents(chunks, embeddings)
    db.save_local(settings.db_path)

    logger.info("Vector DB created successfully")

if __name__ == "__main__":
    ingest_documents()