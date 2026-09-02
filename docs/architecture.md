# 架构规格：gao-human-booster 项目化 + MDX 日档 + 长期性能 + 可选备份

> 本文件是数据契约。实现者（build 脚本 / HTML 壳 / SKILL 流程 / backup 脚本）必须以本文件为准，
> 三者对同一字段的读写必须一致。

## 1. 总体目标

1. **容易初始化**：新机器一条命令 `make init`（或 `python3 scripts/init.py`）就能建好 state、daily、装好 skill 符号链接、生成日历。状态模板、路径解析、安装脚本齐备。
2. **MDX 日档为唯一数据源**：逐日记录与计划统一为 `daily/YYYY-MM-DD.mdx`（每天一份、按日期命名）。**未来计划 + 当日总结 + 情报补给 + 推荐在同一份文件里**。`daily/` 是 source of truth，`data/` + `progress-calendar.html` 是构建产物。`make build` 每次复盘后必跑（幂等 <1s），从根上解决"昨天总结没落到 HTML"。
3. **长期性能**：日历为「**壳页面 + 数据文件**」：
   - `progress-calendar.html`：静态壳，只含 CSS/JS（体积恒定，约 15KB）。
   - `data/index.js`：汇总（领域后验、各月存在性、计划总数、版本）。约 1–2KB。
   - `data/YYYY-MM.js`：单月数据（`window.DATA['YYYY-MM'] = {...}`），每文件约 1–4KB，浏览器**按需加载**。
   - 渲染只取当前月起最近 12 个月 + 未来 6 个月；历史月仍可在日历里翻看（按月懒加载）。
4. **开挂引擎（第五框架）**：复利 × 杠杆 × 情报 × 极致。复利盘点进周复盘；情报补给进每日复盘（基于 profile.interests 联网检索）；推荐库（library.json）防重复推荐并跟进；**极致引擎（构建时自动计算）**：重复行动模板识别（归一化指纹）→ ⚡第 N 次标记 → 完成率前后对比产出"越做越轻松"信号，供周复盘极致审计（模板化/自动化/砍掉三判）。
5. **增益系统（正向 buff）**：构建时按天自动推导 4 个 buff（连击🔥/动能🌊/回血🔋/复利⚡），优先级 recovery > momentum > streak > mastery，一天最多 1 个，未来日期不授予；出口为 `GHB.buff`（今日）与 `days[].buff`（历史）。只顺风加量、低谷减负，不追加义务。
6. **可选 GitHub 备份**：`make backup-init REMOTE=<url>` 启用后，`daily/` + `state/` 镜像到独立的本地备份仓库（`~/.agents/ghb-backup`）并推送到用户指定的 GitHub 私有仓库。**默认关闭，非必选**。

## 2. 目录布局

```
gao-human-booster/
├── SKILL.md                      # skill 主文档（更新流程）
├── README.md                     # 给新用户：如何初始化/构建/备份
├── Makefile                      # init / build / install / clean / backup(可选)
├── .gitignore                    # daily/ state/ data/ progress-calendar.html 不入库
├── docs/
│   └── architecture.md           # 本文件
├── references/
│   ├── state-model.md            # daily/*.mdx 格式 + state schema + 贝叶斯 + 自进化 + 备份
│   └── calendar-integration.md
├── daily/                        # ★ 逐日记录 + 计划唯一数据源（MDX，git 忽略）
│   └── YYYY-MM-DD.mdx            #   今日计划 + 今日总结 + 情报补给 + 推荐
├── state/                        # 运行时数据（git 忽略；init.py 从 state.example 引导）
│   ├── profile.json              # 画像 + 兴趣方向 + 硬规则 + 提醒
│   ├── domains.json              # 领域 + 贝叶斯后验（核心）
│   ├── worries.json              # 担心箱
│   ├── library.json              # 推荐库（书/电影，防重复）
│   ├── backup.json               # 可选备份配置（默认关闭）
│   └── evolution.json            # 版本与升级日志
├── state.example/                # 模板（可入 git）：建 state 用的最小合法结构
├── data/                         # 构建产物（git 忽略）
│   ├── index.js
│   └── YYYY-MM.js
├── scripts/
│   ├── init.py                   # 一键初始化（bootstrap + daily/ + 可选 install + build）
│   ├── build_calendar.py         # 读 daily/*.mdx + state/ → 写 data/ + progress-calendar.html
│   └── backup.py                 # 可选：镜像 daily/ + state/ → 独立仓库 → push
├── icons/                        # Feather 图标源（构建时内联为 sprite）
└── vendor/                       # html2canvas.min.js（CDN 回退源，保留）
```

**运行时数据位置**：skill 可能安装到 `~/.agents/skills/gao-human-booster`（符号链接或拷贝）。
`daily/`、`state/`、`data/` 的解析优先级（build/init 通用）：

1. `--state DIR` 命令行参数（daily/data 取 `DIR/../daily`、`DIR/../data`）；
2. 环境变量 `GHB_STATE`；
3. 仓库本地 `./state`（开发模式，默认）；
4. 安装位置 `~/.agents/skills/gao-human-booster/state`（若存在）。

## 3. 数据层

### 3.1 daily/*.mdx（source of truth）

每天一份，按日期命名，内容 = **今日计划（复选列表）+ 今日总结（完成/未完成/担心/领域评分/明日行动/情报补给/推荐）**。未来计划直接写进目标日期文件（不存在就创建）。完整格式与解析规则见 `references/state-model.md §3`。前端弹层显示「情报补给」「推荐」区块。

### 3.2 state/ JSON

- `profile.json`：含 `interests`（情报雷达）。
- `domains.json`：贝叶斯后验（不变）。
- `worries.json`：担心箱（不变）。
- `library.json`：推荐库（推荐过/在读/已读），防重复推荐 + 跟进。
- `backup.json`：`{remote, enabled, last_push}`，由 backup.py 读写，默认 `enabled:false`。
- `evolution.json`：版本日志（不变）。

### 3.3 state.example/

init.py 若发现 state 缺失，用 `state.example/*.json` 模板初始化（不含 daily_log/plans——已由 daily/*.mdx 取代）。**不包含任何个人数据**。

## 4. 数据层（data/）

### 4.1 `data/index.js`（约 1–2KB）

```js
window.GHB = {
  "version": "v1.2.0",
  "name": "",
  "role": "",
  "months": ["2026-08"],
  "current": "2026-08",
  "today": "2026-08-29",
  "domains": { "工作/事业": {score:0.517, streak:2, best:2, color:"#c05b24", job:"...", status:"active"}, ... },
  "plans": {"2026-08-29": [ {id, text, kind, domain, done} ]},  // 只含 today 起 14 天内 && 未完成 && kind!=backup（页首横幅用）
  "worries_open": 1,
  "buff": "streak",          // 今日 buff（null=无）：streak|momentum|recovery|mastery
  "mastery": [ {"label":"...","count":5,"doneRate":0.8,"easing":true,"domain":"...","last":"..."} ],  // 极致行动榜 Top3
  "meta": {"generated": "2026-08-29", "total_days": 3}
}
```

- `months` 升序，供月份下拉与"跳到最近月"。
- `domains` 是**当前**后验（非历史的）。
- `plans` 仅页首横幅需要：未来 14 天未完成计划（含今日）。

### 4.2 `data/YYYY-MM.js`（约 1–4KB/月）

```js
window.DATA = window.DATA || {};
window.DATA["2026-08"] = {
  "year": 2026, "month": 8,
  "days": {
    "2026-08-27": {"capture": {"done":[...],"undone":[...],"worries":[...]}, "scores": {...}, "next": {...}, "mood": 7, "completed": true, "intel": [...], "recs": [...], "buff": "streak"}
  },
  "plans": {
    "2026-08-28": [ {"id":"P-...","text":"...","kind":"main","domain":"工作/事业","done":false,"reps":3,"rep_total":5} ]
  },
  "mastery": [ {"label":"...","count":5,"doneRate":0.8,"easing":true,"domain":"...","last":"..."} ]
};
```

- `days`：该月内所有有记录的日子（key=date）。`intel`/`recs` 为该日情报补给与推荐（弹层/导出卡显示）；`buff` 为该日生效的增益。
- `plans`：**该月内所有计划**（含已完成/已过期），按 date 分组；`reps`/`rep_total` 为极致引擎的重复标记（reps≥2 时弹层显示 ⚡第 N 次）。
- `mastery`：极致行动榜 Top3（重复行动 + 完成率 + easing「越做越轻松」信号）。
- 渲染时按"当月 1 号往前推 11 个月"作为加载范围（共 12 个月）。未来只允许翻到**当月 + 6 个月**。

### 4.3 构建规则（build_calendar.py）

- 读全部 `daily/*.mdx`（解析器见 `references/state-model.md §3`）+ `state/*.json`，生成 `data/index.js`、当月起最近 12 个月的 `data/YYYY-MM.js`，以及 `progress-calendar.html`（壳）。
- **首次 build 自动迁移**：若 `daily/` 为空但存在旧 `state/daily_log.json` / `plans.json` → 转成 MDX（"明天…"且 date==created 的计划自动顺延一天，修正 off-by-one）→ 迁移成功后删除两个旧 JSON。
- 幂等：重复运行结果一致；不删除用户没引用的旧 data 文件（构建只写，不清理——避免误删）。
- 用 Python 标准库（json/datetime/calendar/re），无第三方依赖。

## 5. 前端壳（progress-calendar.html）

### 5.1 加载与渲染

- `window.DATA` 累积：`<script src="data/index.js"></script>` + 动态 `<script src="data/YYYY-MM.js">`（`onload` 触发 `render(month)`）。
- 初始：打开 index 里 `current` 月；若今天所在月不在 `months` 里，回退到 `months[last]`。
- 月份导航：`‹ ›` 按钮 + 下拉 `<select>`（选项 = `months` + 未来 6 个月）。

### 5.2 卡片（格子）渲染

1. **复盘卡**：有记录的日子 → 评分条/完成/未完成/心情点。
2. **计划卡**：该日有 `plans` → 计划条目（勾选 `- [x]` 已完成淡化、过期红色）。
3. **今日高亮**：今天的格子 gold 边框；有未完成计划 → 页首横幅"今日计划"。

### 5.3 弹层（点格子）

- **单列纵向排版**：完成 → 未完成 → 担心/情绪 → 领域评分 → 情报补给 → 推荐 → 专家点评 → 计划 → 明日行动 → 完成回填，自上而下（v1.2 起弃用双栏 `.rc-cols`）。
- 今日弹层在「明日行动」下方显示 buff 行（增益说明）；计划条目重复 ≥2 次显示 `⚡第N次` 标记。
- 计划卡 → 计划区（完成状态由晚间复盘回填，弹层内注明）。

### 5.4 导出图片

保留 html2canvas 每日卡导出；**导出卡同样单列纵向**（完成/未完成/担心为独立区块，v1.2 起弃用三栏 `.ex-cols`）；含情报补给/推荐摘要与今日 buff（若有）。

### 5.5 其它保留

领域联动高亮、今日 ribbon、木刻纸纹理、图标 sprite（构建时内联进壳）。页脚注明"数据仅本机 / 重新生成：make build"。

## 6. 构建 / 初始化 / 备份流程

### 6.1 `scripts/init.py`（幂等，可重复跑）

```
用法: python3 scripts/init.py [--state DIR] [--install] [--build] [--force]
```
1. 解析数据位置（见 §2 优先级）。
2. 若 state 缺失：从 `state.example/` 复制模板创建；已存在 → 跳过（除非 `--force`）。
3. 创建 `daily/` 目录。
4. `--install`：在 `~/.agents/skills/gao-human-booster` 创建符号链接（已存在则更新）。
5. `--build`（默认开）：调 `scripts/build_calendar.py`。
6. 输出欢迎信息与下一步指引。

### 6.2 `Makefile`

```make
init:   # python3 scripts/init.py
build:  # python3 scripts/build_calendar.py
install:# python3 scripts/init.py --install --no-build
backup-init:# python3 scripts/backup.py init "$(REMOTE)"   # 可选
backup: # python3 scripts/backup.py push                  # 可选
backup-status:# python3 scripts/backup.py status
clean:  # 只删 data/ 和 progress-calendar.html（绝不删 state/ 与 daily/）
```

### 6.3 可选备份（scripts/backup.py）

- `init <REMOTE>`：建 `~/.agents/ghb-backup` 独立 git 仓库 → add origin → 写 `state/backup.json`（enabled=true）→ 首次推送。
- `push`：镜像 `daily/` + `state/` 到备份仓库 → `git add -A` → commit（`backup YYYY-MM-DD HH:MM`）→ `push origin main`；无变化跳过。
- `status`：查看配置与上次推送。
- 复盘完成后若 `backup.json.enabled` → 自动 `make backup`；失败只提示不阻塞。

### 6.4 git 策略

- `.gitignore`：`daily/`、`state/`、`data/`、`progress-calendar.html`（个人数据与构建产物不入库）。
- 保留 `state.example/`、`scripts/`、`Makefile`、`icons/`、`vendor/`、`references/`、`docs/`、`SKILL.md`、`README.md`。

## 7. SKILL 流程变更

### 7.1 初始化（§1）

STEP 0 前检查 `make init` 是否跑过（`daily/` 或 `state/domains.json` 存在）。未初始化 → 引导 → 建档（含**兴趣方向**收集）→ 日历提醒配置。备份为可选，默认不启用。

### 7.2 晚间复盘（§3）

- **§3.0 今日计划检查**：读今天 MDX 的「今日计划」→ 完成勾 `- [x]`，未完成进"未完成"栏。
- **§3.3 明日唯一行动**：写今天 MDX「明日行动」**同时**创建/更新明天 MDX「今日计划」。优先复利行动。
- **§3.4 情报补给**：基于 `profile.interests` + 当天复盘，联网检索 ≤1 条相关资讯/洞见写入今日 MDX「情报补给」；离线/无结果跳过。担心箱 + 今日卡 + `make build`（已启用备份则 `make backup`）。

### 7.3 明日规划（§4）

写目标日期 MDX「今日计划」区 → `make build`。保持"1 主 + ≤2 备选"。

### 7.4 周复盘（§5）

- 下周计划 → 写进下周各天 MDX。
- **复利盘点**（开挂审计）：本周哪些投入变成了资产？什么杠杆被忽略？→ 下周一个复利目标。
- **推荐补给**：推荐 1 书/1 影写入本周某天 MDX「推荐」+ `library.json`。

### 7.5 同步（所有写计划/复盘的动作后）

统一约定：**每次写 daily/*.mdx 后调用 `make build`**；备份启用则追加 `make backup`。

### 7.6 自进化（§6）

新增 #8：library 推荐 2 周无反馈 → 周复盘追问。

### 7.7 状态目录（§7）

已更新为 daily/ + state/（含 library.json、backup.json），见 SKILL.md §7。

## 8. 迁移（老用户）

- 旧 `state/daily_log.json` + `state/plans.json` → 首次 `make build` 自动迁移为 `daily/*.mdx`（见 §4.3），迁移完成后删除旧 JSON。
- 旧 `progress-calendar.html` 会被新壳覆盖（git 不再跟踪，本地自动更新）。

## 9. 性能与隐私

- **性能**：壳 ~15KB 恒定；单月数据 ~1–4KB；12 个月全量 ~50KB，且**只加载用户正在看的月**。DOM 只渲染当前月（28–31 卡片）。
- **隐私**：daily/ 与 state/ 仅本机；data/ 为派生物同样本机。**备份为可选**，仅用户主动 `make backup-init` 后才把数据推送到其指定的 GitHub 私有仓库。
- **删除**：`make clean` 只删构建产物（data/、progress-calendar.html），**绝不删 daily/ 与 state/**。删除数据需手动 `rm -rf`，README 警告。
