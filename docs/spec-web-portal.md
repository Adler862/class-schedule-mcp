# 课表助手 Web 版 · 设计规格

日期：2026-10-31
分支：`feat/web-portal`
基线：`master`（上游 class-schedule-mcp 原样导入）

## 问题

上游已经是一个 MCP 服务，11 个工具，逻辑扎实。但它只能被 MCP 客户端（Cherry Studio 之类）调用——
**普通学生用不了，评委也没法在 30 秒内看到任何东西**。当前形态无法作为参赛作品演示。

真正的用户痛点：教务系统只给一张课表图片。学生每周要靠截图对课表，不知道「明天几节课」「下周哪天空」，
换手机就丢，也没法进日历提醒。

## 目标

给同一套课表引擎加一个**人可以直接用**的入口：浏览器打开即用，手机优先，零安装、零注册、零后端依赖。

一句话定位：**把教务系统的一张图，变成可查询、可订阅、可提醒的结构化日程。**

## 非目标（本期不做）

- 不做多用户/登录/云端同步
- 不做教务系统自动抓取（合规风险）
- 不改 MCP 工具的对外契约（11 个工具行为保持不变）
- 不做新闻/天气模块的 Web 化（网络依赖会让演示不稳定）

## 交付物

| 文件 | 职责 |
|---|---|
| `src/semester.py` | 学期引擎（唯一实现）：学期起点、周次、单双周、节次时间、某日课程、整周网格 |
| `src/webapp.py` | 纯函数 API 层：路由分派、JSON 序列化、自然语言意图解析、ICS 生成 |
| `src/server.py` | `http.server` 适配器（薄壳，只做 HTTP 编解码） |
| `web/index.html` | 单文件前端：周网格 + 周次切换 + 问答框 + 导出 |
| `tests/test_semester.py` | 学期引擎单测 |
| `tests/test_webapp.py` | API 与意图解析单测 |
| `tests/test_today_schedule_compat.py` | 重构回归：`today_schedule.generate()` 输出逐字不变 |

## 关键设计决策

1. **学期起点从 `courses.json` 的 `meta.semesterStart` 读**，不再硬编码 `2026-08-31`。
   现状是硬编码，换学期就得改代码——这是上游的真实缺陷。
2. **`today_schedule.py` 改为薄封装**，逻辑收进 `semester.py`，但输出保持逐字不变（用回归测试锁住）。
3. **Web 层与 MCP 层输出契约不同**：MCP 返回给大模型的 Markdown 文本，Web 返回结构化 JSON。
   所以两层各自格式化，但共享同一份业务规则（都调 `semester.py`）。
4. **零第三方依赖**：只用标准库。PNG 导出复用已有 `schedule_image.py`（Pillow），作为可选路径，
   失败不影响其他接口。

## API 契约

| 方法 | 路径 | 返回 |
|---|---|---|
| GET | `/` | `web/index.html` |
| GET | `/api/meta` | `{student, className, semesterStart, today, currentWeek, weekday}` |
| GET | `/api/week?week=N` | `{week, days:[{day, date, courses:[...]}]}`，省略 `week` 用当前周 |
| GET | `/api/today?date=YYYY-MM-DD` | `{date, week, weekday, courses:[...], next}` |
| GET | `/api/ask?q=...` | `{intent, text, data}` |
| GET | `/api/export.ics` | `text/calendar`，含全部课程实例 |
| GET | `/healthz` | `ok` |

课表条目结构：
```json
{"name":"数据结构","teacher":"张老师","location":"教学楼 A101",
 "day":1,"startPeriod":1,"endPeriod":2,"start":"08:30","end":"10:10"}
```

## 意图集合（`/api/ask`）

| intent | 触发示例 | 说明 |
|---|---|---|
| `today` | 今天课表 / 今天有课吗 | 当日课程 + 统计 |
| `day` | 明天 / 后天 / 周三 / 昨天 | 指定日期 |
| `week` | 本周课表 / 这周 | 整周概览 |
| `next` | 下一节 / 还有多久上课 | 最近一节课 + 倒计时 |
| `free` | 哪天空 / 下周有空的 | 未来 7 天空闲日 |
| `course` | 数据结构什么时候上 | 课程检索 |
| `help` | 帮助 / 怎么用 | 用法 |
| `unknown` | 其他 | 兜底 + 用法提示 |

## 验收标准

1. `/d/Python/python.exe -m unittest discover -s tests` 全绿。
2. 起服务后手机（同一局域网）能打开，周网格正确渲染，单双周课程不串。
3. 问「明天几节课」能返回结构化结果，不是一段看不懂的文本。
4. `export.ics` 能导入手机日历，事件时间正确。
5. `today_schedule.generate()` 输出与重构前逐字一致。
