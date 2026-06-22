# 功能优化执行计划

Status: complete

## Scope

本计划只覆盖用户提出的 5 个优化点:

- 素材池图片展示。
- 屏幕大小适配。
- 平台选择与多平台采集能力。
- AI 内容报告生成失败。
- 找回 MediaCrawler 后端已有多平台能力。

当前回合已按计划完成功能实现、数据回填和验证。

## Phases

### Phase 1: Investigation

Status: complete

- 查阅前端素材池、平台选择、报告页。
- 查阅后端采集服务、AI provider、数据归一化层。
- 检查本地业务库与 MediaCrawler SQLite 数据。
- 检查运行日志。

### Phase 2: Planning Documents

Status: complete

- 创建 `docs/feature-optimization-plan.md`。
- 创建 `docs/feature-optimization-todo.md`。
- 创建 `findings.md` 和 `progress.md` 作为后续执行记录。

### Phase 3: Await User Approval

Status: complete

- 用户已确认按计划执行。
- 已按 To Do List 分阶段实施。

### Phase 4: Implementation

Status: complete

- 修复素材池封面映射。
- 优化 AI 报告错误提示和配置校验。
- 优化响应式布局。
- 打通多平台参数和平台字段映射。

### Phase 5: Verification

Status: complete

- 运行后端测试。
- 运行前端检查。
- 用浏览器视口烟测验证响应式。
- 用本地数据验证素材池和报告链路。

## Decisions

- 先只写计划,不改功能代码。
- 多平台能力不能只打开前端按钮,需要后端 API、任务模型、CrawlerService 和数据映射同时改。
- 公众号当前不在 MediaCrawler 支持平台内,不能宣称已支持真实采集。
- AI 报告失败已确认是 API Key 未配置,后续应改成明确配置提示。
- 非小红书平台内容 ID 使用平台前缀写入业务库,避免不同平台 ID 撞库。
- 小红书等外链封面走 `/api/media/proxy`,如果 CDN URL 已过期则前端显示明确失败态。

## Errors Encountered

| Error | Attempt | Resolution |
| --- | --- | --- |
| PowerShell/Python 控制台输出部分 emoji 或中文时出现 GBK 编码错误 | 查询 SQLite 样本 | 已取得关键字段信息,后续查询可设置 UTF-8 输出或避免打印特殊字符 |
| Playwright 包存在但自带浏览器二进制未安装 | 浏览器烟测 | 改用系统 Chrome 可执行文件完成 375/768/1366 视口检查 |
| 小红书 CDN 外链在浏览器中触发占位图 | 素材池视觉检查 | 增加后端图片代理和前端代理 URL; 已保留图片不可访问失败态 |
