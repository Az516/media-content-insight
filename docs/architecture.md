# 架构文档(草稿):xhs-content-insight

> 本文档为草稿,随后续 M1 - M7 里程碑迭代;现阶段仅锁定与子模块 / 第三方依赖相关的硬约束。

## 1. 第三方依赖:MediaCrawler 子模块约定

本项目通过 git submodule 接入 [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler),挂载位置为仓库根目录下的 `third_party/MediaCrawler`。

### 1.1 当前固定指针

- 子模块路径:`third_party/MediaCrawler`
- 远端仓库:`https://github.com/NanmiCoder/MediaCrawler.git`
- pinned commit SHA:`f328ee35b55e25e8aaeb9c847fe8b622e3f3447f`

`.gitmodules` 文件中以注释形式同步记录该 SHA,任何升级都必须先在 `.gitmodules` 中更新 `pinned-commit` 注释,再随后续 `git add third_party/MediaCrawler` 一起提交。

### 1.2 硬性约束(严禁违反)

1. **子模块仅可通过更新 commit SHA 指针的方式升级,严禁直接修改 `third_party/MediaCrawler/` 下的任何文件。**
   - 不允许在子模块工作树内执行 `git commit`、`git push`、`git rebase`、手工编辑文件等任何会改动 `third_party/MediaCrawler` 内容的操作。
   - 不允许通过 patch、补丁文件、symlink 注入等迂回方式修改子模块内文件。
2. 本仓库的 git 提交历史中,除「`.gitmodules` 中该子模块 commit SHA 指针的更新提交」之外,**不应** 出现任何对 `third_party/MediaCrawler/` 目录下文件内容的新增、修改或删除提交(对齐需求 6.2)。
3. 后端的 `CrawlerService` 在调用 MediaCrawler 时,只读其 `main.py` 与运行时输出,**不写入** 也 **不删除** `third_party/MediaCrawler/` 下的任何文件(对齐需求 6.5)。
4. 子模块路径与解释器路径分别由环境变量 `MEDIA_CRAWLER_ROOT`(默认 `third_party/MediaCrawler`)与 `MEDIA_CRAWLER_PYTHON`(默认当前后端 Python 解释器)配置(对齐需求 6.3、6.5)。

### 1.3 升级流程

```bash
# 1) 在子模块内 fetch + 切换到目标 SHA(只读切换,不在子模块内提交任何变更)
cd third_party/MediaCrawler
git fetch origin
git checkout <new-sha>

# 2) 回到主仓库,同步 .gitmodules 中的 pinned-commit 注释
cd ../..
# 编辑 .gitmodules,把 pinned-commit = ... 改为 <new-sha>

# 3) 提交一次「指针更新」commit
git add .gitmodules third_party/MediaCrawler
git commit -m "chore: bump MediaCrawler to <new-sha>"
```

任何不遵循上述流程的修改(尤其是直接在子模块内编辑文件后提交)都视为违反硬性约束,需要在 PR 审查阶段被拒绝。

### 1.4 初始化与拉取

新克隆本仓库后必须执行:

```bash
git submodule update --init --recursive
```

否则 `third_party/MediaCrawler/main.py` 不存在,`CrawlerService` 启动前置校验会按需求 6.6 把任务标记为 `failed`(`error_msg` 指明 MediaCrawler 子模块未就绪)。

---

后续章节(系统拓扑、数据流、状态机、合规边界等)随对应里程碑补充。
