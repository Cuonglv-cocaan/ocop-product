# OCOP Connect — Kết nối cung cầu sản phẩm OCOP

Ứng dụng Streamlit hỗ trợ tra cứu sản phẩm OCOP, tư vấn tìm sản phẩm bằng AI và quản lý quá trình kết nối người mua với nhà cung cấp. Dữ liệu sản phẩm được thu thập từ Tiki, TikTok và Bưu điện; nhà cung cấp đăng ký và khai báo năng lực cung ứng riêng để quản trị viên xét duyệt.

Hệ thống ghi nhận nhu cầu, phân nhà cung cấp, báo giá và xác nhận đã kết nối trao đổi. Trạng thái `connected` không xác nhận thanh toán, giao hàng hoặc doanh thu.

## Chức năng và phân quyền

Điều hướng dùng slug ASCII trong URL: `?page=home`, `products`, `regions`, `demand`, `login`, `quotes`, `supply`, `supplier-registration`, `admin`, `dashboard`. URL đồng bộ với menu và các nút chuyển trang. Logo là nút Streamlit về trang chủ, giữ phiên đăng nhập và bản nháp. Trang không thuộc quyền của tài khoản hoặc slug không hợp lệ được đưa về trang chủ; URL không cấp thêm quyền truy cập.

| Người dùng | Chức năng |
| --- | --- |
| Khách | Xem/lọc sản phẩm, khám phá theo tỉnh, hỏi AI, mở gian hàng nguồn; gửi nhu cầu liên hệ không cần đăng nhập. |
| Người mua (`buyer`) | Tạo và theo dõi phiếu nhu cầu của mình, chọn báo giá, xác nhận kết nối; đăng ký hồ sơ nhà cung cấp. |
| Nhà cung cấp (`seller`) | Quản lý hồ sơ và sản phẩm cung ứng của đơn vị theo membership; xem và phản hồi các phiếu được phân cho đơn vị đã duyệt. |
| Quản trị viên (`admin`) | Duyệt/tạm ngưng nhà cung cấp, xem yêu cầu liên hệ, phân nhà cung cấp thủ công hoặc theo gợi ý, xem KPI, bật/tắt tài khoản khác. |

Phân quyền được kiểm tra ở lớp dữ liệu bằng tài khoản hiện hành trong PostgreSQL, không chỉ ẩn menu. Mật khẩu lưu bằng Argon2id; phiên chứa identity có chữ ký và `auth_version`. Đổi mật khẩu hoặc khóa tài khoản làm phiên cũ mất hiệu lực. Đăng xuất xóa session state và bản nháp; hội thoại trong database được giữ để nghiên cứu, không hiển thị lại sau đăng nhập. Chưa có đăng ký tài khoản công khai, quên mật khẩu hoặc Supabase Auth/OIDC.

## Kiến trúc và lưu trữ

```text
Tiki / TikTok / Bưu điện → CSV crawler → pipeline chuẩn hóa → DuckDB
                                                 ├─ products → catalog và bộ lọc
                                                 └─ embeddings → tìm kiếm AI / RAG

Giao diện Streamlit → lớp nghiệp vụ Python → PostgreSQL / Supabase
                                            ├─ users, leads
                                            ├─ suppliers, supplier_members, supplier_products
                                            └─ purchase_requests, request_matches,
                                               request_quotes, request_events
```

| Thành phần | Vai trò |
| --- | --- |
| `src/app.py` | Giao diện chính, catalog, trang vùng miền và biểu mẫu khách. |
| `src/search.py`, `src/vectorization.py` | Truy xuất sản phẩm, hội thoại AI và tạo embeddings tăng dần. |
| `src/auth_ui.py`, `src/supplier_ui.py`, `src/purchase_ui.py`, `src/dashboard_ui.py` | Giao diện tài khoản, nhà cung cấp, nhu cầu/báo giá và KPI. |
| `data/database.py`, `data/init_db.sql` | Catalog DuckDB, nhập dữ liệu, nâng cấp schema và export catalog. |
| `data/auth.py`, `data/accounts.py`, `data/leads.py` | Xác thực nội bộ, quản trị tài khoản và yêu cầu liên hệ. |
| `data/suppliers.py`, `data/purchase.py` | Hồ sơ cung ứng và luồng kết nối có trạng thái. |
| `data/matching.py`, `data/metrics.py` | Chấm điểm theo quy tắc và tính KPI từ lịch sử nghiệp vụ. |
| `data/postgres.py`, `data/migrations/` | Transaction PostgreSQL và migration SQL có phiên bản. |
| `crawlers/`, `pipelines/sync_products.py` | Thu thập và đồng bộ sản phẩm theo nguồn. |
| `tests/` | Kiểm thử logic, giao diện và tích hợp PostgreSQL tùy chọn. |

Catalog và embeddings dùng DuckDB. Dữ liệu nghiệp vụ dùng PostgreSQL/Supabase; SQLite chỉ phục vụ công cụ legacy và migration, không phải backend thay thế cho giao diện hiện tại. Ứng dụng không đọc trực tiếp CSV crawler.

Catalog công khai và danh sách sản phẩm tham chiếu dùng `st.cache_data(ttl=600)`, khóa cache gồm đường dẫn, mtime/kích thước DuckDB và WAL nếu có. Chỉ lớp giao diện cache `suppliers.catalog_items()`; kiểm tra nghiệp vụ ở lớp dữ liệu vẫn đọc trực tiếp. Gian hàng hiển thị 12 sản phẩm/trang trong `st.fragment`, nên đổi bộ lọc/phân trang không chạy lại toàn bộ trang. Đổi bộ lọc, sắp xếp hoặc xóa bộ lọc đưa danh sách về trang 1; giữ nguyên hội thoại AI.

## Cài đặt và chạy

Dùng Python 3.10+; crawler cần Chrome. Chạy các lệnh từ gốc repository:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Cấu hình `.env` theo [file mẫu](.env.example), không ghi đè file đang sử dụng:

```dotenv
DUCKDB_PATH=data/ocop.duckdb
DUCKDB_READ_ONLY=false
LEADS_BACKEND=postgres
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.5-flash-lite
```

- `DATABASE_URL`: PostgreSQL URI, không phải Supabase REST URL hoặc anon key. Dùng kết nối/pooler phù hợp môi trường và URL-encode mật khẩu.
- `LEADS_BACKEND=postgres`: bắt buộc cho biểu mẫu liên hệ hiện tại, kể cả khách. Lỗi PostgreSQL không tự ghi dự phòng SQLite.
- `GEMINI_API_KEY` hoặc `GOOGLE_API_KEY`: chỉ cần khi tạo embeddings hoặc dùng AI; xem catalog thông thường không cần khóa Gemini.
- Đường dẫn DuckDB tương đối tính từ gốc dự án. Cấu hình PostgreSQL ưu tiên biến môi trường, `.env`, rồi khóa cấp gốc trong Streamlit secrets.

Nếu chưa có catalog, nhập CSV đã chuẩn bị:

```powershell
python data/database.py --migrate-csv data/products_ocop.csv
```

Khởi tạo schema bằng tài khoản DB có quyền DDL, sau đó tạo tài khoản demo khi cần:

```powershell
python -m data.postgres --init-schema
python -m data.accounts seed
python -m streamlit run src/app.py
```

`seed` hỏi mật khẩu qua prompt ẩn (hoặc đọc `DEMO_ACCOUNT_PASSWORD`), tạo các tài khoản còn thiếu: `buyer01`, `buyer02`, `seller01`, `seller02`, `admin01`. Chạy lại giữ nguyên tài khoản đã có. Đổi mật khẩu bằng `python -m data.accounts set-password --username buyer01`.

Migration áp dụng các file SQL 001–010 theo thứ tự, lưu checksum ở `business.schema_migrations`, có transaction và advisory lock. Chạy lại không áp dụng lại; không sửa migration đã chạy. Ứng dụng không tự migration hoặc seed khi khởi động. Không cần PostgreSQL để chỉ xem catalog, nhưng các chức năng nghiệp vụ sẽ cần cấu hình đầy đủ.

## Chat AI và lịch sử hội thoại

Nút **💬 Chat với AI** ở góc dưới màn hình dùng chung hội thoại với khung khám phá sản phẩm ở các trang. AI dùng lịch sử để hiểu câu hỏi tiếp nối và gợi ý từ catalog hiện có.

Phiên chat mới có 3 câu hỏi gợi ý để bắt đầu bằng một lần bấm. Sau câu trả lời, các nút hỏi tiếp dựa trên sản phẩm vừa gợi ý giúp so sánh, tìm lựa chọn rẻ hơn hoặc khám phá cùng vùng miền. Câu hỏi được chọn gửi qua cùng luồng AI và lưu như câu hỏi tự nhập. AI được hướng dẫn kết thúc bằng một câu hỏi làm rõ nhu cầu, tránh hỏi lại thông tin đã có.

Gợi ý hỏi tiếp hiển thị bằng nút ngắn gọn; câu hỏi đầy đủ được cố định và lưu trong cột JSONB `followup_questions` của `business.chat_turns`, cũng có trong view `business.chat_research`. Tải lại giao diện không sinh lại danh sách khác. Những lượt cũ chưa từng ghi nhận gợi ý có giá trị `[]`; không suy diễn lại gợi ý lịch sử.

- Cả khách và tài khoản đăng nhập: mỗi lần hỏi là một dòng trong `business.chat_turns`, có `question`, `answer`, `products`, `status`, `asked_at`, `answered_at`. Dòng được tạo ngay khi hỏi (`pending`), cập nhật khi AI trả lời (`answered`) hoặc báo lỗi (`error`); thử lưu lại không tạo dòng trùng. `conversation_id` và `turn_number` xác định thứ tự trong hội thoại.
- `business.chat_conversations` chỉ lưu thông tin chung của hội thoại mới, không ghi toàn bộ lịch sử vào `messages`. Migration 009 tách dữ liệu cũ sang `chat_turns` và giữ snapshot cũ làm bản đối chiếu. Thời gian từng lượt của dữ liệu cũ không có sẵn nên dùng thời gian cấp hội thoại khi chuyển đổi.
- Mở view `business.chat_research` để kiểm tra mỗi câu hỏi kèm `user_id`, `session_key` và tiêu đề hội thoại. Khách có `user_id=NULL`; tài khoản đăng nhập được xác minh trước khi lưu.
- Giao diện chỉ hiển thị hội thoại trong phiên Streamlit hiện tại. Phiên mới, đăng nhập hoặc đăng xuất đều bắt đầu lại; không có chức năng mở lịch sử từ database. Bản ghi cũ vẫn được giữ để nghiên cứu.
- Mỗi phiên có khóa ngẫu nhiên phía server (`session_key`), tránh cập nhật hội thoại của phiên khác. Không dùng cookie theo dõi hoặc IP để nhận dạng khách. Dữ liệu nghiên cứu được truy cập bằng công cụ database có quyền phù hợp, không qua giao diện khách hàng.
- Lịch sử tự lưu ngầm. Khi lưu lỗi, chỉ hiện **Chưa lưu được cuộc trò chuyện, sẽ thử lại** và nút **Thử lại**. Tự thử lại khi có tương tác sau ít nhất 30 giây, tránh lặp yêu cầu liên tục. **Bắt đầu cuộc trò chuyện mới** giữ bản đã lưu; nếu còn phần chưa lưu thì mở dialog để tiếp tục chat hoặc xác nhận bắt đầu mới. Đăng xuất/hết phiên làm mất phần chưa lưu.

Sau khi cập nhật mã nguồn, chạy `python -m data.postgres --init-schema` để thêm bảng chat trước khi sử dụng lưu lịch sử. Cấu hình Gemini vẫn dùng các biến môi trường ở trên.

## Luồng nghiệp vụ

### Yêu cầu liên hệ của khách

Khách gửi loại `Nhu cầu mua hàng` hoặc `Nhờ tìm sản phẩm`, kèm tên, nội dung và ít nhất email hoặc số điện thoại. Dữ liệu lưu vào `business.leads` với `user_id=NULL`, chỉ admin đọc được. Đây là yêu cầu hỗ trợ tự do; không tự chuyển thành phiếu mua hàng, không tham gia matching/KPI của `purchase_requests` và chưa tự gửi email.

### Nhà cung cấp

Buyer gửi hồ sơ → `pending` → admin duyệt `approved` hoặc từ chối `rejected` có lý do. Buyer được duyệt trở thành seller. Hồ sơ bị từ chối có thể sửa và gửi lại; admin có thể tạm ngưng đơn vị (`suspended`). Quyền thao tác còn phụ thuộc membership và trạng thái đơn vị.

Nhà cung cấp liên kết sản phẩm bằng khóa `(source, product_id)`, khai báo số lượng tối thiểu, đơn vị, danh mục, khu vực phục vụ, số ngày chuẩn bị và giá tham khảo. Không suy ra đơn vị cung ứng từ tên thương hiệu crawler. Dữ liệu tự khai báo chưa chứng minh năng lực cung ứng thực tế.

### Nhu cầu → phân công → báo giá → kết nối

Trong danh sách nhu cầu, bấm chọn một dòng để xem chi tiết. Các tab gồm **Tổng quan** (thông tin, tiến độ phân công và thao tác kết thúc phiếu), **Báo giá** (so sánh/chọn hoặc gửi báo giá theo vai trò), **Liên hệ & lịch sử**. Admin có thêm tab **Phân công** chứa matching và phân thủ công. Việc chuyển tab không thay đổi quyền truy cập; dữ liệu và thao tác vẫn được kiểm tra ở lớp nghiệp vụ.

Người mua bấm xác nhận kết nối sẽ mở dialog nhắc **Chỉ xác nhận đã trao đổi, không xác nhận thanh toán hay giao hàng**; chỉ nút **Xác nhận** mới lưu trạng thái, **Hủy** không ghi dữ liệu. Lịch sử hiển thị timeline với vai trò nghiệp vụ của từng thao tác thay cho mã tài khoản. Sự kiện báo giá/từ chối kèm tên đơn vị từ lượt phân tương ứng; không suy ra đơn vị từ membership hiện tại. Phạm vi lịch sử seller vẫn giới hạn theo các lượt phân được phép xem.

Người mua so sánh báo giá qua 6 cột chính; phí giao, chi phí chưa gồm, ghi chú và hiệu lực nằm trong expander từng báo giá. Chọn phương án bằng thẻ radio và checkbox xác nhận. Nhãn **Rẻ nhất** theo tổng tiền ghi nhận và **Giao sớm nhất** theo ngày giao chỉ xét các báo giá hiện có thể chọn; các phương án đồng hạng cùng nhận nhãn. Nhãn giá không khẳng định đã gồm toàn bộ chi phí hoặc các phương án có cùng số lượng.

1. Buyer tạo phiếu với số lượng/đơn vị, địa điểm và hạn giao, thông tin liên hệ, ngân sách tùy chọn theo đơn vị hoặc tổng. Chỉ sửa phiếu `open` chưa từng phân công.
2. Admin phân một hoặc nhiều đơn vị `approved`, thủ công hoặc từ gợi ý matching; mỗi cặp phiếu/đơn vị chỉ có một lượt phân.
3. Seller được phân gửi báo giá hoặc từ chối có lý do. Báo giá lưu số lượng, đơn giá, phí giao hàng, chi phí chưa bao gồm, ngày giao và hạn hiệu lực có múi giờ.
4. Buyer chọn báo giá còn hiệu lực, chưa bị thay thế, có ngày giao còn phù hợp và đơn vị còn được duyệt.
5. Chỉ buyer sở hữu xác nhận `connected` sau khi chọn. Buyer/admin có thể hủy hoặc đóng không tìm được nguồn theo trạng thái cho phép.

Trạng thái chính: `open → assigned → quoted → selected → connected`. Khi seller từ chối và không còn báo giá active, phiếu có thể quay từ `quoted` về `assigned`. `cancelled` được phép từ open/assigned/quoted/selected; `closed_no_match` từ open/assigned/quoted. Phiếu đóng hoặc quá hạn giao không nhận thêm phân công/báo giá/lựa chọn.

Báo giá mới tăng phiên bản, thay báo giá active cũ bằng `superseded`; báo giá đã chọn không được sửa/thay thế. Số lượng báo giá có thể đáp ứng một phần, không vượt nhu cầu và phải cùng đơn vị. Tổng tiền = số lượng × đơn giá + phí giao hàng đã khai báo; phí chưa biết không đồng nghĩa miễn phí. Hệ thống chưa bắt buộc báo giá thực tế nằm trong ngân sách.

Thông tin liên hệ được trả về theo quyền tại lớp dữ liệu; seller chỉ thấy liên hệ buyer khi báo giá của mình được chọn trong phiếu selected/connected. Lịch sử phân công, báo giá và sự kiện được giữ để đối chiếu.

## Matching theo quy tắc (`rules-v1`)

Matching nhà cung cấp tách biệt với tìm kiếm sản phẩm bằng AI. Chỉ xét đơn vị `approved` và liên kết cung ứng đang active. Mỗi đơn vị được xếp theo sản phẩm có kết quả tốt nhất.

| Tiêu chí | Điểm khi đáp ứng | Quy tắc |
| --- | --- | --- |
| Sản phẩm/danh mục | 40 | Đúng khóa tham chiếu hoặc cùng danh mục khai báo. |
| Khu vực | 20 | Tỉnh/thành giao thuộc danh sách phục vụ khai báo. |
| Đặt tối thiểu | 15 | Số lượng nhu cầu đạt mức tối thiểu, cùng đơn vị. |
| Chuẩn bị | 15 | Số ngày chuẩn bị không vượt thời gian đến hạn giao. |
| Ngân sách | 10 | Giá tham khảo cùng đơn vị không vượt ngân sách theo cơ sở đơn giá/tổng. |

Có tiêu chí không đáp ứng → **Bị loại**; không vi phạm nhưng thiếu dữ liệu → **Cần xác nhận**; đủ tiêu chí áp dụng → **Đề xuất chính**. Thiếu dữ liệu không cộng điểm. Không đặt ngân sách thì tiêu chí này không áp dụng, tối đa 90 điểm; có ngân sách tối đa 100. Điểm không phải xác suất kết nối thành công.

So sánh văn bản bằng Unicode NFC, casefold và gộp khoảng trắng; không tự quy đổi đơn vị hoặc tên tỉnh viết tắt. Thời gian chuẩn bị chưa bao gồm xác nhận vận chuyển. Giá catalog từ sàn, giá tham khảo nhà cung cấp và báo giá thực tế là ba dữ liệu riêng.

Mở matching chỉ đọc dữ liệu. Khi admin xác nhận phân ứng viên, server tính lại điều kiện và lưu snapshot/phiên bản quy tắc cùng transaction phân công. Nhóm cần xác nhận vẫn cho admin quyết định; nhóm bị loại không được phân bằng nút gợi ý. Phân thủ công chỉ yêu cầu điều kiện nghiệp vụ cơ bản, không áp các tiêu chí loại của matching và không có snapshot quy tắc.

## Dashboard hiệu quả kết nối

Chỉ admin được truy cập. Bộ lọc ngày chọn nhóm phiếu **được tạo** trong khoảng ngày theo `Asia/Ho_Chi_Minh`; lịch sử của nhóm đó được tính đến thời điểm xem, kể cả phân công/báo giá phát sinh sau khoảng ngày chọn. Đọc dữ liệu trong transaction REPEATABLE READ.

| KPI | Cách tính |
| --- | --- |
| Yêu cầu tạo / đã phân | Số phiếu duy nhất / số phiếu có ít nhất một lượt phân. |
| Tỷ lệ có báo giá | Số phiếu có báo giá / số phiếu đã phân; tính cả lịch sử phiên bản. |
| Thời gian đến báo giá đầu | Trung vị thời gian từ từng lượt phân đến báo giá đầu của chính lượt đó. |
| Buyer chọn báo giá | Số phiếu từng có sự kiện selected hoặc còn selected_quote_id. |
| Đã kết nối / hủy / đóng không tìm nguồn | Số phiếu theo từng trạng thái hiện tại. |
| Theo nhà cung cấp | Số lượt phân, lượt phản hồi, lượt có báo giá và trung vị thời gian phản hồi đầu. Từ chối cũng là phản hồi. |

Mẫu số 0 hoặc chưa có thời gian hợp lệ hiển thị `Chưa có dữ liệu`. Nhiều phiên bản báo giá không làm tăng số phiếu có báo giá. Lọc supplier thu hẹp nhóm phiếu và các lượt phân/phản hồi của đơn vị đó; selected/connected vẫn là kết quả cấp phiếu, không quy công cho supplier đang lọc. Dashboard không lọc loại dữ liệu; phiếu seed mô phỏng cũng được tính nếu nằm trong nhóm ngày chọn.

Dashboard đặt 6 KPI chính ở đầu trang, mỗi thẻ có tooltip công thức: yêu cầu tạo, đã phân, có báo giá, đã kết nối, tỷ lệ có báo giá và trung vị thời gian đến báo giá đầu. Bộ lọc từ ngày/đến ngày/NCC nằm cùng một hàng. Phễu **tạo → phân → báo giá → chọn → kết nối** đếm phiếu duy nhất, tooltip thể hiện tỷ lệ trên số phiếu tạo. Khi lọc NCC, kết quả chọn/kết nối có thể lớn hơn bước báo giá của riêng đơn vị đó; biểu đồ giữ số thực tế, không ép giảm dần. Không có phiếu thì phễu và bảng NCC hiển thị `Chưa có dữ liệu`; số đếm bằng 0 vẫn là giá trị hợp lệ.

## Thu thập, đồng bộ và tìm kiếm AI

```powershell
python crawlers/tiki/crawl_tiki.py
python crawlers/tiktok/crawl_tiktok.py
python crawlers/buudien/crawl_buudien.py
# Hoặc nhập CSV crawler đã có:
python pipelines/sync_products.py --source TIKI --input crawlers/tiki/ocop_output/products_tiki.csv
python pipelines/sync_products.py --source TIKTOK --input crawlers/tiktok/ocop_output/products_tiktok.csv
python pipelines/sync_products.py --source BUUDIEN --input crawlers/buudien/ocop_output/products_buudien.csv
```

Crawler đọc danh sách URL cùng thư mục và gọi pipeline sau khi hoàn tất. Pipeline upsert theo `(source, product_id)`, giữ sản phẩm lịch sử và không ghi đè dữ liệu đã biết bằng ô trống. Danh mục hiển thị được chuẩn hóa qua `data/categories.py`, không sửa tên gốc trong catalog. Tỉnh suy ra từ tên sản phẩm và sao OCOP từ nguồn cần kiểm chứng.

Với Bưu điện, thêm URL chi tiết vào `crawlers/buudien/urls_buudien.txt`; crawler giữ dữ liệu đã lưu trong CSV và bỏ qua sản phẩm có cùng mã, kể cả khi URL khác tham số. Mỗi sản phẩm mới được ghi CSV, database được đồng bộ theo lô 10 sản phẩm và đồng bộ phần còn lại khi hoàn tất. Khi chạy lại, CSV hiện có được đồng bộ trước để phục hồi nếu lần trước bị gián đoạn. Dùng `--no-sync` nếu chỉ muốn xuất CSV. Có thể dùng `--url URL`, `--urls-file FILE`, hoặc `--html FILE`; thêm `--listing` khi URL là trang kết quả tìm kiếm (trang kết quả vẫn được tải để tìm link mới). Crawler cần Chrome và Selenium khi có trang mới. Chạy lại tạo embeddings để đưa sản phẩm mới vào tìm kiếm AI.

Bổ sung tỉnh còn thiếu cho CSV TikTok mà không crawl hoặc đồng bộ DB:

```powershell
python crawlers/tiktok/crawl_tiktok.py --backfill-provinces
```

Tạo embeddings trước khi dùng AI:

```powershell
python -m src.vectorization
python -m src.vectorization --source TIKI --batch-size 32
# Chủ động tạo lại trong phạm vi chọn:
python -m src.vectorization --force
```

Vectorization lưu hash nội dung/metadata/model, bỏ qua sản phẩm không đổi và lưu tiến độ theo nhóm sản phẩm đầy đủ. Nếu gặp lỗi API, các nhóm đã lưu vẫn được giữ và vector cũ của nhóm chưa hoàn tất không bị xóa; chạy lại không dùng `--force` để tiếp tục. Tìm kiếm áp bộ lọc trước xếp hạng vector, gộp chunk theo sản phẩm và kiểm tra ID sản phẩm AI chọn với kết quả truy xuất. Chat nhận ngân sách tiếng Việt, giữ ngân sách khi hỏi tiếp và hỗ trợ bỏ giới hạn; lịch sử chỉ nằm trong phiên Streamlit.

Dừng ứng dụng và đóng kết nối DBeaver trước khi ghi/crawl/vectorize DuckDB. Khi cần nâng cấp ràng buộc bảng sản phẩm cũ, dùng `python data/database.py --upgrade-products-schema`.

## Triển khai

Export catalog sạch khi đã đóng các kết nối DuckDB:

```powershell
python data/database.py --export-catalog data/catalog.duckdb
```

Export chỉ chứa products/embeddings, ghi đè file đích; không chứa leads. Pipeline và vectorization tự cập nhật catalog cùng thư mục sau khi ghi thành công; thay đổi SQL trực tiếp cần export lại. Chỉ `data/catalog.duckdb` được cho phép qua .gitignore để triển khai. Cần commit/push catalog mới để cloud nhận dữ liệu.

Trên Streamlit Community Cloud chọn `src/app.py`, dùng requirements ở gốc và đặt Secrets:

```toml
DUCKDB_PATH = "data/catalog.duckdb"
DUCKDB_READ_ONLY = "true"
LEADS_BACKEND = "postgres"
DATABASE_URL = "postgresql://USER:PASSWORD@POOLER_HOST:5432/postgres?sslmode=require"
GEMINI_API_KEY = "your-api-key"
GEMINI_MODEL = "gemini-3.5-flash-lite"
```

Chạy migration PostgreSQL trước triển khai bằng role DDL riêng. Không chạy pipeline/vectorization với DuckDB read-only. Supabase lưu dữ liệu nghiệp vụ qua backend PostgreSQL; phân quyền hiện ở Python, không dùng RLS/Supabase Auth. Không công khai schema `business` qua Data API. Không commit `.env`, URI thật, dữ liệu liên hệ hoặc backup. Cloud không tự đọc dữ liệu trên máy cá nhân.

Streamlit đọc cấu hình theo thư mục chạy lệnh. Muốn dùng `src/.streamlit/config.toml`, chạy `cd src` rồi `python -m streamlit run app.py`.

## Migration dữ liệu legacy

Không cần chạy các lệnh này cho cài mới. Với leads cũ, sao lưu và đối chiếu trước khi chuyển:

```powershell
# DuckDB cũ → SQLite, giữ nguồn gốc:
python data/database.py --migrate-duckdb-leads data/ocop.duckdb
# SQLite → PostgreSQL đã có schema:
python -m data.migrate_leads --source data/leads.sqlite3 --source-id local-main --dry-run
python -m data.migrate_leads --source data/leads.sqlite3 --source-id local-main --apply
```

Nguồn SQLite được mở chỉ đọc; dùng `source-id` ổn định khi chạy lại. ID nguồn được giữ riêng để chống trùng. Dry-run không ghi đích; apply có savepoint mỗi dòng, dòng lỗi được báo failed và dòng hợp lệ vẫn có thể commit. Lỗi transaction/commit rollback đợt nhập. Leads cũ không tự gán chủ sở hữu theo email/tên và không tự chuyển thành purchase_requests.

## Kiểm thử và demo

```powershell
python -m unittest discover -s tests
```

Kiểm thử bao phủ catalog/pipeline, tìm kiếm/RAG, embeddings, phân quyền, hồ sơ nhà cung cấp, trạng thái nhu cầu, phiên bản báo giá, matching, KPI và giao diện Streamlit. Gemini/crawler được giả lập trong tests; các bài tích hợp PostgreSQL được bỏ qua khi chưa cấu hình `TEST_DATABASE_URL`.

Để kiểm thử tích hợp, dùng database **riêng** tên `ocop_leads_test` trên localhost/127.0.0.1, cấu hình `TEST_DATABASE_URL` rồi chạy lại bộ test. Tests tạo lại schema `business`, không dùng database vận hành.

Seed tùy chọn trên database demo sau migration và seed tài khoản:

```powershell
python -m data.seed_suppliers
python -m data.seed_purchase
```

Seed suppliers cần catalog có ít nhất hai sản phẩm. Seed purchase tạo một phiếu open mô phỏng cho buyer01, không tạo phân công/báo giá/kết nối. Kịch bản kiểm tra: buyer tạo nhu cầu → admin xem matching và xác nhận phân → seller báo giá → buyer chọn và xác nhận kết nối → admin đối chiếu KPI. Thử thêm thiếu dữ liệu cung ứng, khác đơn vị, báo giá hết hạn và truy cập phiếu không thuộc quyền.

## Giới hạn hiện tại

Đây là ứng dụng demo hỗ trợ kết nối. Chưa có thanh toán, quản lý vận chuyển, đối soát doanh thu, email/thông báo tự động hoặc xác minh chứng nhận OCOP. Hồ sơ approved là kết quả duyệt nội bộ; matching dựa trên dữ liệu khai báo. AI có thể trả lời sai và cần đối chiếu sản phẩm/nguồn. Xác thực nội bộ chưa có MFA, rate limiting và quy trình khôi phục tài khoản cho triển khai thực tế.
