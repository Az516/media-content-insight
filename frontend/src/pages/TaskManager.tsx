import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { listTasks } from '@/api/tasks';
import type { TaskListItem, TaskStatus } from '@/types/models';
import { platformLabels } from '@/data/workbench';

const STATUS_OPTIONS: { value: TaskStatus | 'all'; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'pending', label: '排队中' },
  { value: 'running', label: '采集中' },
  { value: 'success', label: '完成' },
  { value: 'failed', label: '失败' },
];

const STATUS_TONE: Record<TaskStatus, string> = {
  pending: 'bg-paper-200 text-ink-700 ring-rule',
  running: 'bg-sage-50 text-sage-600 ring-sage-100',
  success: 'bg-paper-100 text-ink-900 ring-rule',
  failed: 'bg-claret-50 text-claret-600 ring-claret-100',
};

const STATUS_LABEL: Record<TaskStatus, string> = {
  pending: '排队中',
  running: '采集中',
  success: '完成',
  failed: '失败',
};

function formatTime(value: string | null | undefined): string {
  if (!value) return '-';
  return value.replace('T', ' ').slice(0, 16);
}

export default function TaskManager(): JSX.Element {
  const [items, setItems] = useState<TaskListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<TaskStatus | 'all'>('all');

  useEffect(() => {
    listTasks()
      .then((res) => setItems(res.items ?? []))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    if (filter === 'all') return items;
    return items.filter((t) => t.status === filter);
  }, [items, filter]);

  return (
    <section className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs font-semibold text-ink-500">
            采集归档
          </div>
          <h2 className="mt-1 font-display text-4xl font-medium tracking-tightish text-ink-900">
            任务列表
          </h2>
          <p className="mt-1 text-sm text-ink-500">
            共 <span className="font-mono tabular-nums text-ink-900">{items.length}</span> 个任务
          </p>
        </div>
        <Link
          to="/track-search"
          className="inline-flex items-center gap-2 rounded-xl bg-ink-900 px-5 py-2.5 text-sm font-medium text-paper-50 transition hover:bg-claret-500"
        >
          + 新建任务
        </Link>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-rule pb-3">
        {STATUS_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setFilter(opt.value)}
            className={`rounded-full px-4 py-1.5 text-xs font-medium transition ${
              filter === opt.value
                ? 'bg-ink-900 text-paper-50'
                : 'bg-white/60 text-ink-500 ring-1 ring-rule hover:text-ink-900'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="rounded-2xl border border-rule bg-white/70 p-10 text-center text-sm text-ink-500">
          加载中…
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-rule bg-paper-50 p-12 text-center text-sm text-ink-500">
          {items.length === 0
            ? '还没有任务，先去首页创建一个关键词采集任务吧。'
            : '当前筛选条件下没有任务。'}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-rule bg-white/70 shadow-lift">
          <table className="min-w-[760px] w-full text-left text-sm">
            <thead className="bg-paper-50 text-xs font-semibold text-ink-500">
              <tr>
                <th className="px-5 py-3">#</th>
                <th className="px-5 py-3">关键词</th>
                <th className="px-5 py-3">平台</th>
                <th className="px-5 py-3">状态</th>
                <th className="px-5 py-3 text-right">笔记数</th>
                <th className="px-5 py-3">创建时间</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {filtered.map((item) => (
                <tr key={item.id} className="transition hover:bg-paper-50">
                  <td className="px-5 py-3.5 font-mono text-xs tabular-nums text-ink-500">
                    {item.id}
                  </td>
                  <td className="px-5 py-3.5 font-display text-base text-ink-900">
                    「{item.keyword || '-'}」
                  </td>
                  <td className="px-5 py-3.5 text-xs text-ink-500">
                    {item.platform ? platformLabels[item.platform] : '小红书'}
                  </td>
                  <td className="px-5 py-3.5">
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[10.5px] font-medium ring-1 ring-inset ${STATUS_TONE[item.status]}`}
                    >
                      {STATUS_LABEL[item.status]}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 text-right font-mono tabular-nums text-ink-700">
                    {item.note_count ?? 0}
                  </td>
                  <td className="px-5 py-3.5 font-mono text-xs tabular-nums text-ink-500">
                    {formatTime(item.created_at)}
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    <Link
                      to={`/tasks/${item.id}`}
                      className="text-sm text-claret-500 underline-offset-4 hover:underline"
                    >
                      查看 →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
