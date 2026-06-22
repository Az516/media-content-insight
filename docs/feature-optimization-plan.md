# 功能优化计划

生成时间: 2026-06-19

## 目标

围绕当前工作台的 5 个问题做一次小范围、可验证的功能优化:

- 素材池真实图片能正常展示。
- 页面在常见桌面、笔记本、平板、手机宽度下可用。
- 平台选择从“小红书单平台”恢复为后端实际支持的多平台能力。
- AI 内容洞察报告失败时能给出明确原因,并在配置正确后可生成。
- 保持本地、单用户、小规模采集和合规边界,不新增自动触达或批量发送能力。

## 已确认现状

### 1. 素材池图片显示不出来

结论: 主要是后端数据归一化漏字段。

- 真实小红书采集数据在 `third_party/MediaCrawler/database/sqlite_tables.db` 的 `xhs_note.image_list` 字段里有图片 URL。
- 当前业务库 `data/insight.db` 的 `notes.cover_url` 对真实任务为空。
- `backend/app/services/data_store.py` 只读取 `raw.get("cover_url")`,没有从 `image_list` 提取第一张图。
- 前端 `frontend/src/components/NoteCard.tsx` 只使用 `note.cover_url`,所以只能显示“无封面”占位。

### 2. 屏幕大小适配不足

结论: 已有部分移动端导航,但整体布局仍偏固定宽度和桌面优先。

- `frontend/src/components/AppShell.tsx` 使用固定侧栏 `260px` 和主内容最大宽度。
- `frontend/src/index.css` 的 `.app-measure` 固定为 `min(1164px, calc(100vw - 40px))`,大屏出现大量空白,小屏页面内控件仍可能挤压。
- 多个页面存在固定列宽或桌面式网格,需要逐页做断点和溢出检查。

### 3. 平台选择只有小红书

结论: 前后端都被硬编码为小红书。

- `frontend/src/pages/TrackSearch.tsx` 中 `const platforms: PlatformKey[] = ['xhs'];`。
- `frontend/src/data/workbench.ts` 只声明了 `douyin | bilibili | xhs | wechat`,但未与后端支持列表对齐。
- `backend/app/api/tasks.py` 创建任务时没有接收 `platform`。
- `backend/app/services/crawler_service.py` 启动 MediaCrawler 时写死 `--platform xhs`。

### 4. AI 内容报告生成失败

结论: 当前失败原因已从日志确认,是 DeepSeek API Key 未配置。

- `.codex-run-logs/backend.err.log` 显示 `DEEPSEEK_API_KEY` 为空。
- 用户选择 DeepSeek `deepseek-chat`,后端抛出 `deepseek: missing API key`。
- API 层把详细错误折叠成 `502 AI_FAILED`,前端只展示“生成 AI 报告失败,请稍后重试”,所以用户看不到真实原因。

### 5. 后端确实支持很多平台

结论: MediaCrawler 子模块支持的平台比当前业务前端多。

在 `third_party/MediaCrawler/main.py` 和 `third_party/MediaCrawler/cmd_arg/arg.py` 中确认:

- `xhs`: 小红书
- `dy`: 抖音
- `ks`: 快手
- `bili`: B 站
- `wb`: 微博
- `tieba`: 百度贴吧
- `zhihu`: 知乎

当前产品文案里还有“公众号”,但 MediaCrawler 子模块没有公众号实现,需要标记为“暂不可采集”或后续接官方 API。

## 优化方案

### Phase 1: 素材池封面修复

目标: 真实采集任务的素材卡片展示可用封面。

计划:

- 在后端归一化层新增封面提取函数,按平台兼容常见字段:
  - 小红书: `cover_url`, `image_list` 第一张。
  - 抖音: `cover_url`。
  - B 站/快手: `video_cover_url`。
  - 其他平台先保留占位。
- 支持 `image_list` 为逗号分隔字符串、JSON 数组、普通字符串三种形态。
- 对旧数据提供一次性回填脚本或后台迁移方案,把已有 `raw_json.image_list` 回填到 `notes.cover_url`。
- 前端保留占位图,但在图片加载失败时显示更明确的“图片不可访问/已过期”状态。

验收:

- 任务 17 的素材池不再全是“无封面”。
- 至少 1 张小红书图文笔记和 1 张视频笔记封面可展示。
- 无封面或图片过期时页面不报错、不塌布局。

### Phase 2: 响应式布局适配

目标: 常见尺寸下内容可读、按钮可点、布局不横向溢出。

计划:

- 建立断点检查清单: 375px、768px、1366px、1920px。
- 调整全局容器:
  - 小屏使用完整宽度和底部导航。
  - 中屏减少固定列宽。
  - 大屏让内容居中或合理扩展,避免左侧堆在一角。
- 逐页处理:
  - 工作台: 指标卡和双栏模块改为自适应网格。
  - 关键词采集: 输入框、平台卡、右侧设置在小屏纵向排列。
  - 素材池: 卡片网格改成 `auto-fit/minmax`,保证卡片宽度稳定。
  - 报告页: 模型选择和生成按钮在小屏换行,历史列表与正文纵向排列。
  - 平台集成: 双栏信息改为移动端单列。

验收:

- Chrome/Playwright 截图覆盖 375、768、1366、1920 四种宽度。
- 没有横向滚动条。
- 顶栏、底部导航、按钮文字和卡片内容不重叠。

### Phase 3: 多平台选择与采集参数贯通

目标: 前端展示后端可采集平台,创建任务时把平台传到后端,后端按平台启动 MediaCrawler。

计划:

- 定义统一平台配置:
  - 业务平台 key: `xhs`, `dy`, `bili`, `ks`, `wb`, `tieba`, `zhihu`。
  - label、颜色、是否可采集、是否需要登录、备注。
- 修改前端 `TrackSearch`:
  - 平台列表来自统一配置。
  - 可采集平台可选。
  - 暂不支持的平台禁用并解释原因。
- 修改 API:
  - `POST /api/tasks` 接收 `platform`。
  - `tasks` 表增加 `platform` 字段,默认 `xhs` 兼容旧数据。
  - 任务详情和列表返回 `platform`。
- 修改 `CrawlerService`:
  - `run_keyword_search(task_id, platform, keyword, max_notes)`。
  - `_invoke_subprocess(platform, keyword, max_notes)` 不再写死 `xhs`。
  - 读取 MediaCrawler 输出时按平台选择表名和字段映射。
- 注意: 公众号不在 MediaCrawler 当前支持范围,本轮不启用真实采集。

验收:

- 小红书保持可用。
- 至少 B 站/抖音等一个非小红书平台能走到正确的 MediaCrawler `--platform` 参数。
- 不支持的平台不能误导用户发起采集。

### Phase 4: AI 报告失败原因与配置优化

目标: 用户能知道失败原因,配置 API Key 后可生成报告。

计划:

- 后端在生成前做 provider 配置预检:
  - DeepSeek 缺少 `DEEPSEEK_API_KEY` 时返回可读错误。
  - OpenAI 缺少 `OPENAI_API_KEY` 时返回可读错误。
  - Gemini 缺少 `GEMINI_API_KEY` 或 SDK 未安装时返回可读错误。
- 前端报告页展示具体错误:
  - “DeepSeek API Key 未配置,请在 backend/.env 设置 DEEPSEEK_API_KEY 后重启后端。”
  - 网络超时、额度限制、模型名错误分别提示。
- 增加本地开发兜底选项:
  - 可选 `MOCK_AI_REPORT=true` 时生成本地模拟报告,用于无 Key 时验证页面。
  - 默认仍使用真实 provider,避免误以为已经真实生成。
- 文档补充 `.env` 示例。

验收:

- 未配置 Key 时不再只显示“稍后重试”,而是显示具体配置问题。
- 配置有效 Key 后可生成并保存一条 `ai_reports` 记录。
- 不把 API Key 写入日志或前端响应。

### Phase 5: 回归测试与文档

目标: 优化完成后可持续验证。

计划:

- 后端测试:
  - 封面字段归一化。
  - 多平台参数校验。
  - AI provider 缺 Key 错误。
- 前端测试:
  - 平台卡展示与禁用态。
  - 报告错误提示。
  - 素材卡有图/无图两种状态。
- 手工验证:
  - 启动后端和前端。
  - 查看旧任务素材池图片。
  - 创建小红书任务。
  - 尝试无 Key 生成 AI 报告。
  - 视口截图检查。

## 风险与决策点

- 多平台不是简单打开前端按钮: 不同平台的 SQLite 表、字段名和评论 ID 映射都不同,需要做平台适配层。
- 已有 `notes` 表没有 `platform` 字段,多平台落库会涉及数据库迁移。
- MediaCrawler 各平台登录和风控差异较大,本轮只做“小规模、本地、用户主动发起”的采集能力,不做批量自动化。
- 图片 URL 可能有过期、防盗链或跨域限制,即使字段映射正确,仍需要前端失败态和可选本地缓存方案。
- AI 报告真实生成依赖外部 provider 和用户自己的 API Key,无 Key 时只能做配置提示或 mock。

## 建议执行顺序

1. 先修素材池封面,这是低风险且立刻可见的体验问题。
2. 再修 AI 报告错误提示,让失败可诊断。
3. 接着做响应式适配,减少页面使用阻力。
4. 最后做多平台贯通,因为涉及数据库/API/采集读回三层改造,风险最高。
