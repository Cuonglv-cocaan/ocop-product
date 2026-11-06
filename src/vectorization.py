from __future__ import annotations

import asyncio
import json
import math
import threading
import uuid
from pathlib import Path

import pandas as pd
from langchain_text_splitters import RecursiveCharacterTextSplitter

from data.database import (
    PROJECT_ROOT,
    connect,
    get_vector_store,
    normalize,
    read_products,
    upsert_products,
)


# Phải khớp table_name trong database.py.
VECTOR_TABLE = "ocop_embeddings_gemini"

# Ngăn hai tác vụ vectorization chạy đồng thời trong cùng tiến trình.
_VECTORIZE_LOCK = threading.Lock()


def _load_csv(
    filepath: Path,
    source: str | None = None,
) -> pd.DataFrame:
    """Đọc CSV, giữ nguyên ID dài và chuẩn hóa về schema OCOP."""
    df = pd.read_csv(
        filepath,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lstrip("\ufeff")
    )

    if df.columns.duplicated().any():
        raise ValueError(f"{filepath.name}: tên cột bị trùng.")

    if df.empty:
        raise ValueError(f"{filepath.name}: file không có dữ liệu.")

    id_column = (
        "product_id" if "product_id" in df.columns else "id"
    )
    if id_column not in df.columns:
        raise ValueError(
            f"{filepath.name}: thiếu cột product_id."
        )

    if df[id_column].str.strip().eq("").any():
        raise ValueError(
            f"{filepath.name}: có dòng thiếu product_id."
        )

    if source is not None:
        source = source.strip().upper()
        if not source:
            raise ValueError("source không được để trống.")
    elif (
        "source" not in df.columns
        or df["source"].str.strip().eq("").any()
    ):
        raise ValueError(
            f"{filepath.name}: thiếu source. "
            'Bổ sung cột source hoặc truyền source="TIKI".'
        )

    # Dùng chung quy tắc chuẩn hóa với database.py:
    # alias tên cột, source viết hoa, tỉnh trống -> Chưa cập nhật.
    df = normalize(df, source)

    if df.empty:
        raise ValueError(
            f"{filepath.name}: không có sản phẩm hợp lệ."
        )

    if df["product_name"].str.strip().eq("").any():
        raise ValueError(
            f"{filepath.name}: có sản phẩm thiếu product_name."
        )

    return df


def _prepare_documents(df: pd.DataFrame):
    """Tạo nội dung tìm kiếm và metadata cho từng sản phẩm."""
    texts = []
    metadatas = []

    for row in df.to_dict(orient="records"):
        metadata = {
            key: str(value).strip()
            for key, value in row.items()
        }

        def value(field):
            return metadata.get(field) or "Chưa cập nhật"

        text = "\n".join([
            f"Tên sản phẩm: {value('product_name')}",
            f"Thương hiệu: {value('brand')}",
            f"Danh mục: {value('category_name')}",
            f"Tỉnh/thành: {value('province_name')}",
            f"Số sao OCOP theo dữ liệu nguồn: {value('ocop_stars')}",
            f"Giá ghi nhận (VND): {value('price')}",
            f"Nguồn bán: {value('source')}",
            f"Mô tả: {value('description')}",
        ])

        texts.append(text)
        metadatas.append(metadata)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=120,
    )

    documents = splitter.create_documents(
        texts,
        metadatas=metadatas,
    )

    # ID xác định theo nguồn + sản phẩm + vị trí chunk.
    counters = {}
    for doc in documents:
        key = (
            doc.metadata["source"],
            doc.metadata["product_id"],
        )
        chunk_index = counters.get(key, 0)
        counters[key] = chunk_index + 1

        doc.metadata["chunk_index"] = chunk_index
        doc.metadata["chunk_id"] = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                json.dumps(
                    [*key, chunk_index],
                    ensure_ascii=False,
                ),
            )
        )

    return documents


def _replace_vectors(keys, documents, vectors):
    """
    Thay toàn bộ chunk của các sản phẩm đang nhập.

    Schema tương ứng cấu hình mặc định của LangChain DuckDB:
        id VARCHAR
        text VARCHAR
        embedding FLOAT[]
        metadata VARCHAR
    """
    if len(documents) != len(vectors):
        raise ValueError("Embedding count does not match document count")
    if not documents:
        raise ValueError("No documents to vectorize")
    dimension = len(vectors[0])
    if not dimension or any(
        len(vector) != dimension or any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) for value in vector
        ) for vector in vectors
    ):
        raise ValueError("Embeddings must have consistent dimensions and finite numbers")
    rows = [
        (
            doc.metadata["chunk_id"],
            doc.page_content,
            vector,
            json.dumps(doc.metadata, ensure_ascii=False),
        )
        for doc, vector in zip(documents, vectors)
    ]

    with connect() as connection:
        connection.begin()
        try:
            # get_vector_store() đã khởi tạo bảng này.
            # Xóa theo cả source và product_id, không xóa cả danh mục.
            connection.executemany(
                f"""
                DELETE FROM {VECTOR_TABLE}
                WHERE json_extract_string(metadata, '$.source') = ?
                  AND json_extract_string(metadata, '$.product_id') = ?
                """,
                keys,
            )

            connection.executemany(
                f"""
                INSERT INTO {VECTOR_TABLE}
                    (id, text, embedding, metadata)
                VALUES (?, ?, ?, ?)
                """,
                rows,
            )

            connection.commit()
        except Exception:
            connection.rollback()
            raise


def _run_vectorize(
    filepath: str | None,
    source: str | None,
    batch_size: int,
) -> dict:
    # Chạy trong worker thread, gồm cả I/O DuckDB và gọi embeddings.
    with _VECTORIZE_LOCK:
        added = updated = 0
        csv_files = []
        if filepath is not None:
            path = Path(filepath).expanduser()
            if not path.is_absolute():
                path = PROJECT_ROOT / path

            if not path.is_file():
                raise FileNotFoundError(path)

            csv_files = [path]
            incoming = _load_csv(path, source)
            added, updated, _ = upsert_products(incoming)
            key_set = set(incoming[["source", "product_id"]].itertuples(index=False, name=None))
        else:
            key_set = None

        # Đọc lại dữ liệu sau merge để không mất các giá trị cũ
        # mà CSV mới để trống.
        current = read_products()
        total = len(current)
        selected = current.copy()
        if key_set is not None:
            selected = selected.loc[
                [(row.source, row.product_id) in key_set for row in selected.itertuples(index=False)]
            ].copy()
        elif source is not None:
            selected = selected.loc[selected["source"] == source].copy()
        if selected.empty:
            raise ValueError("No products to vectorize in DuckDB for the selected source")
        if selected["product_name"].str.strip().eq("").any():
            raise ValueError("Products must have product_name before vectorization")
        keys = list(selected[["source", "product_id"]].itertuples(index=False, name=None))

        documents = _prepare_documents(selected)

        # Initialize inside the worker so synchronous setup does not block asyncio.
        store = asyncio.run(get_vector_store())
        embeddings = store.embeddings
        if embeddings is None:
            raise RuntimeError(
                "Vector store chưa cấu hình embeddings."
            )

        vectors = []

        # Tạo đủ embeddings trước khi thay dữ liệu vector cũ.
        for start in range(0, len(documents), batch_size):
            batch = documents[start:start + batch_size]

            batch_vectors = embeddings.embed_documents(
                [doc.page_content for doc in batch]
            )

            if len(batch_vectors) != len(batch):
                raise RuntimeError(
                    "Số embeddings trả về không khớp số tài liệu."
                )

            vectors.extend(batch_vectors)

        _replace_vectors(keys, documents, vectors)

        stats = {
            "files": len(csv_files),
            "products": len(selected),
            "added": added,
            "updated": updated,
            "total_products": total,
            "chunks": len(documents),
            "collection": VECTOR_TABLE,
        }

        print(
            f"VECTORIZE: {stats['products']} products, "
            f"{stats['chunks']} chunks, "
            f"added={added}, updated={updated}"
        )

        return stats


async def run_vectorize_async(
    filepath: str | None = None,
    source: str | None = None,
    batch_size: int = 32,
) -> dict:
    """
    Không truyền filepath: tạo embeddings từ bảng products trong DuckDB.
    Có filepath: nhập CSV vào products rồi tạo embeddings cho các sản phẩm đó.

    source=None: lấy nguồn từ cột source trong CSV.
    source="TIKI": gán nguồn TIKI cho toàn bộ dữ liệu nhập.
    """
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError("batch_size phải lớn hơn 0.")
    if source is not None:
        source = source.strip().upper()
        if not source:
            raise ValueError("source không được để trống.")

    return await asyncio.to_thread(
        _run_vectorize,
        filepath,
        source,
        batch_size,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Vectorize shared DuckDB products")
    parser.add_argument("--input", help="Optional CSV to import before vectorization")
    parser.add_argument("--source", help="Filter DuckDB source or override CSV source")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    asyncio.run(run_vectorize_async(args.input, args.source, args.batch_size))
