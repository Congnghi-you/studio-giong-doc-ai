import asyncio
import sys
import edge_tts

async def text_to_speech(text_or_file, output_file="output.mp3", voice="vi-VN-NamMinhNeural", rate="+0%"):
    # Nếu là file, đọc nội dung file
    if text_or_file.endswith(".txt"):
        with open(text_or_file, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = text_or_file

    print(f"Bắt đầu tạo âm thanh với giọng: {voice}...")
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(output_file)
    print(f"Đã hoàn thành! File đã lưu tại: {output_file}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Tạo giọng đọc tiếng Việt bằng AI")
    parser.add_argument("--input", "-i", type=str, default="van_ban.txt", help="Văn bản hoặc đường dẫn file .txt")
    parser.add_argument("--output", "-o", type=str, default="audio.mp3", help="Tên file mp3 đầu ra")
    parser.add_argument("--voice", "-v", type=str, default="vi-VN-NamMinhNeural", help="Giọng đọc: vi-VN-NamMinhNeural (Nam) hoặc vi-VN-HoaiMyNeural (Nữ)")
    parser.add_argument("--rate", "-r", type=str, default="+0%", help="Tốc độ đọc, ví dụ: +10% hoặc -10%")
    args = parser.parse_args()

    asyncio.run(text_to_speech(args.input, args.output, args.voice, args.rate))
