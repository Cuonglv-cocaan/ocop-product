# OCOP Connect — Python + Streamlit

Chạy từ gốc dự án với Python 3.10+:

```powershell
python -m pip install -r requirements.txt
python data/database.py --migrate-csv data/products_ocop.csv
cd src
python -m streamlit run app.py
```

Ứng dụng đọc sản phẩm/embeddings từ DuckDB; tài khoản và yêu cầu có chủ sở hữu lưu trong PostgreSQL/Supabase. SQLite cũ giữ làm nguồn migration. Đường dẫn catalog mặc định là `data/ocop.duckdb`, cấu hình qua `DUCKDB_PATH` trong `.env` ở gốc dự án. Đường dẫn tương đối tính từ gốc dự án.

Ứng dụng hỗ trợ tìm kiếm, lọc, xem chi tiết sản phẩm, khám phá theo tỉnh và mở gian hàng nguồn. Biểu mẫu kết nối lưu dữ liệu, chưa tự gửi email. Sao OCOP và xuất xứ chưa được hệ thống tự xác minh.

Trang chủ có ô “Khám phá sản phẩm cùng AI” dưới phần giới thiệu. Người dùng có thể hỏi tiếp trong cùng hội thoại; mỗi câu trả lời kèm sản phẩm gợi ý và liên kết nguồn bán. Lịch sử lưu trong phiên Streamlit và có thể xóa bằng nút bắt đầu cuộc trò chuyện mới. Cần cấu hình `GEMINI_API_KEY` (hoặc `GOOGLE_API_KEY`), `GEMINI_MODEL` và tạo embeddings bằng `python -m src.vectorization` trước khi sử dụng tìm kiếm AI.

Crawler vẫn lưu CSV thô; pipeline nhập dữ liệu vào DuckDB theo khóa `source + product_id`. Ứng dụng không đọc CSV và đọc lại database mỗi lần Streamlit chạy lại.

Khi triển khai, dùng `src/app.py` và requirements ở gốc, nhập dữ liệu vào database trên môi trường triển khai và dùng lưu trữ bền vững. SQLite chứa thông tin liên hệ, không commit lên Git; chỉ dùng bản DuckDB catalog sạch để triển khai. Đóng ứng dụng trước khi chạy pipeline/crawler để tránh khóa file giữa các tiến trình.

Xem [README dự án](../README.md) để biết cách đồng bộ, cấu hình và chuyển leads DuckDB cũ sang SQLite.

Giá thiếu hoặc không hợp lệ hiển thị “Giá chưa cập nhật”, không quy đổi thành 0 đồng. Sao OCOP chỉ hiển thị hạng 3, 4, 5 theo nguồn; dữ liệu khác hiển thị “OCOP chưa cập nhật”.

Chạy kiểm thử từ gốc dự án: `python -m unittest discover -s tests`. Kiểm thử dùng database tạm và embeddings giả, không gọi Gemini hoặc crawl trang thật.

Triển khai Community Cloud: xem hướng dẫn catalog sạch và DUCKDB_READ_ONLY trong README gốc. SQLite cục bộ không được bảo đảm lưu bền vững trên cloud.


PostgreSQL/Supabase và migration: xem mục tương ứng trong [README dự án](../README.md). Leads đi qua data/leads.py; thao tác có đăng nhập yêu cầu LEADS_BACKEND=postgres, DATABASE_URL và schema đã migration. Không fallback SQLite khi lỗi. Catalog/embeddings tiếp tục dùng DuckDB.


Bước 4: đăng nhập nội bộ và yêu cầu có chủ sở hữu dùng PostgreSQL với LEADS_BACKEND=postgres. Khách vẫn xem và tìm kiếm; xem README gốc để chạy migration 003 và seed thủ công bằng prompt mật khẩu. SQLite chỉ còn là nguồn legacy, không dùng cho form có đăng nhập. Không dùng Supabase Auth hoặc Google/OIDC.


Hồ sơ nhà cung cấp: migration 004, seed riêng bằng python -m data.seed_suppliers. Buyer/seller đăng ký tại Nhà cung cấp; admin duyệt tại Duyệt nhà cung cấp. Cung ứng cần role seller + membership + approved; xem README gốc để biết quy trình và test. Không tự chạy migration/seed trên Supabase thật.
