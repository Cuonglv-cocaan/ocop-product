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
| Buyer | Nhu cầu mua / tìm nguồn hàng; hồ sơ nhà cung cấp chờ duyệt | Chỉ của mình | Không quản trị |
| Seller | Hồ sơ đơn vị và cung ứng theo membership + approved | Yêu cầu cũ và đơn vị của mình | Không quản trị |
| Admin | Quản lý, không gửi thay người khác | Tất cả, kể cả leads cũ chưa có chủ | Xem danh sách và bật/tắt tài khoản khác |

Không có nút đổi role, chọn user_id, chuyển nhanh tài khoản hoặc đăng nhập thay người khác. Admin không thể tự khóa tài khoản đang dùng. Người dùng không được tự thay role. Seller quản lý hồ sơ/cung ứng của đơn vị mình theo phần nhà cung cấp phía dưới; không có danh sách nhu cầu buyer hoặc luồng nhận/chia sẻ lead tự động.

`data/auth.py` phát identity có chữ ký nội bộ sau khi kiểm tra mật khẩu. `st.session_state` chỉ giữ phiên gồm user_id, auth_version và chữ ký, không giữ role làm căn cứ phân quyền. Khóa chữ ký ngẫu nhiên tồn tại trong tiến trình; restart app hoặc refresh tạo phiên mới có thể yêu cầu đăng nhập lại, phù hợp demo. Không có cookie đăng nhập bền vững. Nút Đăng xuất xóa toàn bộ session state: identity, widget mật khẩu, bản nháp, dữ liệu riêng và lịch sử chat.

Mỗi hàm bảo vệ (`save_lead`, `read_leads`, `update_note`, `list_accounts`, `set_active`) đọc lại account từ DB trong transaction để kiểm tra active, auth_version và role. Khóa đọc giữ account nhất quán trong thao tác. Điều kiện owner nằm trong SQL, kể cả khi truyền trực tiếp ID lead khác; menu chỉ hỗ trợ điều hướng. Form không quyết định role hoặc chủ sở hữu. `save_lead` giữ 5 trường cũ và thêm keyword `session=...`; gọi thiếu session bị từ chối. Loại yêu cầu phải khớp role từ database. Trả thành công chỉ sau commit; lỗi lưu giữ nội dung form và không fallback.

Migration `003_internal_accounts.sql` chỉ thêm bảng users, cột nullable `leads.user_id` có foreign key và index. Không sửa hoặc xóa leads bước 3, không tự suy đoán chủ theo tên/email. Leads import bằng công cụ SQLite tiếp tục không có chủ sở hữu và chỉ admin đọc/sửa. Migrations 001/002 giữ nguyên checksum; runner vẫn chạy lại an toàn. Không công khai schema business qua Supabase Data API. Tài khoản DB dùng cho app cần USAGE schema business, SELECT users, SELECT/INSERT/UPDATE leads, UPDATE users cho quản trị và quyền sequence cần thiết; giữ quyền DDL/seed ở người vận hành. Đây là phân quyền trong ứng dụng demo, không phải hệ thống đăng nhập production với rate limiting/MFA/khôi phục tài khoản.

### Kiểm thử bước 4

Dùng TEST_DATABASE_URL riêng theo phần PostgreSQL test ở trên, không dùng DATABASE_URL thật. Tests tích hợp chỉ chấp nhận localhost/127.0.0.1 và database `ocop_leads_test`, tái tạo schema business mỗi test. Mật khẩu fixtures được sinh ngẫu nhiên; không dùng tài khoản hoặc dữ liệu thật.

```powershell
python -m unittest discover -s tests
```

Bao gồm đăng nhập đúng/sai/username không tồn tại/inactive; đăng xuất xóa dữ liệu riêng; buyer01 không đọc/sửa lead buyer02; buyer/seller bị chặn quản trị; seller bị chặn loại yêu cầu buyer; chữ ký identity giả bị từ chối; thay role/khóa account/đổi mật khẩu có hiệu lực với phiên cũ; seed lặp lại không đổi hash/role/active; username unique; leads cũ vẫn không chủ; commit/rollback và migration SQLite bước 3. AppTest kiểm tra màn hình login, lỗi login, login thành công, logout và form giữ dữ liệu khi lưu lỗi. Catalog/search/retrieval/crawlers/vectorization vẫn có tests hồi quy cũ.

## Hồ sơ nhà cung cấp và sản phẩm cung ứng

Phần này kế thừa `business.users`, Argon2id, session và phân quyền của bước 4; không tạo hệ thống tài khoản mới. Không có AGENTS.md trong repository/các thư mục cha đã kiểm tra. Tài khoản, leads và nhà cung cấp dùng cùng PostgreSQL; catalog và embeddings vẫn ở DuckDB. Không suy ra nhà cung cấp từ brand hoặc dữ liệu crawler.

### Chuẩn bị thủ công

Chưa chạy migration 004 hoặc seed nhà cung cấp trên Supabase thật. Bạn cần cài requirements, giữ DATABASE_URL Session pooler và LEADS_BACKEND=postgres, rồi chủ động chạy:

```powershell
python -m data.postgres --init-schema
# Chỉ chạy nếu chưa có tài khoản demo; nhập mật khẩu tại prompt ẩn:
python -m data.accounts seed
# Catalog phải có ít nhất hai sản phẩm; không ghi DuckDB khi seed:
python -m data.seed_suppliers
python -m streamlit run src/app.py
```

Migration `004_suppliers.sql` thêm `business.suppliers`, `business.supplier_members`, `business.supplier_products`; không đổi mật khẩu/roles hoặc sửa leads cũ. Migrations 001–003 giữ nguyên checksum. Role DB của ứng dụng cần SELECT/INSERT/UPDATE trên suppliers và supplier_products, SELECT/INSERT trên supplier_members, quyền sequence mới, cùng quyền users hiện có cho admin duyệt và chuyển buyer thành seller. Dùng tài khoản DDL riêng cho migration, không expose schema business qua Supabase Data API.

Suppliers lưu tên, loại đơn vị, mô tả, tỉnh/thành, email/điện thoại, vùng giao hàng, trạng thái, người tạo/người duyệt/thời điểm duyệt và lý do từ chối/tạm ngưng. Chỉ tên là bắt buộc; thông tin chưa biết giữ chuỗi rỗng (minimum_order giữ NULL) và giao diện hiện “Chưa cập nhật”. Không điền thông tin liên hệ, địa chỉ hay năng lực giả vào chỗ chưa biết.

Membership unique theo supplier_id + user_id; sản phẩm unique theo supplier_id + source + product_id. PostgreSQL chỉ FK tới suppliers/users trong cùng database, không FK sang DuckDB. Source được strip/uppercase, product_id là chuỗi giữ số 0 đầu. Hàm thêm/cập nhật cung ứng kiểm tra khóa hiện có trong catalog ở thời điểm thao tác. Không có transaction phân tán giữa DuckDB và PostgreSQL; nếu catalog thay đổi sau kiểm tra, liên kết vẫn là lịch sử và được kiểm tra lại khi hiển thị/cập nhật.

### Luồng đăng ký và quyền thao tác

1. Buyer hoặc seller vào **Nhà cung cấp → Đăng ký đơn vị mới**, nhập hồ sơ. Server tạo trạng thái pending, gắn người tạo và membership trong cùng transaction; form không nhận role, trạng thái hay user_id tùy chọn.
2. Người gửi xem hồ sơ/trạng thái của đơn vị mình. Có thể sửa hồ sơ pending/rejected. Hồ sơ rejected có hai thao tác lưu sửa hoặc **Gửi duyệt lại**; gửi lại chỉ chuyển rejected → pending, xóa quyết định cũ đang hiển thị, không tự approved.
3. Admin vào **Duyệt nhà cung cấp**, mặc định xem pending; có thể lọc mọi trạng thái, xem chi tiết và sản phẩm. Admin duyệt pending/rejected/suspended → approved, từ chối pending → rejected hoặc tạm ngưng approved → suspended. Từ chối và tạm ngưng cần lý do. Người duyệt và thời điểm là quyết định gần nhất; đây chưa phải nhật ký audit đầy đủ.
4. Chỉ thao tác duyệt của admin chuyển thành viên đang là buyer thành seller. Người dùng không tự nâng role, không tự thêm membership vào đơn vị khác và không thể sửa các trường kiểm duyệt qua hàm sửa hồ sơ. Tạm ngưng không hạ role; mỗi lần thao tác vẫn kiểm tra đúng supplier được chọn.
5. Seller quản lý hồ sơ approved và danh sách cung ứng của đơn vị mình. Cần đồng thời account active, role seller, membership hợp lệ và supplier approved cho thêm/cập nhật/ngừng cung ứng. Có role seller nhưng chưa thuộc đơn vị approved thì không được bán. Một tài khoản có thể thuộc nhiều đơn vị; ngưng A không chặn B còn approved. Suspended không được sửa hồ sơ hoặc thao tác cung ứng, nhưng thành viên vẫn xem lịch sử và lý do.

Quyền được kiểm tra trong `data/suppliers.py` với account đọc lại từ PostgreSQL, membership và khóa supplier trong cùng transaction, không chỉ dựa vào menu. Buyer/seller không gọi được danh sách quản trị hoặc hàm review. Admin xem và duyệt; không ghi cung ứng thay seller qua API người bán. Mọi kết quả thành công chỉ trả sau commit. Giao diện giữ form khi validation/database lỗi.

Biểu mẫu leads cũ tiếp tục dành cho nhu cầu mua của buyer. Đường đăng ký seller ở trang kết nối nay dẫn sang hồ sơ nhà cung cấp; không tạo thêm leads làm đăng ký đơn vị. Seller leads cũ vẫn thuộc lịch sử cá nhân của tài khoản, không cấp membership hoặc quyền cung ứng. Không tự chuyển leads cũ thành suppliers.

### Sản phẩm và lịch sử

Chọn sản phẩm theo cặp source + product_id. Có thể nhập số lượng đặt tối thiểu dương (số thập phân dùng dấu chấm), đơn vị tính, thời gian chuẩn bị, năng lực dạng mô tả và bật/tắt đang cung ứng. Lưu lại cùng khóa cập nhật liên kết hiện có, không tạo trùng. Không có chức năng xóa vật lý liên kết.

Sản phẩm đã bị xóa khỏi catalog vẫn giữ đủ thông tin cung ứng và khóa lịch sử, hiển thị **Sản phẩm không còn trong catalog**. Không cho tạo/bật lại/cập nhật thông tin cung ứng cho khóa thiếu; seller của đơn vị approved vẫn có thể chọn **Ngừng cung ứng liên kết hiện có**. Danh mục rỗng không còn chặn đăng nhập, trang hồ sơ, quản trị hoặc lịch sử. Tìm kiếm/catalog/RAG chỉ chạy khi catalog sẵn sàng và không bị thay đổi thuật toán.

### Seed mô phỏng và kiểm tra demo

`python -m data.seed_suppliers` yêu cầu seller01/seller02 active có role seller, admin01 active có role admin, và ít nhất hai khóa sản phẩm thực sự trong DuckDB. Thiếu điều kiện sẽ báo rõ và không ghi một phần. Lệnh không tự tạo tài khoản, không đổi mật khẩu và không tự chạy khi app khởi động.

Lần đầu tạo **Đơn vị A (Mô phỏng)** cho seller01, **Đơn vị B (Mô phỏng)** cho seller02, mỗi đơn vị liên kết một trong hai sản phẩm đầu tiên theo thứ tự source/product_id. Hai hồ sơ mẫu approved và gắn cờ/description dữ liệu mô phỏng; đây không phải chứng nhận cung ứng thật. Thông tin liên hệ/tỉnh/đơn vị tính/số lượng chưa biết để trống. `demo_key` duy nhất định danh mẫu ổn định; chạy lại bỏ qua toàn bộ đơn vị đã tạo (bao gồm membership/sản phẩm), không reset status hoặc ghi đè dữ liệu đã sửa. Nếu operator xóa/chỉnh liên kết, seed không tự phục hồi để tránh ghi đè chủ ý.

Kịch bản kiểm tra: buyer01 gửi hồ sơ → admin01 từ chối có lý do → buyer01 sửa/gửi lại → admin01 duyệt → tài khoản được đọc lại thành seller và quản lý cung ứng. Thử seller01 truy cập/sửa đơn vị B phải bị chặn; tạm ngưng A rồi thử ghi cung ứng A phải bị chặn; B vẫn hoạt động nếu tài khoản là thành viên. Xóa sản phẩm trên bản catalog test rồi kiểm tra lịch sử, không xóa dữ liệu catalog thật để demo.

Kiểm thử tự động dùng TEST_DATABASE_URL local `ocop_leads_test` riêng, dữ liệu/tài khoản giả và DuckDB tạm. Không dùng DATABASE_URL thật cho tests. Docker trong hướng dẫn test chỉ là database test tùy chọn, không phải thành phần triển khai Supabase:

```powershell
# TEST_DATABASE_URL đã trỏ tới PostgreSQL test riêng theo hướng dẫn phía trên.
python -m unittest discover -s tests -p test_suppliers.py -v
python -m unittest discover -s tests -p test_supplier_ui.py -v
python -m unittest discover -s tests
```

Tests bao gồm buyer không tự duyệt/nâng quyền; membership/role/status/inactive; seller01 bị chặn đọc quản trị và sửa B; luồng rejected → pending → approved; suspended và nhiều đơn vị; khóa source+product_id; dữ liệu thiếu và lịch sử catalog rỗng; seed lặp lại không trùng/không ghi đè; thiếu account/catalog không ghi sai; UI đăng ký/duyệt/lịch sử; cùng các tests hồi quy leads, đăng nhập, catalog, RAG, crawler và pipeline cũ.

## Nhu cầu → phân công → báo giá → kết nối

Migration `005_purchase_workflow.sql` thêm purchase_requests, request_matches, request_quotes và request_events trong schema business hiện tại. Dùng lại tài khoản nội bộ, session, supplier_members và kiểm duyệt suppliers; không tạo hệ thống đăng nhập khác. Không sửa/xóa/tự chuyển leads cũ: leads tự do có thể thiếu chủ sở hữu, số lượng và điều kiện nên vẫn ở trang liên hệ cũ với quyền xem hiện có.

### Chuẩn bị và dữ liệu mô phỏng

Chưa chạy migration 005 hoặc seed luồng mua hàng trên Supabase thật. Sau review, giữ DATABASE_URL và LEADS_BACKEND=postgres đã cấu hình rồi chủ động chạy bằng role DDL/operator:

```powershell
python -m data.postgres --init-schema
# Chỉ khi cần tài khoản/đơn vị mô phỏng; không chạy tự động:
python -m data.accounts seed
python -m data.seed_suppliers
# Tùy chọn: tạo duy nhất một nhu cầu OPEN mô phỏng cho buyer01:
python -m data.seed_purchase
python -m streamlit run src/app.py
```

Seed nhu cầu yêu cầu buyer01 active với role buyer; không tạo tài khoản, đổi role hoặc bỏ qua mật khẩu trong giao diện. Lệnh operator tạo phiếu có nhãn MÔ PHỎNG, email thuộc miền example.invalid, số lượng 10 hộp, ngân sách mẫu VND và hạn giao tính từ ngày chạy. Nếu có catalog, dùng khóa sản phẩm đầu tiên thực sự tồn tại; nếu catalog rỗng thì không có sản phẩm tham chiếu. demo_key duy nhất giúp chạy lại bỏ qua toàn bộ phiếu đã có, không đổi nội dung/status/deadline đã chỉnh. Seed không phân công, gửi báo giá, lựa chọn hoặc xác nhận connected thay người dùng. Hai đơn vị mẫu vẫn cần admin phân thủ công qua giao diện.

Role DB của app cần SELECT/INSERT/UPDATE trên purchase_requests/request_matches/request_quotes, SELECT/INSERT trên request_events và quyền dùng các sequence mới, cùng quyền supplier/users đã có. Không cấp sửa/xóa request_events cho role ứng dụng; dùng role DDL/operator riêng, không expose schema business qua Supabase Data API.

### Phiếu nhu cầu và đơn vị tiền

Trang **Nhu cầu** có giao diện theo role. Buyer tạo phiếu với tiêu đề, danh mục, mô tả, số lượng/đơn vị, ngân sách tùy chọn, budget_type per_unit/total, địa điểm và hạn giao, yêu cầu bổ sung. buyer_id luôn lấy từ session được kiểm tra lại từ DB, không có trường chọn buyer hoặc status trong form. Sản phẩm tham chiếu tùy chọn là source + product_id; nút Yêu cầu kết nối từ chi tiết catalog chuyển tới trang này và điền sẵn khóa, tiêu đề, danh mục. Khách đăng nhập xong giữ đúng phần tham chiếu công khai; không giữ lại dữ liệu riêng hoặc mật khẩu từ phiên trước.

Quantity dùng NUMERIC(18,3) và Decimal, bắt buộc dương. Budget/unit_price/shipping_fee/total_amount dùng NUMERIC(18,2), không âm, chỉ tiền VND; API không nhận float hoặc số vượt precision. Đơn vị tính là chuỗi đã strip và báo giá phải dùng đúng đơn vị trên phiếu. Ngân sách dùng để so sánh, không tự cấm báo giá vượt ngân sách. Hạn giao là ngày tại múi giờ Asia/Bangkok, không được tạo/sửa về quá khứ. Không tự quy đổi đơn vị hoặc tiền tệ.

Buyer sửa toàn bộ điều kiện chỉ khi phiếu còn open và chưa từng có request_match. Phân công đầu tiên khóa việc sửa, kể cả nếu nhà cung cấp sau đó từ chối. Muốn thay điều kiện: hủy phiếu và tạo nhu cầu mới. Không có xóa phân công hoặc mở lại phiếu đã đóng để lách khóa. Khóa request trong transaction ngăn sửa/phân công chạy chồng nhau.

### Quyền và thông tin liên hệ

Buyer chỉ xem/sửa/chọn/đóng nhu cầu của chính mình. Admin xem mọi phiếu, phân đơn vị approved, theo dõi và có thể hủy/đóng không tìm được phương án; không chọn báo giá hoặc xác nhận connected thay buyer. Seller chỉ thấy phiếu có phân công cho đơn vị mà mình là thành viên và vẫn approved; role seller riêng không đủ. Một phiếu phân nhiều đơn vị được, nhưng UNIQUE(request_id,supplier_id) ngăn trùng. Không có AI matching, thanh toán hoặc gửi email tự động.

Phiếu có phần liên hệ riêng (tên/email/điện thoại) vì accounts hiện chỉ có username/password. Nhập ít nhất email hoặc điện thoại; đây là dữ liệu do buyer nhập cho phiếu, không suy ra từ leads hoặc email để gán chủ. Không đặt liên hệ vào mô tả/địa điểm/yêu cầu bổ sung. Server chặn việc chép nguyên email/điện thoại đã nhập vào các trường nội dung chia sẻ; không phải công cụ nhận diện mọi thông tin cá nhân trong văn bản tự do.

API request_detail loại bỏ contact_name/contact_email/contact_phone và buyer_id khỏi dữ liệu trả cho seller trước lựa chọn. Seller cũng không nhận báo giá/lý do từ chối/lịch sử phản hồi của đơn vị khác. Buyer thấy các phương án nhưng chưa nhận email/điện thoại nhà cung cấp qua API này trước khi chọn. Admin cũng chưa thấy liên hệ buyer qua API luồng mua hàng trước lựa chọn. Buyer luôn đọc được liên hệ của chính mình.

Sau selected/connected, chỉ đơn vị thắng được xem liên hệ buyer; buyer xem tên/email/điện thoại đơn vị đã chọn từ hồ sơ supplier. Đơn vị không được chọn không được mở liên hệ, kể cả đã từng gửi báo giá. Thông tin supplier còn thiếu hiện Chưa cập nhật; nhà cung cấp cập nhật tại hồ sơ của mình. Khi phiếu cancelled/closed_no_match, API không mở liên hệ cho các bên còn lại. Đây là lọc dữ liệu ở tầng server, không chỉ ẩn cột Streamlit. Không cache dữ liệu riêng; logout vẫn xóa session state.

### Phiên bản báo giá và lựa chọn

Seller chọn một phân công thuộc đơn vị của mình để gửi báo giá hoặc báo không thể đáp ứng kèm lý do. Mỗi phản hồi đều có event, actor và thời điểm. Có thể gửi lại sau một lần từ chối nếu phiếu còn nhận phản hồi; lịch sử từ chối không bị xóa. Phiếu quoted có thể không còn báo giá active nếu tất cả đã từ chối; buyer/admin tự đóng closed_no_match, không tự chọn phương án.

Báo giá gồm số lượng đáp ứng >0 và không vượt nhu cầu, đúng đơn vị, đơn giá, phí giao (để trống nếu chưa biết/chưa gồm), ngày giao dự kiến từ hôm nay đến hạn giao của phiếu, hiệu lực có múi giờ, ghi chú và chi phí chưa bao gồm. Chi phí chưa gồm phải ghi rõ hoặc ghi Không có; khi phí giao để trống server tự thêm chú thích phí giao chưa nằm trong tổng.

Server tính tổng = round(quantity × unit_price + shipping_fee nếu có, 2), Decimal ROUND_HALF_UP; PostgreSQL CHECK kiểm tra lại công thức. Form không gửi total_amount. Chỉ tạo phiên bản mới, đánh dấu bản active cũ superseded, không sửa nội dung bản cũ. Báo giá đã chọn giữ nguyên; sau selected không nhận thêm báo giá hoặc từ chối.

Buyer so sánh các phiên bản, số lượng, giá, tổng, phí chưa gồm, ngày giao và hiệu lực. Chỉ chọn bản active còn hiệu lực của đúng phiếu, supplier vẫn approved và phiếu chưa qua hạn giao. Các báo giá hết hạn hoặc đã thay thế vẫn đọc được như lịch sử nhưng không chọn được. Lựa chọn chạy dưới khóa FOR UPDATE của phiếu, cùng update quote/match/status và event trong một transaction; partial unique index bảo đảm tối đa một quote selected và một match selected cho mỗi phiếu. Hai thao tác chọn đồng thời chỉ một thành công; lỗi ghi event rollback toàn bộ thao tác.

**Selected chỉ là lựa chọn để tiếp tục trao đổi, chưa phải đơn hàng hoặc bằng chứng giao dịch thành công.** Chỉ buyer chủ sở hữu bấm xác nhận đã kết nối để chuyển connected; connected xác nhận việc kết nối trao đổi, không xác nhận giao hàng/thanh toán.

| Trạng thái hiện tại | Thao tác hợp lệ |
| --- | --- |
| open | Buyer sửa; admin phân → assigned; buyer/admin hủy hoặc đóng không có phương án |
| assigned | Admin phân thêm; seller báo giá → quoted hoặc từ chối; buyer/admin hủy/đóng |
| quoted | Admin phân thêm; seller gửi phiên bản mới/từ chối; buyer chọn → selected; buyer/admin hủy/đóng |
| selected | Chỉ buyer sở hữu xác nhận → connected; buyer/admin có thể hủy; không thay lựa chọn |
| connected, cancelled, closed_no_match | Chỉ xem lịch sử; không nhận sửa, phân công, phản hồi, báo giá hoặc lựa chọn mới |

Không tự đóng khi hết ngày; khi đã quá hạn giao, API chặn phân công/báo giá/lựa chọn và cho buyer/admin hủy hoặc đóng theo quy tắc. Không có trạng thái tự mở lại. request_events lưu actor_id, thời gian, loại và nội dung, bao gồm tạo/sửa/phân/quote/từ chối/chọn/đóng; seller chỉ đọc event của phân công thuộc đơn vị mình. Trạng thái và lịch sử cập nhật cùng transaction.

### Kịch bản demo và kiểm thử

1. Buyer01 tạo nhu cầu (hoặc dùng phiếu mô phỏng open), xác nhận số lượng/đơn vị/địa điểm/hạn giao và liên hệ riêng. Buyer02 không đọc/sửa/chọn hộ phiếu này.
2. Admin01 vào Nhu cầu, phân đơn vị A và B đã approved. Phân trùng bị chặn; lúc này buyer không sửa điều kiện được.
3. Seller01 chỉ thấy phân công A, nhập báo giá cùng đơn vị tính; thử gửi lại để xem phiên bản cũ superseded. Seller02 có thể báo giá B hoặc từ chối có lý do. Hai seller chưa xem liên hệ buyer hoặc báo giá của nhau.
4. Buyer01 so sánh và chọn đúng một báo giá còn hiệu lực, đọc cảnh báo chưa phải đơn hàng. Chỉ nhà cung cấp được chọn mở được liên hệ buyer.
5. Buyer01 xác nhận đã kết nối để trao đổi. Sau connected mọi thao tác thay đổi nghiệp vụ bị chặn. Có thể dùng phiếu khác để thử hủy hoặc đóng không có phương án.

Kiểm thử chỉ dùng TEST_DATABASE_URL local `ocop_leads_test`, không lấy DATABASE_URL thật. Các fixtures tạo users/suppliers/catalog và nhu cầu mô phỏng trong PostgreSQL/DuckDB test riêng. Tests concurrency dùng hai kết nối thật tới database test, không dùng mock để chứng minh một lựa chọn.

```powershell
python -m unittest discover -s tests -p test_purchase.py -v
python -m unittest discover -s tests -p test_purchase_ui.py -v
python -m unittest discover -s tests
```

Bao gồm luồng buyer → admin → seller → buyer → connected, quyền khác buyer/membership/approved, thiếu hoặc giả owner, thời gian/số tiền/float không hợp lệ, hết hạn, supplier suspended, giữ phiên bản, từ chối/gửi lại, đóng phiếu, double selection đồng thời, rollback quote/selection khi event lỗi, seed hai lần và UI cho buyer/admin/seller. Catalog, crawler, embeddings, RAG, leads cũ và schema 001–004 giữ nguyên.

## Matching theo quy tắc và hiệu quả kết nối

Migration `006_matching_metrics.sql` bổ sung các khai báo có cấu trúc vào `supplier_products`: `category`, `service_regions` (danh sách tỉnh/thành), `preparation_days` (ngày nguyên), `reference_price` (VND mỗi đơn vị), `reference_price_unit`. Tái sử dụng `minimum_order`, `unit`, `is_active`; giữ nguyên `preparation_time`, `capacity_description`, `suppliers.delivery_areas` dạng mô tả và không tự chuyển chúng thành dữ liệu xác minh. Buyer khai báo thêm `purchase_requests.delivery_region`, tách khỏi địa chỉ giao tự do. Dữ liệu cũ để trống/NULL nên kết quả có thể cần xác nhận. Nhà cung cấp tự nhập dữ liệu qua form cung ứng; khai báo không đồng nghĩa đã được kiểm chứng.

Áp dụng migration bằng lệnh operator `python -m data.postgres --init-schema` trước khi chạy phiên bản app này. Không tự chạy migration/seed khi mở app; không sửa các migration 001–005 đã áp dụng. Migration 006 cũng thêm `purchase_requests.is_demo`, đánh dấu các phiếu có `demo_key` cũ là mô phỏng, và thêm `request_matches.matching_snapshot` JSONB / `rule_version`. Seed nhu cầu mới đặt `is_demo=true`; giữ nguyên tính chống trùng. Không có dịch vụ AI trả phí, Redis, vector database hoặc framework agent mới. Quyền bảng/sequence giữ như bước trước; dashboard chỉ cần đọc các bảng nghiệp vụ hiện có.

### Thuật toán rules-v1

`data.matching.find_candidates(session, request_id)` chỉ admin được gọi, trả một lần mỗi supplier approved có liên kết sản phẩm `is_active=true`. Không suy ra supplier từ brand hay việc xuất hiện trong catalog. Không đọc giá catalog, embedding, sao OCOP hoặc mô tả để khẳng định giá sỉ, năng lực hay chứng nhận đã xác minh. Mỗi ứng viên có toàn bộ sản phẩm đang cung ứng, được xếp theo kết quả tốt nhất; UI hiển thị tối đa ba sản phẩm đầu. Một sản phẩm phải được đánh giá trọn vẹn, không ghép các điều kiện tốt của nhiều sản phẩm thành một phương án giả.

| Tiêu chí bắt buộc khi áp dụng | Đáp ứng và điểm | Không đáp ứng / chưa có dữ liệu |
| --- | --- | --- |
| Sản phẩm/danh mục | 40: đúng `(source, product_id)` **hoặc** danh mục khai báo trùng danh mục nhu cầu | Khác khóa và khác danh mục đã biết: loại. Nhu cầu chỉ định khóa, không có danh mục thay thế, khóa khác: loại. Thiếu danh mục cần để so sánh: cần xác nhận. |
| Khu vực | 20: tỉnh/thành giao có trong danh sách phục vụ khai báo | Đủ hai bên nhưng không trùng: loại. Thiếu một bên: cần xác nhận. |
| Đặt tối thiểu | 15: nhu cầu ≥ minimum_order, cùng đơn vị | Dưới tối thiểu: loại. Thiếu số hoặc đơn vị khác/chưa biết: cần xác nhận; không tự quy đổi kg/hộp. |
| Chuẩn bị | 15: preparation_days ≤ số ngày từ ngày đánh giá đến hạn giao | Không kịp: loại. Thiếu số ngày: cần xác nhận. Đây là thời gian chuẩn bị, vận chuyển vẫn cần xác nhận riêng. |
| Ngân sách | 10: giá tham khảo khai báo cùng đơn vị, ≤ ngân sách trên cùng cơ sở | `per_unit`: so đơn giá; `total`: nhân đơn giá × quantity. Vượt: loại. Thiếu giá/khác đơn vị: cần xác nhận. Buyer không đặt ngân sách: không áp dụng, 0 điểm. |

So sánh danh mục/tỉnh thành/đơn vị bằng Unicode NFC, casefold và gộp khoảng trắng; không bỏ dấu, không dùng substring, không đồng nhất tên viết tắt hay “toàn quốc” thành danh sách đã xác nhận. Ví dụ buyer và supplier cùng ghi `Hồ Chí Minh`; `TP.HCM` chưa tự quy đổi. Ngày đánh giá tại `Asia/Ho_Chi_Minh`. Không tự tách địa chỉ tự do, không tự trích ngày từ “khoảng 3–5 ngày”.

Từng tiêu chí trả `met` (Đáp ứng), `failed` (Không đáp ứng), `unknown` (Chưa có dữ liệu/cần xác nhận); ngân sách không đặt trả `not_applicable`. Có bất kỳ failed → nhóm **Bị loại**; không failed nhưng có unknown → **Cần xác nhận**; còn lại → **Đề xuất chính**. Thiếu dữ liệu không được cộng điểm. Tổng là **điểm phù hợp theo quy tắc**, tối đa 100 (không đặt ngân sách tối đa 90), không phải xác suất thành công. Nhóm được ưu tiên trước điểm; trong nhóm điểm giảm dần, bằng điểm sắp theo supplier_id tăng dần. Sản phẩm bằng nhóm/điểm sắp source, product_id để kết quả ổn định.

**Giá catalog** là giá bán tham khảo từ sàn; **giá tham khảo nhà cung cấp** là tự khai báo VND mỗi đơn vị, chưa xác nhận vận chuyển/thuế; **báo giá thực tế** là `request_quotes` có số lượng, chi phí và phiên bản cho một lượt phân. Không thay thế ba loại giá cho nhau. Điểm ngân sách dựa trên phần giá tham khảo có thể so sánh, không khẳng định tổng chi phí cuối cùng. Quy tắc không cấm seller gửi báo giá thực tế vượt ngân sách theo luồng cũ.

Admin vào chi tiết Nhu cầu, bật **Hiển thị kết quả matching**, xem các nhóm, lý do và thông tin thiếu. Chọn ứng viên, xác nhận đã kiểm tra rồi bấm **Xác nhận phân ứng viên**. Mở màn hình/chạy matching chỉ đọc, không tạo match/event hay gửi email/thông báo. Server kiểm tra lại quyền, trạng thái phiếu, approved và dữ liệu cung ứng; tính lại điểm rồi lưu snapshot lý do/sản phẩm/điểm/ngày đánh giá và `rules-v1` cùng transaction tạo match/event. Snapshot cũ không tính lại khi supplier thay dữ liệu. Nhóm cần xác nhận vẫn cho admin chủ động phân sau xác nhận, nhóm bị loại không được phân bằng nút gợi ý. Form **Phân đơn vị đã duyệt** thủ công vẫn hoạt động bình thường và không áp quy tắc loại; các phân thủ công có snapshot/version NULL để phân biệt nguồn quyết định.

### Định nghĩa KPI

Trang **Hiệu quả kết nối** và API `data.metrics.dashboard` chỉ admin. Bộ lọc ngày lấy **nhóm yêu cầu được tạo** từ 00:00 ngày bắt đầu đến trước 00:00 ngày kế tiếp sau ngày kết thúc ở `Asia/Ho_Chi_Minh`. Không lọc ngày phân/báo giá riêng. Trạng thái và lịch sử của nhóm đó phản ánh **đến thời điểm xem**; các lần phân/báo giá sau khoảng ngày chọn vẫn được tính. Đọc các bảng trong một transaction REPEATABLE READ, không cache dữ liệu riêng. Timestamp DB là TIMESTAMPTZ; hiển thị timestamp theo `Asia/Ho_Chi_Minh` (UTC+07:00), tương đương offset Asia/Bangkok cũ.

| KPI | Cách tính trên nhóm yêu cầu đã chọn |
| --- | --- |
| Yêu cầu tạo | DISTINCT request_id trong nhóm. |
| Yêu cầu đã phân | DISTINCT request_id có ít nhất một request_match. |
| Tỷ lệ có báo giá | DISTINCT request_id có ít nhất một request_quote / DISTINCT request_id đã phân. Đếm cả lịch sử superseded/selected, không chỉ bản active. |
| Trung vị từ phân đến báo giá đầu | Trên từng lượt phân (match) có báo giá: thời điểm báo giá đầu của match trừ assigned_at của chính match; lấy trung vị giờ của các lượt đó. Không lấy mốc phân của supplier khác. Chưa có báo giá không tính thành 0. |
| Buyer chọn báo giá | DISTINCT request_id có event selected hoặc selected_quote_id; vẫn ghi nhận từng chọn nếu sau đó hủy. |
| Buyer xác nhận connected | DISTINCT request_id có trạng thái connected. Chỉ xác nhận kết nối trao đổi, không phải doanh thu/giao dịch thành công. |
| Hủy / đóng không tìm nguồn | Đếm riêng DISTINCT request_id có trạng thái cancelled / closed_no_match. |
| Theo supplier: được phân | Số match duy nhất (mỗi request/supplier chỉ có một match theo schema). |
| Theo supplier: phản hồi | Số match có ít nhất một event declined/quoted hoặc một quote đã gửi. Từ chối là phản hồi, không phải báo giá. |
| Theo supplier: gửi báo giá | Số match có ít nhất một quote, không phải số phiên bản. |
| Theo supplier: thời gian phản hồi | Trên từng match: phản hồi đầu (từ chối hoặc báo giá) trừ assigned_at của chính match; hiển thị trung vị giờ của các match đã phản hồi. |

Mẫu số 0 hoặc không có khoảng thời gian hợp lệ: **Chưa có dữ liệu**, không hiện 0% hay thời gian 0 giả. Các số lượng thực sự bằng 0 vẫn hiển thị 0. Một yêu cầu phân hai đơn vị và có ba phiên bản báo giá vẫn chỉ tính một yêu cầu đã phân/có báo giá. Lọc supplier thu hẹp nhóm tới yêu cầu từng phân cho supplier đó và chỉ xét lượt phân/báo giá/phản hồi của đơn vị đó; KPI chọn/connected vẫn là kết quả của yêu cầu, không quy công cho supplier đang lọc (buyer có thể chọn đơn vị khác).

Bộ lọc **Thật / Mô phỏng** không có lựa chọn trộn. Phiếu có is_demo, demo_key hoặc **bất kỳ** lượt phân cho supplier.is_demo đều thuộc nhóm mô phỏng, kể cả phân lẫn supplier thật và mẫu. Vì vậy báo giá supplier mẫu không làm tăng KPI thật. Supplier bị suspended sau khi phân vẫn giữ lịch sử trong KPI, nhưng không còn là ứng viên matching.

### Demo và đối chiếu

1. Áp dụng migration 006 bằng role operator; đăng nhập seller và khai báo danh mục `Trà`, khu vực `Hồ Chí Minh`, tối thiểu `5 hộp`, chuẩn bị `2` ngày, giá tham khảo `50 VND / hộp` cho một sản phẩm đang cung ứng của đơn vị approved. Có thể dùng các đơn vị mô phỏng từ seed trước; không tự seed phản hồi hay sửa dữ liệu thật.
2. Buyer tạo nhu cầu cùng danh mục/tham chiếu, `10 hộp`, tỉnh/thành `Hồ Chí Minh`, ngân sách tổng `1000`, hạn sau 7 ngày. Admin thấy 100/100. Xóa số ngày chuẩn bị → Cần xác nhận; đổi giá thành 101 → vượt ngân sách; đổi thời gian thành 8 ngày → Bị loại. Khác đơn vị → Cần xác nhận; tạm ngưng đơn vị → không xuất hiện.
3. Mở matching nhiều lần kiểm tra chưa có phân công; xác nhận phân, đọc snapshot. Seller đổi giá, snapshot cũ giữ nguyên. Có thể tiếp tục dùng phân thủ công bình thường.
4. Tạo bốn nhu cầu trong cùng khoảng: R1 connected, R2 cancelled sau phân và từ chối, R3 closed_no_match chưa phân, R4 open chưa phân. R1 phân A lúc t0, B lúc t0+1h; A báo giá t0+2h và +4h, B báo giá +5h. R2 phân A lúc t0 và từ chối +1h. Đối chiếu: tạo 4, phân 2, có báo giá 1, tỷ lệ 50%, trung vị báo giá đầu theo lượt phân là median(2h, 4h) = 3h, selected 1, connected 1, hủy 1, không nguồn 1. A: phân 2/phản hồi 2/có báo giá 1/trung vị phản hồi 1.5h; B: 1/1/1/4h. Đây là fixture tự động, không nạp vào số liệu thật.
5. Dashboard chọn ngày tạo, supplier và đúng loại dữ liệu. Chuyển buyer/seller hoặc gọi API trực tiếp phải bị chặn. Chưa có phân công hiển thị Chưa có dữ liệu cho tỷ lệ/thời gian.

Kiểm thử dùng database test local riêng theo hướng dẫn trên:

```powershell
python -m unittest discover -s tests -p test_matching_metrics.py -v
python -m unittest discover -s tests -p test_matching_dashboard_ui.py -v
python -m unittest discover -s tests
```
