import asyncio
import edge_tts
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

samples = [
    {
        "filename": "1_Nam_KeChuyen_SachNoi.mp3",
        "voice": "vi-VN-NamMinhNeural",
        "rate": "-5%",
        "pitch": "-5Hz",
        "title": "Nam Minh - Kể Chuyện & Sách Nói",
        "text": "Đêm đã về khuya, không gian xung quanh dần chìm vào tĩnh lặng... Những con đường quen thuộc giờ đây chỉ còn lại ánh đèn vàng hắt hiu trong màn sương đêm. Cuộc sống đôi khi trôi qua quá nhanh, khiến chúng ta quên mất việc dừng lại một nhịp, để lắng nghe những rung cảm sâu lắng nhất của tâm hồn mình."
    },
    {
        "filename": "2_Nam_ThoiSu_TinTuc.mp3",
        "voice": "vi-VN-NamMinhNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "title": "Nam Minh - Thời Sự & Báo Chí",
        "text": "Xin kính chào quý vị và các bạn. Mời quý vị theo dõi bản tin cập nhật tình hình kinh tế và xã hội hôm nay. Theo báo cáo mới nhất, thị trường trong nước tiếp tục ghi nhận mức tăng trưởng ổn định, các chỉ số phát triển hạ tầng và chuyển đổi số đều đạt kết quả tích cực so với cùng kỳ năm trước."
    },
    {
        "filename": "3_Nam_NangDong_Review.mp3",
        "voice": "vi-VN-NamMinhNeural",
        "rate": "+10%",
        "pitch": "+5Hz",
        "title": "Nam Minh - Năng Động & Review",
        "text": "Chào các bạn! Chào mừng các bạn đã quay trở lại với kênh của mình! Hôm nay, mình sẽ giới thiệu đến các bạn một công nghệ cực kỳ ấn tượng và mới mẻ. Hãy cùng mình trải nghiệm thực tế ngay bây giờ xem nó có thực sự đỉnh như lời đồn không nhé!"
    },
    {
        "filename": "4_Nu_DiuDang_TamSu.mp3",
        "voice": "vi-VN-HoaiMyNeural",
        "rate": "-8%",
        "pitch": "-5Hz",
        "title": "Hoài My - Dịu Dàng & Tâm Sự",
        "text": "Có những ngày, ta chỉ muốn tìm cho mình một góc nhỏ bình yên... Ngồi bên tách trà ấm, lắng nghe tiếng mưa rơi rả rích ngoài hiên. Dù ngoài kia thế giới có ồn ào và vội vã đến đâu, hy vọng rằng bạn luôn tìm thấy sự an nhiên trong chính trái tim mình."
    },
    {
        "filename": "5_Nu_ThuyetMinh_Chuan.mp3",
        "voice": "vi-VN-HoaiMyNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "title": "Hoài My - Thuyết Minh Chuẩn",
        "text": "Chào mừng bạn đến với chuyên mục kiến thức đời sống. Trong chương trình hôm nay, chúng ta sẽ cùng tìm hiểu về những phương pháp rèn luyện trí nhớ và cách duy trì năng lượng tích cực cho một ngày làm việc hiệu quả."
    },
    {
        "filename": "6_Nu_TuoiTre_Vlog.mp3",
        "voice": "vi-VN-HoaiMyNeural",
        "rate": "+8%",
        "pitch": "+8Hz",
        "title": "Hoài My - Trẻ Trung & Vlog",
        "text": "Hế lô mọi người! Lại là mình đây. Hôm nay mình sẽ dắt mọi người đi khám phá một địa điểm siêu thú vị mà chắc chắn ai xem xong cũng muốn xách ba lô lên và đi ngay lập tức. Cùng đi với mình nào!"
    }
]

async def generate_all():
    out_dir = os.path.join(os.path.dirname(__file__), "mau_giong_doc")
    os.makedirs(out_dir, exist_ok=True)
    
    for item in samples:
        filepath = os.path.join(out_dir, item["filename"])
        print(f"Đang tạo: {item['title']} -> {item['filename']}...")
        comm = edge_tts.Communicate(item["text"], item["voice"], rate=item["rate"], pitch=item["pitch"])
        await comm.save(filepath)
        print(f"  -> Xong: {filepath} ({os.path.getsize(filepath)} bytes)")

if __name__ == "__main__":
    asyncio.run(generate_all())
