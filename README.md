# OCOP Data Pipeline

## Luồng dữ liệu

```text
crawlers/tiki/urls.txt
  -> crawlers/tiki/crawl_tiki.py
  -> crawlers/tiki/ocop_output/products_tiki.csv
  -> pipelines/sync_products.py
  -> data/ocop.duckdb (bảng products)
  -> src/app.py
```

Danh mục sản phẩm và yêu cầu liên hệ dùng chung DuckDB, mặc định `data/ocop.duckdb`. CSV crawler chỉ là dữ liệu đầu vào, ứng dụng đọc trực tiếp bảng `products`.

## Cài đặt và chạy

Chạy từ gốc dự án, dùng Python 3.10+ và Chrome cho crawler:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python data/database.py --migrate-csv data/products_ocop.csv
python -m streamlit run src/app.py
```

Lệnh migrate giữ nguyên CSV cũ, có thể chạy lại mà không tạo sản phẩm trùng. Đóng các tiến trình đang mở DuckDB trước khi nhập hoặc đồng bộ dữ liệu.

Chạy crawler (tự gọi pipeline sau khi hoàn tất):

```powershell
python crawlers/tiki/crawl_tiki.py
```

Hoặc chỉ nhập dữ liệu crawler đã có:

```powershell
python pipelines/sync_products.py --source TIKI --input crawlers/tiki/ocop_output/products_tiki.csv
```

Pipeline gộp theo khóa `source + product_id`, giữ sản phẩm lịch sử và không ghi đè dữ liệu đã biết bằng ô trống. Tỉnh "Chưa cập nhật" không thay thế tỉnh đã biết. Giao dịch lỗi sẽ rollback. Không còn tùy chọn `--master`; database đích dùng `DUCKDB_PATH`. Đường dẫn `--input` tính từ thư mục chạy lệnh.

## Database dùng chung

Schema được định nghĩa chung trong `data/init_db.sql`; Python đọc file này khi khởi tạo. Khóa sản phẩm không được rỗng hoặc có khoảng trắng đầu/cuối; `source` phải viết hoa. Pipeline tự chuẩn hóa trước khi ghi.

Với database đã tồn tại, `CREATE TABLE IF NOT EXISTS` không thêm ràng buộc mới. Ngắt kết nối DBeaver và dừng ứng dụng đang dùng database, rồi chạy:

```powershell
python data/database.py --upgrade-products-schema
```

Lệnh nâng cấp trong transaction, giữ nguyên dữ liệu và rollback nếu khóa cũ không hợp lệ, schema khác dự kiến hoặc có đối tượng phụ thuộc không tương thích. Không tự xóa hay sửa dữ liệu lỗi.

Module [data/database.py](data/database.py) cung cấp `read_products()`, `upsert_products()`, `migrate_csv_products()` và `save_lead()`.

Bảng `products` gồm:
`product_id,product_name,brand,category_name,province_name,ocop_stars,description,source_url,image_url,price,source`.

Các cột lưu dưới dạng VARCHAR để giữ ID có số 0 đầu và tương thích dữ liệu crawler; ứng dụng chuyển giá và sao sang số khi hiển thị. Các trường chi tiết khác trong CSV crawler chưa đưa vào bảng chung. Sao OCOP và tỉnh từ crawler cần kiểm chứng trước khi dùng như dữ liệu chứng nhận.

Module database đọc `.env` ở gốc dự án. `DUCKDB_PATH=data/ocop.duckdb` tính từ gốc dự án, không phụ thuộc thư mục chạy lệnh. Biến môi trường hệ thống được ưu tiên hơn `.env`. Ứng dụng đọc lại database mỗi lần Streamlit chạy lại.

Biểu mẫu lưu bảng `leads`, chưa tự gửi email. Nhập yêu cầu liên hệ từ SQLite cũ:

```powershell
python data/database.py --migrate-sqlite data/leads.sqlite3
```

Lệnh giữ nguyên SQLite và chống nhập trùng theo `legacy_sqlite_id`. Vector store `ocop_embeddings_gemini` dùng cùng database, chỉ khởi tạo khi gọi `get_vector_store()` và cần `GEMINI_API_KEY` hoặc `GOOGLE_API_KEY`. Chạy ứng dụng thông thường không cần khóa Gemini.

## Triển khai và lưu trữ

Tạo embeddings từ bảng `products` (cần khóa Gemini, ngắt kết nối DBeaver trước khi chạy):

```powershell
python -m src.vectorization
python -m src.vectorization --source TIKI --batch-size 32
```

Có thể nhập CSV rồi tạo embeddings cho các sản phẩm trong file:

```powershell
python -m src.vectorization --input crawlers/tiki/ocop_output/products_tiki.csv --source TIKI
```

Chạy lại sẽ thay các chunk của sản phẩm được chọn trong transaction, không tạo bản ghi trùng hoặc xóa vector của nguồn khác. Nếu gọi embeddings lỗi, vector cũ được giữ; dữ liệu sản phẩm đã nhập từ CSV vẫn được lưu để chạy lại. Chạy bằng `-m` từ gốc dự án, không chạy trực tiếp `src/vectorization.py`.

Main file là `src/app.py`, thư viện nằm trong [requirements.txt](requirements.txt). Cần nhập dữ liệu vào DuckDB trên môi trường triển khai; dữ liệu máy cá nhân không tự đồng bộ lên cloud. Dùng ổ lưu trữ bền vững và sao lưu DuckDB khi ứng dụng đã đóng. Không chạy crawler/pipeline và ứng dụng trong các tiến trình cùng mở database; dừng ứng dụng trước khi đồng bộ rồi khởi động lại.

Database chứa cả thông tin liên hệ nên được loại khỏi Git cùng WAL. Không đưa database dùng chung lên GitHub. CSV cũ giữ lại làm nguồn migration, không còn được ứng dụng đọc. Không commit `.env`, API key, secrets, dữ liệu thô hoặc backup.

Streamlit đọc `.streamlit/config.toml` theo thư mục chạy lệnh. Để dùng cấu hình trong `src/.streamlit/`, chạy `cd src` rồi `python -m streamlit run app.py`. Xem thêm [hướng dẫn ứng dụng](src/README.md).
