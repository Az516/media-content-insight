import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { listNotes, listTasks } from '@/api/tasks';
import { PageTitle, Panel, StatusTag } from '@/components/ui';
import type { NoteSummary, TaskListItem } from '@/types/models';

type SortKey = 'comment' | 'collect' | 'like';

const SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
  { key: 'comment', label: '按评论' },
  { key: 'collect', label: '按收藏' },
  { key: 'like', label: '按点赞' },
];

export default function Opportunities(): JSX.Element {
  const navigate = useNavigate();
  const [task, setTask] = useState<TaskListItem | null>(null);
  const [notes, setNotes] = useState<NoteSummary[]>([]);
  const [sortBy, setSortBy] = useState<SortKey>('comment');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listTasks()
      .then(async (res) => {
        if (cancelled) return;
        const latestSuccess = (res.items ?? []).find((item) => item.status === 'success') ?? null;
        setTask(latestSuccess);
        if (latestSuccess) {
          const noteRes = await listNotes(latestSuccess.id);
          if (!cancelled) setNotes(noteRes.items ?? []);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const sorted = useMemo(() => {
    const copy = [...notes];
    copy.sort((a, b) => {
      if (sortBy === 'collect') return (b.collected_count ?? 0) - (a.collected_count ?? 0);
      if (sortBy === 'like') return (b.liked_count ?? 0) - (a.liked_count ?? 0);
      return (b.comment_count ?? 0) - (a.comment_count ?? 0);
    });
    return copy;
  }, [notes, sortBy]);

  return (
    <div>
      <PageTitle title="真实内容素材" />
      <Panel className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 px-8 py-6">
          <div>
            <div className="text-sm font-semibold text-slate-500">来源任务</div>
            <div className="mt-1 text-2xl font-semibold text-slate-950">
              {task ? `「${task.keyword}」` : '暂无已完成任务'}
            </div>
          </div>
          {task && <StatusTag tone="green">{notes.length} 条真实笔记</StatusTag>}
        </div>

        {loading ? (
          <div className="p-10 text-center text-sm text-slate-500">加载真实笔记...</div>
        ) : !task ? (
          <div className="p-12 text-center">
            <div className="text-base font-semibold text-slate-900">还没有可展示的真实素材</div>
            <Link className="mt-4 inline-flex rounded-xl bg-blue-600 px-5 py-2 text-sm font-semibold text-white" to="/track-search">
              去采集关键词
            </Link>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap gap-2 border-b border-slate-200 px-8 py-4">
              {SORT_OPTIONS.map((option) => (
                <button
                  key={option.key}
                  className={`rounded-full px-4 py-1.5 text-xs font-semibold transition ${
                    sortBy === option.key
                      ? 'bg-slate-950 text-white'
                      : 'bg-white text-slate-600 ring-1 ring-slate-300 hover:text-slate-950'
                  }`}
                  type="button"
                  onClick={() => setSortBy(option.key)}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <div className="divide-y divide-slate-200">
              {sorted.map((note) => (
                <article
                  key={note.note_id}
                  className="grid gap-5 px-8 py-6 md:grid-cols-[minmax(0,1fr)_100px_100px_100px_110px] md:items-center"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-3 text-sm text-slate-500">
                      <span className="inline-grid h-6 w-6 place-items-center rounded-md bg-rose-500 text-[10px] font-bold text-white">小</span>
                      <span>小红书</span>
                      <span>{note.type === 'video' ? '视频' : '图文'}</span>
                    </div>
                    <h2 className="mt-3 line-clamp-2 text-[18px] font-semibold text-slate-950">
                      {note.title || '无标题'}
                    </h2>
                    <div className="mt-2 truncate text-sm text-slate-500">
                      作者：{note.author?.nickname || note.author?.user_id || '-'}
                    </div>
                  </div>
                  <Metric label="评论" value={note.comment_count} />
                  <Metric label="收藏" value={note.collected_count} />
                  <Metric label="点赞" value={note.liked_count} />
                  <button
                    className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-blue-600 shadow-sm transition hover:bg-blue-50"
                    type="button"
                    onClick={() => navigate(`/tasks/${task.id}/notes/${note.note_id}`)}
                  >
                    查看原始数据
                  </button>
                </article>
              ))}
            </div>
          </>
        )}
      </Panel>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }): JSX.Element {
  return (
    <div>
      <div className="text-xs text-slate-400">{label}</div>
      <div className="mt-1 font-semibold tabular-nums text-slate-700">{value?.toLocaleString?.() ?? 0}</div>
    </div>
  );
}
