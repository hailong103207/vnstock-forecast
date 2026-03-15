# User workspace

Thư mục `user/` chứa **toàn bộ phần logic và dữ liệu do người dùng tùy biến**,
được tách khỏi `src/` để giảm rủi ro khi nâng cấp hệ thống.

## Mục tiêu

- Cho phép chỉnh sửa bot/filter mà không sửa code lõi.
- Cho phép lưu profile, preset, orderbook theo từng người dùng.
- Dễ backup/di chuyển sang máy khác.

## Cấu trúc hiện tại

- `builtin/`: mẫu tham chiếu (example) do dự án cung cấp.
    - `builtin/bots/technical/`: bản copy từ `src/vnstock_forecast/forecast/technical` để tham khảo.
    - `builtin/profiles/`: profile mẫu (`*.json`) để test nhanh.
- `bots/`: nơi bạn tự viết bot riêng.
- `filters/`:
    - `filters/presets/`: preset filter dạng YAML (khuyến nghị cho use case phổ thông).
    - `filters/functions/`: logic filter Python cho công thức phức tạp.
- `orderbook/`: dữ liệu sổ lệnh local (sẽ dùng cho CLI sau).

## Nguyên tắc làm việc

1. Không sửa trực tiếp trong `src/` cho logic đầu tư cá nhân.
2. Dùng `builtin/*` làm ví dụ, sau đó copy sang `bots/` hoặc `filters/` để tùy chỉnh.
3. Mỗi khi đổi logic, nên tăng version trong file cấu hình/preset để dễ truy vết.
4. Profile trong `builtin/profiles` chỉ là mẫu, không phản ánh hiệu quả hiện tại của thị trường.

## Cơ chế liên kết runtime với `user/`

Hệ thống hiện đã tự động liên kết với thư mục `user/` khi chạy:

- Technique modules sẽ được auto-load từ `user/bots/` (quét đệ quy `*.py`, bỏ qua file bắt đầu bằng `_`).
- `user/builtin/*` vẫn giữ vai trò thư viện mẫu tham khảo (không auto-register để tránh trùng tên technique).
- Profile sẽ được resolve theo thứ tự ưu tiên:
    1. `user/profiles/`
    2. `user/builtin/profiles/`
    3. `profile/` (legacy)

Vì vậy, bạn chỉ cần đặt code/profile đúng thư mục, không cần sửa thêm core loader.

## YAML hay Python cho preset filter?

- **Ưu tiên YAML** khi rule là so sánh chuẩn:
    - ví dụ: `pe > x`, `roe >= y`, `debt_to_equity < z`.
    - lợi thế: dễ đọc, dễ chia sẻ, không cần code.
- **Dùng Python** khi cần công thức/hàm phức tạp:
    - ví dụ: chuẩn hóa theo ngành, rule có nhiều nhánh, rolling logic.
- Khuyến nghị thực tế: dùng mô hình hybrid
    - YAML làm lớp cấu hình chính.
    - Python làm "hook" cho các điều kiện đặc biệt.

## Tài liệu tham khảo

- Notebook data: `notebooks/guide/data_tutorial.ipynb`
- Notebook backtest: `notebooks/guide/backtest_tutorial.ipynb`
- Notebook profiler: `notebooks/guide/profiler_tutorial.ipynb`

Các notebook trên là nguồn tốt để hiểu luồng dữ liệu trước khi viết bot/filter riêng.
