# 日历与定时提醒（每晚 22:00 复盘提醒）

## 方案选择

| 平台 | 方式 | 说明 |
|---|---|---|
| macOS | osascript 写 Apple 日历（每日重复） | 系统级可见提醒；推荐 |
| 通用 | 生成 .ics 文件（RRULE 每日重复） | 导入 Google Calendar / Outlook / 手机 |
| 自动化 | crontab / launchd 定时调起 AI 客户端 | 到点自动启动复盘会话（需用户决定） |

## 1. macOS Apple 日历（每日 22:00 重复）

```applescript
tell application "Calendar"
  set targetCal to first calendar whose name is "人生维护"
  tell targetCal
    set newEvent to make new event with properties {summary:"晚间复盘（gao-human-booster）", start date:(date "2026-08-26 22:00:00"), end date:(date "2026-08-26 22:15:00"), description:"三栏捕获→领域打分→明日唯一行动→担心箱。23:00 后走极简协议。"}
    make new display alarm at end of display alarms of newEvent with properties {trigger interval:0}
    set newEvent's recurrence to "FREQ=DAILY;COUNT=365"
  end tell
end tell
```

注意：osascript 的 `date "..."` 解析依赖系统区域设置；复杂时间场景 **先生成 .ics 再让用户双击导入更稳**。

## 2. 通用：生成 .ics（每日 22:00 重复）

```ics
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//gao-human-booster//CN
BEGIN:VEVENT
UID:ghb-nightly-review@gao-human-booster
DTSTAMP:20260826T000000Z
DTSTART:20260826T140000Z
DTEND:20260826T141500Z
RRULE:FREQ=DAILY;COUNT=365
SUMMARY:晚间复盘（gao-human-booster）
DESCRIPTION:三栏捕获→领域打分→明日唯一行动→担心箱。23:00后走极简协议。
BEGIN:VALARM
ACTION:DISPLAY
TRIGGER:-PT0M
END:VALARM
END:VEVENT
END:VCALENDAR
```

- `DTSTART` 用 UTC 换算（北京时间 22:00 = 14:00 UTC，非夏令时；夏令时需按季节调整，或告知用户手动校对）。
- 每个 `VEVENT` 一个复盘事件，`RRULE` 每日重复 365 天。
- 提醒 `TRIGGER:-PT0M` = 到点立即提醒；可改为 `-PT15M`（提前 15 分钟）。
- 文件名：`ghb-nightly-review.ics`，生成后告知路径。

## 3. crontab 自动化（可选，用户决定是否启用）

```bash
# 每晚 22:00 自动调起 AI 客户端执行晚间复盘（需用户手动添加，替换 <你的 AI 客户端> 为实际命令）
# crontab -e
0 22 * * * cd <你的 booster 仓库路径> && <你的 AI 客户端> --skill gao-human-booster "开始今晚复盘" >> ~/ghb-nightly.log 2>&1
```

（launchd 同理，格式不同。是否启用由用户决定。注意：crontab 自动化需要终端环境与登录态，失败静默不影响手动使用。）

## 4. 执行准则（给 Agent）

- **写日历是可见副作用：执行前必须 ⬜ 确认**（"写入日历？提醒提前几小时？"）。
- 用户拒绝写日历 → 仅输出 .ics 文件路径，不强行写入。
- 提醒时间默认 22:00（保证 ≤23:00 前有 1 小时余量）；用户连续 3 次复盘晚于 23:00 → 自进化 #4 建议提前到 21:30。
- 生成 .ics / 修改 state 一律用 write 工具，不用 shell 重定向。