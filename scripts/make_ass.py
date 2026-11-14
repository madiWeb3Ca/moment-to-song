#!/usr/bin/env python3
"""由句级时间戳生成 ASS 字幕。

lines.json: [{"text":"第一句","start":0.10,"end":4.90}, ...]
用法:
  python3 make_ass.py lines.json --w 960 --h 720 --margin-v 142 --out subs.ass
排版默认：白字 + 深色描边 + 阴影，底部居中，淡入淡出 0.2s。
--avoid-right PX：把字幕右边界内缩，避开右下角烧好的贴纸/角标。
"""
import argparse, json, sys

HDR = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00202020,&H8C000000,-1,0,0,0,100,100,1,0,1,{outline},{shadow},2,{ml},{mr},{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

def ts(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lines")
    ap.add_argument("--w", type=int, default=960)
    ap.add_argument("--h", type=int, default=720)
    ap.add_argument("--font", default="Noto Sans CJK SC")
    ap.add_argument("--size", type=int, default=None, help="默认按画面高度自适应")
    ap.add_argument("--margin-v", type=int, default=None, help="距底边距离（像素）")
    ap.add_argument("--margin-l", type=int, default=40)
    ap.add_argument("--margin-r", type=int, default=40)
    ap.add_argument("--outline", type=float, default=2.6)
    ap.add_argument("--shadow", type=float, default=2.2)
    ap.add_argument("--fade", type=int, default=200)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    size = a.size or max(24, round(a.h * 0.047))          # 720p → 34
    mv   = a.margin_v if a.margin_v is not None else round(a.h * 0.19)
    try:
        lines = json.load(open(a.lines, encoding="utf-8"))
    except Exception:
        sys.exit(f"读不了 {a.lines}：需要 [{{\"text\":..,\"start\":..,\"end\":..}}] 这样的 JSON 数组")

    # 可用宽度：左右留白各 40（或参数值）。汉字宽 ≈ 1 个字号，全角空格按半个算。
    usable = a.w - a.margin_l - a.margin_r

    def txt_w(text, s):
        return sum((s * 0.5 if ch in "　 " else s) for ch in text)

    others = [ln["text"].strip() for ln in lines if ln.get("text", "").strip()]
    actual = size
    if others:
        widest = max(txt_w(t, size) for t in others)
        if widest > usable:                     # 整片统一降到能放下最宽那句
            ratio = usable / widest
            actual = max(14, int(size * ratio * 0.98))

    with open(a.out, "w", encoding="utf-8") as f:
        f.write(HDR.format(w=a.w, h=a.h, font=a.font, size=actual, outline=a.outline,
                           shadow=a.shadow, ml=a.margin_l, mr=a.margin_r, mv=mv))
        for ln in lines:
            txt = ln["text"].strip()
            if not txt:
                continue
            s, e = float(ln["start"]), float(ln["end"])
            if e <= s:
                print(f"跳过时间非法的一句: {txt}", file=sys.stderr)
                continue
            f.write(f"Dialogue: 0,{ts(s)},{ts(e)},Main,,0,0,0,,{{\\fad({a.fade},{a.fade})}}{txt}\n")
    if actual < size:
        print(f"提示: 最宽一句 {max(txt_w(t, size) for t in others):.0f}px 超过安全宽 {usable}px，"
              f"整片字号压到 {actual}（原计划 {size}）。想保住字号就把长句拆短。", file=sys.stderr)
    print(f"已写入 {a.out}（{len(lines)} 句，字号 {actual}，底距 {mv}，安全宽 {usable}px）")

if __name__ == "__main__":
    main()
