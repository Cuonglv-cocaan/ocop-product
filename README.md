# OCOP Data Pipeline

## Luồng dữ liệu

```text
crawlers/tiki/urls.txt
  -> crawlers/tiki/crawl_tiki.py
  -> crawlers/tiki/ocop_output/products_tiki.csv
  -> pipelines/sync_products.py
  -> data/products_ocop.csv
  -> src/app.py
```

- [Crawler Tiki](crawlers/tiki/crawl_tiki.py) đọc [danh sách URL](crawlers/tiki/urls.txt), ghi CSV vào `ocop_output/`, sau đó tự gọi pipeline để cập nhật file tổng, kể cả khi không có URL mới.
- [Pipeline](pipelines/sync_products.py) gộp theo khóa `source + product_id`, giữ dữ liệu lịch sử và không ghi đè bằng ô trống. Bản sao trước cập nhật nằm trong `data/backups/`.
- [Ứng dụng](src/app.py) đọc duy nhất `data/products_ocop.csv`. Dữ liệu dùng chung nằm trong thư mục `data/` ở gốc dự án.
- Yêu cầu kết nối lưu riêng trong `data/leads.sqlite3`.
- Hiện chỉ có crawler Tiki, chưa có crawler TikTok/Shopee hoặc lịch chạy tự động.

## Cài đặt và chạy

Chạy từ thư mục gốc `ocop-product/`, dùng Python 3.10+ và Chrome cho crawler Selenium:

Toàn bộ thư viện của ứng dụng, crawler và pipeline được quản lý chung trong [requirements.txt](requirements.txt) ở thư mục gốc.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python crawlers/tiki/crawl_tiki.py
python -m streamlit run src/app.py
```

Nếu Windows không nhận `python`, dùng `py` để tạo môi trường ảo. Sau đồng bộ, tải lại hoặc thao tác trên ứng dụng để Streamlit đọc dữ liệu mới.

Để chỉ đồng bộ CSV đã có mà không chạy crawler:

```powershell
python -X utf8 pipelines/sync_products.py --source TIKI --input crawlers/tiki/ocop_output/products_tiki.csv
```

Đường dẫn `--input` và `--master` tùy chỉnh tính từ thư mục chạy lệnh. Các đường dẫn mặc định tính từ vị trí script.

CSV tổng gồm:
`product_id,product_name,brand,category_name,province_name,ocop_stars,description,source_url,image_url,price,source`.
Các trường chi tiết khác trong CSV crawler không được đưa vào CSV tổng. Hạng sao và tỉnh từ crawler cần được kiểm chứng trước khi dùng như dữ liệu chứng nhận.

Xem [hướng dẫn ứng dụng](src/README.md). Khi triển khai, main file là `src/app.py`; cần giữ thư mục `data/` cạnh `src/`. Cloud chỉ đọc được dữ liệu đã đưa lên môi trường triển khai, không tự đồng bộ ổ đĩa cá nhân.

Không chạy nhiều tiến trình đồng bộ cùng lúc. Dùng tên nguồn nhất quán (`TIKI`, `TIKTOK`, `SHOPEE`).

## Trước khi đưa lên GitHub

`.gitignore` ở gốc loại database yêu cầu kết nối (có thông tin cá nhân), HTML/CSV thô của crawler, backup, môi trường ảo và file secrets khỏi commit mới. Giữ `data/products_ocop.csv` để ứng dụng có dữ liệu; chỉ công khai CSV này sau khi kiểm tra nội dung được phép chia sẻ.

Không đặt API key, mật khẩu hoặc token trong mã nguồn; cấu hình riêng qua biến môi trường hoặc `.streamlit/secrets.toml`. File `src/.streamlit/config.toml` hiện chỉ chứa giao diện và cấu hình server, có thể commit.

Hiện ứng dụng, crawler và pipeline chưa đọc `.env` và chưa tích hợp Qdrant, Hugging Face, OpenAI hoặc Gemini. Các khóa trong `.env` chưa được sử dụng; không cần cấu hình các dịch vụ này để chạy dự án.

Streamlit đọc `.streamlit/config.toml` theo thư mục chạy lệnh. Để dùng cấu hình trong `src/.streamlit/`, chạy `cd src` rồi `python -m streamlit run app.py`.

Trước commit, kiểm tra `git status --short` và `git diff --cached`. `.gitignore` không loại file đã được Git theo dõi hoặc xóa dữ liệu khỏi lịch sử commit. Nếu từng đưa bí mật lên GitHub, cần thu hồi/thay khóa và xử lý lịch sử liên quan.

