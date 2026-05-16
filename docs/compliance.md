# 合规边界文档(Compliance Boundary)

> 本文件为 `xhs-content-insight` 项目的硬性合规红线,与 `requirements.md` 中需求 19、20 一致,并与 `design.md` 第 5 节「合规与风控边界」对齐。
>
> 任何与本文件冲突的实现 **不得合入主分支**。如确需调整边界,必须先同步修改 `requirements.md`、`design.md` 与本文件,再进入实现。

---

## 0. 项目定位

- 本项目仅用于 **学习研究** 与 **小规模数据分析**,不做任何商业用途、对外服务化或转售。
- 本项目以 git submodule 形式接入 [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) 作为爬虫引擎,**严禁修改其源码**;子模块仅可通过更新 `.gitmodules` 中 commit SHA 指针的方式升级。
- 使用者应自行遵守小红书平台条款及当地法律法规;不当使用所产生的全部后果由使用者承担,与本项目作者无关。

---

## 1. 禁止功能清单(对应需求 19)

### 1.1 唯一数据流与路由收敛(需求 19.1)

- 系统 **仅** 实现「关键词搜索 → 采集笔记 + 评论 → 本地分析」一条数据流。
- 后端对外暴露的 HTTP 路由集合 **恰好等于** 以下 9 条,**不得新增任何额外路由**:

  | # | 方法 | 路径 | 来源需求 |
  |---|------|------|----------|
  | 1 | POST | `/api/tasks` | 需求 1 |
  | 2 | GET  | `/api/tasks` | 需求 4 |
  | 3 | GET  | `/api/tasks/{task_id}` | 需求 5 |
  | 4 | GET  | `/api/tasks/{task_id}/export` | 需求 10 |
  | 5 | GET  | `/api/tasks/{task_id}/notes` | 需求 11 |
  | 6 | GET  | `/api/notes/{note_id}` | 需求 12 |
  | 7 | GET  | `/api/tasks/{task_id}/comments` | 需求 13 |
  | 8 | POST | `/api/tasks/{task_id}/ai-report` | 需求 14 |
  | 9 | GET  | `/api/ai-reports/{report_id}` | 需求 16 |

- 同一任务下的 AI 报告历史列表必须通过扩展 `GET /api/tasks/{task_id}` 响应中的 `reports` 字段提供,**禁止** 新增 `GET /api/ai-reports?task_id=...` 等额外路由。

### 1.2 互动写操作禁止(需求 19.2 ~ 19.7)

后端 **不存在** 任何向小红书发起以下写操作的代码路径,前端 **不暴露** 任何对应入口、按钮、菜单项、表单或 API 调用:

| 编号 | 禁止类别 | 具体含义 | 实现侧约束 |
|------|----------|----------|------------|
| 19.2 | 自动评论 | POST 评论、回复评论 | `Crawler_Service` 调用 MediaCrawler 时 `--type` 取值 **仅限 `search`** |
| 19.3 | 自动点赞 | 点赞 / 取消点赞笔记或评论 | 不向 MediaCrawler 传递任何点赞相关参数 |
| 19.4 | 自动收藏 | 收藏 / 取消收藏笔记 | 不向 MediaCrawler 传递任何收藏相关参数 |
| 19.5 | 自动私信 | 发起 / 回复私信 | 不向 MediaCrawler 传递任何私信相关参数 |
| 19.6 | 自动关注 | 关注 / 取关用户 | 不向 MediaCrawler 传递任何关注相关参数 |
| 19.7 | 自动发布 | 发布 / 编辑 / 删除笔记 | 后端无任何写笔记代码路径 |

### 1.3 批量账号与登录绕过禁止(需求 19.8、19.9)

- **批量账号矩阵 / 多账号轮换** 严格禁止:系统在任意时刻 **仅使用单一登录态 Cookie**,配置层不得提供账号列表、账号池、账号轮换策略等结构。
- **绕过登录验证 / 滑块验证 / 短信验证码** 严格禁止:不包含自动识别滑块、自动填写短信验证码、自动伪造登录 Token 的代码路径。
- 当 MediaCrawler 子进程因登录态失效而退出时,系统按需求 8 的错误处理流程将任务标记为 `failed`(`error_msg = "login_expired: <stderr 前 500 字符>"`),**不发起任何自动绕过尝试**。
- 风控触发时(`error_msg` 前缀 `risk_control`)同样不发起任何自动重试,需用户手动处理后再次发起任务。

### 1.4 前端入口收敛(需求 19.10)

- 前端 `frontend/src/` 下不得存在调用 §1.2、§1.3 所列任意一种禁止功能的代码。
- 前端路由集合 **恰好等于** 需求 17.1 声明的以下 7 条,不得新增:

  ```
  /
  /tasks
  /tasks/:taskId
  /tasks/:taskId/notes
  /tasks/:taskId/notes/:noteId
  /tasks/:taskId/insights
  /tasks/:taskId/report
  ```

  另存在通配 `*` 兜底路由指向 404 页面(需求 17.8)。

### 1.5 匿名访问 / WebHook / 公开下载禁止(需求 19.11)

- 系统 **不对外提供匿名访问的 API、WebHook 或公开数据下载链接**。
- 「匿名访问」定义为:在未持有本机进程内有效会话的前提下,从非 `127.0.0.1` 的来源可访问后端任意路由。
- 后端默认仅监听 `127.0.0.1`(详见 §2.1),且 **不注册任何 WebHook 出站推送**。

### 1.6 二次分发禁止(需求 19.12)

- 系统 **不二次分发** 原始采集数据。
- 「二次分发」定义为:将 `data/insight.db`、`data/json/*.json`,或 `notes`、`comments`、`authors` 表中的任意记录主动上传、推送、同步到任何非 `127.0.0.1` 的网络位置。
- **唯一允许的对外网络出站**:需求 14 定义的 LLM Provider 调用(OpenAI / DeepSeek / Gemini),且该调用仅传输需求 14.6、14.7 规定的 prompt 内容(关键词、Top 笔记标题与截断后的 desc、Top 评论文本截断后的 content),**不得** 传递 `raw_json`、`comments` 全表、用户 PII 或归档文件。

---

## 2. 部署与本地存储约束(对应需求 20)

### 2.1 默认仅本机监听(需求 20.1)

- FastAPI 默认监听 `127.0.0.1`,不对外开放端口。
- `backend/.env.example` 中 `HOST` 配置项的取值 **仅为** `127.0.0.1`;**不得** 出现 `0.0.0.0`、`::`、外网 IP 或任何域名等允许非本地访问的示例值。
- CORS 来源仅允许 `127.0.0.1`。

### 2.2 数据落地仅限 `data/`(需求 20.2、20.3)

- SQLite 库文件 (`data/insight.db`) 与 JSON 归档 (`data/json/{task_id}.json`) 全部写入本仓库 `data/` 目录。
- **不得** 向 `data/` 目录之外的磁盘路径写入任何采集数据文件。
- **不得** 向任何第三方对象存储(S3、OSS、COS、GCS 等)或公网数据库上传采集数据。
- `data/insight.db` 与 `data/json/` 目录在 `.gitignore` 中默认排除,不进入 git 历史。

### 2.3 `raw_json` 敏感字段剥离(需求 20.4)

- 在 `Data_Store.upsert_notes` 入库前,从 `raw_json` 中剔除以下敏感键(忽略大小写)及其取值,持久化结果中 **不保留** 原值:
  - `phone`
  - `mobile`
  - `email`
  - `bind_email`
  - `id_card`
  - `id_number`
  - `identity`
- 上述清单如需扩展,必须先同步修改 `requirements.md` 与本文件。

### 2.4 审计日志(需求 20.5)

- 任务由 `running` 转入 `success` 或 `failed` 时,`Crawler_Service` 必须把以下五元组写入 AuditLog:

  ```
  { keyword, started_at, finished_at, note_count, status }
  ```

  - `started_at`、`finished_at` 为 ISO 8601 文本,精确到秒(UTC)。
  - `status ∈ {success, failed}`。
- AuditLog 仅写入本机日志,**不外发**。

### 2.5 文档固化与 README 引用(需求 20.6)

- 本文件 (`docs/compliance.md`) **固化** 需求 19、20 全部条款。
- `README.md` 前 30 行内必须通过 Markdown 链接形式引用本文件,并明确「仅供学习研究」的项目定位。

---

## 3. 采集规模与频率限制(综合需求 1.5、2.1、7.6、13.5)

| 约束项 | 取值 | 强制点 |
|--------|------|--------|
| 单次采集笔记上限 | `max_notes ∈ [1, 20]` | API 层校验 `OVER_LIMIT`;写入时 `slice(0, max_notes)` |
| 全局并发上限 | 同一时刻 `status='running'` 任务 ≤ 1 | 创建任务事务内 `SELECT COUNT(*) WHERE status='running'`,违反返回 409 `TASK_BUSY` |
| 单笔记热门评论 Top N | `HOT_COMMENT_TOP_N` 默认 5 | `Crawler_Service` 在 `_read_mc_output` 阶段截取并仅保留 `is_top_hot=1` |
| 关键词长度 | `[1, 50]` 字符 | API 层校验 `INVALID_KEYWORD` |
| 采集超时 | `CRAWL_TIMEOUT_SECONDS` 默认 600 秒 | 子进程超时则终止并写 `error_msg = "timeout"` |
| LLM 调用超时 | `LLM_API_TIMEOUT_SECONDS` 默认 120 秒 | 超时冒泡为 `LLMError`,API 返回 502 `AI_FAILED` |

> 上述任何阈值的调整都必须在 `requirements.md` 与 `design.md` 中同步说明并通过评审,本文件随后更新。

---

## 4. MediaCrawler 子模块边界(对应需求 6)

- 仓库根 `.gitmodules` 登记 MediaCrawler 远端 URL 与 **固定 commit SHA 指针**,目标路径 `third_party/MediaCrawler`。
- 除 `.gitmodules` 中 commit SHA 指针的更新提交之外,本仓库 git 历史中 **不得** 出现对 `third_party/MediaCrawler/` 下文件内容的新增、修改或删除提交。
- `Crawler_Service` 通过 `asyncio.create_subprocess_exec` 调用 `MEDIA_CRAWLER_PYTHON main.py`,固定参数集合:

  ```
  --platform xhs
  --type search
  --keywords <keyword>
  --save_data_option db
  --get_comment yes
  --get_sub_comment yes
  --max_notes <max_notes>
  ```

  其中 `--type` 仅可取 `search`,任何其他取值都视为越界。
- 运行期 `Crawler_Service` **不得** 对 `third_party/MediaCrawler/` 下任何文件执行写入或删除。

---

## 5. AI 报告只读约束(对应需求 15)

- `AI_Analyzer.analyze(task_id)` 执行期间,**禁止** 对 `notes`、`comments`、`authors`、`tasks` 任意一张表执行 `INSERT / UPDATE / DELETE`。
- 仅通过 `Data_Store.load_for_ai(task_id)` 读取分析所需数据;仅通过 `Data_Store.save_ai_report(report)` 写入新报告;`save_ai_report` 写入操作 **仅作用于** `ai_reports` 表。
- 检测到对受保护表的写操作尝试时,中止当前执行并抛出受控异常,API 层返回 502 `AI_FAILED`,且不向 `ai_reports` 插入任何记录。
- 「重新生成」始终插入新的 `ai_reports` 记录,**不删除或修改** 既有记录(需求 14.11)。

---

## 6. 合规违规自查清单

合入主分支前应逐项核对:

- [ ] 后端路由数 = 9,且与 §1.1 表一一对应
- [ ] 前端路由数 = 7(+ 通配 `*`),且与 §1.4 列表一致
- [ ] `grep` 全仓未发现向小红书发起评论 / 点赞 / 收藏 / 私信 / 关注 / 发布的代码路径
- [ ] 配置层未出现账号列表 / 账号池 / 账号轮换结构
- [ ] `backend/.env.example` 中 `HOST=127.0.0.1`,无 `0.0.0.0`、`::`、外网 IP 或域名
- [ ] FastAPI 启动后实际监听仅 `127.0.0.1`,CORS 来源仅 `127.0.0.1`
- [ ] `data/` 目录之外的磁盘路径无采集数据写入
- [ ] `notes.raw_json` 中已剥离 `phone` / `mobile` / `email` / `bind_email` / `id_card` / `id_number` / `identity` 键
- [ ] `Crawler_Service` 仅传 `--type search`,未传任何点赞 / 收藏 / 私信 / 关注 / 发布相关参数
- [ ] `.gitmodules` 中 `third_party/MediaCrawler` commit SHA 指针未被修改、子模块下文件无新增 / 修改 / 删除提交
- [ ] AuditLog 在任务进入终态时写入完整五元组
- [ ] AI 报告生成路径未对 `notes` / `comments` / `authors` / `tasks` 任一表写入
- [ ] 唯一对外网络出站为 LLM Provider 调用,且仅传输需求 14.6、14.7 规定的 prompt 内容

任何一项不通过,视为违反合规红线,必须先修复后才允许合入。

---

## 7. 变更治理

- 本文件的任何条款修改必须同步反映到 `requirements.md` 需求 19、20 与 `design.md` 第 5 节,三者之间不允许出现条款级别冲突。
- 修改记录通过 git 提交历史追踪,提交信息中应明确「合规边界变更」字样以便审计。

