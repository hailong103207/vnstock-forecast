# vnstock-forecast

Hệ thống AI dự báo thị trường chứng khoán Việt Nam — bao gồm thu thập dữ liệu OHLCV, lưu trữ dạng Parquet, truy vấn bằng DuckDB, và backtest chiến lược giao dịch.

---

## Mục lục

- [Yêu cầu](#yêu-cầu)
- [Cài đặt](#cài-đặt)
- [Cấu trúc dự án](#cấu-trúc-dự-án)
- [Cấu hình](#cấu-hình)
- [Hướng dẫn sử dụng](#hướng-dẫn-sử-dụng)
- [Makefile Commands](#makefile-commands)

---

## Yêu cầu

| Công cụ | Phiên bản    |
| ------- | ------------ |
| Python  | >= 3.12      |
| Conda   | bản mới nhất |

---

## Cài đặt

### 1. Clone repository

```bash
git clone <repo-url>
cd vnstock-forecast
```

### 2. Tạo môi trường Conda & cài đặt package

```bash
make setup
```

Lệnh trên sẽ:

1. Tạo môi trường Conda tên `vnstock-forecast` (theo `environment.yml`).
2. Cài đặt project ở chế độ editable (`pip install -e .[dev]`).
3. Cài đặt pre-commit hooks.

### 3. Kích hoạt môi trường

```bash
conda activate vnstock-forecast
```

### Cài đặt thủ công (không dùng Make)

```bash
conda env create -f environment.yml
conda activate vnstock-forecast
pre-commit install
pre-commit install --hook-type commit-msg
```

---

## Cấu trúc dự án

```
vnstock-forecast/
├── config/                          # Cấu hình YAML (Hydra/OmegaConf)
│   ├── config.yaml                  #   Entry-point cấu hình chính
│   └── data/
│       ├── updater.yaml             #   Cấu hình updater (lookback, symbols, resolutions)
│       └── discovery/
│           ├── symbols/             #   Danh sách mã CK (vn30, vnindex)
│           └── resolutions/         #   Mapping resolution theo client
│
├── data/                            # Dữ liệu OHLCV (Hive-partitioned Parquet)
│   └── ohlcv/
│       ├── resolution=D/            #   Dữ liệu ngày
│       ├── resolution=W/            #   Dữ liệu tuần
│       ├── resolution=M/            #   Dữ liệu tháng
│       ├── resolution=1/            #   Dữ liệu 1 phút
│       ├── resolution=15/           #   Dữ liệu 15 phút
│       ├── resolution=60/           #   Dữ liệu 60 phút
│       └── resolution=240/          #   Dữ liệu 240 phút
│
├── src/vnstock_forecast/            # Source code chính
│   ├── client/                      #   HTTP clients lấy dữ liệu từ API bên ngoài
│   │   └── vietstock/               #     Client cho Vietstock API
│   │       └── ohlcv.py             #       Lấy dữ liệu OHLCV (retry, backoff)
│   │
│   ├── data/                        #   Module dữ liệu
│   │   ├── updater.py               #     Cập nhật dữ liệu incremental → Parquet
│   │   └── query.py                 #     Truy vấn DuckDB trên Parquet store
│   │
│   ├── backtest/                    #   Backtest engine
│   │   ├── bot_base.py              #     Abstract base class cho bot giao dịch
│   │   ├── engine.py                #     Engine chạy backtest bar-by-bar
│   │   ├── context.py               #     StepContext cho mỗi bar
│   │   ├── portfolio.py             #     Quản lý danh mục
│   │   ├── report.py                #     Báo cáo kết quả backtest
│   │   └── examples.py              #     Bot mẫu
│   │
│   ├── schemas/                     #   Config schemas (dataclass + Hydra)
│   │   ├── config.py                #     Schema cấu hình tổng (AppConfig)
│   │   └── data.py                  #     Schema cấu hình data (symbols, resolutions)
│   │
│   ├── shared/                      #   Hằng số dùng chung (đường dẫn)
│   │   └── path.py
│   │
│   └── utils/                       #   Tiện ích
│       ├── config_utils.py          #     Tìm project root, load config Hydra
│       ├── env_utils.py             #     Biến môi trường (.env)
│       └── time_utils.py            #     Chuyển đổi thời gian
│
├── notebooks/                       # Jupyter notebooks demo & thử nghiệm
├── environment.yml                  # Conda environment spec
├── pyproject.toml                   # Metadata & dependencies
└── Makefile                         # Lệnh phát triển tiện lợi
```

### Tổng quan kiến trúc

| Layer         | Mô tả                                                    |
| ------------- | -------------------------------------------------------- |
| **client/**   | HTTP client lấy dữ liệu thị trường từ API                |
| **data/**     | Lưu trữ Parquet + cập nhật incremental + truy vấn DuckDB |
| **backtest/** | Engine backtest bar-by-bar với pattern pluggable bot     |
| **schemas/**  | Dataclass schema cho cấu hình YAML (Hydra/OmegaConf)     |
| **shared/**   | Hằng số dùng chung (đường dẫn project)                   |
| **utils/**    | Tiện ích: tìm project root, load config, xử lý thời gian |

---

## Cấu hình

Dự án sử dụng **Hydra + OmegaConf** để quản lý cấu hình. File chính: `config/config.yaml`.

```yaml
# config/config.yaml
defaults:
    - _self_
    - data/discovery/symbols@data.discovery.symbols.vn30: vn30
    - data/discovery/symbols@data.discovery.symbols.vnindex: vnindex
    - data/discovery/resolutions@data.discovery.resolutions.vietstock: vietstock
    - data@data.updater: updater
```

Cấu hình được validate bằng dataclass schema trong `schemas/config.py` và `schemas/data.py`.

---

## Hướng dẫn sử dụng

Các notebook hướng dẫn chi tiết nằm trong thư mục [`notebooks/guide/`](notebooks/guide/):

| Notebook                                                           | Mô tả                                                        |
| ------------------------------------------------------------------ | ------------------------------------------------------------ |
| [data_tutorial.ipynb](notebooks/guide/data_tutorial.ipynb)         | Hướng dẫn thu thập, cập nhật và truy vấn dữ liệu OHLCV       |
| [backtest_tutorial.ipynb](notebooks/guide/backtest_tutorial.ipynb) | Hướng dẫn xây dựng bot và chạy backtest chiến lược giao dịch |

---

## Makefile Commands

| Lệnh                   | Mô tả                                       |
| ---------------------- | ------------------------------------------- |
| `make help`            | Hiển thị danh sách lệnh                     |
| `make setup`           | Tạo môi trường Conda + cài pre-commit hooks |
| `make update-env`      | Cập nhật môi trường Conda                   |
| `make update-hooks`    | Cập nhật pre-commit hooks                   |
| `make pre-commit-test` | Chạy pre-commit kiểm tra toàn bộ code       |
| `make delete-env`      | Xoá môi trường Conda                        |
| `make clean`           | Dọn file tạm (`__pycache__`, `.pyc`, ...)   |
