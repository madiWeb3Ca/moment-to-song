#!/usr/bin/env python3
"""素材勘验：读规格 + 拼版，一次看清要配乐的画面。

支持两种素材：
  python3 probe_frames.py VIDEO --outdir ./work --frames 9        # 视频：均匀抽 9 帧
  python3 probe_frames.py PHOTO_DIR --outdir ./work                # 照片：整组拼版 + 每张规格
  python3 probe_frames.py one.jpg --outdir ./work                  # 单张照片
输出:
  <outdir>/sheet.jpg（拼版，必须真看一眼）
  <outdir>/probe.json（规格，喂给后续步骤；now_playing.json 里照片模式带 photos 列表）
"""
import argparse, json, os, subprocess, sys

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".heif", ".tif", ".tiff"}

def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def probe_video(path):
    r = run(["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", path])
    if r.returncode != 0 or not r.stdout.strip():
        sys.exit("ffprobe 读不出这个文件，可能损坏或不是视频: " + r.stderr.strip()[:300])
    d = json.loads(r.stdout)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        sys.exit("这个文件里没有视频流（如果是照片，请直接用照片路径，不要当视频传）")
    num, den = (v.get("r_frame_rate") or "0/1").split("/")
    fps = round(float(num) / float(den), 3) if float(den) else 0
    dur = float(d["format"].get("duration") or 0)
    return {
        "mode": "video",
        "duration": round(dur, 3), "size": int(d["format"].get("size") or 0),
        "width": v["width"], "height": v["height"], "fps": fps,
        "nb_frames": int(v.get("nb_frames") or round(fps * dur)),
        "vcodec": v["codec_name"],
        "has_audio": a is not None,
        "acodec": a["codec_name"] if a else None,
        "sample_rate": a["sample_rate"] if a else None,
        "channels": a["channels"] if a else None,
    }

def collect_photos(path):
    if os.path.isdir(path):
        files = sorted(
            os.path.join(path, f) for f in os.listdir(path)
            if os.path.splitext(f)[1].lower() in IMG_EXT
        )
    else:
        files = [path]
    if not files:
        sys.exit(f"这个目录里没有可用图片（支持 {', '.join(sorted(IMG_EXT))}）")
    return files

def probe_photos(files, outdir, cols=3, cell_w=420):
    try:
        from PIL import Image
    except ImportError:
        sys.exit("缺少 Pillow，无法读照片与拼版：pip install pillow")
    items, ims, bad = [], [], []
    for f in files:
        try:
            w, h = Image.open(f).size
            items.append({"file": f, "width": w, "height": h,
                          "aspect": round(w / h, 3)})
            ims.append(f)
        except Exception as e:
            bad.append({"file": f, "error": type(e).__name__})   # 坏图单独列出，不拖垮整批
    if not items:
        sys.exit("所有照片都读不了：" + json.dumps(bad, ensure_ascii=False))
    rows = (len(items) + cols - 1) // cols
    first = Image.open(ims[0]).convert("RGB")
    ch = int(cell_w * first.height / first.width)
    sheet = Image.new("RGB", (cell_w * cols, ch * rows), "white")
    for i, p in enumerate(ims[:cols * rows]):
        im = Image.open(p).convert("RGB").resize((cell_w, ch), Image.LANCZOS)
        sheet.paste(im, ((i % cols) * cell_w, (i // cols) * ch))
    out = os.path.join(outdir, "sheet.jpg")
    sheet.save(out, quality=90)
    common = max(set((x["width"], x["height"]) for x in items),
                 key=lambda s: sum(1 for x in items if (x["width"], x["height"]) == s))
    return {"mode": "photos", "count": len(items),
            "photos": items, "unreadable": bad,
            "width": common[0], "height": common[1],
            "sheet": out, "mixed_sizes": any((x["width"], x["height"]) != common for x in items)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="视频文件，或照片文件/照片目录")
    ap.add_argument("--outdir", default="./work")
    ap.add_argument("--frames", type=int, default=9, help="视频模式抽几帧")
    a = ap.parse_args()
    if not os.path.exists(a.source):
        sys.exit(f"路径不存在: {a.source}")
    os.makedirs(a.outdir, exist_ok=True)

    is_photo = os.path.isdir(a.source) or os.path.splitext(a.source)[1].lower() in IMG_EXT
    if is_photo:
        info = probe_photos(collect_photos(a.source), a.outdir)
        if info["mixed_sizes"]:
            print("提示: 这组照片尺寸不一致，渲染会按统一画幅居中裁切；竖横混用建议先统一。",
                  file=sys.stderr)
        if info["unreadable"]:
            print("提示: 有照片读不了（可能是 HEIC 或缺插件），已跳过：",
                  file=sys.stderr); print(json.dumps(info["unreadable"], ensure_ascii=False), file=sys.stderr)
        print(json.dumps({k: v for k, v in info.items() if k != "photos"},
                         ensure_ascii=False, indent=2))
        print(f"\n拼版: {info['sheet']}（{info['count']} 张，必须真看一眼）")
    else:
        info = probe_video(a.source)
        if info["duration"] <= 0:
            sys.exit("素材时长读到 0，可能文件损坏或不是视频")
        print(json.dumps(info, ensure_ascii=False, indent=2))
        dur, n = info["duration"], max(3, a.frames)
        ts = [round(dur * (i + 0.5) / n, 2) for i in range(n)]
        paths = []
        for i, t in enumerate(ts):
            p = os.path.join(a.outdir, f"f{i:02d}.jpg")
            run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", a.source, "-frames:v", "1", p])
            paths.append(p)
        try:
            from PIL import Image
        except ImportError:
            sys.exit("缺少 Pillow，无法拼版：pip install pillow（只影响看片，规格已打印在上面）")
        cols = 3; rows = (n + cols - 1) // cols; cell_w = 420
        ims = [Image.open(p) for p in paths if os.path.exists(p)]
        if not ims:
            sys.exit("抽帧失败，一帧都没出来")
        ch = int(cell_w * ims[0].height / ims[0].width)
        sheet = Image.new("RGB", (cell_w * cols, ch * rows), "white")
        for i, im in enumerate(ims):
            sheet.paste(im.convert("RGB").resize((cell_w, ch), Image.LANCZOS),
                        ((i % cols) * cell_w, (i // cols) * ch))
        out = os.path.join(a.outdir, "sheet.jpg")
        sheet.save(out, quality=90)
        info["frames"], info["sheet"] = ts, out
        print("\n拼版:", out)

    with open(os.path.join(a.outdir, "probe.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
