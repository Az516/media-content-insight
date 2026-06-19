import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom';

import ComplianceBanner from '@/components/ComplianceBanner';
import Home from '@/pages/Home';
import Insights from '@/pages/Insights';
import NoteDetail from '@/pages/NoteDetail';
import NoteList from '@/pages/NoteList';
import Report from '@/pages/Report';
import TaskDetail from '@/pages/TaskDetail';
import TaskManager from '@/pages/TaskManager';

function Brand(): JSX.Element {
  return (
    <Link
      to="/"
      className="group inline-flex items-baseline gap-2 leading-none"
      aria-label="多平台内容洞察实验室"
    >
      <span
        aria-hidden
        className="text-2xl font-medium leading-none text-claret-500 transition group-hover:rotate-12"
      >
        ◆
      </span>
      <span className="font-display text-[22px] font-semibold tracking-tightish text-ink-900">
        media
        <span className="px-0.5 text-claret-500">·</span>
        <span className="text-ink-700">insight</span>
      </span>
      <span className="hidden font-mono text-[10px] uppercase tracking-[0.18em] text-ink-400 md:inline">
        Vol. 01 / MVP
      </span>
    </Link>
  );
}

function NavItem({ to, label }: { to: string; label: string }): JSX.Element {
  return (
    <NavLink
      end={to === '/'}
      to={to}
      className={({ isActive }) =>
        [
          'relative rounded-md px-2 py-1 text-sm transition',
          isActive
            ? 'text-ink-900'
            : 'text-ink-500 hover:text-ink-900',
        ].join(' ')
      }
    >
      {({ isActive }) => (
        <span className="relative">
          {label}
          {isActive && (
            <span
              aria-hidden
              className="absolute -bottom-1 left-0 right-0 h-[2px] bg-claret-500"
            />
          )}
        </span>
      )}
    </NavLink>
  );
}

function Shell({ children }: { children: JSX.Element }): JSX.Element {
  const location = useLocation();
  return (
    <div className="flex min-h-screen flex-col text-ink-900">
      <ComplianceBanner />
      <header className="border-b border-rule bg-paper-50/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-6 px-6 py-5">
          <Brand />
          <nav className="flex items-center gap-4 text-sm">
            <NavItem to="/" label="开始" />
            <NavItem to="/tasks" label="任务" />
            <a
              href="https://github.com/NanmiCoder/MediaCrawler"
              target="_blank"
              rel="noreferrer noopener"
              className="hidden text-ink-400 transition hover:text-ink-700 md:inline"
            >
              MediaCrawler ↗
            </a>
          </nav>
        </div>
      </header>

      <main
        key={location.pathname}
        className="page-enter mx-auto w-full max-w-6xl flex-1 px-6 py-10"
      >
        {children}
      </main>

      <footer className="mt-auto border-t border-rule bg-paper-50/60 py-6">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 text-[12px] text-ink-500">
          <span className="font-mono uppercase tracking-[0.18em]">
            multi-platform · research only
          </span>
          <span>
            单次采集上限 <span className="font-mono text-ink-700">20</span> 条 ·
            同一时刻仅允许 <span className="font-mono text-ink-700">1</span> 个采集任务
          </span>
          <span className="font-display italic">
            for editorial study, not for marketing
          </span>
        </div>
      </footer>
    </div>
  );
}

export function App(): JSX.Element {
  return (
    <Routes>
      <Route path="/" element={<Shell><Home /></Shell>} />
      <Route path="/tasks" element={<Shell><TaskManager /></Shell>} />
      <Route path="/tasks/:taskId" element={<Shell><TaskDetail /></Shell>} />
      <Route path="/tasks/:taskId/notes" element={<Shell><NoteList /></Shell>} />
      <Route path="/tasks/:taskId/notes/:noteId" element={<Shell><NoteDetail /></Shell>} />
      <Route path="/tasks/:taskId/insights" element={<Shell><Insights /></Shell>} />
      <Route path="/tasks/:taskId/report" element={<Shell><Report /></Shell>} />
      <Route
        path="*"
        element={
          <Shell>
            <div className="mx-auto max-w-xl rounded-3xl border border-rule bg-white/70 p-12 text-center shadow-paper">
              <div className="font-display text-7xl font-semibold tracking-tighter text-claret-500">
                404
              </div>
              <p className="mt-3 text-sm text-ink-500">
                这条路径不在已注册的 7 条前端路由中。
              </p>
              <Link
                to="/"
                className="mt-6 inline-flex items-center gap-2 rounded-xl bg-ink-900 px-5 py-2.5 text-sm font-medium text-paper-50 hover:bg-ink-700"
              >
                ← 返回首页
              </Link>
            </div>
          </Shell>
        }
      />
    </Routes>
  );
}

export default App;
