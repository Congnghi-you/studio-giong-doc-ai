import os
import re
import sys
import time
import asyncio
import tempfile
import shutil
import subprocess

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import edge_tts

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config['MAX_CONTENT_LENGTH'] = 2048 * 1024 * 1024  # Cho phép upload file lên đến 2GB

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(BASE_DIR, "static", "audio")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
FFMPEG_PATH = os.path.join(BASE_DIR, "ffmpeg.exe")

os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 7 PHONG CÁCH GIỌNG ĐỌC AI
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

# Quản lý lazy load model Whisper để tiết kiệm tài nguyên
whisper_model = None

def get_whisper_model(model_size="base"):
    global whisper_model
    if whisper_model is None:
        from faster_whisper import WhisperModel
        print(f"[*] Đang tải mô hình Whisper AI ({model_size}) tối ưu cho 72 luồng CPU...")
        whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8", cpu_threads=16)
        print("[+] Whisper AI đã sẵn sàng!")
    return whisper_model

def preprocess_text(text, pause_style="standard"):
    if not text:
        return ""
    text = re.sub(r'\[ngh[iỉ]\s*(\d+)s?\]', lambda m: '... ' * min(int(m.group(1)), 4), text, flags=re.IGNORECASE)
    text = re.sub(r'\[(ngh[iỉ]|pause|thở)\]', '... ', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*([!?]+)\s*', r'\1 ... ', text)
    text = re.sub(r'\s*([:;])\s*', r'\1, ', text)
    if pause_style == "deep":
        text = re.sub(r'\n+', '\n\n... ', text)
    return text.strip()

def split_text_into_chunks(text, max_chars=1600):
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

# API 1: TẠO GIỌNG ĐỌC AI TỪ VĂN BẢN
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

# API 2: CHUYỂN ÂM THANH / VIDEO SANG VĂN BẢN (STT)
@app.route("/api/transcribe", methods=["POST"])
def transcribe_audio():
    try:
        source_type = request.form.get("source_type", "file")
        audio_target = None
        temp_input_file = None

        if source_type == "youtube":
            yt_url = request.form.get("youtube_url", "").strip()
            if not yt_url:
                return jsonify({"success": False, "error": "Vui lòng nhập đường link YouTube hợp lệ!"}), 400

            import yt_dlp
            out_tmpl = os.path.join(UPLOAD_DIR, 'yt_%(id)s.%(ext)s')
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': out_tmpl,
                'quiet': True,
                'no_warnings': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(yt_url, download=True)
                downloaded_file = ydl.prepare_filename(info)
                temp_input_file = downloaded_file
                audio_target = downloaded_file
        else:
            if 'file' not in request.files:
                return jsonify({"success": False, "error": "Không tìm thấy file tải lên!"}), 400
            file = request.files['file']
            if file.filename == '':
                return jsonify({"success": False, "error": "Vui lòng chọn 1 file âm thanh hoặc video!"}), 400

            filename = secure_filename(file.filename)
            unique_name = f"{int(time.time())}_{filename}"
            saved_path = os.path.join(UPLOAD_DIR, unique_name)
            file.save(saved_path)
            temp_input_file = saved_path
            audio_target = saved_path

        wav_converted = os.path.join(UPLOAD_DIR, f"conv_{int(time.time())}.wav")

        if os.path.exists(FFMPEG_PATH):
            cmd = [FFMPEG_PATH, "-y", "-i", audio_target, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav_converted]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            transcribe_input = wav_converted
        else:
            transcribe_input = audio_target

        model = get_whisper_model("base")
        segments, info = model.transcribe(transcribe_input, language="vi", beam_size=5, vad_filter=True)

        full_text_list = []
        segments_data = []

        for seg in segments:
            text = seg.text.strip()
            if text:
                full_text_list.append(text)
                segments_data.append({
                    "start": round(seg.start, 1),
                    "end": round(seg.end, 1),
                    "text": text
                })

        full_text = " ".join(full_text_list)

        try:
            if os.path.exists(wav_converted):
                os.remove(wav_converted)
            if temp_input_file and os.path.exists(temp_input_file):
                os.remove(temp_input_file)
        except Exception:
            pass

        return jsonify({
            "success": True,
            "text": full_text,
            "segments": segments_data,
            "duration": round(info.duration, 1),
            "language": info.language
        })

    except Exception as e:
        print("Lỗi nhận diện:", e)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/static/audio/<path:filename>")
def download_file(filename):
    return send_from_directory(AUDIO_DIR, filename, as_attachment=False)

if __name__ == "__main__":
    print("Studio Giọng Đọc & Chuyển Đổi AI Tiếng Việt đang chạy...")
    print("Mở trình duyệt tại: http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
