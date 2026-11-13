# Ứng dụng OCOP Connect

Chạy từ gốc repository với môi trường đã cài [requirements](../requirements.txt):

```powershell
python -m streamlit run src/app.py
```

Ứng dụng đọc catalog/embeddings từ DuckDB; tài khoản, yêu cầu liên hệ, nhà cung cấp, phiếu nhu cầu và báo giá dùng PostgreSQL/Supabase. Khách được xem sản phẩm, hỏi AI và gửi yêu cầu liên hệ. Luồng có đăng nhập phân quyền buyer/seller/admin tại lớp dữ liệu.

Xem [README dự án](../README.md) để cấu hình `.env`, migration, tài khoản demo, luồng nghiệp vụ, matching, KPI và kiểm thử. Xem catalog không cần khóa Gemini; AI cần khóa API và embeddings đã tạo. Biểu mẫu nghiệp vụ cần PostgreSQL đã migration, không dùng SQLite dự phòng.

Để áp dụng cấu hình trong `src/.streamlit/config.toml`, chạy từ gốc:

```powershell
cd src
python -m streamlit run app.py
```

Dừng ứng dụng trước khi đồng bộ hoặc tạo embeddings để tránh khóa DuckDB giữa các tiến trình. `connected` chỉ ghi nhận đã kết nối trao đổi, chưa xác nhận giao dịch thành công.
