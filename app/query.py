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


def _format_answer(text: str) -> str:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return ""

    # Prefer bullet points when there's clear structure.
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(raw_lines) >= 2:
        return "\n".join(f"- {line.lstrip('-•').strip()}" for line in raw_lines)

    # Otherwise, bullet simple sentence splits when it reads better.
    sentences = [s.strip() for s in cleaned.split(". ") if s.strip()]
    if len(sentences) >= 2:
        normalized = [s if s.endswith(".") else f"{s}." for s in sentences]
        return "\n".join(f"- {s}" for s in normalized)

    return cleaned


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
            answer_text = str(result.get("result", result)).strip()
            formatted = _format_answer(answer_text)
            print("\nAnswer:")
            print(formatted if formatted else "No answer returned.")

            source_docs = result.get("source_documents") or []
            unique_sources: list[str] = []
            seen_sources: set[str] = set()
            for doc in source_docs:
                src = doc.metadata.get("source", "Unknown")
                if src in seen_sources:
                    continue
                seen_sources.add(src)
                unique_sources.append(src)
                if len(unique_sources) >= 2:
                    break

            if unique_sources:
                print("\nSources:")
                print("\n".join(f"- {src}" for src in unique_sources))
        except Exception as e:
            print(f"\nError: {e}")


if __name__ == "__main__":
    main()
