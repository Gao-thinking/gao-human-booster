#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gao-human-booster 日历构建器
读取 state/ → 生成 data/ 按月数据 + progress-calendar.html 壳
用法:
  python3 scripts/build_calendar.py
  python3 scripts/build_calendar.py --state /path/to/state
  python3 scripts/build_calendar.py --inline    # 单文件模式（全内嵌，可直接分享单文件）
"""
import argparse, datetime, json, calendar as _cal, html, os, re
from pathlib import Path

# ── 路径解析 ──────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
STATE_DIR = REPO_DIR / "state"
DATA_DIR = REPO_DIR / "data"
ICONS_DIR = REPO_DIR / "icons"
OUT_HTML = REPO_DIR / "progress-calendar.html"

INSTALL_STATE = Path.home() / ".agents" / "skills" / "gao-human-booster" / "state"

TODAY = datetime.date.today()


def resolve_state():
    """解析 state 位置，优先级：--state > GHB_STATE > 本地 > 安装位置"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default=None, help="state 目录路径")
    parser.add_argument("--inline", action="store_true", default=False, help="单文件模式（全内嵌）")
    args = parser.parse_args()
    if args.state:
        state = Path(args.state).resolve()
    elif os.environ.get("GHB_STATE"):
        state = Path(os.environ["GHB_STATE"]).resolve()
    elif STATE_DIR.exists():
        state = STATE_DIR.resolve()
    elif INSTALL_STATE.exists():
        state = INSTALL_STATE
    else:
        state = STATE_DIR.resolve()
    return state, args.inline


def data_dir_for(state: Path) -> Path:
    """data 目录永远与 state 同级的兄弟"""
    return state.parent / "data"


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


# ── 图标精灵 ──────────────────────────────────────────────────────────────
def build_sprite():
    syms = []
    if not ICONS_DIR.exists():
        return ""
    for f in sorted(ICONS_DIR.glob("*.svg")):
        name = f.stem
        raw = f.read_text(encoding="utf-8")
        start = raw.find(">") + 1
        end = raw.rfind("</svg>")
        content = raw[start:end].strip()
        syms.append(
            f'<symbol id="i-{name}" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round">{content}</symbol>'
        )
    return ('<svg xmlns="http://www.w3.org/2000/svg" style="display:none" '
            'aria-hidden="true"><defs>' + "".join(syms) + "</defs></svg>")


DOMAIN_COLORS = {
    "工作/事业": "#c05b24",
    "追求": "#2e7d5b",
    "健身": "#d64541",
    "关系": "#7a5ba6",
}


# ── MDX 日档解析 ─────────────────────────────────────────────────────────
SECTION_ALIASES = {
    "完成": "done",
    "未完成": "undone",
    "担心": "worries",
    "担心 / 情绪": "worries",
    "担心/情绪": "worries",
    "领域评分": "scores",
    "明日行动": "next",
    "情报补给": "intel",
    "推荐": "recs",
}

PLAN_KINDS = {"主行动": "main", "备选": "backup", "事件": "event", "计划": "plan"}


def resolve_daily_dir(state_path: Path) -> Path:
    return state_path.parent / "daily"


def _split_plan_text(raw: str):
    """- [ ] 主行动｜工作/事业：xxx → (kind, domain, text)"""
    raw = raw.strip()
    kind, domain, text = "plan", "", raw
    if "｜" in raw:
        head, rest = raw.split("｜", 1)
        kind = PLAN_KINDS.get(head.strip(), "plan")
        if "：" in rest:
            domain, text = rest.split("：", 1)
        else:
            text = rest
    elif "：" in raw:
        head, text = raw.split("：", 1)
        kind = PLAN_KINDS.get(head.strip(), "plan")
    return kind, domain.strip(), text.strip()


def _parse_score_line(raw: str):
    """- 工作/事业：1 — 依据 → (name, score, basis)"""
    raw = raw.strip()
    if "：" not in raw:
        return None
    name, rest = raw.split("：", 1)
    m = re.match(r"^\s*(\d+(?:\.\d)?)\s*[—\-:：]?\s*(.*)$", rest)
    if not m:
        return None
    val = float(m.group(1))
    r = 1.0 if val >= 0.75 else (0.5 if val >= 0.25 else 0.0)
    return name.strip(), r, m.group(2).strip()


def parse_frontmatter(text: str):
    meta = {}
    if not text.startswith("---"):
        return meta, text
    end = text.find("\n---", 3)
    if end == -1:
        return meta, text
    block = text[3:end]
    rest = text[end + 4:]
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, rest


def parse_mdx(path: Path):
    text = path.read_text(encoding="utf-8")
    meta, rest = parse_frontmatter(text)
    date = meta.get("date", path.stem)
    mood = meta.get("mood")
    try:
        mood = int(mood) if mood is not None else None
    except (ValueError, TypeError):
        mood = None
    energy_note = meta.get("energy", "")

    day = {
        "date": date,
        "capture": {"done": [], "undone": [], "worries": []},
        "scores": {},
        "next": {},
        "energy": {"note": energy_note} if energy_note else {},
        "mood": mood,
        "completed": None,
        "intel": [],
        "recs": [],
    }
    plans = []

    lines = rest.splitlines()
    cur_h2 = None
    cur_h3 = None
    for line in lines:
        m = re.match(r"^#{2}\s+(.*)$", line)
        if m:
            cur_h2 = m.group(1).strip()
            cur_h3 = None
            continue
        m = re.match(r"^#{3}\s+(.*)$", line)
        if m:
            cur_h3 = m.group(1).strip()
            continue
        if cur_h2 == "今日计划":
            m = re.match(r"^\s*-\s+\[([ xX])\]\s*(.*)$", line)
            if m:
                done = m.group(1).strip().lower() == "x"
                kind, domain, text = _split_plan_text(m.group(2))
                if text:
                    plans.append({"kind": kind, "domain": domain, "text": text, "done": done})
            continue
        if cur_h2 == "今日总结":
            key = SECTION_ALIASES.get(cur_h3)
            if not key:
                continue
            m = re.match(r"^\s*-\s+(.*)$", line)
            if not m:
                continue
            item = m.group(1).strip()
            if not item:
                continue
            if key == "done":
                day["capture"]["done"].append(item)
            elif key == "undone":
                day["capture"]["undone"].append(item)
            elif key == "worries":
                day["capture"]["worries"].append(item)
            elif key == "scores":
                parsed = _parse_score_line(item)
                if parsed:
                    name, r, _ = parsed
                    day["scores"][name] = r
            elif key == "next":
                if item.startswith("主行动"):
                    day["next"]["main"] = item.split("：", 1)[-1].strip()
                elif item.startswith("备选"):
                    day["next"].setdefault("backup", []).append(item.split("：", 1)[-1].strip())
            elif key == "intel":
                day["intel"].append(item)
            elif key == "recs":
                day["recs"].append(item)

    mains = [p for p in plans if p["kind"] == "main"]
    if mains:
        day["completed"] = all(p["done"] for p in mains)
    return day, plans


def load_daily_mdx(daily_dir: Path):
    days = {}
    plans_by_date = {}
    if not daily_dir.exists():
        return days, plans_by_date
    for f in sorted(daily_dir.glob("????-??-??.mdx")):
        try:
            day, plist = parse_mdx(f)
        except Exception:
            continue
        date = day["date"]
        days[date] = day
        if plist:
            items = []
            for i, p in enumerate(plist, 1):
                items.append({
                    "id": f"P-{date.replace('-', '')}-{i}",
                    "date": date,
                    "text": p["text"],
                    "kind": p["kind"],
                    "domain": p["domain"],
                    "created": date,
                    "done": p["done"],
                    "done_on": date if p["done"] else None,
                })
            plans_by_date[date] = items
    return days, plans_by_date


# ── 迁移：旧 daily_log.json + plans.json → daily/*.mdx ──────────────────
def _common_len(a, b):
    """最长公共子串长度（短串用，迁移期一次性判定用）"""
    best = 0
    la, lb = len(a), len(b)
    for i in range(la):
        for j in range(lb):
            k = 0
            while i + k < la and j + k < lb and a[i + k] == b[j + k]:
                k += 1
            best = max(best, k)
    return best


def _plan_done_on_day(plan, day):
    """旧数据启发式：计划的完成标准文本与当天 done 列表有 ≥8 字公共子串 → 视为完成"""
    if not day:
        return False
    done_items = (day.get("capture") or {}).get("done", []) or []
    text = (plan.get("text") or "").strip()
    if text.startswith("明天"):
        text = text[2:].strip()
    for item in done_items:
        if not item:
            continue
        if _common_len(item, text) >= 8:
            return True
    return False


def _mig_write_mdx(daily_dir, date, d, plist):
    lines = ["---", f"date: {date}"]
    if d and d.get("mood") is not None:
        lines.append(f"mood: {d['mood']}")
    if d and d.get("energy", {}).get("note"):
        lines.append(f"energy: {d['energy']['note']}")
    lines.append("---")
    lines += ["", "## 今日计划", ""]
    if plist:
        for p in plist:
            kind_cn = {"main": "主行动", "backup": "备选", "event": "事件"}.get(p.get("kind"), "计划")
            dom = p.get("domain", "")
            prefix = kind_cn + ("｜" + dom if dom else "") + "："
            box = "x" if p.get("done") else " "
            lines.append(f"- [{box}] {prefix}{p.get('text', '')}")
    else:
        lines.append("（暂无计划）")
    if d and (d.get("capture") or d.get("scores") or d.get("next")):
        cap = d.get("capture", {}) or {}
        lines += ["", "## 今日总结", ""]
        for label, key in (("完成", "done"), ("未完成", "undone"), ("担心 / 情绪", "worries")):
            items = cap.get(key, []) or []
            if items:
                lines.append(f"### {label}")
                for it in items:
                    lines.append(f"- {it}")
        scores = d.get("scores", {}) or {}
        if scores:
            lines += ["", "### 领域评分", ""]
            for name, r in scores.items():
                lines.append(f"- {name}：{r}")
        nxt = d.get("next", {}) or {}
        if nxt.get("main") or nxt.get("backup"):
            lines += ["", "### 明日行动", ""]
            if nxt.get("main"):
                lines.append(f"- 主行动：{nxt['main']}")
            for b in nxt.get("backup", []) or []:
                lines.append(f"- 备选：{b}")
    (daily_dir / f"{date}.mdx").write_text("\n".join(lines) + "\n", encoding="utf-8")


def migrate_legacy_to_mdx(daily_dir: Path, state_path: Path):
    if daily_dir.exists() and any(daily_dir.glob("*.mdx")):
        return False
    daily_log = load_json(state_path / "daily_log.json", {"days": []})
    plans = load_json(state_path / "plans.json", {"items": []})
    if not daily_log.get("days") and not plans.get("items"):
        return False
    daily_dir.mkdir(parents=True, exist_ok=True)

    days_by_date = {d.get("date", ""): d for d in daily_log.get("days", []) if d.get("date")}
    plan_by_date = {}
    for p in plans.get("items", []):
        date = p.get("date", "")
        text = (p.get("text") or "").strip()
        if text.startswith("明天") and date == p.get("created", ""):
            try:
                date = (datetime.date.fromisoformat(date) + datetime.timedelta(days=1)).isoformat()
                text = text[2:].strip()  # 顺延后去掉"明天"
            except ValueError:
                pass
        p = dict(p)
        p["text"] = text
        if not p.get("done") and date in days_by_date:
            p["done"] = _plan_done_on_day(p, days_by_date[date])
        plan_by_date.setdefault(date, []).append(p)

    written = set()
    for d in daily_log.get("days", []):
        date = d.get("date", "")
        if not date:
            continue
        _mig_write_mdx(daily_dir, date, d, plan_by_date.get(date, []))
        written.add(date)
    for date, plist in plan_by_date.items():
        if date not in written and plist:
            _mig_write_mdx(daily_dir, date, None, plist)

    for name in ("daily_log.json", "plans.json"):
        p = state_path / name
        if p.exists():
            p.unlink()
    return True


# ── 领域牌数据 ────────────────────────────────────────────────────────────
def build_domains_payload(domains):
    payload = {}
    for name, dm in domains.items():
        payload[name] = {
            "score": round(dm.get("score", 0.5), 3),
            "streak": dm.get("streak", 0),
            "best": dm.get("best_streak", 0),
            "color": DOMAIN_COLORS.get(name, "#8a6d3b"),
            "job": dm.get("job", ""),
            "status": dm.get("status", "active"),
        }
    return payload


# ── 专家点评（规则引擎） ─────────────────────────────────────────────────
def expert_for_day(d, dom_payload):
    if not d:
        return None
    scores = d.get("scores", {}) or {}
    cap = d.get("capture", {}) or {}
    undone_text = " ".join(cap.get("undone", []))
    worry_text = " ".join(cap.get("worries", []))
    out = {}
    for name, r in scores.items():
        dm = dom_payload.get(name, {})
        color = dm.get("color", "#8a6d3b")
        if name == "工作/事业":
            coach = "事业教练"
            if "测试" in undone_text:
                text = "开发有推进但测试没闭环——测试是收尾动作，最容易被拖着。"
                tip = "明天上午第一件事就做它：全部功能过一遍、问题清单写下来，就算赢。"
            elif r == 1:
                text = "关键任务闭环了——'完成'是起步阶段最稀缺的能力。"
                tip = "明天把最难的事排在上午第一件，保持'先啃硬骨头'的节奏。"
            elif r == 0.5:
                text = "有推进但没闭环，卡点多半是'想一次做完'。"
                tip = "把剩余部分拆到 30 分钟能启动的一步，明天先做那一小块。"
            else:
                text = "今天没推进。一天没做只是噪声，不必自责。"
                tip = "明天 25 分钟最小启动：打开项目修一个 bug 就算赢。"
        elif name == "追求":
            coach = "语言教练"
            if r == 1:
                text = "超额的一天。但'学过'不等于'记住'。"
                tip = "明天花 5 分钟把学过的内容朗读一遍——说得出才算真会。"
            elif r == 0.5:
                text = "动了但打折。频率比时长重要。"
                tip = "把任务拆小：每天 20 分钟，比周末 3 小时有效得多。"
            else:
                text = "断了一天。断 3 天大脑就开始废弃连接。"
                tip = "明天 10 分钟：先保住连续。"
        elif name == "健身":
            coach = "健身教练"
            st = dm.get("streak", 0)
            if st >= 30 and r >= 0.5:
                text = f"连续 {st} 天——身体正在重写习惯回路，这个价值远大于单次强度。"
            elif r >= 0.5:
                text = "计划缩水但没取消，比'全不做'强 100 倍。"
            else:
                text = "今天没练。断一天是噪声，别让'完美'打败'连续'。"
            tip = "别追完美次数：明天 2 组就算进步，保住连续。"
            if ("脖子" in worry_text) or ("头晕" in worry_text):
                text += " 脖子酸痛+头晕是身体在报警：能量是一切输出的底层设施。"
                tip = "每 45 分钟起身拉伸 2 分钟；明天傍晚散步 20 分钟，比多练 1 组深蹲更值钱。"
        elif name == "关系":
            coach = "关系教练"
            text = "今天给关系账户充了值，继续保持这个主动。"
            tip = "关系是复利资产：明天再花 30 秒，给重要的人发一条消息。"
        else:
            coach = "教练"
            text = "继续推进。"
            tip = "明天保持节奏。"
        out[name] = {"coach": coach, "text": text, "tip": tip, "color": color}

    if not scores:
        out["__overall__"] = "建档日：系统已上线。第一课——不用做到完美，先做到连续。"
        return out
    if "关系" not in scores:
        out["关系"] = {
            "coach": "关系教练",
            "text": "今天没给关系账户充值——不评判，只提醒：它是复利资产，最容易'以为不重要'而断供。",
            "tip": "明天 30 秒：给家人或朋友发一条消息，成本为零。",
            "color": dom_payload.get("关系", {}).get("color", "#7a5ba6"),
        }
    vals = list(scores.values())
    avg = sum(vals) / len(vals)
    if avg >= 0.83:
        overall = "高能日：多线推进，注意别透支。明天挑一件收尾。"
    elif avg >= 0.5:
        overall = "平稳日：有推进有打折。明天的唯一行动，盯紧未完成的那件。"
    else:
        overall = "低能日：先保存能量，明天只做一件事，做完就赢。"
    out["__overall__"] = overall
    return out


# ── 按月数据生成 ─────────────────────────────────────────────────────────
def build_month_data(year, month, days, dom_payload, plans_by_date):
    month_days = {}
    for iso, d in days.items():
        try:
            dt = datetime.date.fromisoformat(iso)
        except ValueError:
            continue
        if dt.year == year and dt.month == month:
            month_days[iso] = {
                "capture": d.get("capture", {}),
                "scores": d.get("scores", {}),
                "next": d.get("next", {}),
                "mood": d.get("mood"),
                "completed": d.get("completed"),
                "intel": d.get("intel", []),
                "recs": d.get("recs", []),
            }
    month_plans = {}
    for iso, p_list in plans_by_date.items():
        if not p_list:
            continue
        try:
            dt = datetime.date.fromisoformat(iso)
        except ValueError:
            continue
        if dt.year == year and dt.month == month:
            month_plans[iso] = [{
                "id": p["id"],
                "text": p["text"],
                "kind": p["kind"],
                "domain": p.get("domain", ""),
                "done": p.get("done", False),
            } for p in p_list]
    return {
        "year": year,
        "month": month,
        "days": month_days,
        "plans": month_plans,
        "expert": {iso: expert_for_day(days.get(iso), dom_payload) for iso in month_days},
    }


# ═════════════════════════════════════════════════════════════════════════
# HTML 壳模板（CSS/JS 中的 { } 一律写成 {{ }}，Python 占位符用单花括号）
# ═════════════════════════════════════════════════════════════════════════
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>人生进度 · 木刻日历</title>
<style>
:root{{--paper:#f7ecd6;--paper-2:#efe0c2;--ink:#3b2a18;--ink-soft:#7a6242;--gold:#d9a441;--r:10px}}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{min-height:100%}}
body{{font-family:-apple-system,"PingFang SC","Microsoft YaHei","Noto Sans SC",sans-serif;color:var(--ink);background:radial-gradient(130% 100% at 50% 0%,rgba(0,0,0,0) 45%,rgba(20,10,3,.38) 100%),url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="520" height="520"><filter id="g"><feTurbulence type="fractalNoise" baseFrequency="0.0035 0.08" numOctaves="6" seed="11"/><feColorMatrix type="matrix" values="0 0 0 0 0.12 0 0 0 0 0.06 0 0 0 0 0.01 0 0 0 0.55 0"/></filter><rect width="520" height="520" filter="url(%23g)"/></svg>'),url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="520" height="520"><filter id="h"><feTurbulence type="turbulence" baseFrequency="0.02 0.004" numOctaves="3" seed="5"/><feColorMatrix type="matrix" values="0 0 0 0 1 0 0 0 0 0.96 0 0 0 0 0.82 0 0 0 0.05 0"/></filter><rect width="520" height="520" filter="url(%23h)"/></svg>'),linear-gradient(180deg,#7c512b 0%,#6b4426 55%,#57381d 100%);background-attachment:fixed;min-height:100vh;padding:30px 20px 60px}}
.board{{max-width:1240px;margin:0 auto}}
header{{text-align:center;margin-bottom:22px}}
.title{{font-family:"Songti SC","STSong","Noto Serif SC",serif;font-size:42px;font-weight:700;letter-spacing:8px;color:#f3e3c0;text-shadow:0 2px 0 #2c1a0b,0 4px 10px rgba(0,0,0,.6)}}
.sub{{margin-top:10px;color:#d8bd93;letter-spacing:2px;font-size:14px;text-shadow:0 1px 2px rgba(0,0,0,.5)}}
.ic{{width:1em;height:1em;display:inline-block;vertical-align:-.12em;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;flex:none}}
.ic-xs{{width:12px;height:12px;vertical-align:-.06em}}
.ic-sm{{width:15px;height:15px;vertical-align:-.1em}}
.ic-lg{{width:24px;height:24px;vertical-align:-.15em}}
.mdot{{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--mc);box-shadow:0 0 4px var(--mc);vertical-align:1px}}
.stats{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}}
.plaque{{flex:1;min-width:150px;background:linear-gradient(180deg,var(--paper),var(--paper-2));border-radius:var(--r);padding:12px 14px;position:relative;box-shadow:0 4px 0 rgba(0,0,0,.35),inset 0 1px 0 rgba(255,255,255,.55),inset 0 0 26px rgba(120,80,30,.10)}}
.plaque .p-name{{font-size:12px;color:var(--ink-soft);display:flex;justify-content:space-between;align-items:center}}
.plaque .p-dot{{width:8px;height:8px;border-radius:50%;background:var(--accent);box-shadow:0 0 6px var(--accent)}}
.plaque .p-score{{font-family:"Songti SC",serif;font-size:30px;font-weight:700;line-height:1.15}}
.plaque .p-bar{{height:6px;border-radius:3px;background:rgba(60,40,15,.14);margin-top:6px;overflow:hidden}}
.plaque .p-bar i{{display:block;height:100%;border-radius:3px;background:var(--accent,#8a6d3b)}}
.plaque .p-streak{{font-size:11px;color:var(--ink-soft);margin-top:5px;letter-spacing:.5px;display:flex;align-items:center;gap:4px}}
.plaque .p-streak-ic{{color:var(--accent)}}
.plaque.today-p{{--accent:var(--gold)}}
.plaque .mi{{color:var(--accent)}}
.p-nav{{display:flex;justify-content:center;align-items:center;gap:14px;margin-bottom:16px}}
.p-nav-btn{{background:rgba(0,0,0,.28);color:#e6cda0;border:none;border-radius:8px;padding:8px 16px;cursor:pointer;font-size:16px;transition:background .15s;line-height:1}}
.p-nav-btn:hover{{background:rgba(0,0,0,.45)}}
.p-nav select{{background:rgba(0,0,0,.28);color:#e6cda0;border:none;border-radius:8px;padding:8px 14px;font-size:15px;cursor:pointer;font-family:inherit;font-weight:700;letter-spacing:1px;text-align:center;appearance:auto}}
.p-nav select option{{background:#4a2e14;color:#e6cda0}}
.cal{{background:rgba(0,0,0,.24);border-radius:16px;padding:12px;box-shadow:inset 0 2px 10px rgba(0,0,0,.5),0 2px 0 rgba(255,255,255,.05)}}
.wd{{display:grid;grid-template-columns:repeat(7,1fr);gap:8px;margin-bottom:8px}}
.wd span{{text-align:center;font-size:12px;color:#e6cda0;letter-spacing:3px;padding:3px 0;text-shadow:0 1px 2px rgba(0,0,0,.6)}}
.grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:8px}}
.cell{{min-height:108px;border-radius:var(--r);position:relative;background:rgba(0,0,0,.28);box-shadow:inset 0 2px 6px rgba(0,0,0,.55),inset 0 0 0 1px rgba(255,255,255,.04);padding:6px;overflow:hidden}}
.cell .empty{{position:absolute;top:8px;right:12px;font-family:"Songti SC",serif;font-size:18px;color:rgba(230,205,160,.42)}}
.card{{height:100%;border-radius:8px;padding:9px 9px 7px;cursor:pointer;position:relative;background:url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="140" height="140"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="3"/><feColorMatrix type="matrix" values="0 0 0 0 0.5 0 0 0 0 0.38 0 0 0 0 0.22 0 0 0 0.07 0"/></filter><rect width="140" height="140" filter="url(%23n)"/></svg>'),linear-gradient(180deg,var(--paper),var(--paper-2));box-shadow:0 3px 5px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.6),inset 0 0 18px rgba(130,85,35,.12);transition:transform .22s ease,box-shadow .22s ease;animation:pop .5s cubic-bezier(.2,.9,.3,1.2) both;animation-delay:calc(var(--i)*26ms);overflow:hidden}}
@keyframes pop{{from{{opacity:0;transform:translateY(12px) scale(.96)}}to{{opacity:1;transform:none}}}}
.card:hover{{transform:translateY(-6px) rotate(-.6deg);z-index:3;box-shadow:0 14px 20px rgba(0,0,0,.55),inset 0 1px 0 rgba(255,255,255,.6)}}
.grid.dim .card{{opacity:.38;filter:saturate(.55)}}
.grid.dim .card.hit{{opacity:1;filter:none;box-shadow:0 6px 12px rgba(0,0,0,.55),0 0 0 2px var(--accent)}}
.tape{{position:absolute;top:-9px;left:50%;transform:translateX(-50%) rotate(-2deg);z-index:2;width:52px;height:16px;background:rgba(244,225,160,.55);box-shadow:0 1px 2px rgba(0,0,0,.25);border-radius:2px;border-left:1px dashed rgba(120,90,30,.35);border-right:1px dashed rgba(120,90,30,.35)}}
.c-top{{display:flex;justify-content:space-between;align-items:baseline}}
.c-date{{font-family:"Songti SC",serif;font-size:25px;font-weight:700;line-height:1}}
.c-flag{{font-size:11px;color:var(--ink-soft);letter-spacing:.5px;display:flex;align-items:center;gap:3px}}
.c-flag .flag-ic{{color:#d64541}}
.c-bar{{display:flex;gap:3px;height:7px;margin:8px 0 6px}}
.c-bar i{{flex:1;border-radius:3px;background:rgba(70,45,15,.14)}}
.c-bar i.f{{background:var(--seg)}}
.c-meta{{font-size:11px;color:var(--ink-soft);display:flex;justify-content:space-between;align-items:center}}
.c-meta .m-l{{display:flex;align-items:center;gap:3px;letter-spacing:.5px}}
.c-meta .mi{{color:#7a9b6a}}
.cell.today .card{{border:2px solid var(--gold);padding-top:27px;box-shadow:0 3px 6px rgba(0,0,0,.5),inset 0 0 18px rgba(130,85,35,.15)}}
.cell.today .card:hover{{box-shadow:0 14px 20px rgba(0,0,0,.55),0 0 0 2px var(--gold)}}
.cell.today .tape{{background:rgba(240,205,120,.75)}}
.ribbon{{position:absolute;top:0;right:0;z-index:2;background:var(--gold);color:#3a2a10;font-size:10px;font-weight:700;padding:2px 8px;border-radius:0 6px 0 9px;letter-spacing:1px;box-shadow:0 2px 3px rgba(0,0,0,.4);animation:glow 2.6s ease-in-out infinite}}
@keyframes glow{{0%,100%{{box-shadow:0 0 0 rgba(217,164,65,0)}}50%{{box-shadow:0 0 14px rgba(217,164,65,.85)}}}}

/* 计划卡 */
.p-plan{{margin-top:4px;border-top:1px dashed rgba(200,170,120,.4);padding-top:4px;font-size:10px;line-height:1.5;max-height:54px;overflow-y:auto;overflow-x:hidden;scrollbar-width:none;-ms-overflow-style:none}}
.p-plan::-webkit-scrollbar{{display:none}}
.p-plan-item{{display:flex;align-items:center;gap:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--ink-soft);cursor:pointer}}
.p-plan-item .p-dot{{width:5px;height:5px;border-radius:50%;flex:none}}
.p-plan-item .p-dot.main{{background:var(--gold);box-shadow:0 0 4px var(--gold)}}
.p-plan-item .p-dot.backup{{background:rgba(120,90,40,.35)}}
.p-plan-item .p-dot.plan{{background:rgba(120,90,40,.5)}}
.p-plan-item .p-dot.event{{background:#5b8db8}}
.p-plan-item.done{{opacity:.5;text-decoration:line-through}}
.p-plan-item.overdue .p-dot.main{{background:#c0392b;box-shadow:0 0 4px #c0392b}}
.p-plan-item.overdue{{color:#c0392b}}

/* 今日计划横幅 */
.today-banner{{max-width:1240px;margin:0 auto 14px;padding:10px 16px;background:rgba(217,164,65,.12);border:1px dashed rgba(217,164,65,.45);border-radius:10px;color:#e6cda0;font-size:13px;display:none;align-items:center;gap:10px;flex-wrap:wrap}}
.today-banner.show{{display:flex}}
.today-banner .tb-label{{font-weight:700;color:var(--gold);white-space:nowrap;letter-spacing:1px;display:flex;align-items:center;gap:5px}}
.today-banner .tb-item{{display:flex;align-items:center;gap:5px}}
.today-banner .tb-item .tb-dot{{width:6px;height:6px;border-radius:50%;flex:none}}
.today-banner .tb-item.done{{opacity:.5;text-decoration:line-through}}
.today-banner .tb-item .tb-dot.main{{background:var(--gold)}}
.today-banner .tb-item .tb-dot.backup{{background:rgba(200,170,120,.5)}}
.today-banner .tb-item .tb-dot.event{{background:#5b8db8}}
.today-banner .tb-item.overdue .tb-dot{{background:#c0392b}}

.legend{{display:flex;gap:18px;flex-wrap:wrap;justify-content:center;margin-top:16px}}
.legend span{{display:flex;align-items:center;gap:6px;font-size:12px;color:#d8bd93}}
.legend i{{width:10px;height:10px;border-radius:50%;background:var(--c);box-shadow:0 0 6px var(--c)}}
.legend .lp-dot{{width:5px;height:5px;border-radius:50%;display:inline-block}}
.legend .lp-dot.main{{background:var(--gold)}}
.legend .lp-dot.backup{{background:rgba(200,170,120,.5)}}
.legend .lp-dot.event{{background:#5b8db8}}
footer{{text-align:center;margin-top:22px;color:#b99a6b;font-size:12px;letter-spacing:1px;line-height:1.9}}
footer code{{font-family:monospace;background:rgba(0,0,0,.2);padding:1px 6px;border-radius:4px;font-size:11px}}

/* 弹层 */
.modal{{position:fixed;inset:0;display:none;align-items:center;justify-content:center;z-index:50;padding:20px}}
.modal.open{{display:flex}}
.overlay{{position:absolute;inset:0;background:rgba(18,9,3,.62);backdrop-filter:blur(3px)}}
.sheet{{position:relative;width:min(560px,94vw);max-height:88vh;overflow:auto;scrollbar-width:none;-ms-overflow-style:none;background:url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="140" height="140"><filter id="n2"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="3"/><feColorMatrix type="matrix" values="0 0 0 0 0.5 0 0 0 0 0.38 0 0 0 0 0.22 0 0 0 0.07 0"/></filter><rect width="140" height="140" filter="url(%23n2)"/></svg>'),linear-gradient(180deg,var(--paper),#f3e6ca);border-radius:14px;padding:22px 24px 20px;box-shadow:0 24px 60px rgba(0,0,0,.6),inset 0 1px 0 rgba(255,255,255,.7);transform:scale(.94);opacity:0;transition:transform .22s cubic-bezier(.2,.9,.3,1.3),opacity .18s}}
.modal.open .sheet{{transform:scale(1);opacity:1}}
.sheet::-webkit-scrollbar{{display:none}}
/* 打印机吐卡效果 */
.sheet-body{{position:relative}}
.sheet.printing .sheet-body{{clip-path:inset(0 0 100% 0);animation:print-reveal 1.15s steps(14,end) .05s forwards}}
.sheet.printing .sheet-body>.m-head,.sheet.printing .sheet-body>.sec,.sheet.printing .sheet-body>.completed{{animation:print-settle .28s ease-out both}}
.sheet.printing .sheet-body>.sec:nth-child(2){{animation-delay:.10s}}
.sheet.printing .sheet-body>.sec:nth-child(3){{animation-delay:.22s}}
.sheet.printing .sheet-body>.sec:nth-child(4){{animation-delay:.34s}}
.sheet.printing .sheet-body>.sec:nth-child(5){{animation-delay:.46s}}
.sheet.printing .sheet-body>.sec:nth-child(6){{animation-delay:.58s}}
.sheet.printing .sheet-body>.sec:nth-child(7){{animation-delay:.70s}}
.sheet.printing .sheet-body>.sec:nth-child(8){{animation-delay:.82s}}
.sheet.printing::after{{content:'';position:absolute;top:10px;left:50%;transform:translateX(-50%);width:62%;height:9px;background:rgba(43,28,12,.9);border-radius:5px;box-shadow:0 2px 5px rgba(0,0,0,.35),inset 0 -2px 0 rgba(0,0,0,.45);z-index:3;pointer-events:none;animation:print-slot 1.3s ease .05s both}}
.modal.open .sheet.printing{{animation:print-jitter .13s linear 10}}
.m-btn.off{{opacity:.45}}
@keyframes print-reveal{{to{{clip-path:inset(0 0 -10px 0)}}}}
@keyframes print-settle{{from{{transform:translateY(-5px);opacity:.4}}to{{transform:none;opacity:1}}}}
@keyframes print-jitter{{0%,100%{{transform:scale(1) translateY(0)}}50%{{transform:scale(1) translateY(1px)}}}}
@keyframes print-slot{{0%,80%{{opacity:1}}100%{{opacity:0}}}}
@media (prefers-reduced-motion: reduce){{.sheet.printing .sheet-body{{animation:none;clip-path:none}}.sheet.printing .sheet-body>.m-head,.sheet.printing .sheet-body>.sec,.sheet.printing .sheet-body>.completed{{animation:none}}.sheet.printing::after{{display:none}}.modal.open .sheet.printing{{animation:none}}}}
.m-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;padding-right:6px}}
.m-actions{{display:flex;gap:8px;align-items:center;flex:none}}
.m-btn{{border:none;cursor:pointer;display:inline-flex;align-items:center;gap:5px;background:rgba(90,60,25,.12);color:var(--ink);font-size:12px;border-radius:8px;padding:6px 9px;transition:background .15s;line-height:1}}
.m-btn:hover{{background:rgba(90,60,25,.25)}}
.m-btn .ic{{width:13px;height:13px}}
.m-close{{width:30px;height:30px;border-radius:50%;justify-content:center;padding:0}}
.m-close .ic{{width:13px;height:13px}}
.m-date{{font-family:"Songti SC",serif;font-size:22px;font-weight:700;letter-spacing:1px}}
.m-wd{{font-size:13px;color:var(--ink-soft);margin-top:4px;display:flex;align-items:center;gap:8px}}
.sec{{margin-top:14px}}
.sec h4{{font-size:13px;letter-spacing:2px;color:var(--ink-soft);border-bottom:1px solid rgba(120,85,40,.25);padding-bottom:5px;margin-bottom:8px;display:flex;align-items:center;gap:6px}}
.lst{{list-style:none}}
.lst li{{padding:3px 0;font-size:14px;line-height:1.55;color:var(--ink);display:flex;gap:7px;align-items:baseline}}
.lst li .ic{{flex:none;transform:translateY(1px)}}
.lst.done .ic{{color:#2e7d5b}}
.lst.undone .ic{{color:#c0392b}}
.lst.worry .ic{{color:#b59a5a}}
.none{{font-size:13px;color:#a08a64;font-style:italic}}
.srow{{display:flex;align-items:center;gap:10px;margin:6px 0}}
.sname{{width:64px;font-size:12px;color:var(--ink-soft);flex:none}}
.sbar{{flex:1;height:9px;border-radius:5px;background:rgba(60,40,15,.14);overflow:hidden}}
.sbar i{{display:block;height:100%;border-radius:5px}}
.sval{{width:26px;text-align:right;font-size:12px;font-weight:700}}
.nextbox{{background:rgba(217,164,65,.14);border:1px dashed rgba(160,115,35,.5);border-radius:10px;padding:10px 12px;margin-top:4px}}
.nextbox .n-main{{font-size:14px;font-weight:700;line-height:1.6;display:flex;gap:7px;align-items:baseline}}
.nextbox .n-bak{{font-size:12px;color:var(--ink-soft);margin-top:6px;line-height:1.7}}
.completed{{margin-top:12px;font-size:12px;color:var(--ink-soft);display:flex;align-items:center;gap:6px}}
.completed .ic{{color:#2e7d5b}}
.completed b.fail{{color:#c0392b}}
.completed b.fail .ic{{color:#c0392b}}
.coach-row{{border-left:3px solid var(--accent);background:rgba(90,60,25,.06);border-radius:0 8px 8px 0;padding:8px 12px;margin-top:8px}}
.coach-tag{{display:inline-block;font-size:11px;font-weight:700;color:#fff;padding:2px 9px;border-radius:10px;letter-spacing:1px;box-shadow:0 1px 2px rgba(0,0,0,.25)}}
.coach-txt{{font-size:13px;line-height:1.65;margin-top:6px}}
.coach-tip{{font-size:12px;color:var(--ink-soft);margin-top:4px;line-height:1.6;display:flex;gap:6px;align-items:baseline}}
.coach-overall{{margin-top:10px;font-size:13px;font-weight:700;padding:9px 12px;background:rgba(217,164,65,.16);border:1px dashed rgba(160,115,35,.45);border-radius:8px;line-height:1.6;display:flex;gap:8px;align-items:center}}
.no-data{{text-align:center;padding:40px 20px;color:#b99a6b;font-size:14px;letter-spacing:1px;grid-column:1/-1}}
.no-data p{{margin-top:8px;font-size:12px;color:#8a7350}}

/* 导出卡片 */
.export{{width:620px;padding:30px 32px;background:#faf3e2;color:#3b2a18;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.6}}
.export .ic{{width:14px;height:14px;vertical-align:-2px}}
.export .ex-brand{{font-family:"Songti SC","STSong",serif;font-size:16px;letter-spacing:4px;color:#8a6a3d;border-bottom:1px solid #e0d2b4;padding-bottom:10px;margin-bottom:8px;text-align:center}}
.export .ex-date{{font-family:"Songti SC","STSong",serif;font-size:26px;font-weight:700;text-align:center}}
.export .ex-mood{{font-size:13px;color:#7a6242;margin-top:4px;text-align:center;display:flex;align-items:center;justify-content:center;gap:6px}}
.export .ex-cols{{display:flex;gap:14px;margin-top:14px}}
.export .ex-col{{flex:1;background:#f4ead2;border-radius:8px;padding:10px 12px;min-width:0}}
.export .ex-col-h{{font-size:13px;font-weight:700;color:#7a6242;margin-bottom:6px;display:flex;align-items:center;gap:6px}}
.export .ex-li{{font-size:13px;padding:3px 0;display:flex;gap:6px;align-items:baseline}}
.export .ex-li-ic{{flex:none;transform:translateY(1px)}}
.export .ex-none{{font-size:12px;color:#a08a64}}
.export .ex-sec{{margin-top:14px}}
.export .ex-sec-h{{font-size:13px;font-weight:700;color:#7a6242;border-bottom:1px solid #e0d2b4;padding-bottom:5px;margin-bottom:8px;display:flex;align-items:center;gap:6px}}
.export .ex-srow{{display:flex;align-items:center;gap:10px;margin:5px 0;font-size:12px}}
.export .ex-sname{{width:60px;color:#7a6242;flex:none}}
.export .ex-sbar{{flex:1;height:8px;border-radius:4px;background:rgba(60,40,15,.12);overflow:hidden}}
.export .ex-sbar i{{display:block;height:100%;border-radius:4px}}
.export .ex-sval{{width:22px;text-align:right;font-weight:700}}
.export .ex-coach{{border-left:3px solid;background:#f4ead2;border-radius:0 8px 8px 0;padding:8px 10px;margin-top:8px;font-size:12px}}
.export .ex-coach-tag{{display:inline-block;font-size:10px;font-weight:700;color:#fff;padding:1px 8px;border-radius:8px;letter-spacing:1px}}
.export .ex-coach-txt{{margin-top:5px;font-size:12px;line-height:1.6}}
.export .ex-coach-tip{{margin-top:3px;font-size:11px;color:#7a6242;display:flex;gap:5px;align-items:baseline}}
.export .ex-overall{{margin-top:12px;font-size:13px;font-weight:700;background:rgba(217,164,65,.15);border:1px dashed #c9a45a;border-radius:8px;padding:8px 10px;display:flex;gap:6px;align-items:center}}
.export .ex-next{{margin-top:10px;font-size:13px;background:#fff8e6;border:1px solid #e0d2b4;border-radius:8px;padding:8px 10px;display:flex;gap:6px;align-items:center}}
.export .ex-foot{{margin-top:16px;text-align:center;font-size:11px;color:#a08a64;letter-spacing:1px}}

@media (max-width:900px){{.cell{{min-height:86px}}.c-meta{{font-size:10px}}.title{{font-size:30px;letter-spacing:5px}}.plaque{{min-width:120px}}}}
@media (max-width:560px){{body{{padding:18px 10px 40px}}.grid,.wd{{gap:4px}}.cal{{padding:8px}}.card{{padding:7px 6px 5px}}.c-date{{font-size:19px}}.tape{{width:34px;height:12px}}.c-flag{{font-size:9px}}.c-meta .m-r{{display:none}}.title{{font-size:24px}}.export{{width:100%}}.p-plan{{font-size:9px}}}}
</style>
</head>
<body>
{sprite}
{warn_banner}

<div class="board" id="app">
  <header>
    <div class="title">人生进度 · 木刻日历</div>
    <div class="sub" id="subhead">加载中…</div>
  </header>

  <div class="stats" id="stats"></div>
  <div class="today-banner" id="todayBanner"></div>

  <div class="p-nav">
    <button class="p-nav-btn" id="prevMonth">‹</button>
    <select id="monthSelect"></select>
    <button class="p-nav-btn" id="nextMonth">›</button>
  </div>

  <div class="cal">
    <div class="wd">
      <span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span>
    </div>
    <div class="grid" id="grid"></div>
  </div>

  <div class="legend" id="legend"></div>

  <footer>
    数据来自 gao-human-booster（本机存储，不外发）· 图标 Feather Icons (MIT) · 重新生成 <code>make build</code>
  </footer>
</div>

<div class="modal" id="modal" aria-hidden="true">
  <div class="overlay"></div>
  <div class="sheet" id="sheet"></div>
</div>

{index_script}
<script src="vendor/html2canvas.min.js"></script>
<script>
/* ═══════════════ 全局状态 ═══════════════ */
var GHB = window.GHB || null;          // 由 data/index.js（或内联）设置，勿覆盖
var DATA = window.DATA || {{}};          // 按月累积 window.DATA
var CURRENT_MONTH = null;
var MONTH_LIST = [];
var EXPORT_ISO = null;
var PLAN_DOT = {{main:'main',backup:'backup',plan:'plan',event:'event'}};

/* ═══════════════ 工具 ═══════════════ */
function esc(s){{return String(s==null?'':s).replace(/[&<>"']/g,function(c){{return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c];}});}}
function ic(name,cls){{cls=cls||'';return '<svg class="ic '+cls+'" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-'+name+'"/></svg>';}}
function moodIcon(m){{if(m==null)return '';if(m<=4)return '<span style="color:#c0392b">'+ic('frown','ic-lg')+'</span>';if(m<=7)return '<span style="color:#d9a441">'+ic('meh','ic-lg')+'</span>';return '<span style="color:#2e7d5b">'+ic('smile','ic-lg')+'</span>';}}
var WD = ['周日','周一','周二','周三','周四','周五','周六'];
var LI_ICON = {{done:'check',undone:'x',worry:'cloud'}};
var LI_COLOR = {{done:'#2e7d5b',undone:'#c0392b',worry:'#b59a5a'}};
var PLAN_COLOR = {{main:'#d9a441',backup:'rgba(120,90,40,.5)',plan:'rgba(120,90,40,.5)',event:'#5b8db8'}};

/* 数据加载：file:// 安全（script 注入，不依赖 fetch） */
function loadMonth(month, cb) {{
  if (DATA[month]) {{ if (cb) cb(); return; }}
  var s = document.createElement('script');
  s.src = 'data/' + month + '.js';
  s.onload = function() {{ if (cb) cb(); }};
  s.onerror = function() {{ if (cb) cb(); }};
  document.head.appendChild(s);
}}

/* ═══════════════ 统计牌 ═══════════════ */
function renderStats() {{
  if (!GHB) return;
  var h = '';
  var domains = GHB.domains || {{}};
  for (var name in domains) {{
    var dm = domains[name];
    if (dm.status !== 'active') continue;
    var pStreak = dm.streak
      ? '<span class="p-streak-ic">'+ic('award','ic-xs')+'</span> 连续 '+dm.streak+' 天'
      : '·';
    h += '<div class="plaque" style="--accent:'+dm.color+'" data-domain="'+esc(name)+'">'+
      '<div class="p-name"><span>'+esc(name)+'</span><span class="p-dot"></span></div>'+
      '<div class="p-score">'+dm.score+'</div>'+
      '<div class="p-bar"><i style="width:'+(dm.score*100)+'%"></i></div>'+
      '<div class="p-streak">'+pStreak+'</div></div>';
  }}
  var todayIso = GHB.today;
  var cur = DATA[GHB.current] || {{}};
  var todayData = (cur.days || {{}})[todayIso] || {{}};
  var todayScores = todayData.scores || {{}};
  var keys = Object.keys(todayScores);
  var todayAvg = keys.length ? (keys.reduce(function(a,k){{return a+todayScores[k];}},0)/keys.length) : null;
  var capT = todayData.capture || {{}};
  var totalDays = (GHB.meta||{{}}).total_days || 0;
  h += '<div class="plaque today-p"><div class="p-name"><span>今日概览</span><span class="p-dot"></span></div>'+
    '<div class="p-score">'+(todayAvg==null?'—':todayAvg.toFixed(2))+'</div>'+
    '<div class="p-bar"><i style="width:'+((todayAvg||0)*100)+'%"></i></div>'+
    '<div class="p-streak"><span class="mi">'+ic('check','ic-xs')+'</span>'+((capT.done||[]).length)+
    ' <span class="mi">'+ic('x','ic-xs')+'</span>'+((capT.undone||[]).length)+' · 已记录 '+totalDays+' 天</div></div>';
  document.getElementById('stats').innerHTML = h;
}}

/* ═══════════════ 今日计划横幅 ═══════════════ */
function renderTodayBanner() {{
  var banner = document.getElementById('todayBanner');
  if (!GHB || !GHB.plans) {{ banner.classList.remove('show'); return; }}
  var plans = GHB.plans[GHB.today];
  if (!plans || !plans.length) {{ banner.classList.remove('show'); return; }}
  var items = [];
  for (var i=0;i<plans.length;i++) {{
    var p = plans[i];
    var cls = 'tb-item' + (p.done ? ' done' : '');
    var dotCls = PLAN_DOT[p.kind] || 'plan';
    items.push('<span class="'+cls+'"><span class="tb-dot '+dotCls+'"></span>'+esc(p.text)+'</span>');
  }}
  banner.innerHTML = '<span class="tb-label">'+ic('crosshair','ic-xs')+' 今日计划</span>'+items.join('');
  banner.classList.add('show');
}}

/* ═══════════════ 网格 ═══════════════ */
function buildCalendar(y, m) {{
  var first = new Date(y, m-1, 1);
  var startDow = first.getDay();          // 0=周日
  startDow = (startDow === 0) ? 6 : startDow - 1;   // 周一开头
  var daysInMonth = new Date(y, m, 0).getDate();
  var weeks = [], week = [];
  for (var i=0;i<startDow;i++) week.push(null);
  for (var d=1;d<=daysInMonth;d++) {{
    var iso = y+'-'+String(m).padStart(2,'0')+'-'+String(d).padStart(2,'0');
    week.push({{day:d, iso:iso}});
    if (week.length === 7) {{ weeks.push(week); week = []; }}
  }}
  if (week.length) {{ while (week.length < 7) week.push(null); weeks.push(week); }}
  return weeks;
}}

function renderMonth(month) {{
  if (!month) return;
  var md = DATA[month] || null;
  var grid = document.getElementById('grid');
  var sub = document.getElementById('subhead');
  if (!md) {{
    var yp = month.split('-');
    var yy = parseInt(yp[0],10), mm = parseInt(yp[1],10);
    sub.textContent = yy+' 年 '+mm+' 月 · 暂无记录';
    renderEmptyGrid(yy, mm, grid);
    return;
  }}
  var y = md.year, m = md.month;
  sub.textContent = y+' 年 '+m+' 月 · 每天 10 分钟闭环';
  var days = md.days || {{}};
  var plans = md.plans || {{}};
  var today = GHB ? GHB.today : '';
  var cal = buildCalendar(y, m);
  var cells = [];
  var idx = 0;
  for (var r=0;r<cal.length;r++) {{
    for (var c=0;c<7;c++) {{
      var cell = cal[r][c];
      if (!cell) {{ cells.push('<div class="cell"></div>'); idx++; continue; }}
      var iso = cell.iso;
      var d = days[iso] || null;
      var pList = plans[iso] || null;
      var isToday = iso === today;
      var cls = isToday ? 'cell today' : 'cell';
      var html = '<div class="'+cls+'" data-day="'+iso+'">';
      if (d) {{
        html += renderDayCard(d, pList, cell.day, iso, idx, today);
      }} else if (pList && pList.length) {{
        html += renderPlanOnlyCard(pList, cell.day, iso, idx, today);
      }} else {{
        html += '<span class="empty">'+cell.day+'</span>';
      }}
      html += '</div>';
      cells.push(html);
      idx++;
    }}
  }}
  grid.innerHTML = cells.join('');
  grid.querySelectorAll('.cell[data-day]').forEach(function(el) {{
    el.addEventListener('click', function() {{ openDay(el.dataset.day); }});
  }});
  grid.querySelectorAll('.p-plan').forEach(function(box) {{
    if (box.scrollHeight <= box.clientHeight) return;
    box.addEventListener('mouseenter', function() {{
      box.scrollTo({{top: box.scrollHeight, behavior: 'smooth'}});
    }});
    box.addEventListener('mouseleave', function() {{
      box.scrollTo({{top: 0, behavior: 'auto'}});
    }});
  }});
}}

function renderEmptyGrid(y, m, grid) {{
  var cal = buildCalendar(y, m);
  var cells = [];
  for (var r=0;r<cal.length;r++) {{
    for (var c=0;c<7;c++) {{
      var cell = cal[r][c];
      if (!cell) {{ cells.push('<div class="cell"></div>'); continue; }}
      cells.push('<div class="cell"><span class="empty">'+cell.day+'</span></div>');
    }}
  }}
  cells.push('<div class="no-data">本月暂无记录<br><p>切到有数据的月份浏览复盘</p></div>');
  grid.innerHTML = cells.join('');
}}

function renderPlanBlock(pList, iso, today) {{
  var items = [];
  for (var i=0;i<pList.length;i++) {{
    var p = pList[i];
    var cls = 'p-plan-item';
    if (p.done) cls += ' done';
    else if (iso < today) cls += ' overdue';
    var dotCls = PLAN_DOT[p.kind] || 'plan';
    var preview = p.text;
    var timeRange = preview.match(/^ *[0-9][0-9]?:[0-9][0-9] *[-–—至到] *[0-9][0-9]?:[0-9][0-9]/);
    if (timeRange) preview = timeRange[0].trim();
    else preview = preview.substring(0,10);
    items.push('<div class="'+cls+'"><span class="p-dot '+dotCls+'"></span>'+esc(preview)+'</div>');
  }}
  var h = '<div class="p-plan">'+items.join('');
  return h + '</div>';
}}

function renderDayCard(d, pList, dayNum, iso, idx, today) {{
  var scores = d.scores || {{}};
  var cap = d.capture || {{}};
  var done = cap.done || [];
  var undone = cap.undone || [];
  var dayWorries = cap.worries || [];
  var dm = GHB ? GHB.domains : {{}};

  var sNames = Object.keys(scores);
  var segs = [];
  for (var i=0;i<Math.min(sNames.length,4);i++) {{
    var name = sNames[i];
    var color = (dm[name]||{{}}).color || '#8a6d3b';
    var r = scores[name];
    segs.push('<i class="f" style="--seg:'+color+';width:'+(r*100)+'%"></i>');
  }}
  for (var j=segs.length;j<4;j++) segs.push('<i></i>');
  var bar = '<div class="c-bar">'+segs.join('')+'</div>';

  var flag = '';
  if (sNames.indexOf('健身')>=0 && dm['健身']) {{
    flag = '<span class="flag-ic">'+ic('award')+'</span>'+dm['健身'].streak;
  }} else if (dayWorries.length) {{
    flag = '<span class="flag-ic">'+ic('cloud')+'</span>'+dayWorries.length;
  }}

  var metaL = '<span class="mi">'+ic('check','ic-xs')+'</span>'+done.length+
    ' <span class="mi">'+ic('x','ic-xs')+'</span>'+undone.length;
  var mood = d.mood;
  var metaR = (mood!=null) ? '<span class="mdot" style="--mc:'+(mood<=4?'#c0392b':(mood<=7?'#d9a441':'#2e7d5b'))+'"></span>' : '';
  var meta = '<span class="m-l">'+metaL+'</span><span class="m-r">'+metaR+'</span>';
  var ribbon = (iso === today) ? '<span class="ribbon">今天</span>' : '';
  var doms = sNames.join(',');
  var planHtml = (pList && pList.length) ? renderPlanBlock(pList, iso, today) : '';
  return '<div class="card" style="--i:'+idx+'" data-doms="'+doms+'" title="点击查看详情">'+
    '<span class="tape"></span>'+ribbon+
    '<div class="c-top"><span class="c-date">'+dayNum+'</span>'+
    '<span class="c-flag">'+flag+'</span></div>'+
    bar+'<div class="c-meta">'+meta+'</div>'+
    planHtml+'</div>';
}}

function renderPlanOnlyCard(pList, dayNum, iso, idx, today) {{
  var ribbon = (iso === today) ? '<span class="ribbon">今天</span>' : '';
  var planHtml = renderPlanBlock(pList, iso, today);
  return '<div class="card" style="--i:'+idx+'" data-doms="" title="点击查看计划">'+
    '<span class="tape"></span>'+ribbon+
    '<div class="c-top"><span class="c-date">'+dayNum+'</span>'+
    '<span class="c-flag" style="color:var(--gold)">'+ic('calendar','ic-xs')+'</span></div>'+
    planHtml+'</div>';
}}

/* ═══════════════ 月份导航 ═══════════════ */
function populateMonthSelect() {{
  var sel = document.getElementById('monthSelect');
  sel.innerHTML = '';
  for (var i=0;i<MONTH_LIST.length;i++) {{
    var m = MONTH_LIST[i];
    var yp = m.split('-');
    var opt = document.createElement('option');
    opt.value = m;
    opt.textContent = yp[0]+' 年 '+parseInt(yp[1],10)+' 月';
    if (m === CURRENT_MONTH) opt.selected = true;
    sel.appendChild(opt);
  }}
}}

function switchMonth(month) {{
  if (month === CURRENT_MONTH) return;
  CURRENT_MONTH = month;
  populateMonthSelect();
  loadMonth(month, function() {{ renderMonth(month); }});
}}

/* ═══════════════ 初始化 ═══════════════ */
function init() {{
  if (!GHB) return;
  MONTH_LIST = GHB.months || [];
  CURRENT_MONTH = GHB.current;
  if (MONTH_LIST.indexOf(CURRENT_MONTH) < 0) {{
    CURRENT_MONTH = MONTH_LIST.length ? MONTH_LIST[MONTH_LIST.length-1] : null;
  }}
  if (CURRENT_MONTH) {{
    loadMonth(CURRENT_MONTH, function() {{
      renderStats();
      renderTodayBanner();
      renderMonth(CURRENT_MONTH);
    }});
  }} else {{
    renderStats();
    renderTodayBanner();
  }}
  populateMonthSelect();

  document.getElementById('prevMonth').addEventListener('click', function() {{
    var i = MONTH_LIST.indexOf(CURRENT_MONTH);
    if (i > 0) switchMonth(MONTH_LIST[i-1]);
  }});
  document.getElementById('nextMonth').addEventListener('click', function() {{
    var i = MONTH_LIST.indexOf(CURRENT_MONTH);
    if (i >= 0 && i < MONTH_LIST.length-1) switchMonth(MONTH_LIST[i+1]);
  }});
  document.getElementById('monthSelect').addEventListener('change', function() {{
    switchMonth(this.value);
  }});
  bindDomainHighlight();
}}

function bindDomainHighlight() {{
  var grid = document.getElementById('grid');
  document.querySelectorAll('.plaque[data-domain]').forEach(function(p) {{
    var dom = p.dataset.domain;
    p.addEventListener('mouseenter', function() {{
      grid.classList.add('dim');
      grid.querySelectorAll('.card').forEach(function(c) {{
        if ((c.dataset.doms||'').split(',').indexOf(dom) >= 0) c.classList.add('hit');
      }});
    }});
    p.addEventListener('mouseleave', function() {{
      grid.classList.remove('dim');
      grid.querySelectorAll('.card.hit').forEach(function(c){{c.classList.remove('hit');}});
    }});
  }});
}}

if (typeof GHB !== 'undefined' && GHB) init();
</script>
<script>
/* ═══════════════ 弹层 ═══════════════ */
var MODAL = document.getElementById('modal');
var SHEET = document.getElementById('sheet');

function findDay(iso) {{
  var mk = iso.substring(0,7);
  var md = DATA[mk];
  if (md && md.days[iso]) return md;
  for (var m in DATA) if (DATA[m].days[iso]) return DATA[m];
  return null;
}}

function openDay(iso) {{
  var md = findDay(iso);
  if (!md) return;
  var d = md.days[iso];
  if (!d) return;
  EXPORT_ISO = iso;
  var dt = new Date(iso+'T00:00:00');
  var cap = d.capture||{{}};
  var done = cap.done||[], undone = cap.undone||[], dw = cap.worries||[];
  var scores = d.scores||{{}};
  var next = d.next||{{}};
  var intel = d.intel||[];
  var recs = d.recs||[];
  var dm = GHB ? GHB.domains : {{}};

  var dayPlans = ((md.plans||{{}})[iso]) || [];
  var lst = function(arr,cls) {{
    return arr.length
      ? '<ul class="lst '+cls+'">'+arr.map(function(x){{return '<li><span style="color:'+LI_COLOR[cls]+'">'+ic(LI_ICON[cls],'ic-xs')+'</span>'+esc(x)+'</li>';}}).join('')+'</ul>'
      : '<p class="none">—</p>';
  }};
  var bars = Object.keys(scores).map(function(n) {{
    var r = scores[n];
    var c = (dm[n]||{{}}).color||'#8a6d3b';
    return '<div class="srow"><span class="sname">'+esc(n)+'</span>'+
      '<div class="sbar"><i style="width:'+(r*100)+'%;background:'+c+'"></i></div>'+
      '<span class="sval">'+r+'</span></div>';
  }}).join('');

  var ex = md.expert ? md.expert[iso] : null;
  var expertHtml = '';
  if (ex) {{
    var rows = Object.keys(dm).filter(function(n){{return ex[n];}}).map(function(n) {{
      var e = ex[n];
      return '<div class="coach-row" style="--accent:'+e.color+'">'+
        '<span class="coach-tag" style="background:'+e.color+'">'+esc(e.coach)+'</span>'+
        '<p class="coach-txt">'+esc(e.text)+'</p>'+
        (e.tip?'<p class="coach-tip"><span>'+ic('arrow-right','ic-xs')+'</span>'+esc(e.tip)+'</p>':'')+
        '</div>';
    }}).join('');
    expertHtml = '<div class="sec"><h4>'+ic('compass','ic-sm')+' 专家点评</h4>'+
      '<div class="coach-list">'+rows+'</div>'+
      (ex.__overall__?'<div class="coach-overall"><span style="color:#c9a45a">'+ic('star','ic-sm')+'</span>'+esc(ex.__overall__)+'</div>':'')+'</div>';
  }}

  var nextBox = '';
  if (next.main) {{
    var baks = (next.backup||[]).map(function(b){{return '<div class="n-bak"><span>'+ic('arrow-right','ic-xs')+'</span>'+esc(b)+'</div>';}}).join('');
    nextBox = '<div class="sec"><h4>'+ic('crosshair','ic-sm')+' 明日行动</h4><div class="nextbox">'+
      '<div class="n-main"><span style="color:#c9a45a">'+ic('crosshair','ic-sm')+'</span>'+esc(next.main)+'</div>'+
      (baks?'<div class="n-bak">'+baks+'</div>':'')+
      '</div></div>';
  }}

  var planHtml = '';
  if (dayPlans.length) {{
    planHtml = '<div class="sec"><h4>'+ic('calendar','ic-sm')+' 计划</h4><ul class="lst">'+
      dayPlans.map(function(p) {{
        var st = p.done ? ' ✓ 已完成' : (p.kind==='main' ? ' · 主行动' : (p.kind==='event' ? ' · 事件' : ''));
        var color = p.done ? '#999' : (PLAN_COLOR[p.kind] || 'rgba(120,90,40,.5)');
        var tdec = p.done ? ' style="text-decoration:line-through"' : '';
        return '<li'+tdec+'><span class="p-dot" style="display:inline-block;width:6px;height:6px;border-radius:50%;background:'+color+';flex:none;margin-right:5px"></span>'+esc(p.text)+' <span style="font-size:11px;color:#a08a64">'+st+'</span></li>';
      }}).join('')+
      '</ul><p style="font-size:11px;color:#a08a64;margin-top:6px;font-style:italic">完成状态由晚间复盘回填</p></div>';
  }}

  var secLst = function(title, icn, arr, color) {{
    if (!arr.length) return '';
    return '<div class="sec"><h4>'+ic(icn,'ic-sm')+' '+title+'</h4><ul class="lst">'+
      arr.map(function(x){{return '<li><span style="color:'+color+'">'+ic('arrow-right','ic-xs')+'</span>'+esc(x)+'</li>';}}).join('')+
      '</ul></div>';
  }};

  var comp = '';
  if (d.completed != null) {{
    comp = '<div class="completed">昨日主行动：'+(d.completed
      ? '<b>'+ic('check','ic-xs')+' 完成</b>'
      : '<b class="fail">'+ic('x','ic-xs')+' 未完成</b>')+'</div>';
  }}

  SHEET.innerHTML =
    '<div class="sheet-body">'+
    '<div class="m-head">'+
      '<div><div class="m-date">'+iso+'</div>'+
      '<div class="m-wd">'+WD[dt.getDay()]+' · 复盘记录 '+moodIcon(d.mood)+'</div></div>'+
      '<div class="m-actions">'+
        '<button class="m-btn" id="mfx" title="打印机效果（动画+音效）">'+ic('printer','ic-sm')+'</button>'+
        '<button class="m-btn'+(PRINT_ON?'':' off')+'" id="mfx-toggle">'+(PRINT_ON?'效果 开':'效果 关')+'</button>'+
        '<button class="m-btn" id="mexport">'+ic('download','ic-sm')+' 导出图片</button>'+
        '<button class="m-btn m-close" id="mclose">'+ic('x')+'</button></div></div>'+
    '<div class="sec"><h4>'+ic('check-circle','ic-sm')+' 完成</h4>'+lst(done,'done')+'</div>'+
    '<div class="sec"><h4>'+ic('x-circle','ic-sm')+' 未完成</h4>'+lst(undone,'undone')+'</div>'+
    '<div class="sec"><h4>'+ic('cloud','ic-sm')+' 担心 / 情绪</h4>'+lst(dw,'worry')+'</div>'+
    (bars?'<div class="sec"><h4>'+ic('bar-chart-2','ic-sm')+' 领域评分</h4>'+bars+'</div>':'')+
    secLst('情报补给','trending-up',intel,'#c9a45a')+
    secLst('推荐','star',recs,'#5b8db8')+
    planHtml+
    expertHtml+
    nextBox+
    comp+
    '</div>';
  MODAL.classList.add('open');
  MODAL.setAttribute('aria-hidden','false');
  document.getElementById('mclose').onclick = function(){{closeModal();}};
  document.getElementById('mexport').onclick = function(){{exportImage();}};
  document.getElementById('mfx-toggle').onclick = function() {{
    PRINT_ON = !PRINT_ON;
    try {{ localStorage.setItem('ghb-print', PRINT_ON?'on':'off'); }} catch(e) {{}}
    this.classList.toggle('off', !PRINT_ON);
    this.textContent = PRINT_ON ? '效果 开' : '效果 关';
    if (!PRINT_ON) {{ clearInterval(PRINT_TIMER); SHEET.classList.remove('printing'); }}
  }};
  playPrint(iso);
}}

function closeModal(){{MODAL.classList.remove('open');MODAL.setAttribute('aria-hidden','true');clearInterval(PRINT_TIMER);}}

/* ═══════════════ 打印机吐卡动画 + 音效 ═══════════════ */
var PRINT_TIMER = null;
var PRINT_ON = (function(){{try{{return localStorage.getItem('ghb-print')!=='off';}}catch(e){{return true;}}}})();
var PRINT_CTX = null;
function printSound() {{
  try {{
    if (!PRINT_CTX) PRINT_CTX = new (window.AudioContext||window.webkitAudioContext)();
    var ctx = PRINT_CTX;
    if (ctx.state==='suspended') ctx.resume();
    var t0 = ctx.currentTime;
    /* 打印头步进：11 段交替双击咔哒声 */
    for (var i=0;i<11;i++) {{
      for (var k=0;k<2;k++) {{
        var o = ctx.createOscillator(), g = ctx.createGain(), f = ctx.createBiquadFilter();
        f.type='bandpass'; f.frequency.value = 2200 + (i%2)*700; f.Q.value = 6;
        o.type='square'; o.frequency.value = 160 + (i%3)*40;
        o.connect(f); f.connect(g); g.connect(ctx.destination);
        var ts = t0 + 0.07 + i*0.095 + k*0.018;
        g.gain.setValueAtTime(0.0001, ts);
        g.gain.exponentialRampToValueAtTime(0.05, ts+0.004);
        g.gain.exponentialRampToValueAtTime(0.0001, ts+0.016);
        o.start(ts); o.stop(ts+0.02);
      }}
    }}
    /* 末尾撕纸声：白噪声短促衰减 */
    var len = ctx.sampleRate * 0.22;
    var buf = ctx.createBuffer(1, len, ctx.sampleRate);
    var ch = buf.getChannelData(0);
    for (var n=0;n<len;n++) ch[n] = (Math.random()*2-1) * (1 - n/len) * (n<40 ? n/40 : 1);
    var src = ctx.createBufferSource(); src.buffer = buf;
    var bp = ctx.createBiquadFilter(); bp.type='highpass'; bp.frequency.value=1800;
    var ng = ctx.createGain(); ng.gain.setValueAtTime(0.06, t0+1.18);
    src.connect(bp); bp.connect(ng); ng.connect(ctx.destination);
    src.start(t0+1.18);
  }} catch(e) {{ /* 音频不可用则静默 */ }}
}}
function playPrint(iso) {{
  var sheet = document.getElementById('sheet');
  clearInterval(PRINT_TIMER);
  if (!PRINT_ON || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  sheet.classList.remove('printing');
  void sheet.offsetWidth;   /* 重置动画 */
  sheet.classList.add('printing');
  printSound();
  PRINT_TIMER = setInterval(function() {{ sheet.classList.remove('printing'); clearInterval(PRINT_TIMER); }}, 1500);
}}
document.querySelector('.overlay').addEventListener('click', closeModal);
document.addEventListener('keydown',function(e){{if(e.key==='Escape')closeModal();}});

/* ═══════════════ 导出图片 ═══════════════ */
function buildExportCard(iso) {{
  var md = findDay(iso);
  if (!md) return null;
  var d = md.days[iso]; if (!d) return null;
  var dt = new Date(iso+'T00:00:00');
  var cap = d.capture||{{}}; var scores = d.scores||{{}}; var next = d.next||{{}};
  var ex = (md.expert||{{}})[iso]||{{}};
  var dm = GHB ? GHB.domains : {{}};

  var mk = function(arr,icn,col) {{
    return (arr&&arr.length)
      ? arr.map(function(x){{return '<div class="ex-li"><span class="ex-li-ic" style="color:'+col+'">'+ic(icn,'ic-xs')+'</span>'+esc(x)+'</div>';}}).join('')
      : '<div class="ex-none">—</div>';
  }};
  var rows = Object.keys(dm).filter(function(n){{return ex[n];}}).map(function(n) {{
    var e = ex[n];
    return '<div class="ex-coach" style="border-color:'+e.color+'">'+
      '<span class="ex-coach-tag" style="background:'+e.color+'">'+esc(e.coach)+'</span>'+
      '<div class="ex-coach-txt">'+esc(e.text)+'</div>'+
      (e.tip?'<div class="ex-coach-tip">'+ic('arrow-right','ic-xs')+' '+esc(e.tip)+'</div>':'')+'</div>';
  }}).join('');
  var bars = Object.keys(scores).map(function(n) {{
    var r = scores[n]; var c = (dm[n]||{{}}).color||'#8a6d3b';
    return '<div class="ex-srow"><span class="ex-sname">'+esc(n)+'</span>'+
      '<div class="ex-sbar"><i style="width:'+(r*100)+'%;background:'+c+'"></i></div>'+
      '<span class="ex-sval">'+r+'</span></div>';
  }}).join('');

  var node = document.createElement('div');
  node.className = 'export';
  node.innerHTML =
    '<div class="ex-brand">人生进度 · 木刻日历</div>'+
    '<div class="ex-date">'+iso.replace(/-/g,' · ')+' '+WD[dt.getDay()]+'</div>'+
    (d.mood!=null?'<div class="ex-mood">'+moodIcon(d.mood)+' 心情 '+d.mood+'/10</div>':'')+
    '<div class="ex-cols">'+
      '<div class="ex-col"><div class="ex-col-h">'+ic('check-circle','ic-sm')+' 完成</div>'+mk(cap.done,'check','#2e7d5b')+'</div>'+
      '<div class="ex-col"><div class="ex-col-h">'+ic('x-circle','ic-sm')+' 未完成</div>'+mk(cap.undone,'x','#c0392b')+'</div>'+
      '<div class="ex-col"><div class="ex-col-h">'+ic('cloud','ic-sm')+' 担心</div>'+mk(cap.worries,'cloud','#b59a5a')+'</div>'+
    '</div>'+
    (bars?'<div class="ex-sec"><div class="ex-sec-h">'+ic('bar-chart-2','ic-sm')+' 领域评分</div>'+bars+'</div>':'')+
    ((d.intel||[]).length?'<div class="ex-sec"><div class="ex-sec-h">'+ic('trending-up','ic-sm')+' 情报补给</div>'+mk(d.intel,'arrow-right','#c9a45a')+'</div>':'')+
    ((d.recs||[]).length?'<div class="ex-sec"><div class="ex-sec-h">'+ic('star','ic-sm')+' 推荐</div>'+mk(d.recs,'arrow-right','#5b8db8')+'</div>':'')+
    (rows?'<div class="ex-sec"><div class="ex-sec-h">'+ic('compass','ic-sm')+' 专家点评</div>'+rows+'</div>':'')+
    (ex.__overall__?'<div class="ex-overall">'+ic('star','ic-sm')+' '+esc(ex.__overall__)+'</div>':'')+
    (next.main?'<div class="ex-next">'+ic('crosshair','ic-sm')+' '+esc(next.main)+'</div>':'')+
    '<div class="ex-foot">gao · 每日复盘 · 数据仅存本机</div>';
  node.style.position = 'fixed'; node.style.left = '-9999px'; node.style.top = '0';
  document.body.appendChild(node);
  return node;
}}

function exportImage() {{
  if (!EXPORT_ISO) return;
  var node = buildExportCard(EXPORT_ISO);
  if (!node) return;
  html2canvas(node,{{scale:2,backgroundColor:'#faf3e2',logging:false,useCORS:true}}).then(function(canvas) {{
    var a = document.createElement('a');
    a.download = 'gao-'+EXPORT_ISO+'.png';
    a.href = canvas.toDataURL('image/png');
    a.click();
    node.remove();
  }}).catch(function(){{node.remove();}});
}}

/* 直达 hash */
(function() {{
  var ed = location.hash.match(/#export=([0-9-]+)/);
  if (ed) {{ var n = buildExportCard(ed[1]); if (n) {{ n.style.position='relative'; n.style.left='0'; n.style.margin='30px auto'; }} }}
  var hd = location.hash.match(/#day=([0-9-]+)/);
  if (hd) setTimeout(function(){{ openDay(hd[1]); }}, 600);
}})();
</script>
</body>
</html>"""


def render_html(sprite, index_script, warn_no_state):
    """index_script: 非内联=加载 data/index.js 的标签；内联=内嵌 GHB+DATA 的 script"""
    warn = ""
    if warn_no_state:
        warn = (
            '<div style="max-width:1240px;margin:12px auto;padding:14px 20px;'
            'background:#f7ecd6;border-radius:10px;border:2px dashed #c05b24;'
            'text-align:center;color:#3b2a18;font-size:14px;line-height:1.8">'
            '⚠️ <b>暂无数据</b> — 运行 <code>make init</code> 初始化后，'
            '再运行 <code>make build</code> 生成日历。'
            '</div>'
        )
    return HTML_TEMPLATE.format(
        sprite=sprite,
        warn_banner=warn,
        index_script=index_script,
    )


# ── 主流程 ───────────────────────────────────────────────────────────────
def main():
    state_path, inline_mode = resolve_state()
    data_dir = data_dir_for(state_path)
    daily_dir = resolve_daily_dir(state_path)
    data_dir.mkdir(parents=True, exist_ok=True)

    profile = load_json(state_path / "profile.json", {})
    domains = load_json(state_path / "domains.json", {}).get("domains", {})
    worries = load_json(state_path / "worries.json", {"items": []})
    evolution = load_json(state_path / "evolution.json", {"version": "v1.0.0"})

    migrated = migrate_legacy_to_mdx(daily_dir, state_path)
    days, plans_by_date = load_daily_mdx(daily_dir)
    dom_payload = build_domains_payload(domains)

    has_state = bool(domains) or bool(days)

    # 月份范围：所有数据日期 ∪ 当前月，前 12 个月 + 未来 6 个月
    ym_set = set()
    for iso in list(days.keys()) + list(plans_by_date.keys()):
        try:
            dt = datetime.date.fromisoformat(iso)
            ym_set.add((dt.year, dt.month))
        except ValueError:
            pass
    # 当前月起往前 11 个月
    for k in range(11, -1, -1):
        mm = TODAY.month - k
        y = TODAY.year
        while mm <= 0:
            mm += 12
            y -= 1
        ym_set.add((y, mm))
    # 未来 6 个月
    for k in range(1, 7):
        mm = TODAY.month + k
        y = TODAY.year
        while mm > 12:
            mm -= 12
            y += 1
        ym_set.add((y, mm))

    ym_sorted = sorted(f"{y}-{m:02d}" for y, m in ym_set)

    index_months = []
    month_js_parts = []   # 内联模式累积
    for ym in ym_sorted:
        y, m = int(ym[:4]), int(ym[5:7])
        month_data = build_month_data(y, m, days, dom_payload, plans_by_date)
        has_any = bool(month_data["days"] or month_data["plans"])
        is_current = (y, m) == (TODAY.year, TODAY.month)
        if not has_any and not is_current:
            continue  # 只有有数据或当前月才生成文件
        index_months.append(ym)
        if not inline_mode:
            js = f"window.DATA=window.DATA||{{}};window.DATA[\"{ym}\"]=" + json.dumps(month_data, ensure_ascii=False) + ";"
            (data_dir / f"{ym}.js").write_text(js, encoding="utf-8")
        else:
            month_js_parts.append(
                f"window.DATA[\"{ym}\"]=" + json.dumps(month_data, ensure_ascii=False)
            )

    # index 数据
    open_worries = sum(1 for w in worries.get("items", []) if w.get("status") == "open")
    today_iso = TODAY.isoformat()

    future_plans = {}
    for date, plist in plans_by_date.items():
        try:
            dt = datetime.date.fromisoformat(date)
        except ValueError:
            continue
        if dt < TODAY or dt > TODAY + datetime.timedelta(days=14):
            continue
        items = []
        for p in plist:
            if p.get("kind") == "backup":
                continue
            items.append({
                "id": p["id"],
                "text": p["text"],
                "kind": p["kind"],
                "domain": p.get("domain", ""),
                "done": p.get("done", False),
            })
        if items:
            future_plans[date] = items

    index_data = {
        "version": evolution.get("version", "v1.0.0"),
        "name": profile.get("user", {}).get("name", ""),
        "role": profile.get("user", {}).get("role", ""),
        "months": index_months,
        "current": f"{TODAY.year}-{TODAY.month:02d}",
        "today": today_iso,
        "domains": dom_payload,
        "plans": future_plans,
        "worries_open": open_worries,
        "meta": {"generated": TODAY.isoformat(), "total_days": len(days)},
    }

    if not inline_mode:
        index_js = "window.GHB=" + json.dumps(index_data, ensure_ascii=False) + ";"
        (data_dir / "index.js").write_text(index_js, encoding="utf-8")
        index_script = '<script src="data/index.js"></script>'
    else:
        inline = "window.DATA={};window.GHB=" + json.dumps(index_data, ensure_ascii=False) + ";"
        for part in month_js_parts:
            inline += "window.DATA[" + json.dumps(part.split("]=", 1)[0].split('"')[1]) + "]=" + part.split("]=", 1)[1] + ";"
        # 更稳的方式：直接拼
        inline = "window.DATA={};window.GHB=" + json.dumps(index_data, ensure_ascii=False) + ";" + "".join(month_js_parts) + ";"
        index_script = "<script>" + inline + "</script>"

    sprite = build_sprite()
    html = render_html(sprite, index_script, warn_no_state=not has_state)
    OUT_HTML.write_text(html, encoding="utf-8")

    print(f"✅ 已生成 {OUT_HTML}")
    if inline_mode:
        print(f"   单文件内嵌 {len(index_months)} 个月")
    else:
        print(f"   data/index.js + {len(index_months)} 个月数据文件 → {data_dir}")
    if migrated:
        print("   ⚠️ 已把旧 daily_log.json / plans.json 迁移为 daily/*.mdx")
    print(f"   今日 {today_iso}, 记录 {len(days)} 天, 担心箱 {open_worries} 件")


if __name__ == "__main__":
    main()
