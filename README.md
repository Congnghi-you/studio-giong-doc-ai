# 🎙️ Studio Giọng Đọc AI Tiếng Việt

Ứng dụng web chuyển đổi văn bản dài (20+ phút) thành âm thanh giọng đọc AI tự nhiên, mượt mà.

## Tính năng chính

- ✅ **6 phong cách giọng đọc**: 3 Nam (Kể chuyện, Thời sự, Năng động) + 3 Nữ (Dịu dàng, Thuyết minh, Trẻ trung)
- ✅ **Hỗ trợ văn bản dài 20+ phút**: Tự động chia đoạn thông minh, ghép nối mượt mà
- ✅ **Nghe thử trực tiếp trên web**: Nút nghe mẫu cho từng giọng đọc
- ✅ **Tuỳ chỉnh tốc độ, cao độ**: Thanh kéo điều chỉnh trực tiếp
- ✅ **Chèn khoảng nghỉ tự chọn**: Nhấn nhá, ngắt nghỉ theo ý muốn
- ✅ **Tải file MP3 về máy**: Xuất file âm thanh chất lượng cao

## Cài đặt

```bash
pip install flask edge-tts
```

## Chạy ứng dụng

**Cách 1**: Bấm đúp chuột vào file `Chay_Trang_Web.bat`

**Cách 2**: Chạy trong terminal:
```bash
python app.py
```

Mở trình duyệt tại: http://localhost:5000

## Cấu trúc thư mục

```
├── app.py                    # Backend Flask + TTS engine
├── Chay_Trang_Web.bat        # File khởi động nhanh
├── tao_am_thanh.py           # Script dùng dòng lệnh
├── tao_tat_ca_giong_mau.py   # Tạo 6 file giọng mẫu
├── templates/
│   └── index.html            # Giao diện web
├── static/
│   ├── audio/                # File audio sinh ra
│   └── samples/              # 6 file mẫu giọng đọc
└── .gitignore
```

## Tác giả

**Congnghi1** - GitHub: [Congnghi-you](https://github.com/Congnghi-you)
