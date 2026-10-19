import os
import re
import sys
import time
import asyncio
import tempfile
import shutil

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from flask import Flask, render_template, request, jsonify, send_from_directory
import edge_tts

app = Flask(__name__, static_folder="static", template_folder="templates")

AUDIO_DIR = os.path.join(os.path.dirname(__file__), "static", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

# 7 PHONG CÁCH GIỌNG ĐỌC ĐÃ TINH CHỈNH TỐI ƯU CƯỜNG ĐIỆU VÀ CẢM XÚC:
# Trong đó bao gồm giọng mô phỏng theo đặc trưng âm học của bạn (120.3Hz, độ trầm ấm sâu, nhịp ngắt nghỉ tự nhiên)
VOICE_PRESETS = {
    "giong_cua_toi": {
        "name": "⭐ Giọng Mô Phỏng Của Bạn (Trầm Ấm & Tự Nhiên)",
        "gender": "Nam",
        "voice": "vi-VN-NamMinhNeural",
        "rate": "-4%",
        "pitch": "-6Hz",
        "desc": "Được tinh chỉnh theo mẫu giọng thật: Tần số trầm ấm 120Hz, dải âm 90-160Hz, nhịp điệu nhấn nhá tự nhiên.",
        "sample": "/static/samples/sample_giong_cua_toi.mp3"
    },
    "nam_truyencam": {
        "name": "Nam Minh - Kể Chuyện & Sách Nói",
        "gender": "Nam",
        "voice": "vi-VN-NamMinhNeural",
        "rate": "-6%",
        "pitch": "-8Hz",
        "desc": "Trầm ấm sâu, giàu cảm xúc, nhấn nhá chậm rãi, ngắt nghỉ theo từng mạch cảm xúc câu chuyện.",
        "sample": "/static/samples/1_Nam_KeChuyen_SachNoi.mp3"
    },
    "nam_thoisu": {
        "name": "Nam Minh - Thời Sự & Báo Chí",
        "gender": "Nam",
        "voice": "vi-VN-NamMinhNeural",
        "rate": "+2%",
        "pitch": "+0Hz",
        "desc": "Rõ ràng, dứt khoát, cường điệu nghiêm túc và chuẩn mực của phát thanh viên truyền hình.",
        "sample": "/static/samples/2_Nam_ThoiSu_TinTuc.mp3"
    },
    "nam_nangdong": {
        "name": "Nam Minh - Năng Động & Review",
        "gender": "Nam",
        "voice": "vi-VN-NamMinhNeural",
        "rate": "+12%",
        "pitch": "+6Hz",
        "desc": "Hào sảng, cuốn hút, giàu năng lượng, rất thích hợp video ngắn, TikTok, YouTube review.",
        "sample": "/static/samples/3_Nam_NangDong_Review.mp3"
    },
    "nu_diudang": {
        "name": "Hoài My - Dịu Dàng & Tâm Sự",
        "gender": "Nữ",
        "voice": "vi-VN-HoaiMyNeural",
        "rate": "-8%",
        "pitch": "-5Hz",
        "desc": "Giọng nữ nhẹ nhàng, êm ái, tha thiết, thích hợp tản văn, truyện tình cảm, radio đêm.",
        "sample": "/static/samples/4_Nu_DiuDang_TamSu.mp3"
    },
    "nu_thuyetminh": {
        "name": "Hoài My - Thuyết Minh Chuẩn",
        "gender": "Nữ",
        "voice": "vi-VN-HoaiMyNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "desc": "Rành mạch, tự nhiên, diễn cảm thông minh, giọng phổ thông chuẩn mực.",
        "sample": "/static/samples/5_Nu_ThuyetMinh_Chuan.mp3"
    },
    "nu_tuoitre": {
        "name": "Hoài My - Trẻ Trung & Vlog",
        "gender": "Nữ",
        "voice": "vi-VN-HoaiMyNeural",
        "rate": "+9%",
        "pitch": "+9Hz",
        "desc": "Tươi vui, hoạt bát, nhí nhảnh, nhiều biểu cảm năng động cho vlog đời sống.",
        "sample": "/static/samples/6_Nu_TuoiTre_Vlog.mp3"
    }
}

def preprocess_text(text, pause_style="standard"):
    """
    Tiền xử lý ngữ điệu & ngắt nhịp biểu cảm:
    - Nhận diện các thẻ [nghỉ 1s], [nghỉ 2s], [thở]
    - Tự động chuẩn hóa dấu câu để máy đọc AI có nhịp thở và biểu cảm câu như người thật
    """
    if not text:
        return ""

    # Xử lý các thẻ dừng nghỉ chủ động
    text = re.sub(r'\[ngh[iỉ]\s*(\d+)s?\]', lambda m: '... ' * min(int(m.group(1)), 4), text, flags=re.IGNORECASE)
    text = re.sub(r'\[(ngh[iỉ]|pause|thở)\]', '... ', text, flags=re.IGNORECASE)

    # Thêm khoảng lặng tự nhiên cho các dấu câu biểu cảm (!, ?, ..., :)
    text = re.sub(r'\s*([!?]+)\s*', r'\1 ... ', text)
    text = re.sub(r'\s*([:;])\s*', r'\1, ', text)

    # Chế độ kể chuyện cảm xúc (nghỉ sâu giữa các đoạn văn)
    if pause_style == "deep":
        text = re.sub(r'\n+', '\n\n... ', text)
    
    return text.strip()

def split_text_into_chunks(text, max_chars=1600):
    """
    Chia văn bản thông minh theo câu hoàn chỉnh để đảm bảo không ngắt giữa chừng,
    chạy êm ả cho văn bản dài 20 - 60 phút.
    """
    paragraphs = text.split("\n")
    chunks = []
    current_chunk = ""

    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        
        if len(p) > max_chars:
            sentences = re.split(r'([.!?]+[\s\n]+)', p)
            temp = ""
            for s in sentences:
                if len(temp) + len(s) < max_chars:
                    temp += s
                else:
                    if temp.strip():
                        chunks.append(temp.strip())
                    temp = s
            if temp.strip():
                chunks.append(temp.strip())
        else:
            if len(current_chunk) + len(p) + 2 < max_chars:
                current_chunk += ("\n" if current_chunk else "") + p
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = p

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks if chunks else [text]

async def generate_speech_async(text, voice, rate, pitch, output_path):
    chunks = split_text_into_chunks(text, max_chars=1600)
    
    if len(chunks) == 1:
        communicate = edge_tts.Communicate(chunks[0], voice=voice, rate=rate, pitch=pitch)
        await communicate.save(output_path)
        return

    temp_dir = tempfile.mkdtemp(prefix="tts_chunks_")
    chunk_files = []
    
    try:
        for idx, chunk in enumerate(chunks):
            chunk_file = os.path.join(temp_dir, f"chunk_{idx:04d}.mp3")
            for retry in range(3):
                try:
                    comm = edge_tts.Communicate(chunk, voice=voice, rate=rate, pitch=pitch)
                    await comm.save(chunk_file)
                    if os.path.exists(chunk_file) and os.path.getsize(chunk_file) > 0:
                        chunk_files.append(chunk_file)
                        break
                except Exception as e:
                    if retry == 2:
                        raise e
                    await asyncio.sleep(1)

        with open(output_path, "wb") as outfile:
            for cf in chunk_files:
                with open(cf, "rb") as infile:
                    shutil.copyfileobj(infile, outfile)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

@app.route("/")
def index():
    return render_template("index.html", presets=VOICE_PRESETS)

@app.route("/api/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json(force=True, silent=True) or {}
        raw_text = data.get("text", "").strip()
        preset_key = data.get("preset", "giong_cua_toi")
        custom_rate = data.get("rate")
        custom_pitch = data.get("pitch")
        pause_style = data.get("pause_style", "standard")

        if not raw_text:
            return jsonify({"success": False, "error": "Vui lòng nhập văn bản cần đọc!"}), 400

        preset = VOICE_PRESETS.get(preset_key, VOICE_PRESETS["giong_cua_toi"])
        voice = preset["voice"]
        rate = custom_rate if custom_rate else preset["rate"]
        pitch = custom_pitch if custom_pitch else preset["pitch"]

        processed_text = preprocess_text(raw_text, pause_style=pause_style)

        filename = f"audio_{int(time.time())}_{preset_key}.mp3"
        output_path = os.path.join(AUDIO_DIR, filename)

        asyncio.run(generate_speech_async(processed_text, voice, rate, pitch, output_path))

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            if os.path.exists(output_path):
                os.remove(output_path)
            return jsonify({"success": False, "error": "Không thể tạo file âm thanh hoặc kết nối bị gián đoạn. Vui lòng thử lại!"}), 500

        word_count = len(raw_text.split())
        est_minutes = round(word_count / 145, 1)

        return jsonify({
            "success": True,
            "audio_url": f"/static/audio/{filename}",
            "filename": filename,
            "word_count": word_count,
            "est_minutes": est_minutes,
            "voice_name": preset["name"]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/static/audio/<path:filename>")
def download_file(filename):
    return send_from_directory(AUDIO_DIR, filename, as_attachment=False)

if __name__ == "__main__":
    print("Studio Giọng Đọc AI Tiếng Việt đang chạy...")
    print("Mở trình duyệt tại: http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
