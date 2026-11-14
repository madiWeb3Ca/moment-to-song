# 专属MV工坊 · moment-to-song

**一张照片，一首只为这个人写的歌。**

把一张照片或一段现场视频，做成一支 20–50 秒的专属 MV：原创 AI 词曲、逐字时间戳字幕、品牌尾片，一键渲染。全流程在一个 AI 环境里跑完，不需要剪辑软件。

> Turn one photo or one clip into a 20–50 second personalized MV: original lyrics, original music, word-level timed captions, a branded end card, and a one-command render. No editing software required.

---

## 它解决什么问题

给孩子的生日、员工的纪念日、一次活动的回顾做片，难点从来不是剪辑软件，而是三件事：

1. **词写不出来。** 一比一写祝福，很容易写成"快乐成长、前程似锦"这种没有画面的空话。
2. **曲排不上。** 从曲库选曲，时长对不上、歌词对不上，最后靠拉伸音轨硬凑，拍点全乱。
3. **字幕对不准。** 靠听感估时间，半截字压在贴纸上，发出去自己都不想看。

这个技能把三件事都钉死了：**词按时长算句数、曲按 duration 参数直出、字幕只取逐字时间戳。**

## 流程

```
-1 环境自检 → 0 勘验 → 1 写词 → 2 出曲（两版并出）
        ──【闸口 A：用户试听拍板】──
        → 3 排字幕 → 4 尾片（先问文案，再排版）→ 5 渲染与自检 → 交付
```

**闸口 A 是硬闸。** 曲没被用户确认，不得开始做画面；曲不过就在第 2 步重出，不许"先用着"。画面做完再换曲 = 全片返工。

## 前置依赖

| 类型 | 组件 |
|---|---|
| 必需 | `ffmpeg` / `ffprobe`（编字幕需 **带 libass** 的 ffmpeg）、`Pillow`、中文字体（Noto Serif CJK 等） |
| 可选 | `librosa`（拍点检测）、`faster-whisper` + ASR 模型（逐字时间戳） |

```bash
python3 scripts/preflight.py
```

缺必需项会以退出码 1 结束并逐项给安装指引；可选组件缺了只标 SKIP 并说明原因，不会假装通过。**看到缺项先补或换机器，不要硬着头皮往下做。**

## 安装

```bash
# 从 SkillHub
skillhub install moment-to-song --namespace user_9462735f

# 或直接从 Git 克隆，放进你的 skills 目录
git clone https://github.com/madiWeb3Ca/moment-to-song.git
```

## 快速开始

```bash
# 0 勘验素材：视频抽 9 帧 / 照片整组拼版
python3 scripts/probe_frames.py 素材.mp4 --outdir ./work
python3 scripts/probe_frames.py ./photos --outdir ./work

# 2 出曲后先过机器质检，再给用户听
python3 scripts/music_qc.py 试听A.mp3 --expect-dur 48 --lyrics lyrics.txt

# 3 由句级时间戳生成字幕
python3 scripts/make_ass.py lines.json --w 960 --h 720 --margin-v 142 --out subs.ass

# 4 尾片
python3 scripts/endcard.py --style left \
  --sig "某某幼儿园　祝　小满" --line1 "天天开心" --line2 "快快成长" \
  --w 960 --h 720 --out endcard.png

# 5 一键渲染
python3 scripts/build_mv.py --photos ./photos --song 试听.mp3 --duration 48 \
  --per-photo 6 --endcard endcard.png --card-dur 4 --out ../成片.mp4

# 5 验收：单帧原尺寸导出，逐张看
python3 scripts/snap.py 成片.mp4 --times 3 12 28 45 --outdir ./chk
```

## 脚本

| 脚本 | 作用 |
|---|---|
| `scripts/preflight.py` | 环境自检：必需/可选分级，缺项给安装指引 |
| `scripts/probe_frames.py` | 勘验素材：视频抽帧拼版 / 照片组拼版与规格 |
| `scripts/music_qc.py` | 音轨六项硬指标（容器/时长/响度/空隙/拍点/词完整性） |
| `scripts/make_ass.py` | 由句级时间戳生成 ASS 字幕 |
| `scripts/endcard.py` | 生成品牌尾片（左对齐 / 居中两种版式） |
| `scripts/build_mv.py` | 一键渲染 + 自检打印（视频 / 照片两种素材） |
| `scripts/snap.py` | 单帧原尺寸导出 + 黑帧提示，验收字幕用 |

## 几条铁律

- **写具体名词，不堆形容词。** 气球、门框、蛋糕中央、五根蜡烛、围成圈。"快乐成长"没有画面。
- **整首押同一个韵。** 偶句必押、奇句可放，比每句换韵好听得多。
- **时长用工具的 duration 参数命中，不做后期 atempo 拉伸。** 拉伸失真且拍点全乱。
- **字幕字号有下限（720p 下 ≥ 34），一行不超过 9 字。** 脚本按安全宽自动压字号时会在 stderr 报是哪句——看到提示就拆句，不要接受偷偷缩小的字。
- **尾片先问文案，再排版。** 排完再改文案等于白做一版。
- **验字幕必须抽单帧 100% 看。** 半截字在拼版缩略图上正好看不见。
- **有儿童出镜时，提醒肖像授权先于发布。** 这比画质更要紧。

## 目录结构

```
moment-to-song/
├── SKILL.md                  # 技能主体与流程
├── agents/                   # 平台适配配置
├── references/
│   ├── music-qc.md           # 六条硬指标 + 三条人耳指标 + 四个真实翻车案例
│   ├── endcard.md            # 品牌配置格式、两种版式、七条排版禁忌
│   └── pitfalls.md           # 踩过的坑（特殊文件与缺组件两类）
└── scripts/                  # 7 个可执行脚本
```

技能包里不放任何机构的徽标和名称，品牌配置由用户自己的 JSON 提供。

## 边界

该用：孩子生日 / 成长纪念、员工纪念、活动回顾、班级节日片、把现成视频换原声重配音乐。

不该用：需要现场纪实的活动片（有人出镜讲话、要求"当天真实"）、长视频精剪、纯口播、要唱童声儿歌（音色不稳）。

## License

MIT © 2026 马迪 (madiWeb3Ca)
