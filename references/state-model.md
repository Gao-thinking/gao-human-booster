# 状态模型与贝叶斯算法

`daily/` 与 `state/` 目录是本 skill 的"记忆"。首次运行由 skill 自动创建；**一律用 write 工具读写，禁止 shell 重定向/heredoc 改文件**。

## 目录结构

```
~/.agents/skills/gao-human-booster/
├── daily/                     # ★ 逐日记录 + 计划的唯一数据源（MDX，git 忽略）
│   └── YYYY-MM-DD.mdx         #   每天一份，按日期命名：今日计划 + 今日总结 + 情报补给 + 推荐
└── state/
    ├── profile.json           # 画像 + 兴趣方向 + 硬规则 + 提醒设置（长期）
    ├── domains.json           # 领域定义 + 贝叶斯后验（核心）
    ├── worries.json           # 担心箱
    ├── library.json           # 推荐库（推荐过/在读/已读的书与电影，防重复推荐）
    ├── backup.json            # 可选备份配置（默认关闭，由 scripts/backup.py 读写）
    └── evolution.json         # 版本与升级日志
```

## 1. profile.json

```json
{
  "user": {"name": "gao", "role": "创业者", "wake_time": "08:00", "sleep_time": "22:00"},
  "review": {"preferred_time": "21:00", "remind": true, "skip_weekend": false},
  "rules": ["23:00 后不展开复盘", "不做需要过度依赖他人的事业"],
  "energy": {"peak": "morning"},
  "interests": ["AI/独立开发", "法语", "健身", "投资"],
  "calendar": {"provider": "apple", "remind_at": "21:00"},
  "created": "2026-08-26"
}
```

- `interests`：建档时收集的 3-5 个兴趣/关注方向。**情报补给与每周推荐从它出发**；用户说"我最近关注 X"→ 增量更新。
- `rules`：用户明确说"以后别 X" → 立即写入，后续流程硬性遵守（自进化 #5）。
- `energy.peak`：由 daily_log 精力记录推断（连续 3 天相同时写入），主行动优先排到该时段。
- `review.skip_weekend`：为 true 时周日只做周复盘，不做晚间复盘。

## 2. domains.json（贝叶斯核心）

```json
{"domains": {
  "工作/事业": {
    "job": "钱+成长，当前主战场是交付 A 项目",
    "priority": 1.0,
    "prior": 0.7,
    "alpha": 2.8, "beta": 1.2,
    "score": 0.7,
    "streak": 3, "best_streak": 9,
    "last_evidence": "2026-08-25",
    "weekly": [{"week": "2026-W34", "avg": 0.83, "days": 4}],
    "status": "active"
  }
}}
```

字段说明：

| 字段 | 含义 |
|---|---|
| job | 该领域被雇佣完成的 Job（建档时用户原话，写不清就重访谈） |
| priority | 用户在意度权重 0~1（建档 + 周复盘可调整） |
| prior | 建档先验；只在重访谈或用户明确改口时更新 |
| alpha / beta | Beta 分布参数；初值 `prior×4` / `(1-prior)×4`（4 次虚拟先验观察） |
| score | 后验均值 = alpha/(alpha+beta)，0~1 |
| streak / best_streak | 连续达标天数（r≥0.5 计一天）与历史最佳 |
| last_evidence | 最近一次有评分日期 |
| weekly | 最近 12 周聚合 [{week, avg, days}]，用于趋势与周报 |
| status | active / archived（封存不删除，保留全部数据） |

## 3. daily/YYYY-MM-DD.mdx（逐日记录 + 计划，唯一数据源）

**每天一份，按日期命名**（`daily/2026-08-29.mdx`）。**未来计划 + 当日总结 + 情报补给 + 推荐都在同一份里**：计划写在目标日期的文件里（没有就先创建），复盘总结追加到当天文件。示例：

```mdx
---
date: 2026-08-29
mood: 7
energy: 下午犯困
---

## 今日计划

- [ ] 主行动｜工作/事业：上午按问题清单打磨 app 的一个核心问题，完成标准=修复/优化 1 项并重新验证
- [ ] 备选｜追求：下午看《野性的呼唤》英法对照 20-30 分钟
- [ ] 事件：周末回家

## 今日总结

### 完成

- 测试家庭照片 app，过了一遍全部功能
- 自制蓝莓紫甘蓝抗炎奶昔

### 未完成

- 法语只做了资料准备，未实际学习

### 担心 / 情绪

- 刀割嗓子疼 + 腰酸

### 领域评分

- 工作/事业：1 — 测试闭环
- 追求：0.5 — 只做了资料准备
- 健身：0.5 — 深蹲 1 组

### 明日行动

- 主行动：上午按问题清单打磨 app 的核心问题，完成标准=修复 1 项并验证
- 备选：下午看《野性的呼唤》英法对照 20-30 分钟

### 情报补给

- 法语入门：Anki 间隔重复可以 5 分钟/天对抗遗忘，适合你的 20 分钟学习节奏

### 推荐

- 《原子习惯》（James Clear）——你连续断档时读它，讲的就是"1% 复利"怎么落地
```

**格式规则**（build_calendar.py 解析依赖，改动必须同步改脚本）：

| 元素 | 规则 |
|---|---|
| frontmatter | `---` 之间的 `key: value`。`date` 必填；`mood`(0-10)、`energy`(备注) 可选 |
| `## 今日计划` | 复选列表 `- [ ]` / `- [x]`。前缀 `主行动｜领域：内容`（kind + 可选领域，用全角 ｜ 和 ：）。kind：主行动 / 备选 / 事件 / 计划（缺省=计划） |
| `## 今日总结` | 下挂 `### 完成 / 未完成 / 担心（担心 / 情绪）/ 领域评分 / 明日行动 / 情报补给 / 推荐` |
| 完成/未完成/担心/情报补给/推荐 | 普通 `- 条目` |
| 领域评分 | `- 领域名：分数 — 依据`；分数 ∈ {0, 0.5, 1}（也接受 0/0.5/1.0 写法） |
| 明日行动 | `- 主行动：…` / `- 备选：…` |
| 完成状态 | 计划勾选 `- [x]` 即完成；当天主行动是否全勾 = 当天 `completed`（完成率统计） |

**写档约定**：
- 晚间复盘：更新今天文件（总结区 + 勾选今天计划）→ **同时创建/更新明天文件**（今日计划区，来自明日行动）。
- 未来规划：直接写目标日期文件（不存在就创建）。
- 情报补给 ≤1-2 条、推荐 ≤1 条，都是可选区；没内容就不写这个标题。
- 状态文件一律用 write 工具读写；build 只读 daily/ 并生成 data/ + HTML（构建产物）。

## 4. worries.json

```json
{"items": [
  {"id": "W-20260825-1", "text": "周末回家安排", "added": "2026-08-25", "earliest": "2026-08-28", "status": "open"}
]}
```

- 晚间复盘把担心写入（含"最早处理时间"），**今晚不再想它**。
- `earliest` 之前的担心在复盘时不重复提出；每周复盘清理 `status=done` 的条目并检查未处理的。
- 担心有明确日期 → 同时写一条 `事件` 计划到那天 MDX。

## 5. library.json（推荐库，防重复 + 跟进）

```json
{
  "books": [
    {"title": "原子习惯", "author": "James Clear", "status": "recommended", "date": "2026-08-29", "note": "断档期推荐"}
  ],
  "movies": [{"title": "荒野生存", "status": "recommended", "date": "2026-08-29", "note": ""}],
  "last_followup": "2026-08-29"
}
```

- 每周推荐前先查 library，**不重复推荐**；用户反馈"在读/读完/想看/不想看" → 更新 status。
- 自进化 #8：推荐 2 周无反馈 → 周复盘时追问一句。

## 6. backup.json（可选备份，默认关闭）

```json
{"remote": "git@github.com:gao/ghb-backup.git", "enabled": true, "last_push": "2026-08-29"}
```

- 由 `scripts/backup.py` 读写，**用户主动 `make backup-init REMOTE=<url>` 后才 enabled=true**。
- 启用后：`make backup` 把 `daily/` + `state/`（含本文件）镜像到 `~/.agents/ghb-backup`（独立仓库）→ commit → push 到用户指定的 GitHub 私有仓库。
- 复盘完成后若 enabled → 自动 `make backup`；失败只提示不阻塞主流程。
- 关闭：编辑 backup.json 设 `enabled: false`。

## 7. evolution.json

```json
{"version": "v1.1.0", "history": [
  {"version": "v1.0.0", "date": "2026-08-26", "changelog": ["初始版本"]},
  {"version": "v1.1.0", "date": "2026-08-29", "changelog": ["存储升级为 daily/*.mdx；新增开挂引擎（复利×杠杆×情报）；新增情报补给与书籍/电影推荐；新增可选 GitHub 备份"]}
]}
```

每次自进化确认后 version 递增、changelog 追加。输出头部注明 `当前版本 vX.Y`。

## 贝叶斯更新算法

### 每日更新（单条证据，评分后执行）

```
r ∈ {0, 0.5, 1}   # 硬数据优先（完成/未完成、次数），感觉只作备注
alpha += r
beta  += (1 - r)
score  = alpha / (alpha + beta)
streak: r ≥ 0.5 → +1；r < 0.5 → 0（best_streak 保留历史最大值）
last_evidence = 今天
```

- 初值：alpha = prior×4, beta = (1-prior)×4。
- **无证据不更新**：今天未涉及的领域不评分、不改参数（缺席一天是弱证据）。

### 衰减（无证据期）

```
last_evidence 距今 > 7 天（连续 7 天无评分）：
  alpha ×= 0.9; beta ×= 0.9      # 后验向 0.5 回归，等效遗忘
连续 14 天无评分 → 触发自进化 #1（提议封存）
```

### 周收敛（强证据，周日执行）

```
评分天数 ≥ 2 才算周证据；avg = Σr / 评分天数
alpha += avg × 评分天数
beta  += (1 - avg) × 评分天数
写入 weekly 数组（保留 12 周，淘汰最旧）
```

### 决策规则

| 决策 | 规则 |
|---|---|
| 下周焦点领域 | `argmin(score × (1 - priority))`——后验最低且用户最在意的先攻；两者矛盾（最低分的不是最在意的）→ ⬜ 问用户 |
| 明日主行动 | 从"未完成 × 在意程度 × 明早精力"里选，不按任务清单长度；写不出完成标准 → 缩小；**优先复利行动（§0.5）** |
| 精力排期 | energy.peak 连续 3 天相同 → 写回 profile，主行动优先排该时段 |
| 周报趋势 | 对比 weekly 最近 3 周 avg：上升/持平/下降；连续下降 3 周 → 自进化 #3（JTBD 重访谈） |

## 数据层（data/，日历按需加载）

`data/` 是构建产物（git 忽略），由 `scripts/build_calendar.py` 读取 `daily/*.mdx` + `state/*.json` 生成：

- `data/index.js`：`window.GHB = {version, months[], current, today, domains{}, plans{}, worries_open, meta}` — 领域当前后验、有数据的月份列表、未来 14 天计划（页首横幅）。
- `data/YYYY-MM.js`：`window.DATA["YYYY-MM"] = {year, month, days{}, plans{}, expert{}}` — 单月复盘 + 计划 + 专家点评 + 情报补给/推荐，浏览器按需加载。

构建规则：读取全部 daily/*.mdx → 生成当前月 + 所有有数据/计划的月份文件 → 壳 HTML 动态 `<script>` 加载（file:// 安全）。幂等，可重复跑。

## 自进化判定细节（对应 SKILL.md §6）

| # | 判定 | 备注 |
|---|---|---|
| 1 | 某领域 status=active 且 last_evidence 距今 ≥14 天 | 提议封存；用户拒绝则重置计时 |
| 2 | 同一 `next.main` 模板连续 3 次 completed=false | 按完成标准缩小为 30 分钟一步 |
| 3 | score < 0.3 且连续 2 周（weekly 最近 2 周 avg < 0.3） | 提议 JTBD 重访谈，不默认加码 |
| 4 | daily_log 连续 3 次复盘时刻 ≥23:00 | 提议把提醒提前到 21:30 |
| 5 | 用户说"以后别 X" | 立即写 profile.rules；不弹窗确认，直接生效 |
| 6 | 连续 3 次复盘耗时 >15 分钟 | 收紧协议：砍掉 3.1 或 3.2 一步 |
| 7 | 同一计划连续 3 次过期未完成 | 提议缩小为 30 分钟一步或删除（数据源 daily/*.mdx 计划区） |
| 8 | library 某推荐 2 周无反馈 | 周复盘追问"上次推荐看了吗"→ 更新 library status |

判定用**运行中的真实数据**，禁止凭空推断；单次偶发不触发（贝叶斯：先验不变，连续模式才更新）。
