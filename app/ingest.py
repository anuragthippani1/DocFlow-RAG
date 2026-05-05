import os
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

load_dotenv()

DATA_PATH = "data/"
DB_PATH = "db/"

def ingest_documents():
    documents = []

    # Load PDFs
    for file in os.listdir(DATA_PATH):
        if file.endswith(".pdf"):
            pdf_path = os.path.join(DATA_PATH, file)
            try:
                loader = PyPDFLoader(pdf_path)
                documents.extend(loader.load())
                print(f"Loaded: {file}")
            except Exception as e:
                print(f"Error loading {file}: {e}")

    print(f"Loaded {len(documents)} pages")

    # Split into chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100
    )
    chunks = text_splitter.split_documents(documents)

    print(f"Created {len(chunks)} chunks")

    # Create embeddings
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        base_url=os.getenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1"),
        default_headers={
            "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", ""),
            "X-Title": os.getenv("OPENROUTER_APP_NAME", "DocFlow-RAG"),
        },
    )

    # Store in FAISS
    db = FAISS.from_documents(chunks, embeddings)
    db.save_local(DB_PATH)

    print("Vector DB created successfully!")

if __name__ == "__main__":
    ingest_documents()