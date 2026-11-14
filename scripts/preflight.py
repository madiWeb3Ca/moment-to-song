#!/usr/bin/env python3
"""开跑前先探一遍环境：缺什么当场说清，不要等渲染到一半才崩。

用法:
  python3 preflight.py
退出码: 0 = 必需项齐（可开跑）；1 = 缺必需项（照提示装/换机器）
"""
import os, shutil, subprocess, sys

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc",
]

def has_bin(name):
    return shutil.which(name)

def ffmpeg_filters():
    """确认 ass / colorbalance / concat 这几个滤镜真的编进去了。"""
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout
        return {f: (f in out) for f in ("ass", "subtitles", "colorbalance", "concat", "zoompan")}
    except Exception:
        return {}

def main():
    rows, ok = [], True
    def add(name, state, detail, required=True):
        nonlocal ok
        rows.append((state, name, detail))
        if required and state == "缺":
            ok = False

    add("ffmpeg", "有" if has_bin("ffmpeg") else "缺",
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, text=True).stdout.split("\n")[0]
        if has_bin("ffmpeg") else "装 ffmpeg（含 libass）")
    add("ffprobe", "有" if has_bin("ffprobe") else "缺", "" if has_bin("ffprobe") else "随 ffmpeg 一起装")
    f = ffmpeg_filters()
    add("libass(字幕)", "有" if f.get("ass") else "缺",
        "" if f.get("ass") else "这版 ffmpeg 没编 libass，烧不了字幕；换带 libass 的构建")

    try:
        import PIL; add("Pillow", "有", f"Pillow {PIL.__version__}")
    except ImportError:
        add("Pillow", "缺", "pip install pillow（勘验拼版、生成尾片都要）")

    font = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)
    add("中文字体", "有" if font else "缺",
        font or "装 Noto Serif/Sans CJK：apt install fonts-noto-cjk")

    for mod, why in (("numpy", "拍点分析"), ("librosa", "拍点分析"), ("soundfile", "读音频数组")):
        try:
            __import__(mod); add(mod, "有", why)
        except ImportError:
            add(mod, "缺", f"pip install {mod}（用于{why}；缺了不影响渲染，只少一项检查）", required=False)

    try:
        import faster_whisper  # noqa
        md = os.environ.get("ASR_MODEL_DIR", "")
        if md and os.path.exists(md):
            add("ASR(词校验)", "有", f"模型目录 {md}", required=False)
        elif md:
            add("ASR(词校验)", "缺", f"ASR_MODEL_DIR 指向的目录不存在: {md}", required=False)
        else:
            add("ASR(词校验)", "缺", "faster-whisper 已装，但没设 ASR_MODEL_DIR（指向本地模型目录）", required=False)
    except ImportError:
        add("ASR(词校验)", "缺", "可选：装 faster-whisper 才能做词完整性检查", required=False)

    print("\n环境自检\n" + "-" * 66)
    for state, name, detail in rows:
        print(f"{state:2}  {name:12}  {detail}")
    print("-" * 66)
    print("结论:", "必需项齐，可开跑" if ok else "缺必需项，先补齐再开跑（可选项缺失只会少一项检查）")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
