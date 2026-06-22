# 功能优化进度记录

## 2026-06-19

- 使用 `planning-with-files` 工作流。
- 阅读项目结构、前端页面、后端采集服务、AI provider、数据存储逻辑。
- 确认素材池图片问题来自 `image_list -> cover_url` 映射缺失。
- 确认平台选择和后端采集命令都硬编码为小红书。
- 确认 MediaCrawler 支持 `xhs/dy/ks/bili/wb/tieba/zhihu`。
- 确认 AI 报告失败原因是 DeepSeek API Key 未配置。
- 创建优化计划文档和 To Do List。
- 当前状态: 等待用户指令后再进入实现阶段。

## 2026-06-19 实现完成

- 为 `tasks` 增加 `platform` 字段,并在启动兼容迁移中自动补齐旧库。
- `POST /api/tasks` 接收并校验 `xhs/dy/ks/bili/wb/tieba/zhihu` 平台。
- `CrawlerService` 去掉 `--platform xhs` 硬编码,按平台启动 MediaCrawler。
- MediaCrawler 读回按平台选择表名,并给原始行附加 `__platform` 供归一化使用。
- `DataStore` 支持多平台 note/comment ID 映射、封面提取、作者字段兼容。
- 新增 `backend/scripts/backfill_cover_urls.py`,并已对本地 `data/insight.db` 回填任务 17 的 20 条封面。
- 新增 `/api/media/proxy`,前端封面外链通过本地代理加载。
- 前端平台选择展示小红书、抖音、B 站、快手、微博、知乎、贴吧,公众号禁用。
- AI 报告生成前增加 provider Key 预检,缺 Key 时返回明确配置提示。
- 新增 `MOCK_AI_REPORT` 开发开关和 `backend/.env.example`。
- 响应式优化了 AppShell、工作台、关键词采集、素材池、报告、平台集成、任务列表。
- 验证结果:
  - `python -m pytest`: 8 passed。
  - `npm run lint`: passed。
  - `npm test`: 4 passed。
  - `npm run build`: passed。
  - Chrome 视口烟测 `/track-search` 与 `/tasks/17/notes` 在 375/768/1366 下无横向溢出。
  - 本地任务 17: `cover_url` 非空数量为 20。
  - 任务 17 样本封面经 `/api/media/proxy` 请求后上游返回 403,说明旧 CDN URL 已拒绝访问; 代码已保留代理链路和图片不可访问失败态。
