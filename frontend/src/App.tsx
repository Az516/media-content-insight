import { Route, Routes } from 'react-router-dom';

import ComplianceBanner from '@/components/ComplianceBanner';
import Placeholder from '@/components/Placeholder';

/**
 * 应用根组件 (`frontend/src/App.tsx`)。
 *
 * 任务 1.5 注册 7 条主路由(需求 17.1)+ `*` 兜底路由(需求 17.8);
 * 任务 8.1 在 `<Routes>` 之外固定挂载 `ComplianceBanner`(需求 17.7 / 18.1 / 18.2),
 * 使其在路由切换、页面滚动期间持续可见,且不提供关闭 / 隐藏入口。
 */
export function App(): JSX.Element {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <ComplianceBanner />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">
        <Routes>
          <Route path="/" element={<Placeholder name="Home" />} />
          <Route path="/tasks" element={<Placeholder name="TaskManager" />} />
          <Route
            path="/tasks/:taskId"
            element={<Placeholder name="TaskDetail" />}
          />
          <Route
            path="/tasks/:taskId/notes"
            element={<Placeholder name="NoteList" />}
          />
          <Route
            path="/tasks/:taskId/notes/:noteId"
            element={<Placeholder name="NoteDetail" />}
          />
          <Route
            path="/tasks/:taskId/insights"
            element={<Placeholder name="Insights" />}
          />
          <Route
            path="/tasks/:taskId/report"
            element={<Placeholder name="Report" />}
          />
          {/* 通配兜底,需求 17.8;实际 NotFound 页面在 §9.7 替换 */}
          <Route path="*" element={<Placeholder name="NotFound" />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
