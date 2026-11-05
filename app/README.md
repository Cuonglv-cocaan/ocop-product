# OCOP Connect — Python + Streamlit

## Cài đặt và chạy riêng

Chạy từ thư mục `app/` với Python 3.10+:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Mở http://localhost:8501. Để chạy cả crawler và pipeline, xem [README dự án](../README.md).

## Dữ liệu và chức năng

Ứng dụng đọc duy nhất [CSV tổng](../data/products_ocop.csv) trong thư mục `data/` ở gốc dự án. Crawler tự gọi pipeline để cập nhật file tổng sau khi chạy xong.

Các cột bắt buộc:
`product_id,product_name,brand,category_name,province_name,ocop_stars,description,source_url,image_url,price,source`.

Khóa dữ liệu là `source + product_id`; `price` là số VND không có dấu phân tách. `image_url` và `source_url` là URL HTTP(S). Hệ thống chưa tự xác minh chứng nhận sao OCOP hoặc xuất xứ.

Ứng dụng hỗ trợ tìm kiếm, lọc sản phẩm, xem chi tiết, khám phá theo tỉnh và mở gian hàng nguồn. Biểu mẫu kết nối lưu vào `../data/leads.sqlite3`, cùng thư mục với CSV tổng, chưa tự gửi email hoặc thông báo.

## Triển khai

Triển khai toàn bộ dự án, main file là `app/app.py`, dùng requirements ở thư mục gốc. Cần giữ thư mục `data/` cạnh `app/`, không triển khai riêng thư mục `app/`.

Cần đưa CSV lên cùng bản triển khai; dữ liệu máy cá nhân không tự xuất hiện trên cloud. SQLite trên môi trường lưu trữ tạm có thể mất khi triển khai lại; cần nơi lưu bền vững khi nhận yêu cầu thực tế.
