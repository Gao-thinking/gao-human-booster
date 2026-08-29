#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gao-human-booster 一键初始化
用法:
  python3 scripts/init.py                    # 初始化 state
  python3 scripts/init.py --install          # 初始化 + 安装符号链接到 ~/.agents/skills/
  python3 scripts/init.py --force            # 覆盖已有 state
  python3 scripts/init.py --no-build         # 初始化后不生成日历
"""
import argparse, json, os, shutil, sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = REPO_DIR / "scripts"
STATE_DIR = REPO_DIR / "state"
STATE_EXAMPLE = REPO_DIR / "state.example"
INSTALL_DIR = Path.home() / ".agents" / "skills" / "gao-human-booster"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true", default=False, help="安装符号链接到 ~/.agents/skills/")
    parser.add_argument("--force", action="store_true", default=False, help="覆盖已有 state")
    parser.add_argument("--no-build", action="store_true", default=False, help="初始化后不生成日历")
    args = parser.parse_args()

    # 1. 初始化 state
    state_exists = STATE_DIR.exists() and (STATE_DIR / "domains.json").exists()
    if state_exists and not args.force:
        print("✅ state/ 已存在，跳过 (--force 覆盖)")
    else:
        if state_exists and args.force:
            shutil.rmtree(STATE_DIR)
        _bootstrap_state(STATE_DIR, STATE_EXAMPLE)
        print("✅ state/ 已初始化")

    # 1.5 初始化 daily/（MDX 日档目录）
    daily_dir = STATE_DIR.parent / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    print("✅ daily/ 已就绪（每天一份 YYYY-MM-DD.mdx）")

    # 2. 安装符号链接
    if args.install:
        install_dir = INSTALL_DIR
        if install_dir.exists() and not install_dir.is_symlink():
            print(f"⚠️  {install_dir} 已存在且不是符号链接，跳过")
        elif install_dir.is_symlink():
            install_dir.unlink()
            install_dir.symlink_to(REPO_DIR)
            print(f"✅ 已更新符号链接 {install_dir} → {REPO_DIR}")
        else:
            install_dir.symlink_to(REPO_DIR)
            print(f"✅ 已创建符号链接 {install_dir} → {REPO_DIR}")

    # 3. 构建日历
    if not args.no_build:
        build_script = SCRIPT_DIR / "build_calendar.py"
        if build_script.exists():
            import subprocess
            result = subprocess.run(
                [sys.executable, str(build_script)],
                cwd=REPO_DIR,
                capture_output=True, text=True,
            )
            print(result.stdout.strip())
            if result.returncode != 0:
                print(f"⚠️  build 脚本出错: {result.stderr.strip()}")
        else:
            print("⚠️  未找到 scripts/build_calendar.py，跳过构建")

    print("\n📋 下一步：")
    print("   - 在 Claude 中调用 skill，说「开始建档」")
    print("   - 或手动编辑 state/profile.json 和 state/domains.json")
    print("   - 日常用 `make build` 同步日历")


def _bootstrap_state(state_dir: Path, example_dir: Path):
    """从 state.example 复制模板创建 state"""
    state_dir.mkdir(parents=True, exist_ok=True)
    if not example_dir.exists():
        # 创建最小结构
        _write_minimal(state_dir)
        return
    for f in example_dir.glob("*.json"):
        target = state_dir / f.name
        if not target.exists():
            shutil.copy2(f, target)
        else:
            # 合并缺失的键（不覆盖已有数据）
            try:
                existing = json.loads(target.read_text(encoding="utf-8"))
                template = json.loads(f.read_text(encoding="utf-8"))
                merged = _deep_merge(template, existing)
                target.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
            except Exception:
                pass  # 保持原样


def _deep_merge(base, override):
    """递归合并，override 的键优先"""
    result = {}
    for k in base:
        if k in override:
            if isinstance(base[k], dict) and isinstance(override[k], dict):
                result[k] = _deep_merge(base[k], override[k])
            else:
                result[k] = override[k]
        else:
            result[k] = base[k]
    for k in override:
        if k not in result:
            result[k] = override[k]
    return result


def _write_minimal(state_dir: Path):
    """无模板时写最小结构"""
    now = __import__("datetime").date.today().isoformat()
    (state_dir / "profile.json").write_text(
        json.dumps({"user": {"name": "", "role": "", "wake_time": "07:00", "sleep_time": "23:00"}, "review": {"preferred_time": "22:00", "remind": True, "skip_weekend": False}, "rules": [], "energy": {}, "interests": [], "calendar": {"provider": "apple", "remind_at": "22:00"}, "created": now}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    (state_dir / "domains.json").write_text(
        json.dumps({"domains": {"工作/事业": {"job": "", "priority": 1.0, "prior": 0.5, "alpha": 2.0, "beta": 2.0, "score": 0.5, "streak": 0, "best_streak": 0, "last_evidence": "", "weekly": [], "status": "active"}, "追求": {"job": "", "priority": 0.8, "prior": 0.5, "alpha": 2.0, "beta": 2.0, "score": 0.5, "streak": 0, "best_streak": 0, "last_evidence": "", "weekly": [], "status": "active"}, "健身": {"job": "", "priority": 0.9, "prior": 0.5, "alpha": 2.0, "beta": 2.0, "score": 0.5, "streak": 0, "best_streak": 0, "last_evidence": "", "weekly": [], "status": "active"}, "关系": {"job": "", "priority": 0.7, "prior": 0.5, "alpha": 2.0, "beta": 2.0, "score": 0.5, "streak": 0, "best_streak": 0, "last_evidence": "", "weekly": [], "status": "active"}}}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    (state_dir / "worries.json").write_text('{"items": []}', encoding="utf-8")
    (state_dir / "evolution.json").write_text(
        json.dumps({"version": "v1.0.0", "history": [{"version": "v1.0.0", "date": now, "changelog": ["初始版本"]}]}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()