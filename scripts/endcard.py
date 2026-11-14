#!/usr/bin/env python3
"""生成品牌尾片：深色底 + 细框 + 白卡片承徽标 + 衷线大字 + 金色署名。

用法:
  python3 endcard.py --sig "某某幼儿园　祝　小满" --line1 "天天开心" --line2 "快快成长" \
      --w 960 --h 720 --out endcard.png

  # 用外部品牌配置（色板、徽标、英文名、页脚都由配置提供）
  python3 endcard.py --profile ./brand.json --style center \
      --sig "某某幼儿园　祝　小满" --line1 "天天开心" --out endcard.png

brand.json:
  {"bg":"#2B2620","accent":"#C9A227","paper":"#FAF6EE","inner":"#4A423A",
   "logo":"/path/to/logo.png","en":"XXXX SCHOOL","top":"XXXX","foot":"EST. 19XX　XXXX"}

定位原则（与品牌无关，换色也不会变）:
  - 深色底上的白底徽标必须放在白色卡片里，不直接叠；徽标不变形、不换色、不投影
  - 中文大字衷线、金色只给署名/英文/细线，白色给祝福主体
  - left = 左对齐杂志式；center = 居中落款式
"""
import argparse, json, os

FONT_DIR = "/usr/share/fonts/opentype/noto"
REG = os.path.join(FONT_DIR, "NotoSerifCJK-Regular.ttc")

DEFAULT_PROFILE = {"bg": "#2B2620", "accent": "#C9A227", "paper": "#FAF6EE",
                   "inner": "#4A423A", "logo": "", "en": "", "top": "", "foot": ""}

def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def tracked(d, text, font, x, y, fill, tr=0):
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        x += d.textlength(ch, font=font) + tr

def twidth(d, text, font, tr=0):
    return sum(d.textlength(c, font=font) + tr for c in text) - (tr if text else 0)

def build(a):
    from PIL import Image, ImageDraw, ImageFont
    W, H = a.w, a.h
    prof = dict(DEFAULT_PROFILE)
    if a.profile:
        prof.update(json.load(open(a.profile, encoding="utf-8")))
    bg, gold, paper = rgb(prof["bg"]), rgb(prof["accent"]), rgb(prof["paper"])
    inner = rgb(prof["inner"])

    im = Image.new("RGB", (W, H), bg); d = ImageDraw.Draw(im)
    m = round(W * 0.036)
    d.rectangle([m, m, W - m, H - m], outline=gold, width=2)
    d.rectangle([m + 8, m + 8, W - m - 8, H - m - 8], outline=inner, width=1)

    fs = lambda s: ImageFont.truetype(REG, s, index=0)
    f_big, f_sig, f_eb = fs(round(W * 0.067)), fs(round(W * 0.023)), fs(round(W * 0.0146))

    # ---- 徽标（白卡承载）----
    lp = prof.get("logo") or ""
    if lp and os.path.exists(lp):
        cw, ch = round(W * 0.18), round(W * 0.161)
        lx, ly = (W - m - 12 - cw, m + 22) if a.style == "left" else ((W - cw) // 2, round(H * 0.133))
        d.rounded_rectangle([lx, ly, lx + cw, ly + ch], radius=3,
                            fill=(255, 255, 255), outline=gold, width=1)
        lg = Image.open(lp).convert("RGB")
        lh = int(ch * 0.86); lw = int(lg.width * lh / lg.height)
        im.paste(lg.resize((lw, lh), Image.LANCZOS), (lx + (cw - lw) // 2, ly + (ch - lh) // 2))

    # ---- 文本 ----
    if a.style == "left":
        x = m + 48
        if prof.get("top"):
            tracked(d, prof["top"], f_eb, x, m + 52, gold, 2)
        tracked(d, a.sig, f_sig, x, round(H * 0.416), gold, 1)
        tracked(d, a.line1, f_big, x - 4, round(H * 0.478), paper, 3)
        if a.line2:
            tracked(d, a.line2, f_big, x - 4, round(H * 0.606), paper, 3)
        ly = round(H * 0.75)
        d.line([x, ly, x + 104, ly], fill=gold, width=2)
        if prof.get("foot"):
            tracked(d, prof["foot"], f_eb, x, ly + 26, gold, 2)
    else:
        def ctr(text, font, y, fill, tr=0):
            tracked(d, text, font, (W - twidth(d, text, font, tr)) / 2, y, fill, tr)
        y1 = round(H * 0.47)
        y2 = y1 + round(H * 0.105)
        ctr(a.line1, f_big, y1, paper, 3)
        if a.line2:
            ctr(a.line2, f_big, y2, paper, 3)
        ly = y2 + round(H * 0.125)
        d.line([W / 2 - 44, ly, W / 2 + 44, ly], fill=gold, width=2)
        ctr(a.sig, f_sig, ly + round(H * 0.042), gold, 1)
        combined = "　".join([v for v in (prof.get("en"), (prof.get("foot") or "").split("　")[0]) if v])
        if combined:
            ctr(combined, f_eb, ly + round(H * 0.115), gold, 2)

    im.save(a.out); print("尾片已生成:", a.out, f"{W}x{H}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None, help="品牌配置 JSON（不传则用中性深色底）")
    ap.add_argument("--style", choices=["left", "center"], default="left")
    ap.add_argument("--sig", required=True, help="署名行，如：某某幼儿园　祝　小满")
    ap.add_argument("--line1", required=True)
    ap.add_argument("--line2", default="")
    ap.add_argument("--w", type=int, default=960)
    ap.add_argument("--h", type=int, default=720)
    ap.add_argument("--out", required=True)
    build(ap.parse_args())

if __name__ == "__main__":
    main()
