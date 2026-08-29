# gao-human-booster Makefile
# 初次使用：make init  →  make build
# 可选备份：make backup-init REMOTE=<github仓库>  →  之后每天自动 make backup

.PHONY: init build install clean backup backup-init backup-status

init:
	@echo "=== 初始化 state ==="
	python3 scripts/init.py

build:
	@echo "=== 生成日历 ==="
	python3 scripts/build_calendar.py

install:
	@echo "=== 安装符号链接到 ~/.agents/skills/ ==="
	python3 scripts/init.py --install --no-build

all: init build

backup:
	@echo "=== 备份到 GitHub（可选功能）==="
	python3 scripts/backup.py push

backup-init:
	@echo "=== 配置备份仓库 ==="
	python3 scripts/backup.py init "$(REMOTE)"

backup-status:
	python3 scripts/backup.py status

clean:
	@echo "=== 清理构建产物（保留 state 和 daily）==="
	rm -rf data/
	rm -f progress-calendar.html
	@echo "✅ 已清理 data/ 和 progress-calendar.html"
	@echo "⚠️  state/ 与 daily/ 未删除，运行 make init 恢复"