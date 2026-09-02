# gao-human-booster

> 一个**陪伴式人生维护引擎**：不是时间管理软件，不是打卡机，而是一个跨会话记住你的画像、领域后验与连续天数的"外置操作系统"。
> 核心：每天 23:00 前 10 分钟晚间复盘，周日 20 分钟收敛，其余时间零打扰。**开挂引擎**：复利 × 杠杆 × 情报 × 极致，让每次投入都产生复利。
> **极致引擎**：重复做的事自动标 ⚡第 N 次，越做越轻松才是对的——「越做越累」触发模板化/自动化/砍掉三判。**增益系统**：连击🔥/动能🌊/回血🧵/复利⚡ 四个正向 buff 自动推导，顺风加量、低谷减负。

## 快速开始

### 前提

- Python 3.8+
- 支持 skill 的 AI 客户端（Claude Code / opencode 等）

### 安装

```bash
# 1. 克隆仓库
git clone <repo-url> ~/gao-human-booster
cd ~/gao-human-booster

# 2. 一键初始化（生成 state/ + daily/）
make init

# 3. 安装 skill 符号链接（可选，让 skill 客户端能找到）
make install

# 4. 生成日历看板
make build
```

初始化后，在 AI 客户端中调用 skill 后说 **"开始建档"**（一次问齐：身份 / **兴趣方向** / 领域 / 先验 / 提醒）。

### 日常使用

```bash
make build        # 每次复盘/更新计划后同步日历（幂等 <1s）
```

或直接：`python3 scripts/build_calendar.py`

## 项目结构

```
gao-human-booster/
├── SKILL.md                    # skill 主文档（流程规范）
├── Makefile                    # init / build / install / clean / backup(可选)
├── scripts/
│   ├── build_calendar.py       # 日历构建器（daily/*.mdx → data + HTML）
│   ├── init.py                 # 一键初始化
│   └── backup.py               # 可选：备份到 GitHub
├── daily/                      # ★ 逐日记录 + 计划（MDX，每天一份，按日期命名）
│   └── YYYY-MM-DD.mdx          #   今日计划 + 今日总结 + 情报补给 + 推荐
├── state/                      # ★ 运行时数据（git 忽略，本机保存）
│   ├── profile.json            # 用户画像 + 兴趣方向
│   ├── domains.json            # 领域定义 + 贝叶斯后验（核心）
│   ├── worries.json            # 担心箱
│   ├── library.json            # 推荐库（书/电影）
│   ├── backup.json             # 可选备份配置
│   └── evolution.json          # 版本与升级日志
├── state.example/              # 模板（可入 git）
├── data/                       # 构建产物（git 忽略）
│   ├── index.js                # 索引（领域后验/月份列表）
│   └── YYYY-MM.js              # 按月数据（按需加载）
├── references/
│   ├── state-model.md          # daily/*.mdx 格式 + state schema + 贝叶斯算法
│   └── calendar-integration.md # 每晚提醒（Apple 日历 / .ics / crontab）
├── icons/  vendor/  docs/
└── .gitignore
```

## 生命周期

1. **初始化** → `make init` → 建档访谈（身份 / 兴趣方向 / 领域 / 先验 / 提醒）
2. **白天随手记** → 30 秒记录，不打断
3. **晚间复盘**（核心）→ 10 分钟闭环：三栏捕获 → 领域打分 → 贝叶斯更新 → 明日行动（写明天 mdx）→ 情报补给 → 担心箱
4. **周复盘** → 周日 20 分钟：数据汇总 → 下周主题 → 复利盘点 → 推荐 1 书/1 影 → 自进化检查
5. **同步日历** → `make build` → `data/` 增量更新，按月懒加载

## 数据存储（MDX 日档）

- **每天一份 `daily/YYYY-MM-DD.mdx`**，按日期命名；**未来计划 + 当日总结 + 情报补给 + 推荐都在同一份文件里**。
- 计划写进目标日期的 mdx（没有就先创建）；复盘总结追加到当天 mdx。
- MDX 是唯一数据源；`data/` 与 `progress-calendar.html` 只是构建产物（`make build` 生成）。

## 开挂引擎（复利 × 杠杆 × 情报）

- **复利**：把时间投进会自动增值的资产（技能/作品/关系/健康），避开纯消耗；明日行动优先选"复利行动"。
- **杠杆**：AI/工具、内容/作品、网络、自动化/系统——一次性投入，长期放大。
- **情报**：每晚基于你的 `profile.interests` 推送 1 条相关资讯/洞见（联网检索）；每周按生活主题推荐 1 本书/1 部电影（记入 library.json，防重复）。

## 可选备份（GitHub）

数据默认只存本机。想要异地备份，**自己建一个 GitHub 私有仓库**（空的即可），然后：

```bash
make backup-init REMOTE=git@github.com:你的用户名/备份仓库名.git   # 启用（一次性）
make backup        # 手动备份；启用后每次复盘完也会自动备份
make backup-status # 查看配置
```

- 备份内容：`daily/` + `state/`（含担心箱等全部个人数据——**请务必用私有仓库**）。
- 备份仓库与本 skill 代码仓库完全分离；本 skill 的代码不会进入备份仓库。
- 关闭备份：把 `state/backup.json` 的 `enabled` 改为 `false`。

## 数据隐私

- 所有数据默认仅存本机 `daily/` + `state/`，不自动外发。
- `daily/`、`state/` 和 `data/` 被 `.gitignore` 排除，不会意外提交。
- 备份是**可选能力**：仅当用户主动 `make backup-init` 后才推送到用户指定的仓库。
- 删除：`make clean` 只删构建产物；删除全部数据需手动 `rm -rf daily/ state/`。

## 性能

- 壳页面 ~15KB 恒定；按月数据文件 ~1-4KB 每个，浏览器按需加载；长期 5 年数据无感。

## 许可

MIT
