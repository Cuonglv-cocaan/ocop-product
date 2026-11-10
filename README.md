# OCOP Data Pipeline

## Luồng dữ liệu

```text
crawlers/tiki/urls_tiki.txt
  -> crawlers/tiki/crawl_tiki.py
  -> crawlers/tiki/ocop_output/products_tiki.csv
  -> pipelines/sync_products.py
  -> data/ocop.duckdb (bảng products)
  -> src/app.py

crawlers/tiktok/urls_tiktok.txt
  -> crawlers/tiktok/crawl_tiktok.py
  -> crawlers/tiktok/ocop_output/products_tiktok.csv
  -> pipelines/sync_products.py (source=TIKTOK)
  -> data/ocop.duckdb (bảng products)
  -> src/app.py
```

Sản phẩm và embeddings lưu trong DuckDB (`data/ocop.duckdb`); yêu cầu liên hệ lưu riêng trong SQLite (`data/leads.sqlite3`). CSV crawler chỉ là dữ liệu đầu vào, ứng dụng đọc trực tiếp bảng `products`.

## Cài đặt và chạy

Chạy từ gốc dự án, dùng Python 3.10+ và Chrome cho crawler:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python data/database.py --migrate-csv data/products_ocop.csv
python -m streamlit run src/app.py
```

Lần cài mới: sao chép `.env.example` khi chưa có `.env`, điền API key để dùng chat, chạy `python -m src.vectorization` trước khi khởi động ứng dụng. Không ghi đè `.env` đã có. Dùng `.venv` riêng để tránh xung đột thư viện của các dự án khác.

Chat nhận diện ngân sách tối đa như “dưới 300k”, “tối đa 300.000 đồng”, “ngân sách 1,5 triệu” và giữ ngân sách khi hỏi tiếp. Câu hỏi có mức giá mới sẽ cập nhật ngân sách; “không giới hạn ngân sách” bỏ giới hạn. Bộ lọc áp dụng trước khi xếp hạng vector, mỗi sản phẩm chỉ chiếm một vị trí. Thẻ hiển thị theo danh sách ID AI chọn, được kiểm tra lại với kết quả tìm kiếm.

Lệnh migrate giữ nguyên CSV cũ, có thể chạy lại mà không tạo sản phẩm trùng. Đóng các tiến trình đang mở DuckDB trước khi nhập hoặc đồng bộ dữ liệu.

Chạy crawler (tự gọi pipeline sau khi hoàn tất):

```powershell
python crawlers/tiki/crawl_tiki.py
python crawlers/tiktok/crawl_tiktok.py
```

Tiki và TikTok dùng chung quy tắc nhận diện tỉnh từ tên sản phẩm trong `crawlers/provinces.py`. TikTok chỉ bổ sung tỉnh còn thiếu hoặc “Chưa cập nhật”; giữ nguyên tỉnh đã có. Tên chứa nhiều tỉnh hoặc không có địa danh rõ ràng sẽ không được suy đoán. Đây là gợi ý từ tên, chưa xác minh nơi sản xuất.

Chỉ bổ sung tỉnh cho CSV TikTok đã crawl (không mở Chrome, không đồng bộ database):

```powershell
python crawlers/tiktok/crawl_tiktok.py --backfill-provinces
```

Lệnh tạo bản sao lưu trước khi sửa CSV và bỏ qua các dòng đã có tỉnh. Khi chạy crawler bình thường, bước bổ sung này cũng tự chạy trước khi kiểm tra URL mới.

Hoặc chỉ nhập dữ liệu crawler đã có:

```powershell
python pipelines/sync_products.py --source TIKI --input crawlers/tiki/ocop_output/products_tiki.csv
python pipelines/sync_products.py --source TIKTOK --input crawlers/tiktok/ocop_output/products_tiktok.csv
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

Biểu mẫu lưu bảng `leads` trong SQLite, chưa tự gửi email. Đường dẫn cấu hình bằng `SQLITE_LEADS_PATH`. Chuyển leads từ DuckDB cũ sang SQLite:

```powershell
python data/database.py --migrate-duckdb-leads data/ocop.duckdb
```

Lệnh giữ nguyên DuckDB cũ và chống nhập trùng theo `legacy_duckdb_id`. SQLite cũ có bảng leads sẽ được tiếp tục sử dụng. Vector store `ocop_embeddings_gemini` dùng cùng database, chỉ khởi tạo khi gọi `get_vector_store()` và cần `GEMINI_API_KEY` hoặc `GOOGLE_API_KEY`. Chạy ứng dụng thông thường không cần khóa Gemini.

## Triển khai và lưu trữ

Tạo embeddings từ bảng `products` (cần khóa Gemini, ngắt kết nối DBeaver trước khi chạy):

```powershell
python -m src.vectorization
python -m src.vectorization --source TIKI --batch-size 32
```

Vectorization lưu SHA-256 trong metadata của từng chunk ở DuckDB. Mặc định chỉ gọi API cho sản phẩm mới, có nội dung/metadata thay đổi hoặc thiếu chunk. Nếu mọi sản phẩm không đổi, không khởi tạo vector store hay gọi API embeddings. Kết quả hiển thị `vectorized` (đã cập nhật) và `skipped` (tái sử dụng).

Embeddings cũ chưa có hash sẽ được tạo lại một lần để thiết lập cơ chế này. Hash bao gồm model embedding và phiên bản định dạng; khi đổi cách chia chunk/định dạng nội dung, tăng phiên bản trong code để cập nhật tương ứng. Chỉ ghi hash cùng vector sau khi tạo thành công, nên lần thất bại có thể chạy lại an toàn.

Để chủ động tạo lại tất cả sản phẩm trong phạm vi được chọn:

```powershell
python -m src.vectorization --force
```

Có thể nhập CSV rồi tạo embeddings cho các sản phẩm trong file:

```powershell
python -m src.vectorization --input crawlers/tiki/ocop_output/products_tiki.csv --source TIKI
```

Chạy lại sẽ thay các chunk của sản phẩm được chọn trong transaction, không tạo bản ghi trùng hoặc xóa vector của nguồn khác. Nếu gọi embeddings lỗi, vector cũ được giữ; dữ liệu sản phẩm đã nhập từ CSV vẫn được lưu để chạy lại. Chạy bằng `-m` từ gốc dự án, không chạy trực tiếp `src/vectorization.py`.

Main file là `src/app.py`, thư viện nằm trong [requirements.txt](requirements.txt). Cần nhập dữ liệu vào DuckDB trên môi trường triển khai; dữ liệu máy cá nhân không tự đồng bộ lên cloud. Dùng ổ lưu trữ bền vững và sao lưu DuckDB khi ứng dụng đã đóng. Không chạy crawler/pipeline và ứng dụng trong các tiến trình cùng mở database; dừng ứng dụng trước khi đồng bộ rồi khởi động lại.

DuckDB cũ có thể còn chứa bảng leads; không đưa file cũ lên GitHub. Xuất bản catalog sạch bằng lệnh bên dưới. SQLite và các database khác vẫn được loại khỏi Git. CSV cũ giữ lại làm nguồn migration, không còn được ứng dụng đọc. Không commit `.env`, API key, secrets, dữ liệu thô hoặc backup.

Streamlit đọc `.streamlit/config.toml` theo thư mục chạy lệnh. Để dùng cấu hình trong `src/.streamlit/`, chạy `cd src` rồi `python -m streamlit run app.py`. Xem thêm [hướng dẫn ứng dụng](src/README.md).

## Streamlit Community Cloud

Chuẩn bị catalog ở máy phát triển, khi ứng dụng và DBeaver đã ngắt kết nối:

```powershell
python data/database.py --migrate-duckdb-leads data/ocop.duckdb
python data/database.py --export-catalog data/catalog.duckdb
```

Export chỉ sao chép products và embeddings, không chứa bảng leads; từ chối ghi đè file đích đã có. Chỉ file `data/catalog.duckdb` được cho phép qua .gitignore để triển khai. Kiểm tra nội dung danh mục trước khi công khai.

Cấu hình trong phần Secrets của Community Cloud:

```toml
DUCKDB_PATH = "data/catalog.duckdb"
DUCKDB_READ_ONLY = "true"
SQLITE_LEADS_PATH = "data/leads.sqlite3"
GEMINI_API_KEY = "your-api-key"
GEMINI_MODEL = "gemini-3.5-flash-lite"
```

Ứng dụng chỉ đọc DuckDB và ghi leads vào SQLite độc lập. Không chạy pipeline/vectorization ở chế độ DUCKDB_READ_ONLY=true. Cloud không tự truy cập file trên máy cá nhân; cần đưa catalog lên môi trường triển khai.

SQLite cục bộ trên Community Cloud không được bảo đảm lưu trữ lâu dài: dữ liệu có thể mất khi khởi động lại/triển khai lại. Nếu leads cần lưu bền vững, cần cơ chế sao lưu ngoài hoặc dịch vụ database bền vững. Xem https://docs.streamlit.io/develop/concepts/connections/connecting-to-data.
