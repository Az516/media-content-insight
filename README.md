# media-content-insight

> ⚠️ **本项目仅供学习研究和小规模数据分析使用**,不得用于任何商业用途、自动化营销、批量发布或对外服务化。
> 使用前请务必阅读并遵守 [合规边界文档 `docs/compliance.md`](docs/compliance.md) 中的全部红线条款。

`media-content-insight` 是一个本地化、单用户、研究用途的多平台内容洞察 MVP。系统面向小红书、B 站、抖音、公众号等公开内容源的关键词研究场景,通过采集少量内容及热门评论,落库到本地 SQLite 并归档为 JSON 文件,然后在 React 前端提供素材池、内容详情、评论洞察、AI 分析报告等视图。

## 合规红线(必读)

- 仅本地运行,FastAPI 默认仅监听 `127.0.0.1`,不对外暴露任何端口。
- 仅实现「关键词搜索 → 采集内容 + 评论 → 本地分析」一条数据流;**禁止** 自动评论 / 点赞 / 收藏 / 私信 / 关注 / 发布、批量账号、绕过登录验证、二次分发等任何写操作。
- 单次采集 ≤ 20 条内容,同一时刻全局仅允许 1 个采集任务运行,不并发不重试。
- 数据仅落地至本仓库 `data/` 目录,不向任何第三方对象存储或公网数据库上传。
- 完整条款见 [`docs/compliance.md`](docs/compliance.md),任何实现 **不得** 与之冲突。

## 技术栈

- **后端**:Python + FastAPI + SQLAlchemy 2 + aiosqlite + pytest + hypothesis
- **前端**:React + Vite + TypeScript + Tailwind CSS + react-markdown + vitest
- **爬虫引擎**:[MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)(git submodule,只调用不修改;当前以小红书链路为首个落地适配)

## 目录结构

```
media-content-insight/
├── backend/            # FastAPI 后端
├── frontend/           # React + Vite 前端
├── third_party/        # 第三方依赖(含 MediaCrawler 子模块)
├── data/               # 本地数据(SQLite + JSON 归档,git 忽略)
├── docs/               # 设计与合规文档
└── docker-compose.yml  # 可选:本地一键启动
```

## 快速开始

> 详细的安装与运行说明将在后续里程碑(M1 之后)逐步补充。当前阶段仅完成项目脚手架与合规边界,运行所需的后端 / 前端 / 子模块尚在搭建中。

1. 克隆仓库并初始化 MediaCrawler 子模块:

   ```bash
   git clone <this-repo>
   cd media-content-insight
   git submodule update --init --recursive
   ```

2. 阅读 [`docs/compliance.md`](docs/compliance.md),确认合规边界后再进入开发或试用流程。

## 文档索引

- [合规边界 `docs/compliance.md`](docs/compliance.md):需求 19、20 全量禁止条款及本地化、单一 Cookie、≤20 条采集、≤1 并发、`raw_json` 敏感字段剥离等约束。
- 设计文档:`.kiro/specs/media-content-insight/design.md`
- 需求文档:`.kiro/specs/media-content-insight/requirements.md`
- 任务清单:`.kiro/specs/media-content-insight/tasks.md`

## 免责声明

本项目作者不为使用者基于本工具产生的任何行为承担责任。使用者应自行遵守目标平台条款及当地法律法规。如发现违反 [`docs/compliance.md`](docs/compliance.md) 的代码或用法,请立即停止使用并删除本地数据。
