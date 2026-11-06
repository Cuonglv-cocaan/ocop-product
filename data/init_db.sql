-- init_db.sql
-- Database: DuckDB
-- Danh mục sản phẩm OCOP từ nhiều nguồn thương mại điện tử.

CREATE TABLE IF NOT EXISTS products (
    product_id     VARCHAR NOT NULL,
    product_name   VARCHAR NOT NULL DEFAULT '',
    brand          VARCHAR NOT NULL DEFAULT '',
    category_name  VARCHAR NOT NULL DEFAULT '',
    province_name  VARCHAR NOT NULL DEFAULT '',
    ocop_stars     VARCHAR NOT NULL DEFAULT '',
    description    VARCHAR NOT NULL DEFAULT '',
    source_url     VARCHAR NOT NULL DEFAULT '',
    image_url      VARCHAR NOT NULL DEFAULT '',
    price          VARCHAR NOT NULL DEFAULT '',
    source         VARCHAR NOT NULL,

    PRIMARY KEY (source, product_id),
    CHECK (length(trim(product_id)) > 0 AND product_id = trim(product_id)),
    CHECK (length(trim(source)) > 0 AND source = upper(trim(source)))
);

-- Bảng lưu thông tin đăng ký kết nối cung cầu.

CREATE SEQUENCE IF NOT EXISTS lead_ids START 1;

CREATE TABLE IF NOT EXISTS leads (
    id               BIGINT PRIMARY KEY DEFAULT nextval('lead_ids'),
    created_at       TEXT NOT NULL,
    kind             TEXT NOT NULL,
    name             TEXT NOT NULL,
    email            TEXT NOT NULL,
    phone            TEXT NOT NULL,
    note             TEXT NOT NULL,
    legacy_sqlite_id BIGINT UNIQUE
);

-- Không tạo bảng embeddings thủ công tại đây.
-- database.py khởi tạo bảng "ocop_embeddings_gemini"
-- thông qua LangChain DuckDB vector store.
-- Bước ingestion sẽ thêm nội dung và embeddings vào bảng đó.
