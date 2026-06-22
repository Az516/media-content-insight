# 功能优化 To Do List

状态说明:

- `[ ]` 未开始
- `[~]` 进行中
- `[x]` 已完成

## 0. 开工前确认

- [x] 等待用户确认是否按本计划执行。
- [x] 确认是否允许修改数据库结构并添加迁移/兼容逻辑。
- [x] 确认多平台第一批优先级: 建议 `xhs -> bili -> dy -> wb -> ks -> zhihu -> tieba`。
- [x] 确认 AI 报告是否需要开发模式 mock。

## 1. 素材池图片

- [x] 在 `backend/app/services/data_store.py` 增加 `cover_url` 归一化函数。
- [x] 支持从 `image_list` 提取第一张图片。
- [x] 支持 B 站/快手等 `video_cover_url` 字段。
- [x] 增加旧数据回填脚本或一次性维护命令。
- [x] 优化 `frontend/src/components/NoteCard.tsx` 图片失败状态。
- [x] 添加封面字段归一化测试。
- [x] 用任务 17 验证素材池封面展示。

## 2. 屏幕适配

- [x] 调整 `frontend/src/index.css` 的主内容宽度策略。
- [x] 调整 `frontend/src/components/AppShell.tsx` 的桌面/移动容器。
- [x] 优化工作台页面响应式布局。
- [x] 优化关键词采集页面响应式布局。
- [x] 优化素材池卡片网格。
- [x] 优化报告页面头部、模型选择、历史列表布局。
- [x] 优化平台集成页面移动端布局。
- [x] 使用 375/768/1366 视口烟测验收。

## 3. 多平台采集

- [x] 建立统一平台配置文件。
- [x] 前端平台选择展示 `xhs/dy/bili/ks/wb/tieba/zhihu`。
- [x] 公众号标记为暂不支持真实采集或移出采集选择。
- [x] `POST /api/tasks` 接收 `platform`。
- [x] `Task` 模型增加 `platform` 字段并兼容旧任务默认 `xhs`。
- [x] `createTask` 前端 API 传递 `platform`。
- [x] `CrawlerService` 去掉 `--platform xhs` 硬编码。
- [x] 为不同平台建立 note/comment 表读取和字段映射。
- [x] 添加多平台参数和字段映射测试。

## 4. AI 报告

- [x] 后端 provider 配置预检。
- [x] 缺少 API Key 时返回明确错误码和错误文案。
- [x] 前端报告页展示具体失败原因。
- [x] 可选实现 `MOCK_AI_REPORT` 开发模式。
- [x] 增加 `.env.example` 或 README 配置说明。
- [x] 添加 DeepSeek/OpenAI/Gemini 缺配置测试。
- [ ] 配置真实 Key 后验证报告保存到 `ai_reports`。当前环境未提供真实 Key,已验证缺 Key 提示与 mock 开关实现。

## 5. 验证与收尾

- [x] 运行后端测试。
- [x] 运行前端类型检查和测试。
- [x] 手工/浏览器验证前端核心路径。
- [x] 更新最终变更说明。
- [ ] 如用户要求,再创建分支/提交。
