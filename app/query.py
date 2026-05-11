import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_classic.chains import RetrievalQA
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

# Allow running as a script: `python app/query.py`
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent import analyze_response
from app.config import get_settings, openrouter_headers


load_dotenv()


def build_qa_chain() -> RetrievalQA:
    settings = get_settings()
    headers = openrouter_headers()

    embeddings = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base,
        default_headers=headers,
    )

    vectorstore = FAISS.load_local(
        settings.db_path, embeddings, allow_dangerous_deserialization=True
    )
    retriever = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={
            "k": settings.retriever_k,
            "fetch_k": settings.retriever_fetch_k,
            "lambda_mult": 0.65,
        },
    )

    llm = ChatOpenAI(
        model=settings.qa_model,
        temperature=0,
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base,
        default_headers=headers,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
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
            answer = str(result["result"]).strip()
            answer_text = answer
            formatted = _format_answer(answer_text)
            print("\nAnswer:")
            print(formatted if formatted else "No answer returned.")

            analysis = analyze_response(answer)
            print("\nAgent Analysis:")
            print(f"- summary: {analysis.get('summary', '').strip()}")
            print(f"- key_insight: {analysis.get('key_insight', '').strip()}")
            print(f"- risk_level: {analysis.get('risk_level', '').strip()}")
            print(f"- recommendation: {analysis.get('recommendation', '').strip()}")

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
