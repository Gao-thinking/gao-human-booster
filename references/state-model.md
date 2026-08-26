# 状态模型与贝叶斯算法

`state/` 目录是本 skill 的"记忆"。首次运行由 skill 自动创建；**一律用 write 工具读写，禁止 shell 重定向/heredoc 改文件**。

## 目录结构

```
~/.agents/skills/gao-human-booster/state/
├── profile.json      # 画像 + 硬规则 + 提醒设置（长期）
├── domains.json      # 领域定义 + 贝叶斯后验（核心）
├── daily_log.json    # 逐日记录（追加，保留 90 天）
├── worries.json      # 担心箱
└── evolution.json    # 版本与升级日志
```

## 1. profile.json

```json
{
  "user": {"name": "gao", "role": "独立开发者", "wake_time": "07:30", "sleep_time": "23:30"},
  "review": {"preferred_time": "22:00", "remind": true, "skip_weekend": false},
  "rules": ["23:00 后不展开复盘", "周日晚上是家庭时间，不安排主行动"],
  "energy": {"peak": "morning"},
  "calendar": {"provider": "apple", "remind_at": "22:00"},
  "created": "2026-08-26"
}
```

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
  },
  "追求": {"job": "做出自己的作品", "priority": 0.8, "prior": 0.5, "alpha": 2.0, "beta": 2.0, "score": 0.5, "streak": 0, "best_streak": 5, "last_evidence": "2026-08-22", "weekly": [], "status": "active"},
  "健身": {"job": "能量供给，支撑不疲劳地工作", "priority": 0.9, "prior": 0.4, "alpha": 1.6, "beta": 2.4, "score": 0.4, "streak": 0, "best_streak": 7, "last_evidence": "2026-08-24", "weekly": [], "status": "active"},
  "关系": {"job": "重要的人还在，情感账户为正", "priority": 0.7, "prior": 0.8, "alpha": 3.2, "beta": 0.8, "score": 0.8, "streak": 1, "best_streak": 12, "last_evidence": "2026-08-25", "weekly": [], "status": "active"}
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

## 3. daily_log.json

```json
{"days": [{
  "date": "2026-08-25",
  "capture": {
    "done": ["交付了 A 方案", "陪爸妈吃了顿饭"],
    "undone": ["没去健身"],
    "worries": ["周末回家安排"]
  },
  "scores": {"工作/事业": 1, "健身": 0, "关系": 0.5},
  "next": {
    "main": "明天9:30前改完客户反馈，完成标准=发出修改版",
    "backup": ["下午处理数据表", "晚上散步 30 分钟"]
  },
  "energy": {"peak": "morning", "note": "下午犯困"},
  "mood": 7,
  "completed": true
}]}
```

- `capture`：三栏捕获原文；随手记（§2）也追加到这里。
- `scores`：当天评分过的领域；未涉及的领域不出现（无证据不更新）。
- `next`：今晚为明天排的行动；**第二天复盘时回填 `completed`**（主行动完成与否），这是"完成率"数据来源。
- `energy`：精力记录，用于推断精力高峰（连续 3 天相同时写回 profile）。
- `mood`：0-10 当天整体感受，**仅记录，不参与贝叶斯**（感受是弱证据）。
- 保留最近 90 天；更早的记录只保留聚合值（周均分）到 domains.weekly。

## 4. worries.json

```json
{"items": [
  {"id": "W-20260825-1", "text": "周末回家安排", "added": "2026-08-25", "earliest": "2026-08-28", "status": "open"}
]}
```

- 晚间复盘把担心写入（含"最早处理时间"），**今晚不再想它**。
- `earliest` 之前的担心在复盘时不重复提出；每周复盘清理 `status=done` 的条目并检查未处理的。

## 5. evolution.json

```json
{"version": "v1.0.0", "history": [
  {"version": "v1.0.0", "date": "2026-08-26", "changelog": ["初始版本"]}
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
| 明日主行动 | 从"未完成 × 在意程度 × 明早精力"里选，不按任务清单长度；写不出完成标准 → 缩小 |
| 精力排期 | energy.peak 连续 3 天相同 → 写回 profile，主行动优先排该时段 |
| 周报趋势 | 对比 weekly 最近 3 周 avg：上升/持平/下降；连续下降 3 周 → 自进化 #3（JTBD 重访谈） |

## 自进化判定细节（对应 SKILL.md §6）

| # | 判定 | 备注 |
|---|---|---|
| 1 | 某领域 status=active 且 last_evidence 距今 ≥14 天 | 提议封存；用户拒绝则重置计时 |
| 2 | 同一 `next.main` 模板连续 3 次 completed=false | 按完成标准缩小为 30 分钟一步 |
| 3 | score < 0.3 且连续 2 周（weekly 最近 2 周 avg < 0.3） | 提议 JTBD 重访谈，不默认加码 |
| 4 | daily_log 连续 3 次复盘时刻 ≥23:00 | 提议把提醒提前到 21:30 |
| 5 | 用户说"以后别 X" | 立即写 profile.rules；不弹窗确认，直接生效 |
| 6 | 连续 3 次复盘耗时 >15 分钟 | 收紧协议：砍掉 3.1 或 3.2 一步 |

判定用**运行中的真实数据**，禁止凭空推断；单次偶发不触发（贝叶斯：先验不变，连续模式才更新）。
