import { NavLink, Outlet } from 'react-router-dom';

import { Icon, type IconName } from '@/components/icons';

const navItems: Array<{ to: string; label: string; icon: IconName }> = [
  { to: '/', label: '工作台', icon: 'home' },
  { to: '/track-search', label: '关键词采集', icon: 'search' },
  { to: '/opportunities', label: '真实素材', icon: 'target' },
  { to: '/leads', label: '热门评论', icon: 'user' },
  { to: '/draft-review', label: '草稿审核', icon: 'file' },
  { to: '/reports', label: '报告', icon: 'chart' },
  { to: '/integrations', label: '平台集成', icon: 'link' },
];

function Brand(): JSX.Element {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-12 w-10 items-center justify-center gap-1">
        <span className="h-6 w-2 rounded-full bg-teal-500/55" />
        <span className="h-10 w-3 rounded-full bg-teal-600/70" />
        <span className="h-8 w-2 rounded-full bg-teal-400/45" />
      </div>
      <div className="text-[20px] font-bold leading-[0.92] tracking-normal text-slate-950">
        <div>媒介</div>
        <div>洞察</div>
      </div>
    </div>
  );
}

function Sidebar(): JSX.Element {
  return (
    <aside className="fixed inset-y-0 left-0 z-20 hidden w-[260px] flex-col border-r border-slate-300/80 bg-white/88 pb-8 pt-12 shadow-sidebar backdrop-blur-2xl lg:flex">
      <div className="px-6">
        <Brand />
      </div>
      <nav className="mt-16 space-y-4 px-5">
        {navItems.map((item) => (
          <NavLink
            end={item.to === '/'}
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              [
                'flex h-14 items-center gap-4 rounded-2xl px-5 text-[17px] font-semibold transition',
                isActive
                  ? 'bg-teal-100/80 text-teal-900 ring-1 ring-teal-200/70 shadow-[0_8px_24px_-18px_rgba(13,148,136,0.8)]'
                  : 'text-slate-700 hover:bg-slate-100 hover:text-slate-950',
              ].join(' ')
            }
          >
            <Icon name={item.icon} className="h-6 w-6" />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <button
        aria-label="收起导航"
        className="mx-auto mt-auto grid h-12 w-20 place-items-center rounded-xl border border-slate-200 bg-white text-slate-400 shadow-[0_8px_24px_rgba(15,23,42,0.04)] transition hover:text-slate-600"
        type="button"
      >
        <Icon name="doubleChevron" className="h-5 w-5" />
      </button>
    </aside>
  );
}

function MobileNav(): JSX.Element {
  return (
    <nav className="fixed inset-x-4 bottom-4 z-30 grid grid-cols-7 rounded-2xl border border-slate-300 bg-white/94 p-2 shadow-sidebar backdrop-blur-xl lg:hidden">
      {navItems.map((item) => (
        <NavLink
          end={item.to === '/'}
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            [
              'grid h-11 place-items-center rounded-xl transition',
              isActive ? 'bg-teal-50 text-teal-800' : 'text-slate-500',
            ].join(' ')
          }
          title={item.label}
        >
          <Icon name={item.icon} className="h-5 w-5" />
        </NavLink>
      ))}
    </nav>
  );
}

function Topbar(): JSX.Element {
  return (
    <header className="app-measure flex h-16 items-center justify-between gap-3 lg:h-20">
      <div className="flex min-w-0 items-center gap-3 lg:hidden">
        <Brand />
      </div>
      <div className="hidden lg:block" />
      <div className="ml-auto flex shrink-0 items-center gap-3 sm:gap-5">
        <div
          aria-label="本地采集已连接"
          className="fixed right-5 top-8 z-40 grid h-10 w-10 place-items-center rounded-full border border-slate-300 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.08)] sm:hidden"
          title="本地采集已连接"
        >
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
        </div>
        <div className="hidden h-10 items-center gap-2 whitespace-nowrap rounded-full border border-slate-300 bg-white px-3 text-sm font-medium text-slate-800 shadow-[0_1px_2px_rgba(15,23,42,0.08)] sm:inline-flex sm:h-12 sm:gap-3 sm:px-5 sm:text-[16px]">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
          本地采集已连接
        </div>
        <div className="hidden items-center gap-3 sm:flex">
          <div className="grid h-12 w-12 place-items-center overflow-hidden rounded-full bg-gradient-to-br from-rose-100 via-slate-100 to-teal-100 text-sm font-bold text-slate-700 ring-1 ring-slate-200">
            洞
          </div>
          <Icon name="chevron" className="h-4 w-4 rotate-90 text-slate-400" />
        </div>
      </div>
    </header>
  );
}

export default function AppShell(): JSX.Element {
  return (
    <div className="min-h-screen bg-app text-slate-950">
      <Sidebar />
      <div className="min-h-screen pb-24 pt-2 lg:ml-[260px] lg:pb-16">
        <Topbar />
        <main className="app-measure page-enter lg:pt-2">
          <Outlet />
        </main>
      </div>
      <MobileNav />
    </div>
  );
}
