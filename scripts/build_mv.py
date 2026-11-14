#!/usr/bin/env python3
"""一键渲染专属 MV：原声整轨静音换新曲 + 烧字幕 + 暖调 + 可选品牌尾片。

视频素材:
  python3 build_mv.py --video 素材.mp4 --song 试听.mp3 --ass subs.ass \
      --endcard endcard.png --card-dur 4 --duration 48 --out 成片.mp4

照片素材（一张或一组照片也能做）:
  python3 build_mv.py --photos ./photos --song 试听.mp3 --duration 48 --out 成片.mp4
  --per-photo 每张停留几秒（默认 = 时长 / 张数）；--pan 平移幅度（默认 1.12 倍画幅）

约定:
  --duration  正片取多长；音乐比片子短也会补静音，不会提前断
  --card-dur  尾片停几秒（0 = 不加尾片）
  渲染完打印自检；帧数、时长、分辨率、响度、削波任一项不达标以非 0 退出。

兼容性（最常让流程中断的几种情况都已处理）:
  可变帧率素材 → 先 fps 归一化再裁；音乐短于片子 → apad 再 atrim；
  路径含空格/引号 → list 传参 + 字幕走临时安全路径；全静音 → 只报 FAIL 不崩；
  奇宽高 → 取偶；照片尺寸不一 → 统一画幅居中裁切。
"""
import argparse, json, os, re, subprocess, sys

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

def sh(cmd):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return r.stdout

def _db(text, key):
    """解析 volumedetect 的 dB 值；全静音输出 -inf，返回 None 而不是崩。"""
    m = re.search(key + r":\s*(-?[\d.]+|-inf|nan)", text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None

def q(path):
    out = sh(["ffprobe", "-v", "error", "-print_format", "json",
              "-show_format", "-show_streams", path])
    try:
        d = json.loads(out)
        v = next(s for s in d["streams"] if s["codec_type"] == "video")
    except Exception:
        sys.exit("读不出视频规格，文件可能损坏或不是视频: " + out[-400:])
    num, den = (v.get("r_frame_rate") or "0/1").split("/")
    fps = round(float(num) / float(den), 3) if float(den) else 0
    dur = float(d["format"].get("duration") or 0)
    return {"dur": dur,
            "frames": int(v.get("nb_frames") or round(fps * dur)),
            "w": v["width"], "h": v["height"], "fps": fps,
            "size": int(d["format"].get("size") or 0)}

def collect_photos(path):
    if os.path.isdir(path):
        files = sorted(os.path.join(path, f) for f in os.listdir(path)
                       if os.path.splitext(f)[1].lower() in IMG_EXT)
    else:
        files = [path]
    if not files:
        sys.exit(f"没找到可用照片: {path}")
    return files

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=None, help="视频素材")
    ap.add_argument("--photos", default=None, help="照片文件或照片目录（与 --video 二选一）")
    ap.add_argument("--song", required=True)
    ap.add_argument("--ass", default=None)
    ap.add_argument("--endcard", default=None)
    ap.add_argument("--card-dur", type=float, default=0)
    ap.add_argument("--duration", type=float, default=None)
    ap.add_argument("--per-photo", type=float, default=None)
    ap.add_argument("--pan", type=float, default=1.12, help="照片平移幅度倍数（1.0 = 不动）")
    ap.add_argument("--fps", type=float, default=24, help="照片模式的输出帧率")
    ap.add_argument("--max-edge", type=int, default=1080,
                    help="照片模式最长边上限（默认 1080，原图 3K/4K 会按比例缩）")
    ap.add_argument("--no-grade", action="store_true")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--fade-out", type=float, default=2.5)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    if not a.video and not a.photos:
        sys.exit("必须给 --video 或 --photos 之一")
    if a.video and a.photos:
        sys.exit("--video 与 --photos 只能二选一（混着用请先剪成一条视频）")
    for p, label in ((a.song, "音乐"), (a.video, "视频"), (a.photos, "照片")):
        if p and not os.path.exists(p):
            sys.exit(f"找不到{label}: {p}")
    if a.ass and not os.path.exists(a.ass):
        sys.exit(f"找不到字幕文件: {a.ass}")

    inputs, fc = [], []

    if a.photos:
        photos = collect_photos(a.photos)
        try:
            from PIL import Image
            w, h = Image.open(photos[0]).size
        except ImportError:
            sys.exit("照片模式需要 Pillow：pip install pillow")
        except Exception as e:
            sys.exit(f"第一张照片读不了（{type(e).__name__}）：{photos[0]}")
        fps = a.fps
        dur = a.duration or round(len(photos) * 3.0, 2)
        per = a.per_photo or round(dur / len(photos), 3)
        long_edge = max(w, h)
        ratio = min(1.0, a.max_edge / long_edge) if a.max_edge else 1.0
        W, H = (int(w * ratio) // 2 * 2, int(h * ratio) // 2 * 2)
        segF = max(1, round(per * fps))
        pan = max(1.0, a.pan)
        CW, CH = int(W * pan) // 2 * 2, int(H * pan) // 2 * 2
        for i, ph in enumerate(photos):
            inputs += ["-loop", "1", "-t", f"{per + 0.15:.3f}", "-i", ph]
            dx = CW - W
            xexpr = (f"{dx}*n/{max(1, segF - 1)}" if i % 2 == 0
                     else f"{dx}*(1-n/{max(1, segF - 1)})")
            fc.append(
                f"[{i}:v]scale={CW}:{CH}:force_original_aspect_ratio=increase,"
                f"crop={CW}:{CH},"
                f"crop={W}:{H}:x='{xexpr}':y='{(CH - H) // 2}',setsar=1,"
                f"fps={fps},trim=duration={per},setpts=PTS-STARTPTS,format=yuv420p[p{i}]")
        fc.append("".join([f"[p{i}]" for i in range(len(photos))]) +
                  f"concat=n={len(photos)}:v=1:a=0[src]")
        src_dur = per * len(photos)
        song_idx = len(photos)
    else:
        src = q(a.video)
        if src["dur"] <= 0:
            sys.exit("素材时长读到 0，无法渲染")
        dur = a.duration or src["dur"]
        W, H = (src["w"] // 2 * 2, src["h"] // 2 * 2)
        fps = src["fps"] or 24
        inputs += ["-i", a.video]
        fc.append(f"[0:v]fps={fps},trim=0:{min(dur, src['dur'])},setpts=PTS-STARTPTS[src]")
        src_dur = src["dur"]
        song_idx = 1

    if dur <= 0:
        sys.exit("duration 必须大于 0")
    if dur > src_dur + 0.02:
        print(f"警告: 片子要 {dur}s，素材只有 {src_dur:.2f}s，按素材长度渲染", file=sys.stderr)
        dur = src_dur

    card = a.card_dur if (a.endcard and a.card_dur > 0) else 0
    if a.endcard and a.card_dur <= 0:
        print("提示: 传了 --endcard 但 --card-dur 为 0，本次不加尾片", file=sys.stderr)
    if card > 0 and not os.path.exists(a.endcard):
        sys.exit(f"找不到尾片文件: {a.endcard}")
    if a.card_dur > 0 and not a.endcard:
        print("提示: --card-dur 大于 0 但没给 --endcard，按不加尾片处理", file=sys.stderr)
        card = 0

    total = dur + card
    vf = f"trim=0:{dur},setpts=PTS-STARTPTS"
    if not a.no_grade:
        vf += (",eq=brightness=0.02:saturation=1.06:contrast=1.03"
               ",colorbalance=rm=0.05:gm=0.015:bm=-0.03")
    vf += ",fade=in:st=0:d=0.6"
    if a.ass:
        vf += ",ass=" + _escape(_filter_path(a.ass))
    fc.append(f"[src]{vf}[v0]")

    inputs += ["-i", a.song]
    maps = ["[v0]", "[a]"]
    if card > 0:
        card_idx = song_idx + 1
        inputs += ["-loop", "1", "-t", str(card), "-i", a.endcard]
        fc.append(f"[{card_idx}:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
                  f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fade=in:st=0:d=0.3,"
                  f"format=yuv420p[v1]")
        fc.append("[v0][v1]concat=n=2:v=1:a=0[v]")
        maps[0] = "[v]"

    # 音轨：先补静音再裁到总时长——音乐比片子短也不会提前断
    fc.append(f"[{song_idx}:a]asetpts=PTS-STARTPTS,apad,atrim=0:{total},asetpts=PTS-STARTPTS,"
              f"afade=in:st=0:d=0.5,"
              f"afade=out:st={max(0, dur - a.fade_out)}:d={a.fade_out}[a]")

    cmd = (["ffmpeg", "-v", "error", "-y"] + inputs +
           ["-filter_complex", ";".join(fc)] +
           ["-map", maps[0], "-map", maps[1]] +
           ["-r", str(fps), "-c:v", "libx264", "-crf", str(a.crf),
            "-preset", "medium", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", a.out])
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        sys.exit("渲染失败:\n" + (r.stderr or "")[-2000:])

    o = q(a.out)
    loud = sh(["ffmpeg", "-i", a.out, "-af", "volumedetect", "-f", "null", "-"])
    mean, mx = _db(loud, "mean_volume"), _db(loud, "max_volume")
    exp_frames = round(total * fps)

    ok = True
    def chk(name, cond, detail):
        nonlocal ok
        print(f"{'PASS' if cond else 'FAIL':5} {name:12} {detail}")
        ok = ok and cond

    print("\n自检 -", a.out)
    chk("时长", abs(o["dur"] - total) <= 0.15, f"{o['dur']:.3f}s / 期望 {total:.3f}s")
    chk("帧数", abs(o["frames"] - exp_frames) <= 4, f"{o['frames']} / 期望 {exp_frames}")
    chk("分辨率", (o["w"], o["h"]) == (W, H), f"{o['w']}x{o['h']} @ {o['fps']}fps")
    chk("响度", mean is not None and -19 <= mean <= -14.5,
        "解析不到（可能全静音）" if mean is None else f"mean {mean} dB")
    chk("削波", mx is not None and mx <= -0.3,
        "解析不到峰值" if mx is None else f"max {mx} dB")
    print("结论:", "可交付" if ok else "需返工")
    return 0 if ok else 1

def _filter_path(p):
    """滤镜串里不能有空格/引号/逗号——这类路径先拷成临时安全路径再用。"""
    if any(ch in p for ch in " \t'\"$,:;()[]\\"):
        import shutil, tempfile
        tmp = os.path.join(tempfile.gettempdir(), "_mv_filter_safe" + os.path.splitext(p)[1])
        shutil.copy(p, tmp)
        print(f"提示: 字幕路径含特殊字符，已临时拷到 {tmp} 供滤镜使用", file=sys.stderr)
        return tmp
    return p

def _escape(p):
    return p.replace("\\", "\\\\").replace(":", "\\:").replace(",", "\\,")

if __name__ == "__main__":
    sys.exit(main())
