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

Sản phẩm và embeddings lưu trong DuckDB (`data/ocop.duckdb`); tài khoản và yêu cầu liên hệ có chủ sở hữu lưu riêng trong PostgreSQL/Supabase với `LEADS_BACKEND=postgres`. SQLite được giữ làm nguồn migration của bước 3; giao diện có đăng nhập không ghi SQLite. CSV crawler chỉ là dữ liệu đầu vào, ứng dụng đọc trực tiếp bảng `products`.

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

Biểu mẫu gọi `data.leads.save_lead()`, chưa tự gửi email. Bước 4 yêu cầu phiên đăng nhập và `LEADS_BACKEND=postgres`, dùng `DATABASE_URL` và bảng `business.leads`. SQLite dùng `SQLITE_LEADS_PATH` cho các công cụ legacy; lệnh chuyển leads từ DuckDB cũ sang SQLite vẫn được giữ:

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

Export chỉ sao chép products và embeddings, không chứa bảng leads; tự ghi đè file đích đã có, không tạo backup. Bản mới được tạo hoàn chỉnh trước khi thay file cũ. Sau khi đồng bộ sản phẩm hoặc tạo embeddings thành công, code tự cập nhật `catalog.duckdb` trong cùng thư mục với database nguồn. Thay đổi trực tiếp bằng SQL/DBeaver cần chạy lệnh export thủ công. Đóng kết nối đang mở catalog trước khi cập nhật. Nếu export lỗi, database nguồn vẫn giữ thay đổi đã commit và lệnh báo lỗi để chạy lại export. Chỉ file `data/catalog.duckdb` được cho phép qua .gitignore để triển khai. Cần commit/push catalog mới để cloud nhận cập nhật.

Cấu hình trong phần Secrets của Community Cloud:

```toml
DUCKDB_PATH = "data/catalog.duckdb"
DUCKDB_READ_ONLY = "true"
SQLITE_LEADS_PATH = "data/leads.sqlite3"
LEADS_BACKEND = "postgres"
DATABASE_URL = "postgresql://USER:PASSWORD@POOLER_HOST:5432/postgres?sslmode=require"
GEMINI_API_KEY = "your-api-key"
GEMINI_MODEL = "gemini-3.5-flash-lite"
```

Ứng dụng chỉ đọc DuckDB và ghi leads vào backend đã chọn. Với PostgreSQL, chạy schema migration trước khi triển khai. Không chạy pipeline/vectorization ở chế độ DUCKDB_READ_ONLY=true. Cloud không tự truy cập file trên máy cá nhân; cần đưa catalog lên môi trường triển khai.

SQLite cục bộ trên Community Cloud không được bảo đảm lưu trữ lâu dài: dữ liệu có thể mất khi khởi động lại/triển khai lại. Nếu leads cần lưu bền vững, cần cơ chế sao lưu ngoài hoặc dịch vụ database bền vững. Xem https://docs.streamlit.io/develop/concepts/connections/connecting-to-data.

### Danh mục tiếng Việt dùng chung

`data/categories.py` định nghĩa bảng ánh xạ `CATEGORY_ALIASES` cho Tiki và TikTok. `read_products()` trả về danh mục chuẩn tiếng Việt cho giao diện, bộ lọc và tìm kiếm; danh mục gốc trong DuckDB và CSV crawler được giữ nguyên. Ví dụ `Cooking Sauces` được gom vào `Gia vị và chế biến`, `Dried Snacks` vào `Đồ ăn vặt`. Đây là bộ danh mục nội bộ của ứng dụng, không phải hệ thống phân loại OCOP chính thức.

Danh mục chưa có ánh xạ hiển thị `Chưa phân loại`. Khi nguồn có danh mục mới, thêm nguyên tên/đường dẫn danh mục vào nhóm phù hợp trong `CATEGORY_ALIASES`; không cần sửa dữ liệu cũ hay chạy lại crawler. Embeddings đã tạo trước đó cần được cập nhật nếu muốn nội dung vector phản ánh danh mục mới.

## Chuẩn bị PostgreSQL / Supabase cho dữ liệu nghiệp vụ

Phiên bản khảo sát ban đầu: commit `6d35690` (Update UIUX). Không có AGENTS.md trong cây dự án hoặc các thư mục cha đã kiểm tra. Catalog `products`, embeddings `ocop_embeddings_gemini`, tìm kiếm, RAG, crawler và pipeline vẫn dùng DuckDB. Bước 4 dùng tài khoản nội bộ trong `business.users`, không dùng Supabase Auth/OIDC/Google.

Các điểm truy cập leads đã rà soát:

- `src/app.py::connect()` là luồng ghi từ biểu mẫu cung cầu, gọi `data/leads.py::save_lead()`. Giao diện giữ nội dung khi lưu lỗi và không hiển thị lỗi driver chứa thông tin kết nối.
- `data/leads.py` yêu cầu `LEADS_BACKEND=postgres` và phiên đăng nhập hợp lệ cho đọc/ghi yêu cầu. Thiếu/sai backend sẽ báo lỗi; PostgreSQL lỗi không tự ghi dự phòng vào SQLite.
- `data/sqlite_leads.py` quản lý kết nối, tạo/nâng cấp bảng SQLite và ghi leads. `data/database.py` giữ alias API cũ để tương thích.
- `data/database.py::migrate_duckdb_leads()` đọc bảng leads DuckDB cũ bằng kết nối chỉ đọc, kiểm tra `legacy_duckdb_id` rồi ghi SQLite. Đây vẫn là lệnh legacy, không ghi PostgreSQL và không được chạy trong thay đổi này.
- `tests/test_database_schema.py` đọc SQLite để kiểm tra và tạo leads DuckDB giả trong thư mục tạm; `tests/test_leads.py` kiểm tra chọn backend, secrets, tham số SQL và xử lý lỗi. Không có luồng đọc leads trong UI, RAG, crawler hay pipeline. Export catalog chỉ sao chép products và embeddings.

`data/postgres.py` đọc cấu hình theo thứ tự: biến môi trường hệ thống, `.env` gốc (không ghi đè môi trường), rồi khóa cấp gốc trong Streamlit secrets. Kết nối mở lười cho từng transaction, timeout kết nối 10 giây, commit khi thành công, rollback khi lỗi và luôn đóng. Không cache kết nối giữa các phiên Streamlit. Tắt prepared statements để tương thích Supabase transaction pooler. Không tự tạo schema khi import hoặc gửi biểu mẫu.

### Chạy local với PostgreSQL thử nghiệm

Cài dependencies bằng `python -m pip install -r requirements.txt`. Tạo database thử nghiệm rỗng bằng PostgreSQL local, ví dụ Docker:

```powershell
docker run --name ocop-postgres -e POSTGRES_USER=ocop -e POSTGRES_PASSWORD=local-development-only -e POSTGRES_DB=ocop -p 5432:5432 -d postgres:16
$env:DATABASE_URL = 'postgresql://ocop:local-development-only@localhost:5432/ocop'
python -m data.postgres --init-schema
$env:LEADS_BACKEND = 'postgres'
python -m streamlit run src/app.py
```

Chỉ lệnh `--init-schema` chạy migration schema, không sao chép dữ liệu. Gửi một yêu cầu thử và kiểm tra `SELECT * FROM business.leads` trong database thử nghiệm. Khi dừng thử nghiệm, đặt LEADS_BACKEND=`sqlite` rõ ràng để chạy local. Không ghi dữ liệu thử vào database production.

Supabase: lấy PostgreSQL URI từ Dashboard > Connect, không dùng REST URL hoặc anon key. Dùng session pooler hoặc transaction pooler phù hợp mạng triển khai, thêm `sslmode=require` và URL-encode mật khẩu. Lưu URI vào DATABASE_URL ở Secrets hoặc môi trường; không commit URI thật. Ví dụ Secrets (giá trị minh họa):

```toml
LEADS_BACKEND = "sqlite" # Đổi postgres sau khi hoàn tất migration/cutover
DATABASE_URL = "postgresql://USER:PASSWORD@HOST:5432/postgres?sslmode=require"
DUCKDB_PATH = "data/catalog.duckdb"
DUCKDB_READ_ONLY = "true"
```

Schema nghiệp vụ trong `data/migrations/` nằm ở `business`, tách khỏi `public`; không thêm schema này vào Supabase exposed schemas. Không cấp quyền truy cập users/leads cho anon/authenticated. Kết nối chỉ từ backend bằng tài khoản DB; dùng role quản trị riêng cho DDL. Phân quyền demo nằm ở các hàm dữ liệu Python, không phải PostgreSQL RLS hay Supabase Auth.

Tham khảo: [Psycopg transaction context](https://www.psycopg.org/psycopg3/docs/basic/transactions.html), [Supabase connections](https://supabase.com/docs/guides/database/connecting-to-postgres).

### Quy trình migration

1. Kiểm kê và sao lưu SQLite cùng các DuckDB legacy chứa leads; xác định nguồn chuẩn, ID trùng, múi giờ và dữ liệu thiếu. Không đưa bản sao chứa thông tin cá nhân vào Git.
2. Khởi tạo schema PostgreSQL ở môi trường staging, chốt mô hình users/Auth và quyền truy cập trước khi triển khai đăng nhập. Bảng leads hiện độc lập với users.
3. Dùng công cụ import bên dưới với dry-run và transaction; bảo toàn created_at (chuẩn hóa UTC), ID nguồn vào `legacy_sqlite_id`/`legacy_duckdb_id`, chống trùng theo `source-id` và ID SQLite. Không gộp theo email vì một người có thể gửi nhiều nhu cầu.
4. Tạm dừng ghi leads, sao lưu cuối, nhập dữ liệu staging rồi đối chiếu tổng số, nội dung, timestamp và khóa nguồn. Nếu giữ ID chính, điều chỉnh identity sequence. Thử rollback và import lại trước production.
5. Khi đã xác nhận dữ liệu và quyền, nhập production rồi đặt LEADS_BACKEND=postgres và DATABASE_URL trong Secrets; thử biểu mẫu, restart và kiểm tra dữ liệu bền vững. Không cần chuyển catalog/embeddings.
6. Giữ SQLite gốc để đối soát. Nếu phải quay lại SQLite sau khi PostgreSQL đã nhận lead mới, dừng ghi và xuất/đối soát phần phát sinh trước khi đổi backend để tránh thất lạc. Không xóa dữ liệu gốc trong giai đoạn chuẩn bị.

Kiểm tra không cần database: `python -m unittest discover -s tests` (bỏ qua tests tích hợp nếu không có TEST_DATABASE_URL). Hướng dẫn PostgreSQL test riêng ở bên dưới.

### Migration SQL có phiên bản

Chạy tường minh `python -m data.postgres --init-schema` bằng tài khoản DDL. Runner áp dụng `001_create_leads.sql`, `002_sqlite_source_identity.sql`, `003_internal_accounts.sql` theo thứ tự trong một transaction, dùng advisory lock ngăn hai runner chạy đồng thời, lưu phiên bản và SHA-256 vào `business.schema_migrations`. Chạy lại không áp dụng lại; sửa file đã áp dụng sẽ gây lỗi và rollback. Thêm file phiên bản mới khi đổi schema, không sửa migration đã chạy. Không tự chạy schema migration khi khởi động app hoặc gửi form.

Schema đã tạo bằng bước chuẩn bị cũ được tiếp nhận bởi migration 001, sau đó nâng cấp bởi 002. ID SQLite đã có được gán namespace `legacy-default`; nếu đây là nguồn đã import trước đó, tiếp tục dùng `--source-id legacy-default`. Schema khác với bản chuẩn cần đối chiếu trước khi áp dụng.

### Import SQLite → PostgreSQL / Supabase

Chỉ chạy import thật khi đã có yêu cầu thực hiện trên database đích. Trước khi thao tác production, dừng ghi leads, sao lưu SQLite và đặt DATABASE_URL tới đúng đích bằng secrets/môi trường. Lệnh không phụ thuộc LEADS_BACKEND và không tự áp dụng DDL; chạy schema migration trước.

```powershell
# DATABASE_URL đã được cấu hình; không đặt URI thật vào Git hoặc lịch sử lệnh chia sẻ.
python -m data.postgres --init-schema
python -m data.migrate_leads --source data/leads.sqlite3 --source-id local-main --dry-run
python -m data.migrate_leads --source data/leads.sqlite3 --source-id local-main --apply
# Chạy lại cùng source-id: các dòng giống hệt được skipped, không tạo trùng.
python -m data.migrate_leads --source data/leads.sqlite3 --source-id local-main --apply
```

Chọn `source-id` ổn định cho từng nguồn SQLite, dùng lại ngay cả khi đổi tên/di chuyển file. Không đổi source-id để thử lại cùng nguồn vì sẽ tạo namespace mới. Khóa duy nhất `(legacy_sqlite_source, legacy_sqlite_id)` chống nhập trùng kể cả khi import đồng thời. PostgreSQL cấp ID chính mới; ID SQLite được giữ ở cột legacy nên không cần reset sequence. `legacy_duckdb_id` được bảo toàn nếu cột tồn tại; trùng ID DuckDB từ nguồn khác sẽ báo failed để đối soát.

Nguồn được mở bằng SQLite URI `mode=ro`, query-only và snapshot đọc; không ALTER/UPDATE/xóa/đánh dấu dòng nguồn. Chuỗi kind/name/email/phone/note được giữ nguyên. created_at phải có timezone, được chuẩn hóa UTC; thời gian thiếu múi giờ hoặc dữ liệu không hợp lệ báo failed để sửa trên bản sao và đối soát. Không tự suy đoán múi giờ hay cắt nội dung.

Dry-run chỉ SELECT trên PostgreSQL trong transaction read-only: không ghi bảng hoặc tăng sequence, báo would_insert/skipped/failed dựa trên kiểm tra dữ liệu và đối chiếu đích. Đây là dự báo, không thực thi INSERT nên không xác nhận toàn bộ constraint/trigger/quyền INSERT; dữ liệu đích có thể đổi sau preview.

Apply dùng một transaction ngoài và savepoint mỗi dòng: dòng lỗi validation/constraint được failed, các dòng hợp lệ vẫn commit. Bản ghi trùng khóa nhưng khác nội dung là failed, không tự ghi đè. Sửa vấn đề và chạy lại cùng source-id. Lỗi kết nối/transaction/commit sẽ rollback toàn đợt, inserted=0 và failed=total. JSON trả `total`, `inserted` (đã commit), `skipped`, `failed`, `would_insert`, `dry_run`, `error`; exit code 0 khi không lỗi, 1 khi có failed/lỗi nguồn hoặc đích. Không in thông tin cá nhân hay URI kết nối. Nếu mất kết nối đúng lúc server commit, cần chạy lại cùng source-id để đối soát kết quả thay vì đổi nguồn.

Sau khi đối soát, đặt `LEADS_BACKEND=postgres` và DATABASE_URL trong Secrets/môi trường rồi khởi động lại app. Form gọi API `save_lead()` cũ; thành công chỉ hiện sau commit. Nếu lỗi, form giữ nội dung để thử lại, không fallback SQLite. App chỉ cần quyền ghi/đọc cần thiết, không cần quyền chạy migration. Catalog DuckDB, tìm kiếm, RAG, crawler và pipeline giữ nguyên.

### Kiểm thử PostgreSQL với dữ liệu giả

```powershell
docker run --name ocop-leads-test --rm -d -e POSTGRES_USER=ocop_test -e POSTGRES_PASSWORD=isolated-test-only -e POSTGRES_DB=ocop_leads_test -p 127.0.0.1:55439:5432 postgres:16
$env:TEST_DATABASE_URL = 'postgresql://ocop_test:isolated-test-only@127.0.0.1:55439/ocop_leads_test'
python -m unittest discover -s tests
docker stop ocop-leads-test
```

Tests chỉ chấp nhận TEST_DATABASE_URL có host localhost/127.0.0.1 và database `ocop_leads_test`; không lấy DATABASE_URL thật làm đích test. Mỗi test tái tạo và dọn schema business trên database test này: tuyệt đối không đặt dữ liệu thật vào đó. SQLite fixtures nằm trong thư mục tạm. Bao gồm lưu lead thấy được từ kết nối mới, rollback sau INSERT và lỗi commit bằng deferred trigger, đóng kết nối khi commit lỗi, migration schema lặp lại, dry-run không ghi, import hai lần không trùng, xung đột nội dung, lỗi từng dòng và báo cáo CLI. AppTest kiểm tra form giữ giá trị khi lỗi và gửi lại thành công.

## Bước 4 — đăng nhập nội bộ cho demo

Khách vẫn xem catalog, tìm kiếm và RAG mà không cần đăng nhập. Trang **Đăng nhập** dùng username/password nội bộ; không cấu hình Google, OIDC, Supabase Auth, callback URL hoặc email. Tài khoản và yêu cầu mới cần PostgreSQL/Supabase và `LEADS_BACKEND=postgres`. SQLite cũ chỉ phục vụ migration/đối soát; không có nhánh ghi SQLite để bỏ qua xác thực. Có thể dùng PostgreSQL local cho demo ngoại tuyến với dịch vụ Supabase.

### Áp dụng thủ công trên database bạn chọn

Code không tự chạy migration, seed hoặc đổi mật khẩu khi khởi động. Bước này chưa áp dụng migration 003 hay seed lên Supabase thật. Sau khi review PR, cấu hình DATABASE_URL ở môi trường hoặc Streamlit Secrets (URI Session pooler với sslmode=require), cài dependencies rồi chạy:

```powershell
python -m pip install -r requirements.txt
python -m data.postgres --init-schema
python -m data.accounts seed
python -m streamlit run src/app.py
```

Lệnh seed hỏi mật khẩu bằng prompt ẩn. Nhập mật khẩu demo chung đã thống nhất cho môn học; mật khẩu không nằm trong source, README, SQL hoặc đối số lệnh. Khi tự động hóa, có thể cung cấp biến môi trường riêng `DEMO_ACCOUNT_PASSWORD`, không commit giá trị vào repository và xóa biến sau khi dùng. Không có giá trị mặc định cho mật khẩu. Không dán mật khẩu vào chat hoặc cấu hình mẫu.

Seed tạo 5 tài khoản nếu thiếu: `buyer01`, `buyer02` có role buyer; `seller01`, `seller02` có role seller; `admin01` có role admin. Username luôn strip rồi lowercase và chỉ nhận 3–32 ký tự ASCII a-z, 0-9, dấu gạch dưới; unique/check constraint trong PostgreSQL giữ cùng quy tắc. Chỉ lưu hash Argon2id có salt ngẫu nhiên từ argon2-cffi. Seed chạy lại báo created/skipped, giữ nguyên mọi mật khẩu, role và active của tài khoản đã tồn tại, kể cả tài khoản inactive.

Đổi mật khẩu bằng lệnh vận hành riêng, cũng nhập mật khẩu mới qua prompt ẩn (hoặc biến môi trường trên):

```powershell
python -m data.accounts set-password --username buyer01
```

Lệnh đổi mật khẩu không tự kích hoạt tài khoản inactive, không thay role, và tăng auth_version để vô hiệu hóa phiên đăng nhập cũ. Đây là công cụ vận hành với quyền DB, không phải chức năng reset password công khai. Không có đăng ký, quên mật khẩu hay xác minh email.

### Phạm vi quyền

| Vai trò | Gửi yêu cầu | Đọc/sửa yêu cầu | Tài khoản |
| --- | --- | --- | --- |
| Khách | Không | Không | Chỉ đăng nhập |
| Buyer | Nhu cầu mua / tìm nguồn hàng | Chỉ của mình | Không quản trị |
| Seller | Đăng ký nhà cung cấp | Chỉ đăng ký của mình | Không quản trị |
| Admin | Quản lý, không gửi thay người khác | Tất cả, kể cả leads cũ chưa có chủ | Xem danh sách và bật/tắt tài khoản khác |

Không có nút đổi role, chọn user_id, chuyển nhanh tài khoản hoặc đăng nhập thay người khác. Admin không thể tự khóa tài khoản đang dùng. Người dùng không được tự thay role. Chức năng seller hiện chỉ gồm đăng ký cung cấp và quản lý đăng ký của chính họ; không có danh sách nhu cầu buyer hoặc luồng nhận/chia sẻ lead tự động.

`data/auth.py` phát identity có chữ ký nội bộ sau khi kiểm tra mật khẩu. `st.session_state` chỉ giữ phiên gồm user_id, auth_version và chữ ký, không giữ role làm căn cứ phân quyền. Khóa chữ ký ngẫu nhiên tồn tại trong tiến trình; restart app hoặc refresh tạo phiên mới có thể yêu cầu đăng nhập lại, phù hợp demo. Không có cookie đăng nhập bền vững. Nút Đăng xuất xóa toàn bộ session state: identity, widget mật khẩu, bản nháp, dữ liệu riêng và lịch sử chat.

Mỗi hàm bảo vệ (`save_lead`, `read_leads`, `update_note`, `list_accounts`, `set_active`) đọc lại account từ DB trong transaction để kiểm tra active, auth_version và role. Khóa đọc giữ account nhất quán trong thao tác. Điều kiện owner nằm trong SQL, kể cả khi truyền trực tiếp ID lead khác; menu chỉ hỗ trợ điều hướng. Form không quyết định role hoặc chủ sở hữu. `save_lead` giữ 5 trường cũ và thêm keyword `session=...`; gọi thiếu session bị từ chối. Loại yêu cầu phải khớp role từ database. Trả thành công chỉ sau commit; lỗi lưu giữ nội dung form và không fallback.

Migration `003_internal_accounts.sql` chỉ thêm bảng users, cột nullable `leads.user_id` có foreign key và index. Không sửa hoặc xóa leads bước 3, không tự suy đoán chủ theo tên/email. Leads import bằng công cụ SQLite tiếp tục không có chủ sở hữu và chỉ admin đọc/sửa. Migrations 001/002 giữ nguyên checksum; runner vẫn chạy lại an toàn. Không công khai schema business qua Supabase Data API. Tài khoản DB dùng cho app cần USAGE schema business, SELECT users, SELECT/INSERT/UPDATE leads, UPDATE users cho quản trị và quyền sequence cần thiết; giữ quyền DDL/seed ở người vận hành. Đây là phân quyền trong ứng dụng demo, không phải hệ thống đăng nhập production với rate limiting/MFA/khôi phục tài khoản.

### Kiểm thử bước 4

Dùng TEST_DATABASE_URL riêng theo phần PostgreSQL test ở trên, không dùng DATABASE_URL thật. Tests tích hợp chỉ chấp nhận localhost/127.0.0.1 và database `ocop_leads_test`, tái tạo schema business mỗi test. Mật khẩu fixtures được sinh ngẫu nhiên; không dùng tài khoản hoặc dữ liệu thật.

```powershell
python -m unittest discover -s tests
```

Bao gồm đăng nhập đúng/sai/username không tồn tại/inactive; đăng xuất xóa dữ liệu riêng; buyer01 không đọc/sửa lead buyer02; buyer/seller bị chặn quản trị; seller bị chặn loại yêu cầu buyer; chữ ký identity giả bị từ chối; thay role/khóa account/đổi mật khẩu có hiệu lực với phiên cũ; seed lặp lại không đổi hash/role/active; username unique; leads cũ vẫn không chủ; commit/rollback và migration SQLite bước 3. AppTest kiểm tra màn hình login, lỗi login, login thành công, logout và form giữ dữ liệu khi lưu lỗi. Catalog/search/retrieval/crawlers/vectorization vẫn có tests hồi quy cũ.
