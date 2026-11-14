---
name: moment-to-song
display_name: "专属MV工坊"
description: "把一张照片或一段现场视频，做成一支带原创 AI 词曲、逐字时间戳字幕和品牌尾片的 20–50 秒专属 MV。当用户要给某个孩子/员工/活动做生日、纪念、成长回顾的专属 MV，或要把一条现成视频换掉原声、按画面重配 AI 音乐时使用。支持一张照片、一组照片或一段现成视频。包含：环境自检、素材勘验（视频抽帧/照片拼版）、歌词创作（押韵、具体名词、禁空话）、词曲两版并出与试听闸口、音轨六项机器质检、逐字时间戳排字幕、品牌尾片排版、一键渲染、单帧原尺寸验收。不用于曲库选曲剪辑、长视频精剪、需要现场纪实的活动片、纯口播视频。"
---

# 专属MV工坊

从一段素材到一支能发出去的专属 MV。核心判断只有一条：**这支片的主角是谁、要给谁看**——它决定词怎么写、曲往哪个气质走、尾片留不留。

## 适用边界

该用：孩子生日 / 成长纪念、员工纪念、活动回顾、班级节日片、把现成视频换原声重配音乐。
不该用：需要现场纪实的活动片（有人出镜讲话、要求"当天真实"）、长视频精剪、纯口播、要唱童声儿歌（音色不稳）。

## 主流程（五步，一个硬闸口）

```
-1 环境自检 → 0 勘验 → 1 写词 → 2 出曲（两版并出） ──【闸口A：用户试听拍板】──
       → 3 排字幕 + 4 尾片（先问文案） → 5 渲染与自检 → 交付
```

**开跑第一件事：**

```bash
python3 scripts/preflight.py
```

缺必需项（ffmpeg / ffprobe / 带 libass 的 ffmpeg / Pillow / 中文字体）会直接以退出码 1 结束，并逐项给出安装指引——**看到缺项先补或换机器，不要硬着头皮往下做**。可选组件（librosa、faster-whisper）缺了只是少一项检查，脚本会标 SKIP 并说明原因，不会假装通过。

**闸口 A 是硬闸。** 曲没被用户确认，不得开始做画面；曲不过就在第 2 步重出，不许"先用着"。画面做完再换曲 = 全片返工。

### 0 素材勘验

```bash
python3 scripts/probe_frames.py 素材.mp4 --outdir ./work     # 视频：抽 9 帧
python3 scripts/probe_frames.py ./photos --outdir ./work      # 照片：整组拼版 + 每张规格
```

产出规格 + 拼版。照片模式会报张数、每张宽高、是否尺寸不一、有没有读不了的图（HEIC 等）。**必须真的看一眼拼版**再写词——画面里有什么、主角在第几秒、有没有烧字或贴纸，直接决定后面字幕放哪。

判三件事：时长（决定词句数）、画幅（4:3 还是 9:16 决定字幕安全区）、原声（现场收声偏响就整轨替换，不要"混一点"）。

### 1 写词

- **句数按时长算**：20–30 秒 → 5 句；40–50 秒 → 8 句。每句 4–9 字，句间留 1–2 秒空隙给呼吸。
- **押同一个韵**：偶句必押、奇句可放。整首押一个韵母，比每句换韵好听得多。
- **写具体名词**，不堆形容词：气球、门框、蛋糕中央、五根蜡烛、围成圈。"快乐成长""美好时光"这类词没有画面。
- **禁空话与口号**：英雄、出征、必胜、辉煌一律不写；祝福也用具体的（"天天开心　快快成长"优于"茁壮成长、前程似锦"）。
- **主角名字进词**：出现在第 2–3 句或倒数第 2 句，不要只放字幕。全名要用户确认，默认用昵称。

### 2 出曲（两版并出）

一次给两版让用户横向比，比一版一版改快。两版要**气质不同**，不是同一首的微调：

- A：温柔女声恱情流行（钢琴 + 轻弦乐、句尾拖音、副歌轻抬）
- B：温暖男声民谣弹唱（木吉他 + 口琴点缀、贴麦、不修音）

提示词必须写清四件事：**音色 + 编曲 + 唱法 + 时长**。时长用工具的 duration 参数直接命中，**不要后期 atempo 拉伸**（失真且拍点全乱）。

生成后先过机器质检，再给用户听：

```bash
python3 scripts/music_qc.py 试听A.mp3 --expect-dur 48 --lyrics lyrics.txt
```

口径见 [references/music-qc.md](references/music-qc.md)。工具常把 PCM/WAV 存成 `.mp3`，**必须 ffprobe 验 codec_name，转真 mp3 再交付**：

```bash
ffmpeg -i raw.bin -ar 44100 -ac 2 -c:a libmp3lame -b:a 192k 试听A.mp3
```

给用户的试听说明只写三件事：这版什么气质、编曲是什么、和另一版差在哪。不要自评"很好听"。

### 3 排字幕

字幕时间**只能来自逐字时间戳**，不许估。取时间戳（先 `ffmpeg -ar 16000 -ac 1` 转单声道 wav）：

```python
import os, soundfile as sf
from faster_whisper import WhisperModel
m = WhisperModel(os.environ["ASR_MODEL_DIR"], device="cpu", compute_type="int8")
a, sr = sf.read("a16.wav"); a = a.astype("float32")          # 必须传数组，不能传路径
segs, _ = m.transcribe(a, language="zh", initial_prompt="整首词放这里",
                       word_timestamps=True, vad_filter=False)
print([(round(w.start,2), round(w.end,2), w.word) for s in list(segs) for w in s.words])  # 返回生成器，要 list()
```

按每句首字起、末字止，写进 `lines.json`（`[{"text":...,"start":...,"end":...}]`），再生成字幕：

```bash
python3 scripts/make_ass.py lines.json --w 960 --h 720 --margin-v 142 --out subs.ass
```

排版铁律：字号 ≥ 34（720p）、白字带描边与阴影、**避开画面里烧好的贴纸角标**、一行不超过 9 字。长句会触发脚本按安全宽自动压字号并在 stderr 报是哪句——**看到提示就拆句，不要接受偷偷缩小的字**。验字幕必须**抽单帧 100% 看**，不许只看拼版缩略图——半截字在缩略图上正好看不见。

### 4 尾片（先问文案，再排版）

**顺序不能反**：先问"尾片要写什么字、署名怎么写"，再排版。排完再改文案等于白做一版。

```bash
# 无品牌：墨黑底 + 金色，不放徽标
python3 scripts/endcard.py --style left \
  --sig "某某幼儿园　祝　小满" --line1 "天天开心" --line2 "快快成长" \
  --w 960 --h 720 --out endcard.png

# 有品牌：把色值、徽标路径、英文名、页脚放到一个 JSON 里传进去
python3 scripts/endcard.py --profile ./brand.json --style center \
  --sig "某某幼儿园　祝　小满" --line1 "天天开心" --line2 "快快成长" --out endcard.png
```

技能包里不放任何机构的徽标和名称，品牌配置由用户的 JSON 提供（格式见 [references/endcard.md](references/endcard.md)）。排版原则与品牌无关：

- 深色底上的白底徽标**必须放在白卡上**，不直接叠；徽标不变形、不换色、不加投影。
- 中文大字用衷线（Noto Serif CJK），金色只给署名/英文/细线，白色只给祝福主体。
- 字距只给英文加；中文加大字距会显得松散断裂。
- 尾片停 **3.5–4 秒**（两行字读完还留半拍），音乐在尾片前 2.5 秒渐隐干净。

### 5 渲染与自检

```bash
# 视频素材
python3 scripts/build_mv.py --video 素材.mp4 --song 试听.mp3 --ass subs.ass \
  --endcard endcard.png --card-dur 4 --duration 48 --out ../成片.mp4

# 照片素材（单张或整组）：统一画幅居中裁切 + 缓慢平移，最长边默认压到 1080
python3 scripts/build_mv.py --photos ./photos --song 试听.mp3 --duration 48 \
  --per-photo 6 --endcard endcard.png --card-dur 4 --out ../成片.mp4
```

渲染做四件事：原声整轨静音换新曲、烧字幕、暖调、尾片拼接。脚本已处理四种常见翻车：可变帧率素材会先做帧率归一化（否则帧数对不上）；音乐比片子短会补静音而不是提前断；路径含空格/引号会走临时安全路径；全静音音轨只报 FAIL 不崩。之后自检：

- 帧数 = 时长 × fps，无黑帧；
- 音轨 mean −19 ~ −14.5 dB、max ≤ −0.3 dB；
- 最后一帧到尾片是直切，**不许中间压暗**（压暗会被当成黑场凑时长）；
- 抽帧单帧复核字幕：**用 `snap.py` 导出原尺寸 PNG 逐张看**（不出框、不半截、不压贴纸），不许看拼版缩略图：

```bash
python3 scripts/snap.py 成片.mp4 --times 3 12 28 45 --outdir ./chk
python3 scripts/snap.py 成片.mp4 --times 30 --crop 0,470,960,250 --outdir ./chk   # 只裁字幕带，100% 看
```

## 交付话术

告诉用户四件事，不要只甩链接：改了什么（原声怎么处理、字幕对哪版音轨）、规格数字（时长/帧数/分辨率/响度）、验过哪几处（单帧结论）、还能怎么调（换词/换曲/尾片改字，各是一分钟还是一轮重出）。

有幼儿或儿童出镜时，交付必须提醒**肖像授权先于发布**，这比画质更要紧。

## 脚本

| 脚本 | 作用 |
|---|---|
| `scripts/probe_frames.py` | 勘验素材：视频抽帧拼版 / 照片组拼版与规格 |
| `scripts/music_qc.py` | 音轨六项硬指标（容器/时长/响度/空隙/拍点/词完整性） |
| `scripts/make_ass.py` | 由句级时间戳生成 ASS 字幕 |
| `scripts/endcard.py` | 生成品牌尾片（左对齐 / 居中两种版式） |
| `scripts/build_mv.py` | 一键渲染 + 自检打印（视频 / 照片两种素材） |
| `scripts/snap.py` | 单帧原尺寸导出 + 黑帧提示，验收字幕用 |
| `scripts/preflight.py` | 环境自检：必需/可选分级，缺项给安装指引 |

## 参考

- [references/music-qc.md](references/music-qc.md)：六条硬指标 + 三条人耳指标 + 四个真实翻车案例
- [references/endcard.md](references/endcard.md)：品牌配置格式、尾片两种版式、七条排版禁忌
- [references/pitfalls.md](references/pitfalls.md)：踩过的坑（含特殊文件与缺组件两类）
