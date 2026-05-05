import os

from dotenv import load_dotenv
from langchain_classic.chains import RetrievalQA
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS


load_dotenv()

DB_PATH = "db/"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _openrouter_headers() -> dict[str, str]:
    return {
        "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", ""),
        "X-Title": os.getenv("OPENROUTER_APP_NAME", "DocFlow-RAG"),
    }


def _openai_compatible_base_url() -> str:
    return os.getenv("OPENAI_API_BASE", DEFAULT_OPENROUTER_BASE_URL)


def build_qa_chain() -> RetrievalQA:
    base_url = _openai_compatible_base_url()
    headers = _openrouter_headers()

    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        base_url=base_url,
        default_headers=headers,
    )

    vectorstore = FAISS.load_local(
        DB_PATH, embeddings, allow_dangerous_deserialization=True
    )
    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

    llm = ChatOpenAI(
        model="gpt-3.5-turbo",
        temperature=0,
        base_url=base_url,
        default_headers=headers,
    )

    return RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        chain_type="stuff",
        return_source_documents=True,
    )


def main() -> None:
    qa = build_qa_chain()

    print("RAG CLI ready. Type your question, or 'exit' to quit.")
    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            return

        if not question:
            continue
        if question.lower() == "exit":
            print("Bye.")
            return

        try:
            result = qa.invoke({"query": question})
            answer = result.get("result", result)
            print("\nAnswer:\n" + str(answer).strip())

            source_docs = result.get("source_documents") or []
            top_sources = [
                doc.metadata.get("source", "Unknown") for doc in source_docs[:2]
            ]
            if top_sources:
                print("\nSources:")
                for src in top_sources:
                    print(f"- {src}")
        except Exception as e:
            print(f"\nError: {e}")


if __name__ == "__main__":
    main()
