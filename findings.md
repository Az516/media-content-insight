# 功能优化调研记录

## 素材池图片

- `frontend/src/components/NoteCard.tsx` 使用 `note.cover_url` 作为封面,为空时显示内联占位图。
- `backend/app/services/data_store.py` 的 `_normalise_note_row` 只从 `raw.get("cover_url")` 写入 `notes.cover_url`。
- 真实小红书数据在 `raw_json.image_list` 中存在图片 URL,但 `notes.cover_url` 为空。
- 任务 17 的样本显示 `image_list` 是逗号分隔的 URL 字符串。
- 结论: 需要后端归一化从 `image_list` 提取第一张图,并可选回填旧数据。

## 响应式布局

- `frontend/src/components/AppShell.tsx` 有移动端底部导航,但桌面侧栏和主容器宽度较固定。
- `.app-measure` 固定 `min(1164px, calc(100vw - 40px))`,大屏内容利用率差。
- 多个页面使用固定列宽或大屏优先网格,需要逐页断点优化。

## 平台选择

- `frontend/src/pages/TrackSearch.tsx` 平台数组硬编码为 `['xhs']`。
- `frontend/src/data/workbench.ts` 声明 `douyin/bilibili/xhs/wechat`,但不等于 MediaCrawler 支持列表。
- `backend/app/api/tasks.py` 创建任务没有 `platform` 参数。
- `backend/app/services/crawler_service.py` 命令行写死 `--platform xhs`。

## MediaCrawler 支持平台

- `third_party/MediaCrawler/main.py` 的 `CrawlerFactory.CRAWLERS` 支持 `xhs/dy/ks/bili/wb/tieba/zhihu`。
- `third_party/MediaCrawler/cmd_arg/arg.py` 的 `PlatformEnum` 同样支持 `xhs/dy/ks/bili/wb/tieba/zhihu`。
- MediaCrawler 不包含公众号采集实现。

## AI 报告失败

- `.codex-run-logs/backend.err.log` 显示启动配置中 `DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`GEMINI_API_KEY` 都为空。
- 同一日志显示 DeepSeek 报告生成失败: `deepseek: missing API key; set the matching *_API_KEY environment variable`。
- API 返回 502 `AI_FAILED`,前端退化成泛化提示。
- 结论: 需要 provider 预检和前端具体错误展示。
