#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gao-human-booster 可选备份（默认关闭，需用户主动启用）
把 daily/ 与 state/ 镜像到独立的本地备份仓库（~/.agents/ghb-backup），
再推送到用户指定的 GitHub 私有仓库。备份仓库与本 skill 代码仓库完全分离。

用法:
  python3 scripts/backup.py init <REMOTE_URL>   # 配置备份仓库并首次推送
  python3 scripts/backup.py push                # 镜像 daily/ + state/ → 提交 → 推送
  python3 scripts/backup.py status              # 查看备份配置与上次推送时间
"""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
BACKUP_ROOT = Path.home() / ".agents" / "ghb-backup"
STATE_DIR = REPO_DIR / "state"
DAILY_DIR = REPO_DIR / "daily"
CONFIG_PATH = STATE_DIR / "backup.json"


def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"remote": "", "enabled": False, "last_push": ""}


def save_config(cfg):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo)] + list(args), capture_output=True, text=True
    )


def mirror(src: Path, dst: Path):
    """清空 dst 后镜像 src（本地删除也同步到备份）"""
    dst.mkdir(parents=True, exist_ok=True)
    for item in dst.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    if src.exists():
        for item in src.iterdir():
            target = dst / item.name
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
    return dst


def cmd_init(remote):
    if not remote:
        print("❌ 缺少仓库地址，用法：make backup-init REMOTE=git@github.com:用户名/仓库名.git")
        sys.exit(1)
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    if not (BACKUP_ROOT / ".git").exists():
        git(BACKUP_ROOT, "init", "-q")
        git(BACKUP_ROOT, "branch", "-m", "main")
    r = git(BACKUP_ROOT, "remote", "get-url", "origin")
    if r.returncode != 0:
        git(BACKUP_ROOT, "remote", "add", "origin", remote)
    else:
        git(BACKUP_ROOT, "remote", "set-url", "origin", remote)
    (BACKUP_ROOT / "README.md").write_text(
        "# gao-human-booster 数据备份\n\n由 `make backup` 自动生成的个人数据镜像（daily/ + state/），仅存本机 + 你指定的 GitHub 私有仓库。\n",
        encoding="utf-8",
    )
    cfg = {"remote": remote, "enabled": True, "last_push": ""}
    save_config(cfg)
    print(f"✅ 备份仓库已配置 → {BACKUP_ROOT}\n   remote = {remote}\n   首次推送中…")
    if cmd_push(initial=True) != 0:
        print("   ⚠️ 首次推送失败，可稍后运行 `make backup` 重试（本地备份仓库已就绪）")
        sys.exit(1)
    print("✅ 备份已启用。之后复盘完成会自动 `make backup`，也可手动执行。")


def cmd_push(initial=False):
    cfg = load_config()
    if not cfg.get("enabled") or not cfg.get("remote"):
        print("ℹ️  备份未启用（可选功能）。启用：make backup-init REMOTE=<github 私有仓库地址>")
        return 0
    if not (BACKUP_ROOT / ".git").exists():
        print("❌ 备份仓库未初始化，先运行 make backup-init REMOTE=<url>")
        return 1
    mirror(DAILY_DIR, BACKUP_ROOT / "daily")
    mirror(STATE_DIR, BACKUP_ROOT / "state")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    git(BACKUP_ROOT, "add", "-A")
    diff = git(BACKUP_ROOT, "diff", "--cached", "--quiet")
    if diff.returncode == 0 and not initial:
        print("ℹ️  无变化，跳过推送")
        return 0
    git(BACKUP_ROOT, "commit", "-q", "-m", f"backup {stamp}")
    p = git(BACKUP_ROOT, "push", "-q", "origin", "main")
    if p.returncode != 0:
        print(f"⚠️  推送失败（本地已提交，可重试）：{p.stderr.strip()[:200]}")
        return 1
    cfg["last_push"] = stamp.split(" ")[0]
    save_config(cfg)
    print(f"✅ 已备份并推送 → {cfg['remote']}（{stamp}）")
    return 0


def cmd_status():
    cfg = load_config()
    if not cfg.get("enabled"):
        print("备份：未启用（可选功能）\n启用：make backup-init REMOTE=git@github.com:用户名/仓库名.git")
        return
    print(f"备份：已启用\n  本地仓库: {BACKUP_ROOT}\n  remote  : {cfg.get('remote')}\n  上次推送: {cfg.get('last_push') or '—'}")


def main():
    parser = argparse.ArgumentParser(description="gao-human-booster 可选备份")
    sub = parser.add_subparsers(dest="cmd")
    p_init = sub.add_parser("init")
    p_init.add_argument("remote", nargs="?")
    sub.add_parser("push")
    sub.add_parser("status")
    args = parser.parse_args()
    if args.cmd == "init":
        cmd_init(args.remote)
    elif args.cmd == "push":
        sys.exit(cmd_push())
    elif args.cmd == "status":
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
