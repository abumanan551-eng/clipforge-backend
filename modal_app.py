import modal
import os
import subprocess
import uuid
import re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import yt_dlp

image = (
    modal.Image.debian_slim()
    .apt_install("ffmpeg", "curl")
    .pip_install("fastapi", "uvicorn", "yt-dlp", "python-multipart")
)

app = modal.App("clipforge-backend")
web_app = FastAPI()

web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "/tmp/uploads"
OUTPUT_DIR = "/tmp/outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

web_app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

def format_ass_time(seconds: float) -> str:
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    return f"{hrs}:{mins:02d}:{secs:02d}.{cs:02d}"

def get_caption_style_config(style_name: str):
    styles = {
        "hormozi": {"primary": "&H0000FFFF", "outline": "&H00000000", "border_style": "1", "outline_w": "4", "shadow": "2", "font": "Arial Black"},
        "capcut_pop": {"primary": "&H0000D7FF", "outline": "&H00000000", "border_style": "3", "outline_w": "5", "shadow": "0", "font": "Impact"},
        "mrbeast": {"primary": "&H003333FF", "outline": "&H0000FFFF", "border_style": "1", "outline_w": "5", "shadow": "4", "font": "Arial Black"},
        "neon": {"primary": "&H0000FF55", "outline": "&H00000000", "border_style": "1", "outline_w": "4", "shadow": "4", "font": "Arial Black"},
        "tiktok_red": {"primary": "&H000000FF", "outline": "&H00FFFFFF", "border_style": "1", "outline_w": "4", "shadow": "2", "font": "Arial Black"},
        "glow_pink": {"primary": "&H00FF00FF", "outline": "&H00000000", "border_style": "1", "outline_w": "4", "shadow": "3", "font": "Arial Black"},
        "minimal": {"primary": "&H00FFFFFF", "outline": "&H00000000", "border_style": "1", "outline_w": "2", "shadow": "1", "font": "Arial"}
    }
    return styles.get(style_name, styles["hormozi"])

def create_ass_file(filepath: str, duration: float, template: str):
    cfg = get_caption_style_config(template)
    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{cfg['font']},72,{cfg['primary']},-1,{cfg['outline']},&H80000000,-1,0,0,0,100,100,0,0,{cfg['border_style']},{cfg['outline_w']},{cfg['shadow']},2,60,60,380,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    words_pool = ["WAIT FOR THIS", "NOBODY EXPECTED THIS", "LISTEN VERY CAREFULLY", "THIS IS SHOCKING", "WATCH UNTIL END", "BEST VIRAL MOMENT"]
    chunk_dur = 2.5
    total_chunks = int(duration // chunk_dur)

    for i in range(total_chunks):
        c_start = format_ass_time(i * chunk_dur)
        c_end = format_ass_time((i + 1) * chunk_dur)
        text = words_pool[i % len(words_pool)]
        ass_content += f"Dialogue: 0,{c_start},{c_end},Default,,0,0,0,,{text}\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(ass_content)

def generate_viral_metadata(video_title: str, idx: int):
    clean = re.sub(r'[^\w\s]', '', video_title).strip()
    words = clean.split()
    core_kw = words[0] if words else "Podcast"

    hooks = [
        f"The darkest truth about {core_kw} nobody tells you 🤯",
        f"Why everyone is silently terrified of {core_kw} 😱",
        f"He exposed the entire {core_kw} reality in 30 seconds 🔥",
        f"This unexpected moment left everyone speechless 😳",
        f"The most controversial debate on {core_kw} ever 🚨",
        f"Never ignore this critical warning about {core_kw} ⚠️",
        f"Proof that everything we knew was completely wrong 🧠",
        f"The untold reality that went instantly viral 👀",
        f"Watch what happens right before the end... 💥",
        f"Why millionaires never talk about {core_kw} publicly 🤫"
    ]
    return hooks[idx % len(hooks)], f"#{core_kw} #PodcastViral #Shorts #LifeLessons #Trending"

@web_app.get("/")
def home():
    return {"status": "ok"}

@web_app.post("/download-yt")
def download_youtube_video(payload: dict):
    raw_url = payload.get("url", "").strip()
    clean_url = raw_url.split("&")[0].split("?si=")[0]
    count = int(payload.get("count", 3))
    dur = float(payload.get("duration", 30))

    unique_id = uuid.uuid4().hex[:8]
    output_template = os.path.join(UPLOAD_DIR, f"yt_{unique_id}.%(ext)s")

    ydl_opts = {
        'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best',
        'outtmpl': output_template,
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'extractor_args': {'youtube': {'player_client': ['android']}}
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=True)
            filename = ydl.prepare_filename(info)
            if not filename.endswith('.mp4'):
                filename = os.path.splitext(filename)[0] + '.mp4'

        total_duration = float(info.get('duration', 120.0) or 120.0)
        usable_duration = max(total_duration - dur - 10, 10.0)
        step = usable_duration / max(count, 1)

        clips = []
        for i in range(count):
            start = round(10.0 + (i * step), 2)
            end = round(start + dur, 2)
            clips.append({"timestamp_start": str(start), "timestamp_end": str(end)})

        return {"status": "success", "path": filename, "title": info.get('title', 'Podcast Video'), "clips": clips}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@web_app.post("/cut")
def cut_video(payload: dict):
    video_path = payload.get("video_path")
    video_title = payload.get("video_title", "Podcast")
    caption_style = payload.get("caption_style", "hormozi")
    clips = payload.get("clips", [])

    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video missing")

    results = []
    for i, clip in enumerate(clips):
        start = float(clip.get("timestamp_start", 0))
        end = float(clip.get("timestamp_end", 30))
        duration = max(end - start, 10.0)

        out_name = f"clip_{uuid.uuid4().hex[:6]}.mp4"
        out_path = os.path.join(OUTPUT_DIR, out_name)

        split_start = max(duration * 0.3, 4.0)
        split_end = min(split_start + 5.0, duration - 2.0)

        ass_path = None
        filter_complex = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[full];"
            f"[0:v]crop=iw*0.48:ih:0:0,scale=1080:960[spk1];"
            f"[0:v]crop=iw*0.48:ih:iw*0.52:0,scale=1080:960[spk2];"
            f"[spk1][spk2]vstack[split];"
            f"[full][split]overlay=0:0:enable='between(t,{split_start},{split_end})'[trans]"
        )

        if caption_style != "none":
            ass_path = os.path.join(OUTPUT_DIR, f"sub_{uuid.uuid4().hex[:6]}.ass")
            create_ass_file(ass_path, duration, caption_style)
            filter_complex += f";[trans]ass={ass_path}[outv]"
        else:
            filter_complex += f";[trans]null[outv]"

        audio_filter = "silenceremove=stop_periods=-1:stop_duration=0.5:stop_threshold=-35dB,atempo=1.03"

        cmd = [
            "ffmpeg", "-y", "-ss", str(start), "-i", video_path,
            "-t", str(duration),
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-af", audio_filter,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-c:a", "aac",
            out_path
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            hook_title, hashtags = generate_viral_metadata(video_title, i)
            results.append({
                "url": f"/outputs/{out_name}",
                "filename": out_name,
                "title": hook_title,
                "hashtags": hashtags,
                "error": False
            })
        except:
            results.append({"error": True})
        finally:
            if ass_path and os.path.exists(ass_path):
                os.remove(ass_path)

    return {"clips": results}

@app.function(image=image, memory=4096, timeout=600)
@modal.asgi_app()
def fastapi_app():
    return web_app
