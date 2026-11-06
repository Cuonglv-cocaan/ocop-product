# OCOP Connect — Python + Streamlit

## Cài đặt và chạy riêng

Chạy từ thư mục gốc dự án với Python 3.10+. Toàn bộ thư viện được quản lý trong [requirements.txt](../requirements.txt):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cd src
python -m streamlit run app.py
```

Mở http://localhost:8501. Để chạy cả crawler và pipeline, xem [README dự án](../README.md).

## Dữ liệu và chức năng

Ứng dụng đọc duy nhất [CSV tổng](../data/products_ocop.csv) trong thư mục `data/` ở gốc dự án. Crawler tự gọi pipeline để cập nhật file tổng sau khi chạy xong.

Các cột bắt buộc:
`product_id,product_name,brand,category_name,province_name,ocop_stars,description,source_url,image_url,price,source`.

Khóa dữ liệu là `source + product_id`; `price` là số VND không có dấu phân tách. `image_url` và `source_url` là URL HTTP(S). Hệ thống chưa tự xác minh chứng nhận sao OCOP hoặc xuất xứ.

Ứng dụng hỗ trợ tìm kiếm, lọc sản phẩm, xem chi tiết, khám phá theo tỉnh và mở gian hàng nguồn. Biểu mẫu kết nối lưu vào bảng `leads` trong DuckDB, mặc định `../data/ocop.duckdb`, chưa tự gửi email hoặc thông báo. Đổi đường dẫn bằng `DUCKDB_PATH` trong `.env` ở gốc dự án; đường dẫn tương đối tính từ gốc dự án. Xem [hướng dẫn chuyển dữ liệu SQLite cũ](../README.md).

## Triển khai

Triển khai toàn bộ dự án, main file là `src/app.py`, dùng requirements ở thư mục gốc. Cần giữ thư mục `data/` cạnh `src/`, không triển khai riêng thư mục `src/`.

Cần đưa CSV lên cùng bản triển khai; dữ liệu máy cá nhân không tự xuất hiện trên cloud. DuckDB trên môi trường lưu trữ tạm có thể mất khi triển khai lại; cần nơi lưu bền vững khi nhận yêu cầu thực tế.
