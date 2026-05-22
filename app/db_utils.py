from pathlib import Path


def vector_db_ready(db_path: str | Path) -> bool:
    db_dir = Path(db_path)
    return (db_dir / "index.faiss").is_file() and (db_dir / "index.pkl").is_file()
