# frontend (xhs-content-insight)

React + Vite + TypeScript + Tailwind 单页应用。仅供本地开发,严禁对外部署或开放访问。

## 本地开发

```bash
npm install
npm run dev      # 启动 Vite dev server,监听 127.0.0.1:5173
npm run build    # 类型检查 + 生产构建
npm run test     # 运行 vitest 单元测试
```

后端 API 默认期望运行在 `http://127.0.0.1:8000/api`。如需调整,可在 `frontend/.env.local` 中设置 `VITE_API_BASE_URL`(出于合规约束,不要指向非 `127.0.0.1` 的地址)。

## 路由

参考 `src/App.tsx`,目前 7 条业务路由 + 1 条 `*` 兜底。实际页面会在任务 9.x 中替换占位组件。

| 路径 | 占位名 |
| --- | --- |
| `/` | Home |
| `/tasks` | TaskManager |
| `/tasks/:taskId` | TaskDetail |
| `/tasks/:taskId/notes` | NoteList |
| `/tasks/:taskId/notes/:noteId` | NoteDetail |
| `/tasks/:taskId/insights` | Insights |
| `/tasks/:taskId/report` | Report |
| `*` | NotFound(任务 9.7 替换) |
