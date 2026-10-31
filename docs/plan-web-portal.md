# 实施计划 · 课表助手 Web 版

规格见 `docs/spec-web-portal.md`。每个任务独立可验证，预计 2–5 分钟。

## T1 学期引擎：测试先行
- 文件：`tests/test_semester.py`（新建）
- 覆盖：学期第 1 周边界、跨学期负周次、单双周判定、`weeks` 显式列表优先、节次起止时间、某日课程排序、整周 7 天网格
- 验证：`python -m unittest tests.test_semester -v` → 全红（模块不存在）

## T2 实现学期引擎
- 文件：`src/semester.py`（新建）
- 从 `courses.json` 的 `meta.semesterStart` 读学期起点，缺省回退 `2026-08-31`
- 导出：`load()` / `current_week()` / `course_active()` / `period_time()` / `courses_of()` / `week_grid()` / `meta()`
- 验证：T1 转绿

## T3 兼容回归测试
- 文件：`tests/test_today_schedule_compat.py`（新建）
- 断言 `today_schedule.generate(某日)` 输出与重构前快照逐字一致（固定三个日期：有课、无课、单双周边界）
- 验证：先在**未改造**的 `today_schedule.py` 上跑绿，作为基线快照

## T4 改造 today_schedule 为薄封装
- 文件：`src/today_schedule.py`
- 内部改为调用 `semester`，公开函数名与输出格式不变
- 验证：T3 仍绿

## T5 Web API：测试先行
- 文件：`tests/test_webapp.py`（新建）
- 覆盖：`/api/meta` 字段、`/api/week` 结构与单双周过滤、`/api/ask` 八类意图、`/api/export.ics` 的 VEVENT 数量与 DTSTART 格式、404 路径
- 验证：全红

## T6 实现 Web API 层
- 文件：`src/webapp.py`（新建）
- `handle(method, path, query, body, root)` 返回 `(status, content_type, bytes)`，纯函数、不碰 socket
- 验证：T5 转绿

## T7 HTTP 适配器
- 文件：`src/server.py`（新建）
- `http.server.ThreadingHTTPServer` + `BaseHTTPRequestHandler`，静态文件白名单，`--port`/`--host` 参数
- 验证：`curl http://127.0.0.1:8765/healthz` 返回 ok

## T8 前端单页
- 文件：`web/index.html`（新建）
- 周网格（6 大节 × 7 天，单双周灰显）、周次切换、问答框、导出 ICS 按钮、移动端断点
- 验证：`python src/server.py` 后浏览器打开截图

## T9 端到端验收
- 起服务，跑 T1/T3/T5 全部测试，手动验证四类问答与 ICS 导入
- 验证：`python -m unittest discover -s tests` 全绿 + 目视确认

## T10 提交与说明
- 更新 `README.md` 增「Web 版」一节；提交到 `feat/web-portal`
