import os
import subprocess
import uuid
import re
import glob
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yt_dlp
import whisper

app = FastAPI(title="ClipForge Pro AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

# Whisper AI ماڈل (سب سے متوازن اور طاقتور "base" ماڈل)
whisper_model = None

def get_whisper():
    global whisper_model
    if whisper_model is None:
        whisper_model = whisper.load_model("base")
    return whisper_model

def parse_time(time_str: str) -> float:
    parts = list(map(int, re.split(r'[:.]', str(time_str).strip())))
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0.0

def format_ass_time(seconds: float) -> str:
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    return f"{hrs}:{mins:02d}:{secs:02d}.{cs:02d}"

def get_caption_style_config(style_name: str):
    styles = {
        "hormozi": {"primary": "&H0000FFFF", "outline": "&H00000000", "border_style": "1", "outline_w": "4", "shadow": "2"},
        "mrbeast": {"primary": "&H000033FF", "outline": "&H0000FFFF", "border_style": "1", "outline_w": "5", "shadow": "3"},
        "neon": {"primary": "&H0000FF00", "outline": "&H00000000", "border_style": "1", "outline_w": "4", "shadow": "4"},
        "blue": {"primary": "&H00FFAA00", "outline": "&H00000000", "border_style": "1", "outline_w": "4", "shadow": "2"},
        "box": {"primary": "&H00FFFFFF", "outline": "&H00000000", "border_style": "3", "outline_w": "3", "shadow": "0"},
        "pink": {"primary": "&H00FF00CC", "outline": "&H00000000", "border_style": "1", "outline_w": "4", "shadow": "2"},
        "gold": {"primary": "&H0022D4FD", "outline": "&H00000000", "border_style": "1", "outline_w": "4", "shadow": "2"},
        "minimal": {"primary": "&H00FFFFFF", "outline": "&H00000000", "border_style": "1", "outline_w": "2", "shadow": "1"}
    }
    return styles.get(style_name, styles["hormozi"])

def create_ass_file(filepath: str, text: str, duration: float, template: str):
    cfg = get_caption_style_config(template)
    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,74,{cfg['primary']},-1,{cfg['outline']},&H80000000,-1,0,0,0,100,100,0,0,{cfg['border_style']},{cfg['outline_w']},{cfg['shadow']},2,60,60,360,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    words = text.split()
    if not words:
        words = ["CHECK", "THIS", "OUT!"]

    chunk_size = 3
    chunks = [" ".join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]
    chunk_dur = duration / max(len(chunks), 1)

    for i, chk in enumerate(chunks):
        c_start = format_ass_time(i * chunk_dur)
        c_end = format_ass_time((i + 1) * chunk_dur)
        ass_content += f"Dialogue: 0,{c_start},{c_end},Default,,0,0,0,,{chk.upper()}\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(ass_content)

class ClipMeta(BaseModel):
    timestamp_start: str
    timestamp_end: str
    title: Optional[str] = "Clip"
    caption_text: Optional[str] = ""

class CutRequest(BaseModel):
    video_path: str
    clips: Optional[List[ClipMeta]] = []
    aspect_ratio: str = "9:16"
    caption_style: str = "hormozi"
    auto_ai: bool = True
    clips_count: int = 3

class YoutubeRequest(BaseModel):
    url: str

@app.get("/")
def health_check():
    return {"status": "ok", "message": "Backend running with Auto-Whisper AI"}

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    ext = file.filename.split(".")[-1]
    dest_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}.{ext}")
    with open(dest_path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024 * 10):
            buffer.write(chunk)
    return {"status": "success", "path": dest_path}

@app.post("/download-yt")
def download_youtube_video(payload: YoutubeRequest):
    unique_id = uuid.uuid4().hex[:8]
    output_template = os.path.join(UPLOAD_DIR, f"yt_{unique_id}.%(ext)s")

    ydl_opts = {
        'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best',
        'outtmpl': output_template,
        'merge_output_format': 'mp4',
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['en'],
        'quiet': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(payload.url, download=True)
            video_filename = ydl.prepare_filename(info)
            if not video_filename.endswith('.mp4'):
                video_filename = os.path.splitext(video_filename)[0] + '.mp4'
        return {"status": "success", "path": video_filename, "title": info.get('title', 'Video')}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# آٹو AI ٹرانسکرپٹ اور کلپ جنریٹر
@app.post("/cut")
def cut_video_clips(payload: CutRequest):
    if not os.path.exists(payload.video_path):
        raise HTTPException(status_code=404, detail="Video file not found")

    clips_to_process = payload.clips or []

    # اگر ٹرانسکرپٹ نہیں دیا گیا تو خودکار Whisper AI آڈیو سنے گا
    if not clips_to_process or payload.auto_ai:
        model = get_whisper()
        transcription = model.transcribe(payload.video_path)
        segments = transcription.get("segments", [])
        
        clips_to_process = []
        # طویل وائرل سیگمنٹس کو یکجا کرنا (30 سے 45 سیکنڈ کے کلپس)
        current_text = []
        seg_start = 0.0
        
        for seg in segments:
            if not current_text:
                seg_start = seg["start"]
            current_text.append(seg["text"])
            
            if (seg["end"] - seg_start) >= 30:
                clips_to_process.append(ClipMeta(
                    timestamp_start=str(round(seg_start, 2)),
                    timestamp_end=str(round(seg["end"], 2)),
                    title=f"Viral Highlight #{len(clips_to_process) + 1}",
                    caption_text=" ".join(current_text)
                ))
                current_text = []
                if len(clips_to_process) >= payload.clips_count:
                    break

        if not clips_to_process:
            clips_to_process = [ClipMeta(timestamp_start="10", timestamp_end="40", title="Best Moment", caption_text=transcription.get("text", "")[:120])]

    results = []
    ratio_filters = {
        "9:16": "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "1:1": "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080",
        "16:9": "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
    }
    base_vf = ratio_filters.get(payload.aspect_ratio, ratio_filters["9:16"])

    for i, clip in enumerate(clips_to_process):
        start_sec = parse_time(clip.timestamp_start)
        end_sec = parse_time(clip.timestamp_end)
        duration = max(end_sec - start_sec, 20.0)

        output_filename = f"clip_{uuid.uuid4().hex[:8]}_{i+1}.mp4"
        output_filepath = os.path.join(OUTPUT_DIR, output_filename)

        vf_filter = base_vf
        ass_path = None
        if payload.caption_style != "none":
            ass_path = os.path.join(OUTPUT_DIR, f"sub_{uuid.uuid4().hex[:6]}.ass")
            create_ass_file(ass_path, clip.caption_text or clip.title, duration, payload.caption_style)
            vf_filter += f",ass={ass_path}"

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-i", payload.video_path,
            "-t", str(duration),
            "-vf", vf_filter,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            output_filepath
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            file_size = round(os.path.getsize(output_filepath) / (1024 * 1024), 2)
            results.append({
                "url": f"/outputs/{output_filename}",
                "filename": output_filename,
                "title": clip.title,
                "size_mb": file_size,
                "error": False
            })
        except subprocess.CalledProcessError as e:
            results.append({"title": clip.title, "error": True, "msg": str(e.stderr.decode() if e.stderr else e)})
        finally:
            if ass_path and os.path.exists(ass_path):
                os.remove(ass_path)

    return {"clips": results}
