# OCOP Connect — Python + Streamlit

Chạy từ gốc dự án với Python 3.10+:

```powershell
python -m pip install -r requirements.txt
python data/database.py --migrate-csv data/products_ocop.csv
cd src
python -m streamlit run app.py
```

Ứng dụng đọc bảng `products` và ghi yêu cầu liên hệ vào bảng `leads` trong cùng DuckDB. Đường dẫn mặc định là `data/ocop.duckdb`, cấu hình qua `DUCKDB_PATH` trong `.env` ở gốc dự án. Đường dẫn tương đối tính từ gốc dự án.

Ứng dụng hỗ trợ tìm kiếm, lọc, xem chi tiết sản phẩm, khám phá theo tỉnh và mở gian hàng nguồn. Biểu mẫu kết nối lưu dữ liệu, chưa tự gửi email. Sao OCOP và xuất xứ chưa được hệ thống tự xác minh.

Crawler vẫn lưu CSV thô; pipeline nhập dữ liệu vào DuckDB theo khóa `source + product_id`. Ứng dụng không đọc CSV và đọc lại database mỗi lần Streamlit chạy lại.

Khi triển khai, dùng `src/app.py` và requirements ở gốc, nhập dữ liệu vào database trên môi trường triển khai và dùng lưu trữ bền vững. Database chung có thông tin liên hệ, không commit lên Git. Đóng ứng dụng trước khi chạy pipeline/crawler để tránh khóa file giữa các tiến trình.

Xem [README dự án](../README.md) để biết cách đồng bộ, cấu hình và chuyển dữ liệu SQLite cũ.