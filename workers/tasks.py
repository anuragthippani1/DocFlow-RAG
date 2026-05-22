from workers.celery_app import celery_app


@celery_app.task(name="workers.ingest_document")
def ingest_document_task(filename: str) -> dict[str, str]:
    from app.ingest import ingest_documents
    from app.status import DocumentStatus, set_document_status

    set_document_status(filename, DocumentStatus.PROCESSING, "Worker started ingestion")
    try:
        ingest_documents()
        set_document_status(filename, DocumentStatus.DONE, "Ingestion completed")
        return {"filename": filename, "status": DocumentStatus.DONE.value}
    except Exception as exc:
        set_document_status(filename, DocumentStatus.FAILED, str(exc))
        raise
