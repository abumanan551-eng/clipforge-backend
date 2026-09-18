import os
import subprocess
import uuid
import re
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="ClipForge Backend")

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

def parse_time(time_str: str) -> float:
    parts = list(map(int, re.split(r'[:.]', time_str.strip())))
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0.0

class ClipMeta(BaseModel):
    rank: Optional[int] = 1
    viral_score: Optional[float] = 8.5
    timestamp_start: str
    timestamp_end: str
    duration_seconds: Optional[float] = 30
    title: Optional[str] = "Clip"
    speaker: Optional[str] = ""
    reason: Optional[str] = ""
    hook_line: Optional[str] = ""

class CutRequest(BaseModel):
    video_path: str
    clips: List[ClipMeta]
    aspect_ratio: str = "9:16"
    add_captions: bool = False

@app.get("/")
def health_check():
    return {"status": "ok", "message": "Backend is running"}

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    ext = file.filename.split(".")[-1]
    unique_name = f"{uuid.uuid4()}.{ext}"
    dest_path = os.path.join(UPLOAD_DIR, unique_name)
    
    with open(dest_path, "wb") as buffer:
        while chunk := await file.read(1024 * 1024 * 10):
            buffer.write(chunk)
            
    return {"status": "success", "path": dest_path}

@app.post("/cut")
def cut_video_clips(payload: CutRequest):
    if not os.path.exists(payload.video_path):
        raise HTTPException(status_code=404, detail="File not found")

    results = []
    ratio_filters = {
        "9:16": "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "1:1": "scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080",
        "16:9": "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080",
        "4:5": "scale=1080:1350:force_original_aspect_ratio=increase,crop=1080:1350"
    }
    vf_filter = ratio_filters.get(payload.aspect_ratio, ratio_filters["9:16"])

    for i, clip in enumerate(payload.clips):
        start_sec = parse_time(clip.timestamp_start)
        end_sec = parse_time(clip.timestamp_end)
        duration = end_sec - start_sec
        if duration <= 0:
            duration = clip.duration_seconds or 30

        output_filename = f"clip_{uuid.uuid4().hex[:8]}_{i+1}.mp4"
        output_filepath = os.path.join(OUTPUT_DIR, output_filename)

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-i", payload.video_path,
            "-t", str(duration),
            "-vf", vf_filter,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "128k",
            output_filepath
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            file_size = round(os.path.getsize(output_filepath) / (1024 * 1024), 2)
            results.append({
                "url": f"/outputs/{output_filename}",
                "filename": output_filename,
                "title": clip.title,
                "viral_score": clip.viral_score,
                "timestamp_start": clip.timestamp_start,
                "timestamp_end": clip.timestamp_end,
                "size_mb": file_size,
                "error": False
            })
        except subprocess.CalledProcessError as e:
            results.append({
                "title": clip.title,
                "error": True,
                "msg": str(e.stderr.decode() if e.stderr else e)
            })

    return {"clips": results}
