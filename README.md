# DELTA X - ULTRA CONTROLLER

**Phiên bản**: 1.0.0
**Ngôn ngữ**: Python (PyQt5)
**Tác giả**: Nhat Phan

## Giới Thiệu
**DELTA X CONTROLLER** là phần mềm điều khiển máy CNC/Robot Delta X chuyên nghiệp, được xây dựng trên nền tảng Python và Qt5. Phần mềm cung cấp giao diện Dark Mode hiện đại, khả năng kết nối Serial mạnh mẽ và hệ thống chạy Macro thông minh.

## Tính Năng Nổi Bật

### 1. Giao Diện Người Dùng (UI)
- **Dark Mode**: Giao diện tối màu chuyên nghiệp, giúp giảm mỏi mắt khi vận hành lâu.
- **Responsive**: Bố cục linh hoạt, trực quan.

### 2. Điều Khiển (Control)
- **Jogging**: Điều khiển các trục X, Y, Z với các bước nhảy linh hoạt (0.01mm đến 200mm).
- **Manual/Auto Mode**: Chuyển đổi linh hoạt giữa chế độ chạy tay và tự động.
- **Safety**: Nút dừng khẩn cấp (EMG) và Reset Alarm (M999) được tích hợp sẵn.

### 3. Hệ Thống Macro Nâng Cao
Trình chạy G-code thông minh với các tính năng vượt trội:
- **Handshake (Hỏi-Đáp)**: Đảm bảo từng lệnh được thực thi xong (`ok` response) trước khi gửi lệnh tiếp theo.
- **GOTO & Line Numbers**: Hỗ trợ lệnh nhảy dòng `GOTO` và đánh số dòng `N`.
- **Visual Feedback**: Higlight dòng lệnh đang chạy theo thời gian thực (Mũi tên chỉ dẫn).

**Ví dụ Macro:**
```gcode
N0 G28         ; Về Home
N5 GOTO 15     ; Nhảy qua dòng 10
N10 G01 X100   ; Lệnh này sẽ bị bỏ qua
N15 M03        ; Bật Spindle
```

## Cài Đặt & Chạy

### Yêu Cầu
- Python 3.10+
- Conda (khuyên dùng)

### Cài Đặt Thư Viện
```bash
pip install PyQt5 pyserial
```

### Chạy Phần Mềm
```bash
python main.py
```

## Cấu Trúc Dự Án
```
DELTA_X/
├── main.py                # File khởi chạy chính
├── src/
│   ├── core/
│   │   ├── serial_worker.py  # Xử lý kết nối Serial đa luồng
│   │   └── macro_runner.py   # Bộ xử lý Macro thông minh
│   └── ui/
│       ├── main_window.py    # Giao diện chính
│       └── styles.py         # Giao diện Dark Theme (QSS)
└── README.md
```