import { useTheme } from '@/contexts/ThemeContext';

export default function ThemeToggle(): JSX.Element {
  const { isDark, toggleTheme } = useTheme();

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={isDark ? '切换到浅色模式' : '切换到夜间模式'}
      className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
    >
      {isDark ? '浅色' : '夜间'}
    </button>
  );
}
