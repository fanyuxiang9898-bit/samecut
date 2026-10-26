"""A transparent FFmpeg/Pillow pipeline. No cloud model or hidden API calls."""
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
POSITIONS = ["bottom-left", "top-right", "vertical-left", "bottom-right", "top-left", "center"]


class SamecutError(ValueError):
    """Actionable input or execution error."""


def command(args, timeout=300):
    try:
        result = subprocess.run([str(x) for x in args], capture_output=True,
                                encoding="utf-8", errors="replace", timeout=timeout)
    except FileNotFoundError as exc:
        raise SamecutError(f"Missing executable: {args[0]}. Install FFmpeg/ffprobe first.") from exc
    except subprocess.TimeoutExpired as exc:
        raise SamecutError(f"Operation timed out: {args[0]}") from exc
    if result.returncode:
        raise SamecutError(result.stderr[-2200:] or result.stdout[-2200:] or "Command failed")
    return result


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def probe(path):
    info = json.loads(command(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                               "-of", "json", path]).stdout)
    videos = [s for s in info["streams"] if s["codec_type"] == "video"]
    if not videos:
        raise SamecutError("Reference has no video stream.")
    video = videos[0]
    duration = float(video.get("duration") or info["format"]["duration"])
    if not math.isfinite(duration) or not .2 <= duration <= 180:
        raise SamecutError("Reference must be between 0.2 and 180 seconds.")
    return {"duration": duration, "width": video["width"], "height": video["height"],
            "has_audio": any(s["codec_type"] == "audio" for s in info["streams"])}


def share_url(text):
    match = re.search(r"https://[^\s<>\"，。]+", text)
    if not match:
        raise SamecutError("Paste a Douyin share URL, or provide a local reference file.")
    url = match.group().rstrip("/)!！）;；") + ("/" if match.group().endswith("/") else "")
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if (parts.username or parts.password or parts.port not in (None, 443)
            or not any(host == d or host.endswith("." + d) for d in ("douyin.com", "iesdouyin.com"))):
        raise SamecutError("Only HTTPS Douyin share links are accepted. Other sources: use a local file.")
    return url


def resolve_reference(value, work):
    if "https://" not in value:
        p = Path(value).expanduser().resolve()
        if not p.is_file():
            raise SamecutError("Reference file not found.")
        return p
    url = share_url(value)
    target = Path(work) / "download"
    target.mkdir(parents=True, exist_ok=True)
    try:
        command([sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist",
                 "--no-progress", "--socket-timeout", "15", "--retries", "1",
                 "--max-filesize", "500M", "--merge-output-format", "mp4",
                 "-o", str(target / "reference.%(ext)s"), "--", url], timeout=180)
    except SamecutError as exc:
        # Never request cookies, bypass a challenge, or claim failed retrieval succeeded.
        raise SamecutError("Douyin download failed or requires platform verification. "
                           "Upload the reference MP4 instead. No browser credentials are read.") from exc
    files = [p for p in target.glob("reference.*") if p.suffix in {".mp4", ".webm", ".mkv"}]
    if len(files) != 1:
        raise SamecutError("No complete reference video downloaded; upload a local MP4.")
    return files[0].resolve()


def frame(path, at, output, width=480):
    command(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.5f}", "-i", path,
             "-frames:v", "1", "-vf", f"scale={width}:-1", output])


def normalize_cuts(times, total, fps, min_frames=6):
    cuts = [0]
    for t in sorted(times):
        n = round(float(t) * fps)
        if n - cuts[-1] >= min_frames and total - n >= min_frames:
            cuts.append(n)
    return cuts + [total]


def analyze(reference, work, fps=30, threshold=.23):
    info = probe(reference)
    if not .01 <= threshold <= .9:
        raise SamecutError("Scene threshold must be 0.01–0.9.")
    result = command(["ffmpeg", "-hide_banner", "-i", reference, "-an", "-vf",
                      f"scale=320:-1,select='gt(scene,{threshold})',showinfo",
                      "-fps_mode", "vfr", "-f", "null", "-"], timeout=240)
    times = [float(x) for x in re.findall(r"pts_time:([0-9.]+)", result.stderr)]
    total = round(info["duration"] * fps)
    cuts = normalize_cuts(times, total, fps)
    warnings = []
    if len(cuts) == 2 and total > fps * 2:
        cuts = list(range(0, total, fps)) + [total]
        if cuts[-1] - cuts[-2] < 6:
            cuts.pop(-2)
        warnings.append("No hard cuts detected; using 1-second fallback rhythm.")
    result = {**info, "fps": fps, "total_frames": total, "cuts": cuts,
              "method": "FFmpeg scene score + deterministic editorial typography (no OCR)",
              "warnings": warnings}
    write_json(Path(work) / "analysis.json", result)
    return result


def fingerprint(image):
    small = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    px = list(small.get_flattened_data() if hasattr(small,"get_flattened_data") else small.getdata())
    value = sum((px[y * 9 + x] > px[y * 9 + x + 1]) << (y * 8 + x)
                for y in range(8) for x in range(8))
    color = ImageStat.Stat(image.resize((16, 16)).convert("RGB")).mean
    return value, color


def inventory(folder, manifest=None, reviewed_clean=False, as_of=None, recent_days=None):
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise SamecutError("Assets folder not found.")
    metadata = {}
    if manifest:
        metadata = json.loads(Path(manifest).read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise SamecutError("Manifest must be an object keyed by filename.")
    if any(not isinstance(v,dict) for v in metadata.values()):
        raise SamecutError("Each manifest entry must be an object.")
    today = date.fromisoformat(as_of) if as_of else date.today()
    if recent_days is not None and not 1 <= recent_days <= 365:
        raise SamecutError("Recent days must be 1–365.")
    accepted, rejected, hashes = [], [], []
    for p in sorted(folder.iterdir()):
        if not p.is_file() or p.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        meta = metadata.get(p.name, {})
        if meta.get("watermark") != "clean" and not (reviewed_clean and not meta.get("watermark")):
            rejected.append({"file": p.name, "reason": "watermarked or unreviewed"})
            continue
        try:
            with Image.open(p) as opened:
                im = ImageOps.exif_transpose(opened).convert("RGB")
                sha = hashlib.sha256(im.tobytes() + str(im.size).encode()).hexdigest()
                dh, col = fingerprint(im)
                dimensions = list(im.size)
            duplicate = next((name for h, d, c, name in hashes
                              if sha == h or ((dh ^ d).bit_count() <= 4
                                              and sum(abs(a-b) for a,b in zip(col,c)) < 50)), None)
            if duplicate:
                rejected.append({"file": p.name, "reason": "duplicate", "duplicate_of": duplicate})
                continue
            published = meta.get("published_at")
            if published is not None and not isinstance(published,str):
                raise ValueError("published_at must be a date string")
            day = date.fromisoformat(published[:10]) if published else None
            recent = bool(day and today - timedelta(days=(recent_days or 2)-1) <= day <= today)
            accepted.append({"file": str(p), "name": p.name, "sha256": sha,
                             "dimensions": dimensions, "published_at": published,
                             "source_url": meta.get("source_url"), "recent": recent,
                             "watermark": "user-confirmed-clean"})
            hashes.append((sha, dh, col, p.name))
        except (OSError, ValueError) as exc:
            rejected.append({"file": p.name, "reason": f"invalid image/metadata: {type(exc).__name__}"})
    if not accepted:
        raise SamecutError("No eligible photos. Review watermarks and supply manifest or --reviewed-clean.")
    if recent_days and not any(a["recent"] for a in accepted):
        raise SamecutError("No eligible recent photo. Supply published_at in assets.json; file mtime is not evidence.")
    # Required fresh photos always enter the rendered subset, never only the inventory.
    accepted.sort(key=lambda a: not a["recent"] if recent_days else False)
    return accepted, rejected


def plan(analysis, assets, aliases, width=1280):
    if not aliases or any(not x.strip() or len(x) > 60 for x in aliases):
        raise SamecutError("Use 1–60 character nonempty aliases.")
    cuts = analysis["cuts"][:]
    warnings = analysis["warnings"][:]
    # Merge shortest neighboring intervals when photos are scarce. Never loop an asset.
    while len(cuts)-1 > len(assets):
        boundary = min(range(1, len(cuts)-1), key=lambda i: cuts[i+1]-cuts[i-1])
        cuts.pop(boundary)
    if cuts != analysis["cuts"]:
        warnings.append("Not enough unique photos: merged cuts instead of repeating photos.")
    width = int(width)
    if width < 320 or width > 1920 or width % 2:
        raise SamecutError("Width must be an even number between 320 and 1920.")
    height = round(width * analysis["height"] / analysis["width"] / 2) * 2
    if not 180 <= height <= 3840:
        raise SamecutError("Unsupported reference aspect ratio.")
    scenes = []
    for i, (start, end) in enumerate(zip(cuts, cuts[1:])):
        scenes.append({"start_frame": start, "end_frame": end, "asset": assets[i],
                       "text": aliases[i % len(aliases)], "position": POSITIONS[i % len(POSITIONS)],
                       "font_style": ["serif", "italic", "sans", "bold"][i % 4],
                       "motion": "push-in" if i % 2 == 0 else "pull-out"})
    return {"version": 1, "width": width, "height": height, "fps": analysis["fps"],
            "total_frames": analysis["total_frames"], "scenes": scenes, "warnings": warnings,
            "typography": "varied heuristic layouts, not extracted reference fonts"}


def validate_plan(recipe):
    cursor, seen = 0, set()
    for s in recipe["scenes"]:
        if s["start_frame"] != cursor or s["end_frame"] <= cursor:
            raise SamecutError("Timeline has a gap, overlap, or empty scene.")
        if s["asset"]["sha256"] in seen:
            raise SamecutError("Timeline repeats a photo.")
        seen.add(s["asset"]["sha256"])
        cursor = s["end_frame"]
    if cursor != recipe["total_frames"]:
        raise SamecutError("Timeline does not cover the complete reference.")


def find_font(style, custom=None):
    if custom:
        p = Path(custom)
        if not p.is_file():
            raise SamecutError("Font file not found.")
        return str(p)
    win = {"serif": "times.ttf", "italic": "timesi.ttf", "sans": "arial.ttf", "bold": "arialbd.ttf"}
    linux = {"serif": "DejaVuSerif.ttf", "italic": "DejaVuSerif-Italic.ttf",
             "sans": "DejaVuSans.ttf", "bold": "DejaVuSans-Bold.ttf"}
    candidates = [Path("C:/Windows/Fonts")/win[style],
                  Path("/usr/share/fonts/truetype/dejavu")/linux[style],
                  Path("/System/Library/Fonts/Supplemental") / ("Times New Roman.ttf" if style == "serif" else "Arial.ttf")]
    return next((str(p) for p in candidates if p.is_file()), None)


def compose(image_path, scene, size, background, font_path=None):
    w, h = size
    canvas = Image.new("RGB", size, tuple(background))
    with Image.open(image_path) as opened:
        photo = ImageOps.exif_transpose(opened).convert("RGB")
    # Contain rather than crop: preserve faces and keep only one occurrence of the photo.
    photo = ImageOps.contain(photo, (w, h), Image.Resampling.LANCZOS)
    canvas.paste(photo, ((w-photo.width)//2, (h-photo.height)//2))
    layer = Image.new("RGBA", size)
    draw = ImageDraw.Draw(layer)
    fpath = find_font(scene["font_style"], font_path)
    fontsize = max(18, round(min(w,h)*.105))
    def getfont(n):
        return ImageFont.truetype(fpath,n) if fpath else ImageFont.load_default(size=n)
    font = getfont(fontsize)
    text = scene["text"]
    maxwidth = (h*.78 if scene["position"] == "vertical-left" else w*.86)
    while draw.textbbox((0,0),text,font=font)[2] > maxwidth and fontsize > 10:
        fontsize -= 1
        font = getfont(fontsize)
    box = draw.textbbox((0,0),text,font=font)
    tw,th = box[2]-box[0],box[3]-box[1]
    pad = max(15,round(min(w,h)*.05))
    pos = scene["position"]
    x = w-tw-pad if "right" in pos else pad
    y = pad if "top" in pos else h-th-pad
    if pos == "center":
        x,y = (w-tw)//2, h*.78
    if pos == "vertical-left":
        word = Image.new("RGBA", (tw+12,th+12))
        ImageDraw.Draw(word).text((6-box[0],6-box[1]),text,font=font,fill="white",
                                  stroke_width=1,stroke_fill=(0,0,0,160))
        word = word.rotate(90,expand=True)
        layer.paste(word,(pad,(h-word.height)//2))
    else:
        draw.text((x-box[0],y-box[1]),text,font=font,fill="white",stroke_width=1,
                  stroke_fill=(0,0,0,160))
    return canvas, layer


def render(reference, recipe, work, font=None, progress=print):
    validate_plan(recipe)
    work = Path(work)
    clips = work / "clips"
    clips.mkdir(exist_ok=True)
    w,h,fps = recipe["width"],recipe["height"],recipe["fps"]
    for i,s in enumerate(recipe["scenes"]):
        progress(f"Rendering {i+1}/{len(recipe['scenes'])}")
        sample = work / "sample.jpg"
        frame(reference,(s["start_frame"]+s["end_frame"])/2/fps,sample)
        with Image.open(sample) as im:
            bg = tuple(round(x) for x in ImageStat.Stat(im.convert("RGB")).median)
        s["reference_background"] = list(bg)
        canvas, overlay = compose(s["asset"]["file"],s,(w,h),bg,font)
        canvas.save(clips / f"{i:03d}.jpg",quality=95)
        overlay.save(clips / f"{i:03d}-type.png")
        count = s["end_frame"]-s["start_frame"]
        zoom = f"1+0.025*on/{max(count-1,1)}" if s["motion"] == "push-in" else f"1.025-0.025*on/{max(count-1,1)}"
        vf = (f"[0:v]zoompan=z='{zoom}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2'"
              f":d={count}:s={w}x{h}:fps={fps}[photo];[photo][1:v]overlay=0:0,format=yuv420p[v]")
        command(["ffmpeg","-v","error","-y","-i",clips/f"{i:03d}.jpg","-i",clips/f"{i:03d}-type.png",
                 "-filter_complex",vf,"-map","[v]","-frames:v",count,"-an","-c:v","libx264",
                 "-preset","fast","-crf","20","-threads","2",clips/f"{i:03d}.mp4"],timeout=240)
    # Names are generated, not user-controlled concat syntax.
    (clips/"list.txt").write_text("\n".join(f"file '{i:03d}.mp4'" for i in range(len(recipe["scenes"]))),encoding="utf-8")
    output = work / "video.mp4"
    command(["ffmpeg","-v","error","-y","-f","concat","-safe","1","-i",clips/"list.txt",
             "-i",reference,"-map","0:v:0","-map","1:a:0?","-c:v","copy","-c:a","aac","-b:a","192k",
             "-af","apad","-t",f"{recipe['total_frames']/fps:.8f}","-movflags","+faststart",output])
    actual = probe(output)
    if abs(actual["duration"]-recipe["total_frames"]/fps) > 1/fps + .01:
        raise SamecutError("Rendered duration mismatch.")
    if probe(reference)["has_audio"] != actual["has_audio"]:
        raise SamecutError("Audio stream missing from export.")
    frame(output,max(0,actual["duration"]-2/fps),work/"last-frame.jpg",width=min(w,960))
    write_json(work/"recipe.json",recipe)
    return output


def run(reference, assets, output, aliases=None, manifest=None, reviewed_clean=False,
        recent_days=None, as_of=None, width=1280, threshold=.23, font=None, progress=print):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise SamecutError("Output directory must be new or empty; existing work is never overwritten.")
    output.mkdir(parents=True,exist_ok=True)
    progress("Checking photos")
    photos,rejected = inventory(assets,manifest,reviewed_clean,as_of,recent_days)
    write_json(output/"assets-report.json",{"accepted":photos,"rejected":rejected})
    progress("Reading reference")
    reference = resolve_reference(reference,output)
    progress("Detecting cuts and reading audio")
    analysis = analyze(reference,output,threshold=threshold)
    recipe = plan(analysis,photos,aliases or ["chance","QIANCHENG"],width)
    validate_plan(recipe)
    write_json(output/"recipe.json",recipe)
    video = render(reference,recipe,output,font,progress)
    report = {"video":"video.mp4","scenes":len(recipe["scenes"]),"no_repeated_photos":True,
              "recent_photos_used":sum(s["asset"]["recent"] for s in recipe["scenes"]),
              "watermark_check":"user declarations, not automatic watermark detection",
              "date_check":"manifest publication dates, not independent online verification",
              "duration":analysis["total_frames"]/analysis["fps"],"warnings":recipe["warnings"]}
    write_json(output/"report.json",report)
    progress("Complete")
    return video
