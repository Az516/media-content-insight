# 实施计划:多平台内容洞察 MVP (media-content-insight)

## 概述

本实施计划由 `design.md` 与 `requirements.md` 推导而来,严格遵循设计中的 7 个里程碑(M1 项目脚手架 + 子模块 → M2 采集服务 → M3 数据层 → M4 后端 API → M5 素材池 / 笔记详情 → M6 评论洞察 → M7 AI 报告)。出于技术依赖考虑(`CrawlerService` 调用 `DataStore`、API 层依赖 Service 层、前端依赖 API),数据层(M3)的编码任务安排在采集服务(M2)之前完成,以保证每个检查点都能提供端到端可验证的功能。

每条 20 项需求都至少被一个核心实现任务覆盖,设计中的 6 条形式化正确性属性各自作为独立的属性测试子任务,贴近其实现位置以便尽早暴露错误。所有禁止类合规约束(需求 19、20)在 `1.3` 文档化、并通过 API 集合不暴露禁止入口的方式在编码层实现。后端 HTTP 路由集合恰好等于需求 19.1 锁定的 9 条,任何额外路由(包括 `GET /api/ai-reports?task_id=...`)均不允许新增,因此「同一任务下的历史 AI 报告列表」通过扩展 `GET /api/tasks/{task_id}` 响应中的 `reports` 字段提供。

后端使用 **Python + FastAPI + SQLAlchemy 2 + aiosqlite + hypothesis + pytest-asyncio**;前端使用 **React + Vite + TypeScript + Tailwind + react-markdown + vitest**;第三方爬虫 `MediaCrawler` 通过 git submodule 接入,**严禁修改其源码**。

## 任务列表

- [ ] 1. 项目脚手架与合规基线 (M1)
  - [x] 1.1 创建仓库目录结构与基础配置
    - 创建 `backend/`、`frontend/`、`third_party/`、`data/`(含 `data/json/`)、`docs/` 目录骨架
    - 编写仓库根 `.gitignore`,排除 `data/insight.db`、`data/json/`、`frontend/node_modules`、`backend/.venv`、`backend/__pycache__`、`.env` 等
    - 编写 `docker-compose.yml`(可选)用于本地启动后端 + 前端 dev server
    - _需求: 17.1, 20.2_

  - [-] 1.2 引入 MediaCrawler 作为 git submodule
    - 在仓库根 `.gitmodules` 登记 MediaCrawler 远端仓库 URL 与一个固定 commit SHA 指针,目标路径 `third_party/MediaCrawler`
    - 执行 `git submodule add` + `git submodule update --init`,确认 `third_party/MediaCrawler/main.py` 存在
    - 在 `docs/architecture.md` 草稿中明确「子模块仅可通过 commit SHA 指针更新,严禁直接修改其下任何文件」的约定
    - _需求: 6.1, 6.2_

  - [-] 1.3 编写 README 与合规边界文档
    - 创建 `docs/compliance.md`,固化需求 19、20 中的全部禁止条款(自动评论 / 点赞 / 收藏 / 私信 / 关注 / 发布、批量账号、绕过登录验证、二次分发等)与本地化、单一 Cookie、≤20 条采集、≤1 并发、`raw_json` 敏感字段剥离等约束
    - 创建 `README.md`,前 30 行内通过 Markdown 链接形式引用 `docs/compliance.md`,并简要说明项目仅供学习研究
    - _需求: 19.1-19.12, 20.1-20.6_

  - [-] 1.4 初始化后端 FastAPI 项目
    - 创建 `backend/pyproject.toml`,依赖固定为 `fastapi`、`uvicorn[standard]`、`pydantic>=2`、`sqlalchemy>=2`、`aiosqlite`、`httpx`、`python-dotenv`、`openai`、`google-generativeai`(可选)、`pytest`、`pytest-asyncio`、`hypothesis`
    - 创建 `backend/.env.example`,`HOST=127.0.0.1`(不出现 `0.0.0.0`、`::`、外网 IP 或域名),配置 `MEDIA_CRAWLER_ROOT`、`MEDIA_CRAWLER_PYTHON`、`CRAWL_TIMEOUT_SECONDS=600`、`HOT_COMMENT_TOP_N=5`、`AI_PROVIDER=openai`、`LLM_API_TIMEOUT_SECONDS=120`、`MODEL_CONTEXT_LIMIT=8000`、`JSON_ARCHIVE_DIR=data/json`
    - 实现 `backend/app/core/config.py` 用 `pydantic-settings` 加载并暴露上述配置
    - 实现 `backend/app/core/logger.py` 输出结构化日志(含 AuditLog channel)
    - 实现 `backend/app/main.py`:注册根路由占位、CORS(仅 `127.0.0.1` 来源)、生命周期事件、统一异常处理(返回 `{"code","message","detail"}`),uvicorn 默认监听 `127.0.0.1`
    - _需求: 17.2, 19.11, 20.1_

  - [-] 1.5 初始化前端 React + Vite + Tailwind 项目
    - 创建 `frontend/package.json`、`vite.config.ts`、`tsconfig.json`、`tailwind.config.js`、`postcss.config.js`、`index.html`,核心依赖固定为 `react`、`react-dom`、`react-router-dom`、`axios`、`react-markdown`、`remark-gfm`、`vitest`、`@testing-library/react`
    - 实现 `frontend/src/types/models.ts`,定义 `Task`、`Author`、`Note`、`Comment`、`AIReport` 等 TypeScript 接口
    - 实现 `frontend/src/api/client.ts`:Axios 实例 baseURL 默认 `http://127.0.0.1:8000/api`,timeout=30000ms
    - 实现 `frontend/src/App.tsx`:注册 7 条路由占位(`/`、`/tasks`、`/tasks/:taskId`、`/tasks/:taskId/notes`、`/tasks/:taskId/notes/:noteId`、`/tasks/:taskId/insights`、`/tasks/:taskId/report`)+ 通配 `*` 兜底路由(指向占位 NotFound,实际页面在 `9.7` 中接入)
    - _需求: 17.1, 17.2, 17.8_

- [x] 2. 数据层与持久化 (M3)
  - [x] 2.1 定义 SQLAlchemy ORM 模型与 DDL 约束
    - 在 `backend/app/models/` 下分别实现 `task.py`、`author.py`、`note.py`、`comment.py`、`ai_report.py`,匹配 design §2 的 5 张表
    - 通过 SQLAlchemy `CheckConstraint` 落实 `tasks.status IN ('pending','running','success','failed')`、`notes.type IN ('normal','video')`、`comments.is_top_hot IN (0,1)`、`ai_reports.provider IN ('openai','deepseek','gemini')`
    - 配置外键 `ON DELETE CASCADE`:`notes→tasks`、`comments→notes`、`comments→comments(parent_comment_id)`、`ai_reports→tasks`;`notes→authors` 设 `ON DELETE SET NULL`
    - 创建索引:`idx_notes_task_id`、`idx_notes_author_id`、`idx_comments_note_id`、`idx_comments_parent_id`、`idx_comments_hot(note_id, is_top_hot)`、`idx_ai_reports_task_id`
    - 实现 `backend/app/core/db.py`:基于 `aiosqlite` 创建 `async_engine` 与 `async_sessionmaker`,启动时执行 `Base.metadata.create_all` 初始化 `data/insight.db`,启用 `PRAGMA foreign_keys=ON`
    - _需求: 3.6, 9.1, 9.7, 9.8, 20.2_

  - [x] 2.2 实现 DataStore 任务状态机方法
    - 在 `backend/app/services/data_store.py` 中实现 `mark_task_running` / `mark_task_success` / `mark_task_failed`
    - 每个方法通过 `SELECT ... FOR UPDATE`(或 SQLite 的事务串行)读取当前 `status`,断言前置状态 ∈ 允许集合,违例时抛出 `AssertionError` 并 `rollback`,保证 `status`、`started_at`、`finished_at`、`error_msg` 四字段保持转移前取值
    - `mark_task_running`:`pending → running`,写入 `started_at = utcnow().isoformat(timespec='seconds')`,`finished_at` 与 `error_msg` 保持 NULL
    - `mark_task_success`:`running → success`,写入 `finished_at`、`note_count`、`json_path`,`error_msg` 保持 NULL
    - `mark_task_failed`:`pending|running → failed`,写入 `finished_at`,`error_msg` 截断为前 1000 字符
    - _需求: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 2.3 属性测试:任务状态机单调推进
    - **属性 5: 任务状态机单调推进**
    - **校验需求 3.1, 3.2**
    - 文件:`backend/tests/test_state_machine_property.py`,使用 `hypothesis` 生成 `(operation, target_status)` 序列(操作集 = {`mark_running`,`mark_success`,`mark_failed`}),分别施加在初始 `status` 各取值的任务上
    - 断言:任意非允许集合 `{pending→running, running→success, running→failed}` 的转移触发 `AssertionError`,且事务回滚后 `tasks.status`、`started_at`、`finished_at`、`error_msg` 四字段值与转移前完全一致
    - 断言:允许的转移成功后,`status` 落在 `{pending, running, success, failed}` 内,从不回退

  - [x] 2.4 实现 upsert 写入与评论树完整性校验
    - 在 `data_store.py` 中实现 `upsert_authors_from_raw(raw_notes)`、`upsert_notes(task_id, raw_notes)`、`upsert_comments(raw_comments)`
    - 使用 SQLite `INSERT ... ON CONFLICT(<pk>) DO UPDATE SET ...` 覆盖除主键(`user_id` / `note_id` / `comment_id`)外的所有字段
    - 写入顺序保证:`authors` → `notes`(关联 `task_id`) → `comments` 一级评论(`parent_comment_id IS NULL`) → 二级评论
    - 写入二级评论时,先在事务内 `SELECT note_id FROM comments WHERE comment_id = :parent_id`,父评论不存在或 `note_id` 与子评论 `note_id` 不一致则 `RAISE IntegrityError`,调用方将该任务转 `failed` 并写入「评论树结构错误」`error_msg`
    - _需求: 7.3, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ]* 2.5 属性测试:note_id 唯一
    - **属性 1: note_id 唯一**
    - **校验需求 9.1, 9.2**
    - 文件:`backend/tests/test_note_id_unique_property.py`,使用 `hypothesis` 生成 `raw_notes` 列表(允许 `note_id` 重复出现 ≥1 次,字段值随机)
    - 断言:连续调用 `upsert_notes(task_id, raw_notes)` 后,`SELECT note_id, COUNT(*) FROM notes GROUP BY note_id` 中所有 count 等于 1
    - 断言:对于重复出现的 `note_id`,数据库中该行除 `note_id` 外字段取最后一次写入的值

  - [ ]* 2.6 属性测试:评论树结构完整
    - **属性 2: 评论树结构完整**
    - **校验需求 9.5, 9.6**
    - 文件:`backend/tests/test_comment_tree_property.py`,使用 `hypothesis` 生成 (a) 一级评论列表、(b) 二级评论列表(包含合法、`parent_comment_id` 不存在、`parent_comment_id` 指向不同 `note_id` 三种情况)
    - 断言:合法输入下 `upsert_comments` 后,∀ `c.parent_comment_id ≠ NULL` ⇒ ∃ `p ∈ comments`:`p.comment_id = c.parent_comment_id ∧ p.note_id = c.note_id`
    - 断言:非法输入下 `upsert_comments` 抛出 `IntegrityError`,关联任务被转入 `failed` 状态且 `error_msg` 包含「comment_tree」字样

  - [x] 2.7 实现 archive_json、json_path 回写、敏感字段剥离与读取接口
    - 实现 `archive_json(task_id) -> Path`:写入 `data/json/{task_id}.json`,顶层字段恰好为 `{"task_id","exported_at","notes","comments"}`,`exported_at` 为当前 UTC ISO8601 时间戳(精确到秒),使用 UTF-8 + `ensure_ascii=False`,中文原样保留
    - 写入完成后将 `tasks.json_path` 更新为 `"data/json/{task_id}.json"`(相对仓库根)
    - 在 `upsert_notes` 入库前,从 `raw_json` 中剔除 `phone`、`mobile`、`email`、`bind_email`、`id_card`、`id_number`、`identity` 等敏感键(忽略大小写)及其取值,持久化结果不保留原值
    - 实现 `load_for_ai(task_id) -> tuple[str, list[Note], list[Comment]]`:返回 `(keyword, notes, comments)`,只 SELECT 不修改任何表;实现 `save_ai_report(report) -> int`:仅向 `ai_reports` 表插入一条记录并返回新 `id`,不读写其他表
    - 实现 `list_ai_reports(task_id) -> list[AIReportSummary]`:仅 SELECT,按 `created_at DESC` 返回 `{id, provider, model, prompt_version, created_at}`,供需求 16.5 与 5.4 中 `reports` 字段使用
    - _需求: 10.1, 10.2, 10.7, 15.5, 15.6, 16.5, 20.3, 20.4_

  - [ ]* 2.8 单元测试:JSON 归档往返等价
    - 文件:`backend/tests/test_archive_json_roundtrip.py`,构造 fake `notes` / `comments`,先调用 `upsert_*`,再调用 `archive_json`,从生成的 JSON 文件反序列化后的 `notes` / `comments` 字段名集合与字段取值与数据库 `SELECT *` 结果完全一致
    - 断言文件以 UTF-8 编码、中文字符未发生 `\u` 转义
    - _需求: 10.3_

- [x] 3. 采集服务 CrawlerService (M2)
  - [x] 3.1 实现 _invoke_subprocess 与启动前置校验
    - 在 `backend/app/services/crawler_service.py` 中实现 `_invoke_subprocess(keyword, max_notes)`
    - 启动前校验 `settings.MEDIA_CRAWLER_ROOT` 解析后的绝对路径存在、是目录、且其下存在 `main.py`;不满足则抛出 `CrawlerError("media_crawler_not_ready")`,调用方据此把任务转 `failed`
    - 通过 `asyncio.create_subprocess_exec` 启动 `settings.MEDIA_CRAWLER_PYTHON main.py --platform xhs --type search --keywords <keyword> --save_data_option db --get_comment yes --get_sub_comment yes --max_notes <max_notes>`,`cwd` 设为子模块绝对路径
    - 通过 `asyncio.wait_for(proc.communicate(), timeout=settings.CRAWL_TIMEOUT_SECONDS)` 包裹,超时后调用 `proc.kill()` 并 `await proc.wait()`,确保 10 秒内子进程释放,抛出 `asyncio.TimeoutError`
    - 运行期不写入或删除 `third_party/MediaCrawler/` 目录下任何文件
    - _需求: 6.3, 6.4, 6.5, 6.6, 8.3, 19.2_

  - [x] 3.2 实现错误分类与 _read_mc_output
    - 子进程返回码非 0 时:`stderr.lower()` 包含 `"login"` → 抛 `LoginExpiredError(stderr[:500])`;否则包含 `"risk"` 或 `"verify"` → `RiskControlError(stderr[:500])`;其余 → `CrawlerError("unexpected: " + stderr[:500])`
    - 实现 `_read_mc_output(raw_dir)`:从 MediaCrawler 输出的 `data/xhs/contents.db` / `comments.db` 或 JSON 中读取 `raw_notes` / `raw_comments`(纯只读)
    - 在 `_read_mc_output` 阶段对二级评论按 `(note_id, like_count DESC)` 截取每条笔记 Top `settings.HOT_COMMENT_TOP_N` 条且仅保留 `is_top_hot=1`(实现需求 13.5)
    - _需求: 6.5, 7.2, 8.1, 8.2, 13.5_

  - [x] 3.3 实现 run_keyword_search 主流程与 AuditLog
    - 入口先调用 `store.mark_task_running(task_id)`
    - TRY 块按序:`raw_dir <- _invoke_subprocess(keyword, max_notes)` → `(raw_notes, raw_comments) <- _read_mc_output(raw_dir)` → `upsert_authors_from_raw(raw_notes)` → `upsert_notes(task_id, raw_notes[:min(len(raw_notes), max_notes)])` → `upsert_comments(raw_comments)` → `archive_json(task_id)` → `mark_task_success(task_id, note_count=min(len(raw_notes), max_notes), json_path=...)`
    - 若 `len(raw_notes) == 0`:转 `mark_task_failed(task_id, "no_notes_returned")`,不写 `notes` / `comments` / `authors`,不生成 JSON 归档
    - 异常分支:`LoginExpiredError` → `error_msg="login_expired: <stderr[:500]>"`;`RiskControlError` → `error_msg="risk_control: <stderr[:500]>"`,**不发起任何自动重试**;`asyncio.TimeoutError` → `error_msg="timeout"`;其他 → `error_msg="unexpected: <e[:500]>"`
    - 任务进入 `success` 或 `failed` 终态时,通过 logger 写 AuditLog 记录 `{keyword, started_at, finished_at, note_count, status}` 五元组(`status ∈ {success, failed}`,时间格式 ISO8601 精确到秒)
    - _需求: 7.1, 7.2, 7.3, 7.4, 7.5, 7.7, 7.8, 7.9, 8.1, 8.2, 8.3, 8.4, 8.5, 20.5_

  - [ ]* 3.4 属性测试:采集数量上限与 note_count 一致性
    - **属性 3: 采集数量上限**
    - **校验需求 7.6, 7.7, 1.5**
    - 文件:`backend/tests/test_max_notes_property.py`,使用 `hypothesis` 生成 `len(raw_notes) ∈ [0, 100]`、`max_notes ∈ [1, 20]` 的组合,mock `_invoke_subprocess` 返回该列表
    - 断言:任务进入 `success` 时,`tasks.note_count = min(len(raw_notes), max_notes) ∧ note_count ≤ max_notes ≤ 20`,`SELECT COUNT(*) FROM notes WHERE task_id = t` 等于 `tasks.note_count`(覆盖 7.7)
    - 断言:`len(raw_notes) == 0` 时任务为 `failed` 且 `notes` 表中本任务对应记录数 = 0

  - [ ]* 3.5 单元测试:CrawlerService 错误分支
    - 文件:`backend/tests/test_crawler_service.py`,mock 子进程 stderr 分别为 `"login expired"`、`"Risk Warning"`、`"verify code required"`、运行超时、其他未知输出
    - 断言任务终态为 `failed`,`error_msg` 前缀依次为 `login_expired`、`risk_control`、`risk_control`、`timeout`、`unexpected`
    - 断言 `RiskControlError` 后系统不发起任何自动重试
    - _需求: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 4. 检查点 - 采集端到端可跑通
  - 在本地以无关测试关键词触发一次完整采集,确认 `tasks` 表状态机推进正确、`notes` / `comments` / `authors` 入库、`data/json/{task_id}.json` 归档存在、敏感字段已剥离、AuditLog 已写入。运行 §1-§3 全部测试(含属性测试 1、2、3、5),确保通过;遇到问题及时与用户确认。

- [ ] 5. 任务相关 REST API (M4 第一组)
  - [x] 5.1 实现 POST /api/tasks 创建任务与并发校验
    - 在 `backend/app/schemas/task.py` 定义 `TaskCreateRequest`(`keyword: str`,`max_notes: int = 20`)与 `TaskCreateResponse`
    - 在 `backend/app/api/tasks.py` 注册 `POST /api/tasks`
    - 校验:`keyword.strip()` 长度 ∈ `[1, 50]`,否则 422 `INVALID_KEYWORD`;`max_notes` 整数 ∈ `[1, 20]`,否则 422 `OVER_LIMIT`(均不在 `tasks` 表中创建任何记录)
    - 在显式开启串行隔离的事务内执行 `SELECT COUNT(*) FROM tasks WHERE status='running'`,>0 时返回 409 `TASK_BUSY` 且不修改任何 running 任务字段;事务读取本身失败返回 500 `INTERNAL_ERROR`
    - 通过 `BackgroundTasks` 异步触发 `CrawlerService.run_keyword_search(task_id, keyword, max_notes)`;接口在 2 秒内返回 202 + `{"task_id": <int>, "status": "pending"}`
    - 数据库插入失败或未预期异常返回 500 `INTERNAL_ERROR`,且不在 `tasks` 表中保留任何记录
    - _需求: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 2.1, 2.2, 2.4, 2.6_

  - [ ]* 5.2 属性测试:全局并发限制
    - **属性 6: 全局并发限制**
    - **校验需求 2.1, 2.2**
    - 文件:`backend/tests/test_concurrency_property.py`,使用 `hypothesis` + `asyncio.gather` 生成任意并发的 `POST /api/tasks` 请求序列(任意 keyword、`max_notes` 组合)
    - 在每次并发批次后断言 `SELECT COUNT(*) FROM tasks WHERE status='running' ≤ 1`,且并发争抢中除一个请求成功(202 + `pending`)外,其余请求必须返回 409 `TASK_BUSY` 而非创建新任务
    - 通过 mock `CrawlerService.run_keyword_search` 让其挂起一段时间以制造可观察的 running 窗口

  - [-] 5.3 实现 GET /api/tasks 任务列表
    - 支持 `status` / `limit` / `offset` 查询参数;按 `(created_at DESC, id DESC)` 排序,以保证返回顺序确定
    - 默认 `limit=20` 范围 `[1,100]`、`offset=0` 范围 `[0,+∞)`
    - 越界、非整数或 `status` 不在 `{pending,running,success,failed}` 时返回 422 `INVALID_QUERY_PARAM`,且不返回任何任务记录
    - 响应 `{"items":[...],"total":<int>}`,`total` 为本次过滤条件下任务总数;每条 item 含 `id`、`keyword`、`status`、`note_count`、`started_at`、`finished_at`、`created_at`
    - _需求: 4.1, 4.2, 4.3, 4.4, 4.6_

  - [~] 5.4 实现 GET /api/tasks/{task_id} 详情、summary 与历史报告内嵌
    - 顶层字段含 `id`、`keyword`、`status`、`note_count`、`max_notes`、`started_at`、`finished_at`、`error_msg`、`json_path`、`summary`、`reports`
    - `summary.total_likes = SUM(notes.liked_count WHERE task_id=t)`、`summary.total_comments = COUNT(comments INNER JOIN notes ON note_id WHERE task_id=t)`、`summary.top_authors` 为按所属笔记数降序、长度上限 5 的数组,每项含 `user_id`、`nickname`、`note_count`
    - `reports` 由 `Data_Store.list_ai_reports(task_id)` 返回,按 `created_at DESC` 排序,每项含 `id`、`provider`、`model`、`prompt_version`、`created_at`,用于支撑需求 16.5 的历史报告列表(避免新增独立路由违反需求 19.1)
    - `task_id` 不存在返回 404
    - _需求: 5.1, 5.2, 16.5_

  - [~] 5.5 实现 GET /api/tasks/{task_id}/export JSON 导出
    - `tasks.json_path` 为空或目标文件不存在返回 404,响应体包含说明归档不可用的错误指示
    - 文件存在时返回 200,Content-Type 为 `application/json`,响应头 `Content-Disposition: attachment; filename="task_{task_id}.json"`,响应体为该归档文件的全部内容
    - _需求: 10.4, 10.5, 10.6_

  - [ ]* 5.6 单元测试:任务 API 错误码与分页
    - 文件:`backend/tests/test_api_tasks.py`(独立于其他 API 测试文件,避免同 wave 文件冲突)
    - 使用 `httpx.AsyncClient` 走 ASGI,覆盖 `INVALID_KEYWORD`、`OVER_LIMIT`、`TASK_BUSY`、`INVALID_QUERY_PARAM`、404、500 全部错误码以及 202、200 正常路径
    - 验证 `GET /api/tasks/{id}` 响应中 `reports` 字段按 `created_at DESC` 排序、空时为 `[]`
    - _需求: 1.4, 1.5, 1.7, 2.2, 4.6, 5.2, 10.6_

- [ ] 6. 笔记与评论 REST API (M4 第二组 + M6 后端)
  - [x] 6.1 实现 GET /api/tasks/{task_id}/notes 列表分页
    - 在 `backend/app/api/notes.py` 与 `backend/app/schemas/note.py` 实现该端点
    - items 按 `notes.publish_time DESC` 排序;`limit ∈ [1,100]` 默认 20、`offset ∈ [0, 1_000_000]` 默认 0
    - 任务不存在返回 404 + 错误信息;参数非法返回 422 + 错误信息
    - 每条 item 含 `note_id`、`title`、`type`、`cover_url`、`liked_count`、`collected_count`、`comment_count`、`author{user_id, nickname}`
    - _需求: 11.1, 11.2, 11.3, 11.4_

  - [-] 6.2 实现 GET /api/notes/{note_id} 详情与评论树
    - 响应 `{"note": {...}, "author": {...}, "comments": [...]}`
    - `note` 至少含 `note_id`、`title`、`desc`、`type`、`cover_url`、`video_url`、`liked_count`、`collected_count`、`comment_count`;`author` 至少含 `user_id`、`nickname`、`avatar`、`fans_count`
    - 一级评论(`parent_comment_id IS NULL`)按 `(like_count DESC, create_time DESC)` 排序;二级评论按 `create_time ASC` 嵌入到对应一级评论的 `sub_comments`
    - 每条评论保留 `comment_id`、`user_id`、`nickname`、`content`、`like_count`、`sub_comment_count`、`create_time`、`is_top_hot`
    - `note_id` 不存在返回 404 `NOTE_NOT_FOUND`
    - _需求: 12.1, 12.2, 12.3, 12.4_

  - [x] 6.3 实现 GET /api/tasks/{task_id}/comments 评论聚合
    - 在 `backend/app/api/comments.py` 实现该端点
    - `top_keywords`:对评论 `content` 用 `jieba` 或简单空格 + 标点分词后统计,过滤停用词,最多 50 项,按 `(count DESC, word ASC)` 排序
    - `sentiment`:`positive` / `neutral` / `negative` ∈ `[0.0, 1.0]`,三者之和 = 1.0(±0.01),MVP 用规则法或离线打分
    - `top_hot_comments`:仅 `is_top_hot=1`,按 `(like_count DESC, create_time DESC)` 排序,最多 20 条
    - 任务不存在返回 404;任务存在但无评论时返回 `total_comments=0`、`top_keywords=[]`、`top_hot_comments=[]`、`sentiment={"positive":0.0,"neutral":1.0,"negative":0.0}`
    - _需求: 13.1, 13.2, 13.3, 13.4, 13.7, 13.8_

  - [ ]* 6.4 单元测试:笔记 / 评论 / 评论聚合 API
    - 文件:`backend/tests/test_api_notes_comments.py`(独立于其他 API 测试文件,避免同 wave 文件冲突)
    - 覆盖空数据、`is_top_hot` 过滤、分页边界、404 路径、`sentiment` 求和容差
    - 验证响应 schema 与排序规则
    - _需求: 11.1, 11.2, 11.3, 11.4, 12.1, 12.2, 12.3, 12.4, 13.1, 13.2, 13.3, 13.4, 13.7, 13.8_

- [~] 7. 检查点 - 后端 API 全量联通
  - 启动 FastAPI 后访问 `/docs`,确认恰好 9 条路由(`POST /api/tasks`、`GET /api/tasks`、`GET /api/tasks/{id}`、`GET /api/tasks/{id}/notes`、`GET /api/notes/{id}`、`GET /api/tasks/{id}/comments`、`POST /api/tasks/{id}/ai-report`(占位)、`GET /api/ai-reports/{id}`(占位)、`GET /api/tasks/{id}/export`)已注册,且不存在任何额外路由(满足需求 19.1);运行 §5、§6 全部测试(含属性测试 6),遇到问题及时与用户确认。

- [ ] 8. 前端通用组件、API 客户端与 Hook (M5 基础)
  - [x] 8.1 实现 ComplianceBanner 与全局布局
    - 文件:`frontend/src/components/ComplianceBanner.tsx`
    - 顶部固定渲染文案「本工具仅供学习研究和小规模数据分析,请遵守平台条款,不得用于自动化营销、批量发布或商业用途」,文案不可被截断或省略
    - 在 `App.tsx` 全局布局组件中固定挂载 `ComplianceBanner`,路由切换、滚动期间持续可见,且不提供关闭 / 隐藏入口
    - _需求: 17.7, 18.1, 18.2_

  - [-] 8.2 实现 KeywordInput 组件
    - 文件:`frontend/src/components/KeywordInput.tsx`,`onSubmit({keyword, maxNotes})`
    - 关键词受控,`trim` 后非空且长度 ≤ 50 才允许提交
    - `maxNotes` 受控为整数,范围 `[1, 20]`;非整数 / `<1` / `>20` 时禁用提交按钮并显示文案:`>20` 时「单次采集上限 20 条」、`<1` 时「单次采集至少 1 条」
    - _需求: 1.1, 17.3, 17.4_

  - [-] 8.3 实现 NoteCard 组件
    - 文件:`frontend/src/components/NoteCard.tsx`
    - 展示 `cover_url`、`title`、`liked_count`、`collected_count`、`comment_count`
    - `cover_url` 缺失或 null 用占位图,`title` 缺失用占位「-」,数值字段缺失用「-」;不抛渲染异常
    - 点击触发 `onClick(noteId)`
    - _需求: 11.7, 17.5, 17.6_

  - [-] 8.4 实现 CommentTree 组件
    - 文件:`frontend/src/components/CommentTree.tsx`,`comments: CommentNode[]`(一级评论数组,内含 `sub_comments`)
    - 渲染一级 + 二级评论嵌套结构
    - `is_top_hot=1` 评论附加显式「热门」徽标或差异化背景;`is_top_hot=0` 不出现该标识
    - `comments` 为空数组时渲染「暂无评论」占位文案,不渲染空白容器
    - _需求: 12.5, 12.6, 12.7_

  - [-] 8.5 实现 MarkdownView 组件
    - 文件:`frontend/src/components/MarkdownView.tsx`,基于 `react-markdown` + `remark-gfm` 渲染 Markdown
    - _需求: 16.3_

  - [-] 8.6 实现 usePolling Hook 与 API 封装
    - 文件:`frontend/src/hooks/usePolling.ts`,签名 `usePolling<T>(fn: () => Promise<T>, intervalMs: number, shouldStop: (data: T) => boolean): {data: T|null, loading: boolean, error: Error|null}`,单次请求超时 5 秒
    - 在 `frontend/src/api/{tasks,notes,reports}.ts` 中封装所有后端方法;请求出错或非 2xx 时由调用方决定重试 / 暂停
    - _需求: 5.3, 5.4, 5.6_

  - [ ]* 8.7 前端组件单元测试
    - 文件:`frontend/src/components/__tests__/components.test.tsx`,使用 `vitest` + `@testing-library/react` 覆盖 `KeywordInput` 边界(超上限 / 低于下限 / 空 keyword)、`NoteCard` 字段缺失、`CommentTree` 热门标识与空状态
    - _需求: 12.6, 12.7, 17.4, 17.6_

- [ ] 9. 前端核心页面 (M5 + M6)
  - [~] 9.1 实现首页 Home (`/`)
    - 文件:`frontend/src/pages/Home.tsx`
    - 顶部嵌入 `KeywordInput`,提交时调用 `POST /api/tasks`,202 后 1 秒内 `navigate('/tasks/{task_id}')`;非 2xx 显示包含错误码的提示且不跳转
    - 当存在 `status='running'` 任务时,「开始采集」按钮禁用且不可点击,并在按钮旁显示当前 `task_id`
    - 终态(`success` / `failed`)5 秒内重新启用按钮并清除「当前正在执行 task_id」显示
    - 页脚固定展示「单次采集上限 20 条笔记,同一时刻仅允许一个采集任务运行」
    - 下方列出最近 10 条历史任务卡片
    - _需求: 1.1, 1.6, 1.8, 2.3, 2.5, 18.3_

  - [~] 9.2 实现任务管理页 TaskManager (`/tasks`)
    - 文件:`frontend/src/pages/TaskManager.tsx`
    - 表格展示 `id`、`keyword`、`status`、`note_count`、`started_at`、`finished_at`,支持按 `status` 筛选与分页
    - 响应 `items` 为空数组时显示空状态提示而非空白表格
    - _需求: 4.5_

  - [~] 9.3 实现任务详情页 TaskDetail (`/tasks/:taskId`)
    - 文件:`frontend/src/pages/TaskDetail.tsx`
    - 通过 `usePolling` 每 2 秒调用 `GET /api/tasks/{task_id}`,单次请求超时 5 秒;状态由 `running` 转入终态时停止轮询并以最新字段重新渲染
    - `success` 时展示「查看素材池」「查看评论洞察」「查看 AI 报告」三个入口
    - `failed` 时根据 `error_msg` 前缀显示对应处置建议:`login_expired`(重新登录)、`risk_control`(等待冷却 / 人工处理)、`timeout`(缩小范围 / 稍后重试)、`unexpected`(查看任务详情 / 联系管理员)
    - 轮询请求非 2xx 或网络错时:暂停轮询、保留最近一次成功响应、顶部显示带「重试」按钮的错误提示
    - _需求: 5.3, 5.4, 5.5, 5.6, 8.6_

  - [~] 9.4 实现素材池页 NoteList (`/tasks/:taskId/notes`)
    - 文件:`frontend/src/pages/NoteList.tsx`
    - 使用 `NoteCard` 网格渲染笔记列表;为空时显示空状态提示
    - 点击 `NoteCard` 跳转 `/tasks/:taskId/notes/:noteId`
    - _需求: 11.5, 11.6, 11.7_

  - [~] 9.5 实现笔记详情页 NoteDetail (`/tasks/:taskId/notes/:noteId`)
    - 文件:`frontend/src/pages/NoteDetail.tsx`
    - 渲染笔记正文(`title`、`desc`;`video_url` 非空时渲染视频播放器,否则渲染 `cover_url` 封面图)
    - 渲染作者卡片(`avatar`、`nickname`、`fans_count`)
    - 嵌入 `CommentTree` 渲染一级 + 二级评论
    - _需求: 12.5_

  - [~] 9.6 实现评论洞察页 Insights (`/tasks/:taskId/insights`)
    - 文件:`frontend/src/pages/Insights.tsx`
    - 调用 `GET /api/tasks/{task_id}/comments`,渲染「高频词列表 / 词云」「情感分布饼图」「热门评论 Top 列表」三块视图
    - 任务存在但无评论时,基于后端默认值渲染空状态视图
    - _需求: 13.6, 13.8_

  - [~] 9.7 实现 404 兜底页
    - 文件:`frontend/src/pages/NotFound.tsx`,在 `App.tsx` 通配路由 `*` 上替换 `1.5` 中的占位组件
    - 页面内提供「返回首页」入口跳转到 `/`
    - _需求: 17.8_

  - [ ]* 9.8 前端端到端冒烟测试
    - 文件:`frontend/src/__tests__/e2e_smoke.test.tsx`,使用 `vitest` 或 `playwright` 模拟「输入关键词 → 任务详情 → 素材池 → 笔记详情 → 评论洞察」最小流程;mock 后端响应
    - _需求: 1.6, 5.5, 11.7, 12.5_

- [~] 10. 检查点 - 前后端端到端用户流程
  - 联调前后端,真实跑通「输入关键词 → 等待任务完成 → 素材池 → 笔记详情(评论树展开) → 评论洞察」,确认 `ComplianceBanner` 在每个页面顶部固定显示且无关闭入口;运行 §8、§9 全部测试,遇到问题及时与用户确认。

- [ ] 11. AI 报告模块 (M7)
  - [x] 11.1 实现 AIAnalyzer 抽象基类、PROMPT_V1 与 build_prompt
    - 在 `backend/app/services/ai_analyzer.py` 实现 `AIAnalyzer ABC`、`AIReport` dataclass、`PROMPT_V1` 模板(包含 `{keyword}` / `{materials}` 两个槽位)
    - `build_prompt(keyword, notes, comments)`:笔记按 `liked_count DESC` 取 Top 20,`desc` 截断到前 80 字符;评论按 `like_count DESC` 取 Top 50,`content` 截断到前 120 字符;返回组装好的 materials 字符串
    - 实现 `backend/app/utils/token_count.py` 估算 token 数(可基于 `len(prompt)//4` 或 `tiktoken`),`analyze` 调用 `_call_llm` 前 `assert estimated_tokens(prompt) < settings.MODEL_CONTEXT_LIMIT`
    - `analyze(task_id)` 内部仅通过 `store.load_for_ai(task_id)` 读取 `keyword/notes/comments`,通过 `store.save_ai_report(report)` 写入,**不直接 query 或修改** `notes/comments/authors/tasks` 任意表
    - _需求: 14.6, 14.7, 14.8, 15.5, 15.6_

  - [ ] 11.2 实现 OpenAI / DeepSeek / Gemini Provider 与工厂方法
    - `OpenAIAnalyzer`(使用 `openai` SDK)、`DeepSeekAnalyzer`(OpenAI 兼容 base_url)、`GeminiAnalyzer`(`google-generativeai` SDK),三者各自实现 `_call_llm(prompt) -> str`
    - 单次 LLM 调用超时 `settings.LLM_API_TIMEOUT_SECONDS`(默认 120 秒);超时 / 网络 / 鉴权错均冒泡为 `LLMError`
    - `make_analyzer(provider, model, store)`:`provider = (provider or os.getenv("AI_PROVIDER", "openai")).lower()`;不在 `{openai, deepseek, gemini}` 抛 `ValueError`;返回对应 Provider 实例
    - _需求: 14.3, 14.4, 14.5, 14.10_

  - [~] 11.3 实现 POST /api/tasks/{task_id}/ai-report
    - 在 `backend/app/api/ai_reports.py` 与 `backend/app/schemas/ai_report.py` 注册端点
    - 校验:`task_id` 不存在返回 404 `TASK_NOT_FOUND`;`task.status != 'success'` 返回 409 `TASK_NOT_READY`(不发起 LLM 调用,不创建任何 `ai_reports` 记录);`provider`(忽略大小写)不在 `{openai, deepseek, gemini}` 返回 422 `INVALID_PROVIDER`;`model` 长度不在 `[1, 100]` 返回 422
    - 调用 `make_analyzer(provider, model, store).analyze(task_id)`;`LLMError` 时返回 502 `AI_FAILED` 且不写入任何 `ai_reports` 记录
    - 成功时通过 `store.save_ai_report` 插入记录(`task_id`、`provider`、`model`、`prompt_version='v1'`、`report_md`(非空)、`created_at` UTC ISO8601 精确到秒),返回 202 + `{"report_id": <int>, "status": "pending"}`
    - _需求: 14.1, 14.2, 14.3, 14.4, 14.9, 14.10, 14.12, 14.13_

  - [ ]* 11.4 属性测试:AI 报告生成只读
    - **属性 4: AI 报告只读**
    - **校验需求 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8**
    - 文件:`backend/tests/test_ai_readonly_property.py`,使用 `hypothesis` 生成任意 `(authors, notes, comments, tasks)` 数据库快照(其中至少有一个 `task.status='success'`)
    - mock `_call_llm` 返回任意非空字符串;在 `analyze(task_id)` 调用前后分别 `SELECT *` 四张表
    - 断言:`before.notes = after.notes ∧ before.comments = after.comments ∧ before.authors = after.authors ∧ before.tasks = after.tasks`(覆盖 15.7)
    - 断言:`ai_reports` 表恰好新增 1 条记录,且 `prompt_version='v1'`、`report_md` 非空
    - 通过 SQLAlchemy event hook 监听 `before_flush` 检测 `notes/comments/authors/tasks` 任意写操作,出现写时立即抛 `RuntimeError` 验证 15.1-15.4、15.8 的运行时拦截

  - [~] 11.5 实现 GET /api/ai-reports/{report_id}
    - 在 `ai_reports.py` 注册端点
    - `report_id` 不存在返回 404 `REPORT_NOT_FOUND`,响应体包含说明报告不存在的错误信息
    - 存在时返回 200 + `{id, task_id, provider, model, prompt_version, report_md, created_at}`
    - _需求: 16.1, 16.2_

  - [~] 11.6 实现 AI 报告页 Report (`/tasks/:taskId/report`)
    - 文件:`frontend/src/pages/Report.tsx`
    - 通过 `GET /api/tasks/{taskId}` 响应中的 `reports` 字段获取该任务下的历史报告元数据列表(每项含 `id`、`provider`、`model`、`prompt_version`、`created_at`),不调用任何额外路由(满足需求 19.1)
    - 默认通过 `MarkdownView` 渲染 `created_at` 最新一条报告的 `report_md`(其完整 `report_md` 由 `GET /api/ai-reports/{report_id}` 拉取)
    - `reports.length > 1` 时提供历史报告列表,每项展示 `created_at`、`provider`、`model`、`prompt_version`;点击切换为对应 `report_id` 的 `MarkdownView` 渲染
    - `reports.length == 0` 时渲染空状态文案 + 「生成 AI 报告」按钮触发 `POST /api/tasks/{taskId}/ai-report`
    - 「重新生成」按钮每次调用 `POST` 后插入新记录,**不删除或修改既有记录**;成功后重新拉取 `GET /api/tasks/{taskId}` 刷新历史列表
    - _需求: 14.11, 16.3, 16.4, 16.5, 16.6_

  - [ ]* 11.7 单元测试:AI 报告 API 错误路径
    - 文件:`backend/tests/test_api_ai_reports.py`(独立于其他 API 测试文件,避免同 wave 文件冲突)
    - 覆盖 `TASK_NOT_FOUND`(404)、`TASK_NOT_READY`(409)、`INVALID_PROVIDER`(422)、`AI_FAILED`(502)、`REPORT_NOT_FOUND`(404)以及 202 + 200 正常路径
    - 验证 `AI_FAILED` 时 `ai_reports` 表无新记录、`TASK_NOT_READY` 时不发起 LLM 调用、「重新生成」插入新记录而非覆盖既有记录
    - _需求: 14.1, 14.2, 14.4, 14.10, 14.11, 14.12, 16.1, 16.2_

- [~] 12. 最终检查点 - 全量验收与合规复核
  - 运行后端全部测试(含 6 条属性测试 1-6)与前端测试,确认全部通过
  - 按 `docs/compliance.md` 与需求 19、20 逐条复核仓库:`grep` 全仓确保不存在向目标平台发起评论 / 点赞 / 收藏 / 私信 / 关注 / 发布的代码路径,前端路由集合恰好等于需求 17.1 所声明的 7 条,后端 HTTP 路由集合恰好等于需求 19.1 中所声明的 9 条
    - 确认 `.gitmodules` 中 `third_party/MediaCrawler` commit SHA 指针未被修改、git 历史中无对其内容的新增 / 修改 / 删除提交
    - 确认 `data/` 目录之外的磁盘路径无采集数据写入,`raw_json` 中已剥离手机号 / 邮箱 / 身份证号
    - 确认 `.env.example` 中 `HOST=127.0.0.1`,FastAPI 默认仅本机监听
  - 遇到问题及时与用户确认。

## 备注

- 标记 `*` 的子任务为可选,聚焦于属性测试、单元测试、组件测试与端到端冒烟,可为快速 MVP 跳过,但发布前必须执行;非 `*` 子任务为核心实现路径,不可跳过。
- 6 条形式化正确性属性已分别落到独立属性测试子任务,贴近其实现位置以便尽早暴露错误:
  - 属性 1(note_id 唯一)→ 任务 `2.5` → 校验需求 9.1, 9.2
  - 属性 2(评论树结构完整)→ 任务 `2.6` → 校验需求 9.5, 9.6
  - 属性 3(采集数量上限)→ 任务 `3.4` → 校验需求 7.6, 7.7, 1.5
  - 属性 4(AI 报告只读)→ 任务 `11.4` → 校验需求 15.1-15.8
  - 属性 5(任务状态机单调推进)→ 任务 `2.3` → 校验需求 3.1, 3.2
  - 属性 6(全局并发限制)→ 任务 `5.2` → 校验需求 2.1, 2.2
- 检查点(任务 4、7、10、12)是端到端可验证的功能里程碑,完成后应运行测试并与用户对齐进度。
- 所有任务均映射到 `requirements.md` 中具体子条款(显式标注于 `_需求: x.y, x.z_`),便于追踪。
- **严禁** 任意任务修改 `third_party/MediaCrawler/` 子模块下任何文件;子模块仅可通过更新 `.gitmodules` 中 commit SHA 指针的方式升级。
- **严禁** 引入需求 19 第 2-9 条所列任意一种禁止功能(自动评论 / 点赞 / 收藏 / 私信 / 关注 / 发布、批量账号、绕过登录验证、二次分发);任何后续扩展若需偏离这些约束必须先同步修改 `requirements.md`、`design.md` 与 `docs/compliance.md`。
- **严禁** 新增需求 19.1 锁定的 9 条 HTTP 路由集合之外的任何路由;同一任务下的 AI 报告历史列表通过扩展 `GET /api/tasks/{task_id}` 响应中的 `reports` 字段提供。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0,  "tasks": ["1.1"] },
    { "id": 1,  "tasks": ["1.2", "1.3", "1.4", "1.5"] },
    { "id": 2,  "tasks": ["2.1"] },
    { "id": 3,  "tasks": ["2.2"] },
    { "id": 4,  "tasks": ["2.3", "2.4"] },
    { "id": 5,  "tasks": ["2.5", "2.6", "2.7"] },
    { "id": 6,  "tasks": ["2.8", "3.1"] },
    { "id": 7,  "tasks": ["3.2"] },
    { "id": 8,  "tasks": ["3.3"] },
    { "id": 9,  "tasks": ["3.4", "3.5"] },
    { "id": 10, "tasks": ["5.1", "6.1", "6.3", "8.1", "11.1"] },
    { "id": 11, "tasks": ["5.2", "5.3", "6.2", "8.2", "8.3", "8.4", "8.5", "8.6", "11.2"] },
    { "id": 12, "tasks": ["5.4", "11.3"] },
    { "id": 13, "tasks": ["5.5", "9.1", "9.2", "9.3", "9.4", "9.5", "9.6", "9.7", "11.5"] },
    { "id": 14, "tasks": ["5.6", "6.4", "8.7", "9.8", "11.4", "11.6", "11.7"] }
  ]
}
```
