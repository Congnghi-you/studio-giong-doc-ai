# 🎙️ Studio Giọng Đọc AI Tiếng Việt

Ứng dụng web chuyển đổi văn bản dài (20+ phút) thành âm thanh giọng đọc AI tự nhiên, mượt mà — kèm công cụ chuyển video/âm thanh thành văn bản (Whisper AI).

## Tính năng chính

### Tab 1 — Giọng đọc AI (Text → Speech)
- ✅ **7 phong cách giọng đọc**: 3 Nam (Kể chuyện, Thời sự, Năng động) + 3 Nữ (Dịu dàng, Thuyết minh, Trẻ trung) + 1 giọng mô phỏng
- ✅ **Hỗ trợ văn bản dài 20+ phút**: Tự động chia đoạn, ghép nối mượt mà
- ✅ **Nghe thử trực tiếp trên web**, tuỳ chỉnh tốc độ / cao độ, chèn khoảng nghỉ
- ✅ **Văn bản dài tự chia tối đa 2.000 từ/phần**: Tạo lần lượt từng phần, tải ngay phần hoàn tất rồi bấm tiếp tục
- ✅ Các đoạn gửi tới TTS được xử lý tuần tự; nếu lỗi, có thể thử lại mà không tạo lại những đoạn nhỏ đã thành công
- ✅ **Giao diện 5 ngôn ngữ**: Tiếng Việt, Anh, Trung, Nhật và Hàn

### Tab 2 — Chuyển Video → Văn bản (Speech → Text)
- ✅ **Dán link từ 1000+ nền tảng**: YouTube, TikTok, Facebook, Instagram, X/Twitter, Vimeo, Bilibili, Douyin… (qua `yt-dlp`)
- ✅ **Hoặc tải file trực tiếp**: `.mp4, .mkv, .mov, .webm, .m4a, .mp3, .wav` (tới 2GB)
- ✅ **Tự động nhận diện ngôn ngữ** (hoặc chọn tay: Việt, Anh, Trung, Nhật, Hàn, Thái…)
- ✅ **3 mức độ chính xác**: `base` (nhanh) / `small` (cân bằng) / `medium` (chính xác nhất)
- ✅ **Cookies tích hợp**: lấy trực tiếp từ Edge/Chrome/Firefox hoặc tải `cookies.txt` — dùng cho video riêng tư, YouTube chặn bot
- ✅ **Kiểm tra link** trước khi tải (tiêu đề, nền tảng, thời lượng)
- ✅ Kết quả: sao chép, tải `.txt`, hoặc đẩy thẳng sang tab Giọng đọc

## Cài đặt

**Không cần làm gì.** Máy này đã cài sẵn toàn bộ thư viện — chỉ cần bấm đúp `Chay_Trang_Web.bat`.

Nếu chuyển sang máy khác: cài **Python 3.13** từ [python.org](https://www.python.org/downloads/) (nhớ tick *"Add python.exe to PATH"*), rồi bấm đúp `Chay_Trang_Web.bat` — nó tự cài thư viện còn thiếu trong lần chạy đầu.

Yêu cầu: **Python 3.13** và `ffmpeg.exe` đặt cạnh `app.py` (đã có sẵn trong thư mục).

> Các thư viện được ghim phiên bản trong `requirements.txt` vì bản mới hơn bị crash trên Windows:
> `ctranslate2==4.6.0`, `onnxruntime==1.20.1`, `setuptools<81`.

## Chạy ứng dụng

**Cách 1 (khuyên dùng)**: Bấm đúp `Chay_Trang_Web.bat` — tự giải phóng cổng 5000, tự mở trình duyệt.

**Cách 2** (nếu cần xem log):
```bash
python app.py
```

Mở trình duyệt tại: http://localhost:5000

## Mẹo dùng tab chuyển video thành văn bản

| Tình huống | Cách xử lý |
|---|---|
| Video công khai YouTube/TikTok | Dán link → Kiểm tra → Chuyển |
| Facebook/Instagram video riêng tư | Chọn "Cookies từ trình duyệt" đang đăng nhập |
| YouTube báo "Sign in to confirm you're not a bot" | Chọn cookies Edge/Chrome, hoặc tải `cookies.txt` (tiện ích *Get cookies.txt LOCALLY*) |
| Video tiếng nước ngoài | Đổi "Ngôn ngữ trong video" sang ngôn ngữ tương ứng |
| Văn bản còn sai dấu | Đổi model sang `medium` (chính xác nhất, chậm gấp ~5 lần) |
| Video không có tiếng | Không nhận diện được — cần video có âm thanh |

> Văn bản trả về đã được tự động **viết hoa đầu câu, chấm câu và chia đoạn**.
> Model mặc định là `small` (nhanh, khá chính xác); `medium` cho kết quả tốt nhất nhưng chậm hơn nhiều.

## Cấu trúc thư mục

```
├── app.py                    # Backend Flask + TTS + STT
├── Chay_Trang_Web.bat        # File khởi động nhanh
├── requirements.txt          # Thư viện cần cài
├── tao_am_thanh.py           # Script dùng dòng lệnh
├── tao_tat_ca_giong_mau.py   # Tạo 6 file giọng mẫu
├── ffmpeg.exe                # Bộ chuyển đổi âm thanh
├── templates/
│   └── index.html            # Giao diện web
├── static/
│   ├── audio/                # File audio sinh ra
│   ├── uploads/              # File tải lên / tải về tạm thời
│   └── samples/              # 6 file mẫu giọng đọc
```

## Tác giả

**Congnghi1** - GitHub: [Congnghi-you](https://github.com/Congnghi-you)
