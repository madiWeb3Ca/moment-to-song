#!/usr/bin/env python3
"""单帧检查：把指定时刻按**原尺寸**抽成 PNG，用来验收字幕、贴纸、黑帧。

用法:
  python3 snap.py 成片.mp4 --times 3 12 28 45 --outdir ./chk
  python3 snap.py 成片.mp4 --count 6 --outdir ./chk          # 均匀抽 6 帧
  python3 snap.py 成片.mp4 --times 30 --crop 0,470,1280,300 --outdir ./chk   # 只裁字幕带看 100%

输出:
  <outdir>/snap_00.png ...（原生分辨率，不缩放、不拼版）
  <outdir>/snap.json（每帧的平均亮度与"是否接近黑帧"判断）
为什么不用拼版验收: 拼版会缩到 420px 宽，半截字、描边断口、贴纸压字全都看不见。
"""
import argparse, json, os, subprocess, sys

def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--times", nargs="*", type=float, default=None, help="秒数列表")
    ap.add_argument("--count", type=int, default=None, help="不给 --times 时均匀抽几帧")
    ap.add_argument("--crop", default=None, help="x,y,w,h —— 只导出该区域（100% 看字幕）")
    ap.add_argument("--outdir", default="./chk")
    a = ap.parse_args()

    if not os.path.exists(a.video):
        sys.exit(f"找不到视频: {a.video}")
    os.makedirs(a.outdir, exist_ok=True)

    info = run(["ffprobe", "-v", "error", "-print_format", "json",
                "-show_format", "-show_streams", a.video])
    try:
        d = json.loads(info.stdout)
        dur = float(d["format"]["duration"])
    except Exception:
        sys.exit("读不出视频时长: " + info.stderr.strip()[:300])

    if a.times:
        ts = sorted(max(0.0, min(dur - 0.05, t)) for t in a.times)
    else:
        n = max(2, a.count or 6)
        ts = [round(dur * (i + 0.5) / n, 2) for i in range(n)]

    rows = []
    for i, t in enumerate(ts):
        out = os.path.join(a.outdir, f"snap_{i:02d}.png")
        cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", a.video,
               "-frames:v", "1", "-pix_fmt", "rgb24"]
        if a.crop:
            try:
                x, y, w, h = [int(v) for v in a.crop.split(",")]
            except ValueError:
                sys.exit("--crop 格式应为 x,y,w,h 四个整数")
            cmd += ["-vf", f"crop={w}:{h}:{x}:{y}"]
        cmd.append(out)
        r = run(cmd)
        if r.returncode != 0 or not os.path.exists(out):
            rows.append({"t": t, "file": None, "error": r.stderr.strip()[:200]})
            continue

        rows.append({"t": t, "file": out, "bytes": os.path.getsize(out)})

    # 用 ffmpeg 的 signalstats 判亮度（比逐像素读 raw 稳）
    for r in rows:
        if not r.get("file"):
            continue
        s = run(["ffmpeg", "-v", "error", "-i", r["file"],
                 "-vf", "signalstats,metadata=mode=print:file=-", "-f", "null", "-"]).stdout
        yavg = None
        for line in s.splitlines():
            if "YAVG=" in line:
                try:
                    yavg = float(line.split("YAVG=")[1].split()[0])
                except (IndexError, ValueError):
                    pass
        r["yavg"] = yavg
        r["near_black"] = (yavg is not None and yavg < 16)

    print(json.dumps({"video": a.video, "duration": round(dur, 3),
                      "frames": rows, "crop": a.crop}, ensure_ascii=False, indent=2))
    with open(os.path.join(a.outdir, "snap.json"), "w", encoding="utf-8") as f:
        json.dump({"video": a.video, "duration": round(dur, 3),
                   "frames": rows, "crop": a.crop}, f, ensure_ascii=False, indent=2)

    bad = [r for r in rows if r.get("file") is None]
    if bad:
        print("有帧没导出成功：", json.dumps(bad, ensure_ascii=False), file=sys.stderr)
        return 1
    nb = [r["t"] for r in rows if r.get("near_black")]
    if nb:
        print(f"提示: {len(nb)} 帧接近黑场（{nb}），检查是不是压暗转场或没拍到内容。", file=sys.stderr)
    print(f"\n导出了 {len(rows)} 张原尺寸帧到 {a.outdir}/ —— 逐张 100% 看，不要看拼版。")
    return 0

if __name__ == "__main__":
    sys.exit(main())
