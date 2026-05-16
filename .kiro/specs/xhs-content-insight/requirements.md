# 需求文档:小红书内容洞察 MVP (xhs-content-insight)

## 简介

`xhs-content-insight` 是一个本地化、单用户、研究用途的小红书内容洞察 MVP。系统封装开源项目 [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) (以 git submodule 形式接入,**严禁修改其源码**),通过关键词触发采集约 20 条小红书笔记及其热门评论,落库到 SQLite 并归档为 JSON 文件,然后在 React 前端提供素材池、笔记详情、评论洞察、AI 分析报告等视图。

本需求文档由已批准的 `design.md` 反向推导而来,职责是把设计中的功能边界、状态机、错误处理、数据完整性约束以及合规红线,以 EARS 格式固化为可验证的验收条件。

技术栈定型在设计文档中:**Python + FastAPI + SQLAlchemy + SQLite(后端)、React + Vite + TypeScript + Tailwind CSS(前端)、MediaCrawler(只调用不修改的爬虫引擎)**。

---

## 术语表 (Glossary)

- **System**:整个 `xhs-content-insight` 应用,包含前端、后端、本地存储、第三方 MediaCrawler。
- **API_Layer**:后端 FastAPI 的路由层 (`backend/app/api/*`),负责参数校验与编排。
- **Crawler_Service**:后端 `backend/app/services/crawler_service.py`,封装对 MediaCrawler 的子进程调用。
- **AI_Analyzer**:后端 `backend/app/services/ai_analyzer.py`,LLM Provider 抽象层及 OpenAI / DeepSeek / Gemini 实现。
- **Data_Store**:后端 `backend/app/services/data_store.py`,基于 SQLAlchemy 的持久化层,同时管理 `data/insight.db` 与 `data/json/` 归档目录。
- **Frontend_UI**:基于 React + Vite + TypeScript + Tailwind 的前端单页应用 (`frontend/src/*`)。
- **MediaCrawler**:第三方开源爬虫,以 git submodule 引入到 `third_party/MediaCrawler`,本仓库仅调用其 `main.py`,不读取或修改其源码。
- **ComplianceBanner**:前端通用组件 (`frontend/src/components/ComplianceBanner.tsx`),全局合规提示横幅。
- **KeywordInput**:前端通用组件 (`frontend/src/components/KeywordInput.tsx`),关键词输入与采集启动入口。
- **CommentTree**:前端通用组件 (`frontend/src/components/CommentTree.tsx`),渲染一级 + 二级评论树。
- **AuditLog**:后端写入到日志文件的审计记录,字段包含关键词、时间、采集数量。
- **Task_Status**:`tasks.status` 取值,集合为 `{pending, running, success, failed}`。
- **Hot_Comment**:`comments.is_top_hot = 1` 的二级评论,即 MediaCrawler 标记的热门评论。

---

## 需求 (Requirements)

### 需求 1:采集任务创建

**用户故事:** 作为研究人员,我希望通过关键词一键启动采集任务,以便获取该话题下的小红书素材。

#### 验收条件

1. WHEN 用户在 `KeywordInput` 中输入长度 1 至 50 字符的关键词并点击「开始采集」, THE Frontend_UI SHALL 向 `POST /api/tasks` 发起请求,请求体包含字符串字段 `keyword` 与整数字段 `max_notes`。
2. WHEN `POST /api/tasks` 接收到通过校验的请求, THE API_Layer SHALL 在 `tasks` 表中插入一条记录,初始 `status` 为 `pending`,`max_notes` 取请求值,若请求未提供该字段则默认为 20。
3. WHEN 任务记录插入成功, THE API_Layer SHALL 在 2 秒内返回 HTTP 202 状态码及 JSON `{"task_id": <int>, "status": "pending"}`。
4. IF `keyword` 字段缺失、值非字符串、去除首尾空白后长度为 0 或超过 50 字符, THEN THE API_Layer SHALL 返回 HTTP 422,错误码 `INVALID_KEYWORD`,且不在 `tasks` 表中插入任何记录。
5. IF `max_notes` 字段值非整数或不在区间 `[1, 20]` 内, THEN THE API_Layer SHALL 返回 HTTP 422,错误码 `OVER_LIMIT`,且不在 `tasks` 表中插入任何记录。
6. WHEN 任务创建成功, THE Frontend_UI SHALL 在收到 HTTP 202 响应后 1 秒内跳转到 `/tasks/{task_id}` 路由。
7. IF 数据库插入操作失败或后端发生未预期异常, THEN THE API_Layer SHALL 返回 HTTP 500,错误码 `INTERNAL_ERROR`,且不在 `tasks` 表中保留任何记录。
8. IF `POST /api/tasks` 返回非 2xx 状态码, THEN THE Frontend_UI SHALL 在当前页面显示包含返回错误码的错误提示,且不执行路由跳转。

---

### 需求 2:全局单任务并发约束

**用户故事:** 作为系统操作者,我希望任意时刻只允许一个采集任务在执行,以便降低对小红书平台的压力并规避风控。

#### 验收条件

1. THE System SHALL 在任意时刻保证 `tasks` 表中 `status = 'running'` 的记录数小于等于 1。
2. IF 创建任务请求到达且已存在 `status = 'running'` 的任务, THEN THE API_Layer SHALL 返回 HTTP 409,错误码 `TASK_BUSY`,不创建新任务,且不修改现有 running 任务的状态、`started_at`、`finished_at`、`error_msg` 任一字段。
3. WHILE 存在 `status = 'running'` 的任务, THE Frontend_UI SHALL 在首页「开始采集」按钮关联区域将该按钮设置为禁用且不可点击,并在按钮旁显示当前正在执行的 `task_id`。
4. WHEN API_Layer 收到创建采集任务请求, THE API_Layer SHALL 使用单次事务读取(`SELECT COUNT(*) WHERE status='running' FOR UPDATE` 或等价的串行隔离)校验并发约束,以避免竞态。
5. WHEN 系统中所有任务进入终态(`success` 或 `failed`), THE Frontend_UI SHALL 在 5 秒内重新启用「开始采集」按钮并清除「当前正在执行 task_id」的显示。
6. IF 并发约束的事务读取本身失败(数据库连接异常、锁等待超时等), THEN THE API_Layer SHALL 返回 HTTP 500,错误码 `INTERNAL_ERROR`,且不创建任何任务。

---

### 需求 3:任务状态机

**用户故事:** 作为系统架构师,我希望任务生命周期严格遵守一个单调推进的状态机,以便保证数据一致性与可审计性。

#### 验收条件

1. THE Data_Store SHALL 仅允许以下状态转移:`pending → running`、`running → success`、`running → failed`。
2. IF 调用方尝试执行不在允许集合内的状态转移(包括但不限于 `success → *`、`failed → *`、`running → pending`、`pending → success`、`pending → failed`), THEN THE Data_Store SHALL 拒绝转移并抛出断言异常,且不修改 `tasks` 表中的任何字段(`status`、`started_at`、`finished_at`、`error_msg` 在事务回滚后保持转移前的取值)。
3. WHEN 任务由 `pending` 转入 `running`, THE Data_Store SHALL 把 `started_at` 写为当前 UTC 时间(ISO8601 格式,精确到秒),并保持 `finished_at` 与 `error_msg` 为 NULL。
4. WHEN 任务由 `running` 转入 `success`, THE Data_Store SHALL 把 `finished_at` 写为当前 UTC 时间(ISO8601 格式,精确到秒),且保持 `error_msg` 为 NULL。
5. WHEN 任务由 `running` 转入 `failed`, THE Data_Store SHALL 把 `finished_at` 写为当前 UTC 时间(ISO8601 格式,精确到秒),并写入长度大于等于 1 且小于等于 1000 个字符的 `error_msg`;当原始错误信息长度超过 1000 个字符时,SHALL 仅保留原始内容的前 1000 个字符并丢弃其余部分。
6. THE Data_Store SHALL 通过数据库 `CHECK (status IN ('pending', 'running', 'success', 'failed'))` 约束保证 `tasks.status` 的取值集合。

---

### 需求 4:任务列表查询

**用户故事:** 作为研究人员,我希望查看历史任务列表并按状态筛选,以便回溯既往采集成果。

#### 验收条件

1. WHEN 用户访问 `GET /api/tasks`, THE API_Layer SHALL 返回 HTTP 200 状态码及 JSON `{"items": [...], "total": <int>}`,其中 `total` 为符合本次查询过滤条件(包括 `status`)的任务总数(用于前端计算分页),`items` 数组中每个元素至少包含 `id`、`keyword`、`status`、`note_count`、`started_at`、`finished_at`、`created_at` 字段。
2. THE API_Layer SHALL 按 `created_at` 降序返回任务列表;当两条记录的 `created_at` 相同时,SHALL 以 `id` 降序作为次级排序键,以保证返回顺序确定。
3. WHERE 请求参数包含 `status` 且取值在 `{pending, running, success, failed}` 中, THE API_Layer SHALL 仅返回该状态的任务。
4. WHERE 请求参数包含 `limit` 与 `offset`, THE API_Layer SHALL 按 `LIMIT/OFFSET` 分页返回结果;`limit` 必须为区间 `[1, 100]` 的整数(缺省时取 `20`),`offset` 必须为大于等于 `0` 的整数(缺省时取 `0`)。
5. THE Frontend_UI SHALL 在 `/tasks` 页面以表格形式渲染任务列表,展示 `id`、`keyword`、`status`、`note_count`、`started_at`、`finished_at` 字段;当响应 `items` 为空数组时,SHALL 显示空状态提示(说明当前无采集任务)而非空白表格。
6. IF 请求参数 `status` 取值不在 `{pending, running, success, failed}` 中,或 `limit` 不在 `[1, 100]` 整数范围内,或 `offset` 小于 0 或非整数, THEN THE API_Layer SHALL 返回 HTTP 422,错误码 `INVALID_QUERY_PARAM`,且不返回任何任务记录。

---

### 需求 5:任务详情查询与轮询

**用户故事:** 作为研究人员,我希望实时查看任务执行状态及汇总数据,以便决定下一步动作。

#### 验收条件

1. WHEN 用户访问 `GET /api/tasks/{task_id}`, THE API_Layer SHALL 返回 JSON 对象,顶层字段包含 `id`、`keyword`、`status`、`note_count`、`max_notes`、`started_at`、`finished_at`、`error_msg`、`json_path` 与 `summary`;其中 `summary.total_likes` 等于该任务下所有笔记 `liked_count` 字段之和、`summary.total_comments` 等于该任务下所有评论记录的总条数、`summary.top_authors` 为按所属笔记数降序排序、长度上限 5 的数组,每项包含 `user_id`、`nickname`、`note_count` 三个字段。
2. IF 指定的 `task_id` 不存在, THEN THE API_Layer SHALL 返回 HTTP 404。
3. WHILE 任务状态为 `running`, THE Frontend_UI SHALL 通过 `usePolling` 每 2 秒调用一次任务详情接口,单次请求超时时间为 5 秒。
4. WHEN 任务状态从 `running` 转入 `success` 或 `failed`, THE Frontend_UI SHALL 停止 `usePolling` 调用并以最新返回的 `status`、`finished_at`、`error_msg`、`summary` 字段重新渲染任务详情页。
5. IF 任务状态为 `success`, THEN THE Frontend_UI SHALL 在任务详情页展示「查看素材池」、「查看评论洞察」、「查看 AI 报告」三个入口。
6. IF 任务详情轮询请求返回非 2xx 状态码或发生网络错误, THEN THE Frontend_UI SHALL 暂停后续轮询、保留最近一次成功响应的任务字段并在页面顶部显示带「重试」按钮的错误提示。

---

### 需求 6:MediaCrawler 子模块集成约束

**用户故事:** 作为系统架构师,我希望以 git submodule 方式接入 MediaCrawler 且不修改其源码,以便随时升级且降低法律与维护风险。

#### 验收条件

1. THE System SHALL 通过 git submodule 方式将 MediaCrawler 接入到仓库的 `third_party/MediaCrawler` 目录,且仓库根目录下的 `.gitmodules` 文件 SHALL 登记该子模块的远端仓库 URL 与一个固定的 commit SHA 指针。
2. THE System SHALL 保证本仓库的 git 提交历史中,除 `.gitmodules` 中该子模块 commit SHA 指针的更新提交之外,不存在任何对 `third_party/MediaCrawler` 目录下文件内容的新增、修改或删除提交。
3. WHEN Crawler_Service 启动一次 MediaCrawler 子进程, THE Crawler_Service SHALL 通过 `asyncio.create_subprocess_exec` 启动 MediaCrawler 的 `main.py`,且子进程的工作目录(cwd)设置为环境变量 `MEDIA_CRAWLER_ROOT` 解析得到的绝对路径。
4. WHEN 启动 MediaCrawler 子进程, THE Crawler_Service SHALL 传入参数 `--platform xhs --type search --keywords <keyword> --save_data_option db --get_comment yes --get_sub_comment yes --max_notes <max_notes>`,其中 `<keyword>` 取自当前任务的 `tasks.keyword` 字段,`<max_notes>` 取自当前任务的 `tasks.max_notes` 字段且取值范围为 `[1, 20]`。
5. THE Crawler_Service SHALL 通过环境变量 `MEDIA_CRAWLER_ROOT`(未设置时默认为仓库根目录下的相对路径 `third_party/MediaCrawler`)与 `MEDIA_CRAWLER_PYTHON`(未设置时默认为当前后端进程的 Python 解释器路径)配置 MediaCrawler 的路径与解释器,且 THE Crawler_Service SHALL NOT 在运行期对 `third_party/MediaCrawler` 目录下任何文件执行写入或删除操作。
6. IF `MEDIA_CRAWLER_ROOT` 解析后的路径不存在、不是目录,或其下不存在 `main.py` 文件, THEN THE Crawler_Service SHALL 拒绝启动子进程,使该任务由 `running` 转入 `failed` 状态,并写入指明 MediaCrawler 子模块未就绪或未初始化的 `error_msg`。

---

### 需求 7:采集执行流程

**用户故事:** 作为研究人员,我希望一次成功的采集会把笔记、作者、评论与归档 JSON 完整入库,以便后续的素材池与 AI 分析使用同一份数据。

#### 验收条件

1. WHEN Crawler_Service 开始执行某个状态为 `pending` 的任务, THE Data_Store SHALL 调用 `mark_task_running` 将该任务状态置为 `running` 并把 `started_at` 写为当前 UTC 时间(ISO8601 格式,精确到秒)。
2. WHEN MediaCrawler 子进程返回码为 0 且原始输出至少包含 1 条笔记, THE Crawler_Service SHALL 取 `slice(0, min(len(raw_notes), max_notes))` 条笔记进行后续处理。
3. WHEN 采集成功且需要写入数据库, THE Data_Store SHALL 按以下顺序写入数据:先写 `authors`,再写 `notes`(关联 `task_id`),最后写 `comments`(其中 `parent_comment_id IS NULL` 的一级评论必须先于其所有 `parent_comment_id` 指向同一笔记的二级评论写入)。
4. WHEN `authors`、`notes`、`comments` 全部写入成功, THE Data_Store SHALL 在 `data/json/{task_id}.json` 写入归档快照。
5. WHEN 归档完成, THE Data_Store SHALL 调用 `mark_task_success`,把 `note_count` 设为实际入库笔记数,把 `json_path` 设为相对仓库根目录的归档文件路径(形式为 `data/json/{task_id}.json`)。
6. THE Data_Store SHALL 保证任务状态为 `success` 后 `1 ≤ tasks.note_count ≤ tasks.max_notes ≤ 20`。
7. THE Data_Store SHALL 保证任务状态为 `success` 后,`notes` 表中 `task_id = t` 的笔记条数等于 `tasks` 表中 `id = t` 行的 `note_count` 值。
8. WHEN 任务由 `running` 转入 `success`, THE Crawler_Service SHALL 把 `{keyword, finished_at, note_count}` 三元组写入 AuditLog。
9. IF MediaCrawler 子进程返回码为 0 但原始输出 0 条笔记, THEN THE Crawler_Service SHALL 把任务转入 `failed` 状态、写入 `error_msg = "no_notes_returned"`,且不向 `notes`、`authors`、`comments` 表写入任何记录,也不生成 JSON 归档。

---

### 需求 8:采集错误处理

**用户故事:** 作为研究人员,我希望采集失败时能拿到明确的错误分类,以便决定是重试还是放弃。

#### 验收条件

1. IF MediaCrawler 子进程的 stderr(忽略大小写)包含子串 `login`, THEN THE Crawler_Service SHALL 抛出 `LoginExpiredError`,且 Data_Store SHALL 将任务状态置为 `failed` 并写入 `error_msg = "login_expired: <stderr 前 500 字符>"`。
2. IF MediaCrawler 子进程的 stderr(忽略大小写)不包含子串 `login` 且包含子串 `risk` 或 `verify`, THEN THE Crawler_Service SHALL 抛出 `RiskControlError`,且 Data_Store SHALL 将任务状态置为 `failed` 并写入 `error_msg = "risk_control: <stderr 前 500 字符>"`。
3. IF MediaCrawler 子进程运行时长超过 `CRAWL_TIMEOUT_SECONDS`(默认 600 秒)仍未结束, THEN THE Crawler_Service SHALL 在 10 秒内终止该子进程,且 Data_Store SHALL 将任务状态置为 `failed` 并写入 `error_msg = "timeout"`。
4. IF Crawler_Service 在执行过程中抛出任何未被前述规则分类的异常, THEN THE Data_Store SHALL 将任务状态置为 `failed` 并写入 `error_msg = "unexpected: <异常信息前 500 字符>"`。
5. IF Crawler_Service 抛出 `RiskControlError`, THEN THE System SHALL 保持任务为 `failed` 状态且不发起任何自动重试,直至用户手动操作。
6. WHEN 任务进入 `failed` 状态, THE Frontend_UI SHALL 在任务详情页显示完整 `error_msg` 文本,并根据 `error_msg` 前缀显示对应处置建议:前缀为 `login_expired` 时显示提示重新登录的建议;前缀为 `risk_control` 时显示提示等待冷却或人工处理风控的建议;前缀为 `timeout` 时显示提示缩小采集范围或稍后重试的建议;前缀为 `unexpected` 时显示提示查看任务详情或联系管理员的建议。

---

### 需求 9:数据持久化与唯一性

**用户故事:** 作为系统架构师,我希望同一份数据在多次采集中不会被重复插入或破坏,以便保证数据库的可信性。

#### 验收条件

1. THE Data_Store SHALL 通过 `notes.note_id`、`comments.comment_id`、`authors.user_id` 三个主键约束保证三张表中各自主键唯一;任何违反主键唯一性的纯 INSERT 操作 SHALL 被数据库拒绝并触发完整性错误。
2. WHEN 采集到的 `note_id` 已存在于 `notes` 表中, THE Data_Store SHALL 执行 upsert 而非 insert,且新数据 SHALL 覆盖该记录除主键 `note_id` 外的所有字段。
3. WHEN 采集到的 `comment_id` 已存在于 `comments` 表中, THE Data_Store SHALL 执行 upsert 而非 insert,且新数据 SHALL 覆盖该记录除主键 `comment_id` 外的所有字段。
4. WHEN 采集到的 `user_id` 已存在于 `authors` 表中, THE Data_Store SHALL 执行 upsert 而非 insert,且新数据 SHALL 覆盖该记录除主键 `user_id` 外的所有字段。
5. WHEN 写入 `parent_comment_id` 不为 NULL 的二级评论时, THE Data_Store SHALL 校验其父评论存在于 `comments` 表中,且父评论的 `note_id` 等于子评论的 `note_id`。
6. IF 写入二级评论时其父评论不存在,或父评论的 `note_id` 与子评论的 `note_id` 不一致, THEN THE Data_Store SHALL 拒绝该写入操作并把当前任务转入 `failed` 状态,写入指明评论树结构错误的 `error_msg`。
7. THE Data_Store SHALL 在以下字段建立索引:`notes.task_id`、`notes.author_user_id`、`comments.note_id`、`comments.parent_comment_id`、`comments(note_id, is_top_hot)`、`ai_reports.task_id`。
8. WHEN 删除一个 `tasks` 记录时, THE Data_Store SHALL 在同一事务内通过 `ON DELETE CASCADE` 级联删除该任务对应的 `notes`、`comments`、`ai_reports` 记录,事务任一环节失败时整体回滚。

---

### 需求 10:JSON 归档与导出

**用户故事:** 作为研究人员,我希望每个采集任务都有一份独立的 JSON 归档,既能用于断点恢复也能下载用于离线分析。

#### 验收条件

1. WHEN `Data_Store.archive_json(task_id)` 被调用, THE Data_Store SHALL 写入或覆盖 `data/json/{task_id}.json`,文件根对象顶层字段恰好包含 `task_id`、`exported_at`、`notes`、`comments` 四个键,其中 `exported_at` 为当前 UTC 时间的 ISO 8601 时间戳(精确到秒)。
2. THE Data_Store SHALL 使用 UTF-8 编码并以 `ensure_ascii=False` 写入 JSON,中文字符在文件中以原文呈现,不进行 `\u` 转义。
3. WHILE 任务状态为 `success`, THE Data_Store SHALL 保证从该任务的 `data/json/{task_id}.json` 反序列化得到的 `notes` 与 `comments` 集合,与数据库中对应任务的 `notes` 与 `comments` 在字段名集合及字段取值上完全一致(字段名集合相同且每条记录每个字段值相等,称之为往返等价)。
4. WHEN 用户访问 `GET /api/tasks/{task_id}/export` 且 `data/json/{task_id}.json` 文件存在, THE API_Layer SHALL 返回 HTTP 200,响应体为该归档文件的全部内容,Content-Type 为 `application/json`。
5. WHEN API_Layer 成功返回归档内容, THE API_Layer SHALL 在响应头中设置 `Content-Disposition: attachment; filename="task_{task_id}.json"`。
6. IF `tasks.json_path` 为空或目标归档文件不存在, THEN THE API_Layer SHALL 返回 HTTP 404,响应体中包含说明归档不可用的错误指示。
7. WHEN `Data_Store.archive_json(task_id)` 成功写入归档文件, THE Data_Store SHALL 将 `tasks.json_path` 字段更新为该归档文件相对仓库根目录的路径(形式为 `data/json/{task_id}.json`)。

---

### 需求 11:笔记列表

**用户故事:** 作为研究人员,我希望在素材池中以网格方式浏览某次采集得到的笔记,以便快速锁定感兴趣的内容。

#### 验收条件

1. WHEN 用户访问 `GET /api/tasks/{task_id}/notes`, THE API_Layer SHALL 返回 HTTP 200 与 `{"items": [...], "total": <int>}`,每条 item 包含 `note_id`、`title`、`type`、`cover_url`、`liked_count`、`collected_count`、`comment_count` 与 `author` 简要对象(`user_id`、`nickname`),items 按笔记发布时间倒序排列;若该任务下无笔记,items 为空数组且 total 为 0。
2. WHERE 请求参数包含 `limit` 与 `offset`, THE API_Layer SHALL 按 `LIMIT/OFFSET` 分页返回,默认 `limit = 20`、`offset = 0`,其中 `limit` 取值范围为 `[1, 100]` 的整数,`offset` 取值范围为 `[0, 1_000_000]` 的整数。
3. IF 指定的 `task_id` 不存在, THEN THE API_Layer SHALL 返回 HTTP 404 并附带说明任务不存在的错误信息。
4. IF `limit` 或 `offset` 超出允许范围或不是整数, THEN THE API_Layer SHALL 返回 HTTP 422 并附带说明参数无效的错误信息,且不返回笔记数据。
5. WHEN 用户访问 `/tasks/:taskId/notes` 路由, THE Frontend_UI SHALL 使用 `NoteCard` 组件以网格形式渲染笔记列表。
6. IF 当前任务的笔记列表为空, THEN THE Frontend_UI SHALL 在网格区域显示空状态提示,告知用户当前任务暂无笔记。
7. WHEN 用户点击 `NoteCard`, THE Frontend_UI SHALL 跳转到 `/tasks/:taskId/notes/:noteId` 路由。

---

### 需求 12:笔记详情与评论树

**用户故事:** 作为研究人员,我希望进入某条笔记后看到完整正文、作者信息以及一二级评论,以便理解上下文与受众反馈。

#### 验收条件

1. WHEN 用户访问 `GET /api/notes/{note_id}`, THE API_Layer SHALL 返回 JSON `{"note": {...}, "author": {...}, "comments": [...]}` 三段数据,其中 `note` 至少包含 `note_id`、`title`、`desc`、`type`、`cover_url`、`video_url`、`liked_count`、`collected_count`、`comment_count` 字段,`author` 至少包含 `user_id`、`nickname`、`avatar`、`fans_count` 字段。
2. THE API_Layer SHALL 在 `comments` 字段中把一级评论(`parent_comment_id IS NULL`)放在顶层并按 `like_count` 降序排序(`like_count` 相同则按 `create_time` 降序),把二级评论作为对应一级评论的 `sub_comments` 数组嵌入并按 `create_time` 升序排序。
3. THE API_Layer SHALL 在每条评论(含一级与二级)中保留 `comment_id`、`user_id`、`nickname`、`content`、`like_count`、`sub_comment_count`、`create_time`、`is_top_hot` 字段。
4. IF 指定的 `note_id` 不存在, THEN THE API_Layer SHALL 返回 HTTP 404,错误码 `NOTE_NOT_FOUND`。
5. THE Frontend_UI SHALL 在 `/tasks/:taskId/notes/:noteId` 页面渲染笔记正文(`title`、`desc`;当 `video_url` 非空时渲染视频播放器,否则渲染 `cover_url` 封面图)、作者卡片(展示 `avatar`、`nickname`、`fans_count` 字段)与 `CommentTree` 组件。
6. WHERE 评论的 `is_top_hot = 1`, THE CommentTree SHALL 在该评论上附加显式的「热门」视觉标识(如徽标文字或区别于普通评论的背景样式),且该标识不在 `is_top_hot = 0` 的评论上出现。
7. WHEN `GET /api/notes/{note_id}` 返回的 `comments` 数组为空, THE Frontend_UI SHALL 在 `CommentTree` 区域渲染「暂无评论」占位文案,且不渲染空白评论容器。

---

### 需求 13:评论洞察聚合

**用户故事:** 作为研究人员,我希望快速看到某次采集所有评论的高频词、情感分布和热门评论 Top N,以便定位用户关注点。

#### 验收条件

1. WHEN 用户访问 `GET /api/tasks/{task_id}/comments` 且 `task_id` 对应的任务存在, THE API_Layer SHALL 返回 `{"total_comments": <int>, "top_keywords": [...], "sentiment": {...}, "top_hot_comments": [...]}`,其中 `total_comments` 为非负整数。
2. THE API_Layer SHALL 在 `top_keywords` 中返回最多 50 项,每项结构为 `{"word": str, "count": int}`,按 `count` 降序排序;`count` 相同的项按 `word` 字典序升序排序。
3. THE API_Layer SHALL 在 `sentiment` 中提供 `positive`、`neutral`、`negative` 三个浮点数,每个数值取值范围为 `[0.0, 1.0]`,三者之和为 `1.0`(±0.01 容差)。
4. THE API_Layer SHALL 在 `top_hot_comments` 中仅返回 `is_top_hot = 1` 的评论,按 `like_count` 降序排序;`like_count` 相同的项按评论创建时间降序排序,最多返回 20 条。
5. THE Crawler_Service SHALL 对每条笔记的二级评论只采集热门部分(`is_top_hot = 1`),且单条笔记的 Hot_Comment 条数不超过 `HOT_COMMENT_TOP_N`(默认 5)。
6. WHEN 用户访问 `/tasks/:taskId/insights` 页面, THE Frontend_UI SHALL 渲染高频词列表(或词云)、情感分布饼图、热门评论 Top 列表三块视图。
7. IF 请求的 `task_id` 在系统中不存在, THEN THE API_Layer SHALL 返回 HTTP 404 并包含错误信息(指明任务不存在),且不返回评论聚合字段。
8. IF 任务存在但没有任何已采集评论, THEN THE API_Layer SHALL 返回 `total_comments = 0`、`top_keywords = []`、`top_hot_comments = []`,且 `sentiment` 默认为 `{"positive": 0.0, "neutral": 1.0, "negative": 0.0}`。

---

### 需求 14:AI 报告生成

**用户故事:** 作为研究人员,我希望对一次采集得到的素材池一键生成 AI 内容洞察报告,以便快速得到结构化的内容运营建议。

#### 验收条件

1. WHEN 用户调用 `POST /api/tasks/{task_id}/ai-report`,请求体包含 `provider`(字符串)与 `model`(长度为 1 至 100 的字符串), THE API_Layer SHALL 校验目标任务的 `status` 为 `success`。
2. IF 目标任务的 `status` 不是 `success`, THEN THE API_Layer SHALL 返回 HTTP 409,错误码 `TASK_NOT_READY`,不发起任何 LLM 调用,且不在 `ai_reports` 表中创建任何记录。
3. THE AI_Analyzer SHALL 通过 `make_analyzer(provider, model, store)` 工厂方法,根据 `provider` 取值(忽略大小写)在 `{openai, deepseek, gemini}` 中选择实现类。
4. IF `provider` 取值(忽略大小写)不在 `{openai, deepseek, gemini}` 内, THEN THE API_Layer SHALL 返回 HTTP 422,错误码 `INVALID_PROVIDER`,且不在 `ai_reports` 表中创建任何记录。
5. WHERE 请求未显式提供 `provider`, THE AI_Analyzer SHALL 从环境变量 `AI_PROVIDER` 读取(默认 `openai`)。
6. THE AI_Analyzer SHALL 使用 `PROMPT_V1` 模板构建 prompt,且 prompt 至少包含 `keyword`、Top 笔记标题、Top 评论文本三部分。
7. THE AI_Analyzer SHALL 在构建 prompt 时按 `liked_count` 降序取笔记 Top 20、按 `like_count` 降序取评论 Top 50,并对长文本进行截断(笔记 desc 保留前 80 个字符,评论 content 保留前 120 个字符)。
8. THE AI_Analyzer SHALL 保证生成的 prompt 估算 token 数小于 `MODEL_CONTEXT_LIMIT`(默认 8000 tokens)。
9. WHEN AI 分析成功, THE Data_Store SHALL 在 `ai_reports` 表插入一条记录,字段包含 `task_id`、`provider`、`model`、`prompt_version`(取值固定为 `v1`,与 `PROMPT_V1` 对应)、`report_md`(非空字符串)、`created_at`(UTC ISO8601 格式,精确到秒)。
10. IF LLM API 调用失败(网络错误、鉴权错误、超过 `LLM_API_TIMEOUT_SECONDS`(默认 120 秒)等), THEN THE API_Layer SHALL 返回 HTTP 502,错误码 `AI_FAILED`,且不在 `ai_reports` 表插入任何记录。
11. WHEN 用户在 AI 报告页点击「重新生成」, THE Frontend_UI SHALL 重新调用 `POST /api/tasks/{task_id}/ai-report`,在成功时插入新的 `ai_reports` 记录,且不删除或修改既有记录。
12. IF `task_id` 在 `tasks` 表中不存在, THEN THE API_Layer SHALL 返回 HTTP 404,错误码 `TASK_NOT_FOUND`,且不在 `ai_reports` 表中创建任何记录。
13. WHEN AI 分析成功且记录写入完成, THE API_Layer SHALL 返回 HTTP 202 状态码及 JSON `{"report_id": <int>, "status": "pending"}`,后续报告查询遵循需求 16。

---

### 需求 15:AI 报告生成只读约束

**用户故事:** 作为系统架构师,我希望 AI 分析过程严格只读源数据,以便保护采集结果不被误改。

#### 验收条件

1. WHILE AI_Analyzer 执行 `analyze(task_id)`, THE AI_Analyzer SHALL NOT 对 `notes` 表执行任何 INSERT、UPDATE 或 DELETE 操作。
2. WHILE AI_Analyzer 执行 `analyze(task_id)`, THE AI_Analyzer SHALL NOT 对 `comments` 表执行任何 INSERT、UPDATE 或 DELETE 操作。
3. WHILE AI_Analyzer 执行 `analyze(task_id)`, THE AI_Analyzer SHALL NOT 对 `authors` 表执行任何 INSERT、UPDATE 或 DELETE 操作。
4. WHILE AI_Analyzer 执行 `analyze(task_id)`, THE AI_Analyzer SHALL NOT 对 `tasks` 表执行任何 INSERT、UPDATE 或 DELETE 操作。
5. THE AI_Analyzer SHALL 仅通过 `Data_Store.load_for_ai(task_id)` 读取分析所需的 `keyword`、`notes`、`comments`。
6. THE AI_Analyzer SHALL 仅通过 `Data_Store.save_ai_report(report)` 写入新报告,且写入操作仅作用于 `ai_reports` 表。
7. FOR ALL 在调用 `analyze(task_id)` 前后的数据库快照, THE 比较结果 SHALL 满足 `before.notes = after.notes` 且 `before.comments = after.comments` 且 `before.authors = after.authors` 且 `before.tasks = after.tasks`。
8. IF AI_Analyzer 在 `analyze(task_id)` 执行过程中检测到对 `notes`、`comments`、`authors`、`tasks` 任一表的写操作尝试, THEN THE AI_Analyzer SHALL 中止当前执行并抛出受控异常,API_Layer 返回 HTTP 502 错误码 `AI_FAILED`,且不向 `ai_reports` 表插入任何记录。

---

### 需求 16:AI 报告查询

**用户故事:** 作为研究人员,我希望在前端阅读已生成的 AI 报告,并保留历史版本。

#### 验收条件

1. WHEN 用户访问 `GET /api/ai-reports/{report_id}` 且该 `report_id` 在 `ai_reports` 表中存在, THE API_Layer SHALL 返回 HTTP 200 状态码及 JSON `{"id", "task_id", "provider", "model", "prompt_version", "report_md", "created_at"}`。
2. IF `report_id` 不存在, THEN THE API_Layer SHALL 返回 HTTP 404,错误码 `REPORT_NOT_FOUND`,响应体中包含说明报告不存在的错误信息。
3. WHEN 用户进入 `/tasks/:taskId/report` 页面, THE Frontend_UI SHALL 通过 `MarkdownView` 组件(基于 react-markdown + remark-gfm)渲染该任务最新一条 `ai_reports` 记录的 `report_md` 字段。
4. IF 同一个 `task_id` 下存在多条 `ai_reports` 记录, THEN THE Frontend_UI SHALL 默认渲染 `created_at` 最新的一条。
5. WHEN 同一个 `task_id` 下存在多条 `ai_reports` 记录, THE Frontend_UI SHALL 在报告页提供历史报告列表,列表每项展示 `created_at`、`provider`、`model`、`prompt_version` 字段;用户点击列表中的任一历史报告时,SHALL 切换 `MarkdownView` 渲染该选中报告的 `report_md`。
6. IF 当前 `task_id` 下不存在任何 `ai_reports` 记录, THEN THE Frontend_UI SHALL 在 `/tasks/:taskId/report` 页面渲染空状态提示文案,并展示「生成 AI 报告」按钮以触发需求 14 的报告生成流程。

---

### 需求 17:前端页面与路由

**用户故事:** 作为研究人员,我希望一套完整的页面来覆盖采集发起、素材池浏览、评论洞察与 AI 报告查阅,以便不依赖命令行操作。

#### 验收条件

1. THE Frontend_UI SHALL 提供以下路由及对应页面:`/`(`Home.tsx`)、`/tasks`(`TaskManager.tsx`)、`/tasks/:taskId`(`TaskDetail.tsx`)、`/tasks/:taskId/notes`(`NoteList.tsx`)、`/tasks/:taskId/notes/:noteId`(`NoteDetail.tsx`)、`/tasks/:taskId/insights`(`Insights.tsx`)、`/tasks/:taskId/report`(`Report.tsx`)。
2. THE Frontend_UI SHALL 通过 `frontend/src/api/client.ts` 中统一配置的 Axios 实例访问后端 API,Base URL 默认为 `http://127.0.0.1:8000/api`,单次请求超时时间为 30 秒。
3. THE KeywordInput 组件 SHALL 强制 `maxNotes` 输入为 `[1, 20]` 范围内的整数。
4. IF KeywordInput 中 `maxNotes` 输入值非整数、小于 1 或大于 20, THEN THE KeywordInput 组件 SHALL 禁用提交按钮并显示提示「单次采集上限 20 条」(超出上限时)或「单次采集至少 1 条」(小于下限时)。
5. THE NoteCard 组件 SHALL 显示笔记封面、标题、`liked_count`、`collected_count`、`comment_count` 字段。
6. IF NoteCard 渲染所需字段(`cover_url`、`title`、`liked_count`、`collected_count`、`comment_count`)中任一字段缺失或为 null, THEN THE NoteCard 组件 SHALL 在该字段位置显示占位符(空封面用占位图、空数值显示「-」),且不抛出渲染异常。
7. THE Frontend_UI SHALL 在每个页面顶部固定渲染 `ComplianceBanner`(详见需求 18)。
8. IF 用户访问的路由不在第 1 条声明的路由集合中, THEN THE Frontend_UI SHALL 渲染 404 兜底页面,并提供「返回首页」入口跳转到 `/`。

---

### 需求 18:合规横幅与提示

**用户故事:** 作为合规负责人,我希望前端持续提醒使用者合规边界,以便防止无意越界。

#### 验收条件

1. THE Frontend_UI SHALL 在所有页面顶部固定渲染 `ComplianceBanner` 组件,该组件在路由切换、页面滚动期间持续可见,且不提供允许用户隐藏或关闭横幅的交互入口。
2. THE ComplianceBanner SHALL 完整显示固定文案「本工具仅供学习研究和小规模数据分析,请遵守平台条款,不得用于自动化营销、批量发布或商业用途」,文案不得被截断或省略。
3. THE Frontend_UI SHALL 在 `/`(首页)布局的页脚区域固定展示采集上限说明文案「单次采集上限 20 条笔记,同一时刻仅允许一个采集任务运行」。

---

### 需求 19:合规红线 - 禁止功能

**用户故事:** 作为合规负责人,我希望系统从代码与界面两个维度都严格禁止任何自动化营销、批量发布、绕过验证类行为,以便守住法律与平台条款红线。

#### 验收条件

1. THE System SHALL 仅实现「关键词搜索 → 采集笔记 + 评论 → 分析」一条数据流,且后端对外暴露的 HTTP 路由集合 SHALL 完全等于需求 1、4、5、10、11、12、13、14、16 中显式声明的路由集合,不存在任何额外路由。
2. THE System SHALL 不实现自动评论功能,具体表现为:后端不存在向小红书发起 POST/comment 类写操作的代码路径,且 Crawler_Service 调用 MediaCrawler 时 `--type` 参数取值仅限于 `search`(见需求 6)。
3. THE System SHALL 不实现自动点赞功能,具体表现为:后端不存在向小红书发起点赞类写操作的代码路径,且不向 MediaCrawler 传递任何点赞相关参数。
4. THE System SHALL 不实现自动收藏功能,具体表现为:后端不存在向小红书发起收藏类写操作的代码路径,且不向 MediaCrawler 传递任何收藏相关参数。
5. THE System SHALL 不实现自动私信功能,具体表现为:后端不存在向小红书发起私信类写操作的代码路径,且不向 MediaCrawler 传递任何私信相关参数。
6. THE System SHALL 不实现自动关注或自动取关功能,具体表现为:后端不存在向小红书发起关注/取关类写操作的代码路径,且不向 MediaCrawler 传递任何关注相关参数。
7. THE System SHALL 不实现自动发布或自动改稿功能,具体表现为:后端不存在向小红书发起发布、编辑、删除笔记类写操作的代码路径。
8. THE System SHALL 不实现批量账号矩阵管理或多账号轮换功能,具体表现为:系统在任意时刻仅使用单一登录态 Cookie,配置层不提供账号列表、账号池、账号轮换策略等结构。
9. THE System SHALL 不实现绕过登录验证、滑块验证或短信验证码的功能,具体表现为:不包含自动识别滑块、自动填写短信验证码、自动伪造登录 Token 的代码路径;当 MediaCrawler 子进程因登录态失效而退出时,系统遵循需求 8 的错误处理流程并将任务标记为 `failed`,不发起任何自动绕过尝试。
10. THE Frontend_UI SHALL 不暴露第 2 至第 9 条所列任意一种禁止功能的入口、按钮、菜单项、表单或对应 API 调用,具体表现为:`frontend/src/` 下不存在调用上述禁止功能的代码,前端路由集合与需求 17 第 1 条声明的路由集合完全一致。
11. THE System SHALL 不对外提供匿名访问的 API、WebHook 或公开数据下载链接,其中「匿名访问」定义为:在未持有本机进程内有效会话的前提下,从非 `127.0.0.1` 的来源可访问后端任意路由;系统遵循需求 20 第 1 条仅监听 `127.0.0.1`,且不注册任何 WebHook 出站推送。
12. THE System SHALL 不二次分发原始采集数据,「二次分发」定义为:将 `data/insight.db`、`data/json/*.json` 或 `notes`、`comments`、`authors` 表中的任意记录主动上传、推送、同步到任何非 `127.0.0.1` 的网络位置;唯一允许的对外网络出站为需求 14 定义的 LLM Provider 调用,且该调用仅传输需求 14 第 6、7 条规定的 prompt 内容。

---

### 需求 20:合规红线 - 部署与本地存储

**用户故事:** 作为合规负责人,我希望系统默认仅本地运行、仅本地存储,以便避免数据外泄与滥用。

#### 验收条件

1. THE System SHALL 默认配置 FastAPI 仅监听 `127.0.0.1`,且 `.env.example` 中 `HOST` 配置项的取值仅为 `127.0.0.1`,不提供 `0.0.0.0`、`::`、外网 IP 或域名等任何允许非本地访问的示例值。
2. THE Data_Store SHALL 把 SQLite (`data/insight.db`) 与 JSON 归档 (`data/json/*.json`) 全部写入本仓库 `data/` 目录,且不向 `data/` 目录之外的磁盘路径写入任何采集数据文件。
3. THE Data_Store SHALL 不向任何第三方对象存储(S3、OSS、GCS 等)或公网数据库上传采集数据。
4. IF MediaCrawler 原始数据(`raw_json` 字段)中包含手机号、绑定邮箱、身份证号中的任一字段, THEN THE Data_Store SHALL 在入库前从 `raw_json` 中删除这些键值对,持久化结果中不保留原始值。
5. WHEN 任务由 `running` 转入 `success` 或 `failed`, THE Crawler_Service SHALL 把 `{keyword, started_at, finished_at, note_count, status}` 五元组写入 AuditLog,其中 `started_at`、`finished_at` 为 ISO 8601 格式精确到秒,`status` 取值在 `{success, failed}` 中。
6. THE System SHALL 在 `docs/compliance.md` 中固化本节合规边界文案,且 `README.md` 前 30 行内 SHALL 通过 Markdown 链接形式引用 `docs/compliance.md`。

---

## 备注

- 所有时间字段统一使用 UTC ISO8601 文本表示,精确到秒。
- 所有 API 错误响应统一遵循 `{"code": <int|str>, "message": <str>, "detail": <any>}` 结构。
- 本需求文档中所有「禁止」类条目均为硬性约束,任何后续实现与扩展都必须不违反这些条款。如需修改,必须同步更新 `design.md` 与 `docs/compliance.md`。
- 本需求文档中的 6 条形式化正确性属性(见 `design.md` 「Correctness Properties」章节)已分别映射到具体需求条款:属性 1(note_id 唯一)→ 需求 9.1/9.2;属性 2(评论树结构完整)→ 需求 9.5/9.6;属性 3(采集数量上限)→ 需求 7.6/1.5;属性 4(AI 报告只读)→ 需求 15;属性 5(任务状态机单调推进)→ 需求 3;属性 6(全局并发限制)→ 需求 2。
