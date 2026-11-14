#!/usr/bin/env python3
"""音轨质检：机器能判的六项硬指标。

用法:
  python3 music_qc.py song.mp3                 # 基础六项
  python3 music_qc.py song.mp3 --lyrics l.txt  # 追加 ASR 词完整性（需 faster-whisper + 模型目录）
  python3 music_qc.py song.mp3 --expect-dur 48
判据（全部 PASS 才准往下做画面）:
  1 容器真实     codec_name 必须是 mp3/aac（工具常把 PCM/WAV 存成 .mp3）
  2 时长对齐     与 --expect-dur 误差 ≤ 0.05s
  3 响度与削波   mean ≈ -18 ~ -15 dB，max ≤ -0.3 dB（偏轻就 loudnorm 后复测）
  4 静音空隙     标出 <-33dB 且 ≥0.06s 的段落，供字幕断开/镜头停留用
  5 拍点稳定     拍间隔 std ≤ 0.05（librosa 缺失时 SKIP，不假装通过）
  6 词完整性     歌词每句在 ASR 文本里逐字命中 ≥60%（同音字放行，漏句判失败）
兼容性: 带封面图的 mp3（attached_pic）会被跳过，不会把图片流当成音频流。
"""
import argparse, json, os, re, subprocess, sys

def sh(cmd):
    """cmd 传 list；路径含空格、引号、中文都不会断。"""
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return r.stdout

def probe(path):
    out = sh(["ffprobe", "-v", "error", "-print_format", "json",
              "-show_format", "-show_streams", path])
    try:
        return json.loads(out)
    except Exception:
        sys.exit("读不出音频信息，文件可能损坏: " + out[-400:])

def audio_stream(d):
    """只取真正的音频流；mp3 封面图是 video 流，不能误当成音频。"""
    return next((s for s in d["streams"] if s.get("codec_type") == "audio"), None)

def _db(text, key):
    m = re.search(key + r":\s*(-?[\d.]+|-inf|nan)", text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None

def loudness(path):
    txt = sh(["ffmpeg", "-i", path, "-af", "volumedetect", "-f", "null", "-"])
    return _db(txt, "mean_volume"), _db(txt, "max_volume")

def silences(path):
    txt = sh(["ffmpeg", "-i", path, "-af", "silencedetect=noise=-33dB:d=0.06",
              "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", txt)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*(-?[\d.]+)", txt)]
    return list(zip(starts, ends))

def to_wav(path):
    """统一转 16k 单声道 wav；转不出来返回 None，不抛异常。"""
    import tempfile
    wav = os.path.join(tempfile.gettempdir(), "_qc16k.wav")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path,
                        "-ar", "16000", "-ac", "1", wav],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return wav if r.returncode == 0 and os.path.exists(wav) else None

def beats(path):
    try:
        import librosa, numpy as np
        wav = to_wav(path) or path
        y, sr = librosa.load(wav, sr=16000, mono=True)
        bpm, idx = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(np.atleast_1d(bpm)[0])
        t = librosa.frames_to_time(idx, sr=sr)
        return bpm, len(t), (float(np.diff(t).std()) if len(t) > 1 else None)
    except Exception:
        return None, None, None

def asr_lines(path, lyrics):
    try:
        import soundfile as sf
        from faster_whisper import WhisperModel
    except Exception:
        return None
    model_dir = os.environ.get("ASR_MODEL_DIR")
    if not model_dir:
        return {"error": "未设置 ASR_MODEL_DIR（faster-whisper 本地模型目录）"}
    if not os.path.exists(model_dir):
        return {"error": "ASR_MODEL_DIR 指向的目录不存在: " + model_dir}
    wav = to_wav(path)
    if not wav:
        return {"error": "音频转 wav 失败，无法做词完整性检查"}
    m = WhisperModel(model_dir, device="cpu", compute_type="int8")
    a, sr = sf.read(wav); a = a.astype("float32")      # 必须传数组，不能传路径
    segs, _ = m.transcribe(a, language="zh", initial_prompt=" ".join(lyrics),
                           word_timestamps=True, vad_filter=False)
    text = "".join(s.text for s in list(segs))          # 返回生成器，要 list()
    norm = lambda s: re.sub(r"[^\u4e00-\u9fff]", "", s)
    hit, miss = [], []
    for ln in lyrics:
        core = norm(ln)
        if not core:
            continue
        got = sum(1 for ch in core if ch in norm(text))
        (hit if got / len(core) >= 0.6 else miss).append(ln)
    return {"hit": hit, "miss": miss, "raw": text}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--expect-dur", type=float, default=None)
    ap.add_argument("--lyrics", default=None, help="歌词文件，每行一句")
    a = ap.parse_args()

    if not os.path.exists(a.audio):
        sys.exit(f"找不到音频文件: {a.audio}")
    info = probe(a.audio)
    st = audio_stream(info)
    if st is None:
        sys.exit("这个文件里没有音频流（可能只是图片或已损坏）")
    codec = st.get("codec_name")
    dur = float(info["format"].get("duration") or st.get("duration") or 0)
    mean, mx = loudness(a.audio)
    sil = silences(a.audio)
    bpm, nbeat, bstd = beats(a.audio)

    rows, ok = [], True
    def add(name, passed, detail):
        nonlocal ok
        rows.append((name, "PASS" if passed else "FAIL", detail))
        if not passed:
            ok = False

    add("1 容器真实", codec in ("mp3", "aac"),
        f"codec_name={codec}" + ("" if codec in ("mp3", "aac") else "（需转真 mp3：-c:a libmp3lame）"))
    add("2 时长对齐", a.expect_dur is None or abs(dur - a.expect_dur) <= 0.05,
        f"{dur:.3f}s" + (f" vs 期望 {a.expect_dur:.3f}s" if a.expect_dur else ""))
    add("3 响度/削波", mean is not None and mx is not None
        and -19 <= mean <= -14.5 and mx <= -0.3,
        f"mean {mean} dB / max {mx} dB" if mean is not None else "解析不到音轨电平（可能全静音）")
    add("4 静音空隙", True, f"{len(sil)} 段" + (f"，首个 {sil[0][0]:.2f}s 起" if sil else ""))
    add("5 拍点稳定", bstd is not None and bstd <= 0.05,
        "librosa 不可用或解析失败（SKIP）" if bstd is None
        else f"BPM {bpm:.2f} / {nbeat} 拍 / 间隔 std {bstd:.3f}s")

    if a.lyrics:
        if not os.path.exists(a.lyrics):
            rows.append(("6 词完整性", "SKIP", f"歌词文件不存在: {a.lyrics}"))
        else:
            lyr = [l.strip() for l in open(a.lyrics, encoding="utf-8") if l.strip()]
            res = asr_lines(a.audio, lyr)
            if res is None:
                rows.append(("6 词完整性", "SKIP", "未安装 faster-whisper/soundfile"))
            elif "error" in res:
                rows.append(("6 词完整性", "SKIP", res["error"]))
            else:
                passed = len(res["miss"]) == 0
                rows.append(("6 词完整性", "PASS" if passed else "FAIL",
                             f"命中 {len(res['hit'])}/{len(lyr)}"
                             + ("；漏: " + " / ".join(res["miss"]) if res["miss"] else "")))
                ok = ok and passed

    print(f"\n音轨: {a.audio}\n" + "-" * 64)
    for n, s, d in rows:
        print(f"{s:5}  {n:10}  {d}")
    print("-" * 64)
    print("结论:", "全部通过，可进入试听闸口" if ok else "存在 FAIL，先修再往下")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
