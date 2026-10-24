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
WHISPER_MODELS = {}
SUPPORTED_MODEL_SIZES = ("base", "small", "medium")

# --- Tối ưu tốc độ ---
# Số luồng CPU cho Whisper (16 là điểm ngọt trên CPU 18 nhân; nhiều hơn sẽ chậm lại)
WHISPER_THREADS = 24
# beam_size=1 (greedy) nhanh gấp ~2 lần beam_size=5 mà gần như không đổi nội dung
WHISPER_BEAM_SIZE = 1

SUPPORTED_LANGUAGES = {
    "auto": None,
    "vi": "vi",
    "en": "en",
    "zh": "zh",
    "ja": "ja",
    "ko": "ko",
    "th": "th",
    "fr": "fr",
    "de": "de",
    "es": "es",
    "id": "id",
}

# Các trình duyệt yt-dlp có thể lấy cookies trực tiếp
COOKIE_BROWSERS = ("chrome", "edge", "firefox", "brave", "opera", "vivaldi", "safari")


def get_whisper_model(model_size=None):
    model_size = (model_size or DEFAULT_MODEL_SIZE).strip().lower()
    if model_size not in SUPPORTED_MODEL_SIZES:
        model_size = DEFAULT_MODEL_SIZE
    if model_size not in WHISPER_MODELS:
        from faster_whisper import WhisperModel

        print(f"[*] Đang tải mô hình Whisper AI ({model_size})...")
        try:
            # Model đã có trong máy: nạp thẳng, không kiểm tra mạng (tránh treo khi mạng lỗi)
            model = WhisperModel(
                model_size, device="cpu", compute_type="int8", cpu_threads=WHISPER_THREADS,
                local_files_only=True,
            )
        except Exception:
            print("[*] Chưa có model trong máy — đang tải từ Internet (chỉ lần đầu)...")
            model = WhisperModel(
                model_size, device="cpu", compute_type="int8", cpu_threads=WHISPER_THREADS
            )
        WHISPER_MODELS[model_size] = model
        print(f"[+] Whisper AI ({model_size}) đã sẵn sàng!")
    return WHISPER_MODELS[model_size]


def is_valid_url(url):
    return bool(re.match(r"^https?://", url or "", re.IGNORECASE))


def friendly_download_error(raw_error):
    """Chuyển lỗi kỹ thuật của yt-dlp thành thông báo tiếng Việt dễ hiểu."""
    msg = str(raw_error)
    low = msg.lower()
    if "sign in to confirm" in low or "not a bot" in low:
        return ("YouTube đang chặn tải tự động (yêu cầu xác minh không phải bot). "
                "Hãy chọn 'Cookies từ trình duyệt' đang đăng nhập YouTube, hoặc tải file cookies.txt.")
    if "private" in low:
        return "Video ở chế độ riêng tư — cần cookies của tài khoản có quyền xem video đó."
    if "unsupported url" in low or "no suitable" in low:
        return "Link này chưa được yt-dlp hỗ trợ. Hãy kiểm tra lại đường dẫn."
    if "login" in low or "log in" in low or "cookies" in low:
        return "Nền tảng yêu cầu đăng nhập — hãy chọn cookies từ trình duyệt hoặc tải file cookies.txt."
    if "not available in your country" in low or "geo" in low:
        return "Video bị chặn theo quốc gia, không tải được từ Việt Nam."
    if "timed out" in low or "timeout" in low:
        return "Hết thời gian kết nối tới nền tảng. Vui lòng thử lại."
    return msg


def safe_remove(*paths):
    for path in paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


def load_wav_audio(path):
    """Đọc file WAV 16kHz mono 16-bit thành mảng float32.

    faster-whisper gọi av.open(..., metadata_errors="ignore"), nhưng PyAV 19
    đã bỏ tham số này. Tự đọc WAV bằng thư viện chuẩn giúp tránh hẳn lỗi đó
    và cũng nhanh hơn vì không phải giải mã lại lần nữa.
    """
    import wave
    import numpy as np

    with wave.open(path, "rb") as wav_file:
        frames = wav_file.readframes(wav_file.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


# ---------------------------------------------------------------------------
# HẬU XỬ LÝ VĂN BẢN: chấm câu, viết hoa, chia đoạn
# ---------------------------------------------------------------------------
DEFAULT_MODEL_SIZE = "small"
TERMINAL_RE = re.compile(r"[.!?…]+$")

# Câu mồi giúp Whisper viết đúng dấu tiếng Việt và biết ngắt câu
INITIAL_PROMPTS = {
    "vi": (
        "Đây là lời thoại tiếng Việt rõ ràng, có dấu đầy đủ và chấm câu tự nhiên. "
        "Ví dụ: Xin chào, hôm nay chúng ta sẽ bàn về kinh tế. Đúng vậy, giá vàng đang tăng mạnh. "
        "Người dẫn chương trình hỏi: ông nghĩ sao về vấn đề này? Tôi cho rằng rất đáng quan tâm."
    ),
    "en": (
        "This is a clear conversation with natural punctuation. "
        "For example: Hello, today we will discuss the economy. That's right, prices are rising."
    ),
}


def normalize_spacing(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"\s+([,.;:!?%…])", r"\1", text)
    text = re.sub(r"([,;:])(?=[^\s\d])", r"\1 ", text)
    text = re.sub(r"([.!?…])(?=[^\s.!?…])", r"\1 ", text)
    return text


def capitalize_sentence(text):
    for index, char in enumerate(text):
        if char.isalpha():
            return text[:index] + char.upper() + text[index + 1:]
    return text


def polish_sentence(sentence):
    sentence = normalize_spacing(sentence).strip(" ,;:-")
    if not sentence:
        return ""
    sentence = capitalize_sentence(sentence)
    if not TERMINAL_RE.search(sentence):
        sentence += "."
    return sentence


def split_long_sentence(sentence, max_words=55):
    """Cắt câu quá dài tại dấu phẩy gần giữa, tránh trả về một câu dài cả đoạn."""
    words = sentence.split()
    if len(words) <= max_words:
        return [sentence]

    head = " ".join(words[:max_words])
    tail = " ".join(words[max_words:])
    cut = head.rfind(",")
    if cut > len(head) * 0.35:
        return [head[:cut + 1], head[cut + 1:].strip() + " " + tail]
    return [head, tail]


def format_transcript(segments, pause_gap=1.0, max_sentence_words=60,
                      sentences_per_paragraph=4):
    """Ghép các đoạn Whisper trả về thành văn bản có chấm câu, viết hoa, chia đoạn.

    Ưu tiên giữ dấu câu tự nhiên của Whisper; chỉ đóng câu khi có khoảng lặng
    >= pause_gap hoặc câu đã quá dài. Câu nào chưa có dấu kết thúc sẽ được
    thêm dấu chấm, và mọi câu đều được viết hoa chữ đầu.
    """
    sentences = []
    current = []
    current_words = 0
    previous_end = None

    def flush():
        nonlocal current, current_words
        if current:
            sentences.append(" ".join(current))
            current = []
            current_words = 0

    for segment in segments:
        text = normalize_spacing(segment.get("text", ""))
        if not text:
            continue

        gap = segment["start"] - previous_end if previous_end is not None else 0.0
        word_count = len(text.split())

        if current and (gap >= pause_gap or current_words + word_count > max_sentence_words):
            flush()

        current.append(text)
        current_words += word_count
        previous_end = segment["end"]

        if TERMINAL_RE.search(text):
            flush()

    flush()

    polished = []
    for sentence in sentences:
        for piece in re.split(r"(?<=[.!?…])\s+", sentence):
            for part in split_long_sentence(piece):
                formatted = polish_sentence(part)
                if formatted:
                    polished.append(formatted)

    paragraphs = [
        " ".join(polished[i:i + sentences_per_paragraph])
        for i in range(0, len(polished), sentences_per_paragraph)
    ]
    return "\n\n".join(paragraphs), polished

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
    chunk_paths = [os.path.join(temp_dir, f"chunk_{idx:04d}.mp3") for idx in range(len(chunks))]

    # Tối ưu hóa tải song song (Parallel Concurrency): Tải 4 đoạn cùng lúc
    semaphore = asyncio.Semaphore(4)

    async def fetch_chunk(idx, chunk, chunk_file):
        async with semaphore:
            for retry in range(3):
                try:
                    comm = edge_tts.Communicate(chunk, voice=voice, rate=rate, pitch=pitch)
                    await comm.save(chunk_file)
                    if os.path.exists(chunk_file) and os.path.getsize(chunk_file) > 0:
                        return True
                except Exception as e:
                    if retry == 2:
                        raise e
                    await asyncio.sleep(0.5)
            return False

    try:
        tasks = [fetch_chunk(idx, chunk, chunk_paths[idx]) for idx, chunk in enumerate(chunks)]
        await asyncio.gather(*tasks)

        # Ghép nối tuần tự các đoạn thành 1 file MP3 duy nhất
        with open(output_path, "wb") as outfile:
            for cf in chunk_paths:
                if os.path.exists(cf):
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

# API 2: CHUYỂN ÂM THANH / VIDEO (FILE HOẶC LINK ĐA NỀN TẢNG) SANG VĂN BẢN (STT)
@app.route("/api/transcribe", methods=["POST"])
def transcribe_audio():
    cleanup_paths = []
    try:
        source_type = (request.form.get("source_type") or "file").strip().lower()
        if source_type in ("youtube", "link", "url"):
            source_type = "url"

        language_key = (request.form.get("language") or "auto").strip().lower()
        language = SUPPORTED_LANGUAGES.get(language_key)

        model_size = (request.form.get("model_size") or DEFAULT_MODEL_SIZE).strip().lower()
        if model_size not in SUPPORTED_MODEL_SIZES:
            model_size = DEFAULT_MODEL_SIZE

        meta = {}

        if source_type == "url":
            video_url = (request.form.get("video_url") or request.form.get("youtube_url") or "").strip()
            if not video_url:
                return jsonify({"success": False, "error": "Vui lòng dán đường link video!"}), 400
            if not is_valid_url(video_url):
                return jsonify({"success": False, "error": "Link không hợp lệ — link phải bắt đầu bằng http:// hoặc https://"}), 400

            try:
                import yt_dlp
            except ImportError:
                return jsonify({"success": False, "error": "Thiếu thư viện yt-dlp. Chạy lệnh: pip install yt-dlp"}), 500

            cookie_file = None
            cookies_upload = request.files.get("cookies_file")
            if cookies_upload and cookies_upload.filename:
                cookie_file = os.path.join(UPLOAD_DIR, f"cookies_{int(time.time())}.txt")
                cookies_upload.save(cookie_file)
                cleanup_paths.append(cookie_file)

            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join(UPLOAD_DIR, "dl_%(id)s.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "retries": 3,
                "fragment_retries": 3,
                "socket_timeout": 30,
            }

            if cookie_file:
                ydl_opts["cookiefile"] = cookie_file
            else:
                browser = (request.form.get("cookies_browser") or "").strip().lower()
                if browser in COOKIE_BROWSERS:
                    ydl_opts["cookiesfrombrowser"] = (browser,)

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=True)
                    if info.get("_type") == "playlist":
                        entries = [e for e in (info.get("entries") or []) if e]
                        if not entries:
                            return jsonify({"success": False, "error": "Không tìm thấy video nào trong link này."}), 400
                        info = entries[0]
                    downloaded_file = ydl.prepare_filename(info)
                    requested = info.get("requested_downloads") or []
                    if requested and requested[0].get("filepath"):
                        downloaded_file = requested[0]["filepath"]
            except Exception as download_error:
                print("Lỗi tải link:", download_error)
                return jsonify({"success": False, "error": friendly_download_error(download_error)}), 502

            if not downloaded_file or not os.path.exists(downloaded_file):
                return jsonify({"success": False, "error": "Tải video thất bại — không tìm thấy file sau khi tải."}), 502

            cleanup_paths.append(downloaded_file)
            audio_target = downloaded_file
            meta = {
                "title": info.get("title") or "",
                "source": info.get("extractor_key") or info.get("extractor") or "",
                "source_url": info.get("webpage_url") or video_url,
            }
        else:
            if "file" not in request.files:
                return jsonify({"success": False, "error": "Không tìm thấy file tải lên!"}), 400
            file = request.files["file"]
            if file.filename == "":
                return jsonify({"success": False, "error": "Vui lòng chọn 1 file âm thanh hoặc video!"}), 400

            filename = secure_filename(file.filename) or f"upload_{int(time.time())}"
            unique_name = f"{int(time.time())}_{filename}"
            saved_path = os.path.join(UPLOAD_DIR, unique_name)
            file.save(saved_path)
            cleanup_paths.append(saved_path)
            audio_target = saved_path
            meta = {"title": file.filename, "source": "Tệp tải lên"}

        wav_converted = os.path.join(UPLOAD_DIR, f"conv_{int(time.time())}.wav")

        if os.path.exists(FFMPEG_PATH):
            cmd = [FFMPEG_PATH, "-y", "-i", audio_target, "-vn", "-ar", "16000", "-ac", "1",
                   "-c:a", "pcm_s16le", wav_converted]
            result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if result.returncode != 0 or not os.path.exists(wav_converted):
                return jsonify({
                    "success": False,
                    "error": "File/video này không có âm thanh để nhận diện (hoặc định dạng chưa được hỗ trợ)."
                }), 400
            cleanup_paths.append(wav_converted)
            transcribe_input = wav_converted
        else:
            transcribe_input = audio_target

        model = get_whisper_model(model_size)
        print(f"[*] Nhận diện: model={model_size}, ngôn ngữ={language or 'tự động'}, "
              f"file={os.path.basename(transcribe_input)}")

        transcribe_source = transcribe_input
        if wav_converted and os.path.exists(wav_converted):
            transcribe_source = load_wav_audio(wav_converted)

        initial_prompt = INITIAL_PROMPTS.get(language or "")
        if initial_prompt is None and language is None:
            # Chế độ tự động: mồi nhẹ để Whisper vẫn chấm câu, nhưng không ép ngôn ngữ
            initial_prompt = None

        segments, stt_info = model.transcribe(
            transcribe_source,
            language=language,
            beam_size=WHISPER_BEAM_SIZE,
            vad_filter=True,
            initial_prompt=initial_prompt,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
        )

        segments_data = []
        for seg in segments:
            text = seg.text.strip()
            if text:
                segments_data.append({
                    "start": round(seg.start, 1),
                    "end": round(seg.end, 1),
                    "text": text
                })

        full_text, sentences = format_transcript(segments_data)

        if not full_text.strip():
            return jsonify({
                "success": False,
                "error": "Không nhận diện được lời nói nào — video có thể chỉ có nhạc hoặc không có tiếng."
            }), 400

        return jsonify({
            "success": True,
            "text": full_text,
            "sentences": sentences,
            "segments": segments_data,
            "duration": round(getattr(stt_info, "duration", 0) or 0, 1),
            "language": getattr(stt_info, "language", None) or language_key,
            "language_probability": round(getattr(stt_info, "language_probability", 0) or 0, 2),
            "model": model_size,
            **meta
        })

    except Exception as e:
        print("Lỗi nhận diện:", e)
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        safe_remove(*cleanup_paths)


# API 3: KIỂM TRA NHANH LINK VIDEO (không tải, chỉ lấy tiêu đề/thời lượng)
@app.route("/api/link-info", methods=["POST"])
def link_info():
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    if not is_valid_url(url):
        return jsonify({"success": False, "error": "Link không hợp lệ."}), 400

    try:
        import yt_dlp
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "socket_timeout": 20,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if info.get("_type") == "playlist":
            entries = [e for e in (info.get("entries") or []) if e]
            info = entries[0] if entries else {}

        duration = info.get("duration") or 0
        return jsonify({
            "success": True,
            "title": info.get("title") or "",
            "duration": round(duration, 1) if duration else 0,
            "source": info.get("extractor_key") or info.get("extractor") or "",
            "uploader": info.get("uploader") or "",
        })
    except Exception as e:
        return jsonify({"success": False, "error": friendly_download_error(e)}), 502

@app.route("/static/audio/<path:filename>")
def download_file(filename):
    return send_from_directory(AUDIO_DIR, filename, as_attachment=False)

if __name__ == "__main__":
    print("Studio Giọng Đọc & Chuyển Đổi AI Tiếng Việt đang chạy...")
    print("Mở trình duyệt tại: http://localhost:5000")
    try:
        from waitress import serve
        serve(app, host="127.0.0.1", port=5000, threads=8)
    except ImportError:
        app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
