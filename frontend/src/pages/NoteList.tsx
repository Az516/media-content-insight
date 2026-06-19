import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { listNotes } from '@/api/tasks';
import NoteCard from '@/components/NoteCard';
import type { NoteSummary } from '@/types/models';

type SortKey = 'like' | 'collect' | 'comment';

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'like', label: '按点赞' },
  { value: 'collect', label: '按收藏' },
  { value: 'comment', label: '按评论' },
];

export default function NoteList(): JSX.Element {
  const { taskId } = useParams();
  const navigate = useNavigate();
  const [items, setItems] = useState<NoteSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<SortKey>('like');

  useEffect(() => {
    if (!taskId) return;
    setLoading(true);
    listNotes(Number(taskId))
      .then((res) => setItems(res.items ?? []))
      .finally(() => setLoading(false));
  }, [taskId]);

  const sorted = useMemo(() => {
    const copy = [...items];
    copy.sort((a, b) => {
      if (sortBy === 'collect') return (b.collected_count ?? 0) - (a.collected_count ?? 0);
      if (sortBy === 'comment') return (b.comment_count ?? 0) - (a.comment_count ?? 0);
      return (b.liked_count ?? 0) - (a.liked_count ?? 0);
    });
    return copy;
  }, [items, sortBy]);

  return (
    <section className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.25em] text-ink-500">
            <Link to={`/tasks/${taskId}`} className="hover:text-ink-900">
              ← Task #{taskId}
            </Link>
            <span className="text-ink-400">/</span>
            <span>素材池</span>
          </div>
          <h2 className="mt-2 font-display text-4xl font-medium tracking-tightish text-ink-900">
            素材池
          </h2>
          <p className="mt-1 text-sm text-ink-500">
            共 <span className="font-mono tabular-nums text-ink-900">{items.length}</span> 条笔记，按互动数排序
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {SORT_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setSortBy(opt.value)}
              className={`rounded-full px-4 py-1.5 text-xs font-medium transition ${
                sortBy === opt.value
                  ? 'bg-ink-900 text-paper-50'
                  : 'bg-white/60 text-ink-500 ring-1 ring-rule hover:text-ink-900'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="rounded-2xl border border-rule bg-white/70 p-10 text-center text-sm text-ink-500">
          加载中…
        </div>
      ) : sorted.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-rule bg-paper-50 p-12 text-center text-sm text-ink-500">
          暂无素材，返回首页创建一个任务吧。
        </div>
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {sorted.map((note, idx) => (
            <div
              key={note.note_id}
              className="animate-fade-up"
              style={{ animationDelay: `${Math.min(idx * 40, 400)}ms` }}
            >
              <NoteCard
                note={note}
                onClick={(noteId) => navigate(`/tasks/${taskId}/notes/${noteId}`)}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
