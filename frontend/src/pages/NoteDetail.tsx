import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { getNote } from '@/api/tasks';
import CommentTree from '@/components/CommentTree';
import type { NoteDetailResponse } from '@/types/models';

function StatBlock({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: number | string;
  accent?: boolean;
}): JSX.Element {
  return (
    <div className="rounded-2xl border border-rule bg-white/70 px-4 py-3 shadow-lift">
      <div className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-500">
        {label}
      </div>
      <div
        className={`mt-1 font-display text-2xl font-medium tabular-nums ${
          accent ? 'text-claret-500' : 'text-ink-900'
        }`}
      >
        {typeof value === 'number' ? value.toLocaleString() : value}
      </div>
    </div>
  );
}

export default function NoteDetail(): JSX.Element {
  const { taskId, noteId } = useParams();
  const [data, setData] = useState<NoteDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!noteId) return;
    setLoading(true);
    getNote(noteId)
      .then(setData)
      .finally(() => setLoading(false));
  }, [noteId]);

  if (loading || !data) {
    return (
      <div className="rounded-2xl border border-rule bg-white/70 p-10 text-center text-sm text-ink-500">
        {loading ? '加载笔记…' : '笔记不存在'}
      </div>
    );
  }

  const note = data.note;
  const author = data.author;

  return (
    <section className="space-y-8">
      <div>
        <div className="flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.25em] text-ink-500">
          <Link to={`/tasks/${taskId}/notes`} className="hover:text-ink-900">
            ← 素材池
          </Link>
          <span className="text-ink-400">/</span>
          <span>{note.note_id}</span>
        </div>
        <h2 className="mt-3 font-display text-4xl font-medium leading-tight tracking-tightish text-ink-900">
          {note.title || '无标题'}
        </h2>
        {note.publish_time && (
          <p className="mt-2 font-mono text-xs tabular-nums text-ink-500">
            发布于 {note.publish_time.replace('T', ' ').slice(0, 16)}
            {note.ip_location ? ` · ${note.ip_location}` : ''}
          </p>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-6">
          {note.cover_url && note.type !== 'video' && (
            <img
              src={note.cover_url}
              alt={note.title ?? ''}
              className="w-full rounded-2xl border border-rule object-cover shadow-lift"
            />
          )}
          {note.video_url && (
            <video
              controls
              src={note.video_url}
              poster={note.cover_url ?? undefined}
              className="w-full rounded-2xl border border-rule shadow-lift"
            />
          )}

          <div className="rounded-2xl border border-rule bg-white/70 p-6 shadow-lift">
            <p className="whitespace-pre-line text-[15px] leading-relaxed text-ink-700">
              {note.desc || '-'}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatBlock label="Likes" value={note.liked_count ?? 0} accent />
            <StatBlock label="Collects" value={note.collected_count ?? 0} />
            <StatBlock label="Comments" value={note.comment_count ?? 0} />
            <StatBlock label="Shares" value={note.share_count ?? 0} />
          </div>
        </div>

        <aside className="space-y-6">
          {author && (
            <div className="rounded-2xl border border-rule bg-white/70 p-5 shadow-lift">
              <div className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-500">
                Author
              </div>
              <div className="mt-3 flex items-center gap-3">
                {author.avatar ? (
                  <img
                    src={author.avatar}
                    alt={author.nickname ?? ''}
                    className="h-12 w-12 rounded-full border border-rule object-cover"
                  />
                ) : (
                  <div className="flex h-12 w-12 items-center justify-center rounded-full border border-rule bg-paper-100 font-display text-claret-500">
                    {(author.nickname || '?').slice(0, 1)}
                  </div>
                )}
                <div className="min-w-0">
                  <div className="truncate font-display text-base text-ink-900">
                    {author.nickname || author.user_id}
                  </div>
                  {author.ip_location && (
                    <div className="text-xs text-ink-500">{author.ip_location}</div>
                  )}
                </div>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-2 text-center text-xs">
                <div className="rounded-lg bg-paper-50 px-2 py-2">
                  <div className="text-ink-500">粉丝</div>
                  <div className="font-mono text-base tabular-nums text-ink-900">
                    {author.fans_count ?? 0}
                  </div>
                </div>
                <div className="rounded-lg bg-paper-50 px-2 py-2">
                  <div className="text-ink-500">关注</div>
                  <div className="font-mono text-base tabular-nums text-ink-900">
                    {author.follow_count ?? 0}
                  </div>
                </div>
              </div>
            </div>
          )}

          {note.tag_list && note.tag_list.length > 0 && (
            <div className="rounded-2xl border border-rule bg-white/70 p-5 shadow-lift">
              <div className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-500">
                Tags
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {note.tag_list.map((t) => (
                  <span
                    key={t}
                    className="rounded-full bg-claret-50 px-2.5 py-0.5 text-xs text-claret-600"
                  >
                    #{t}
                  </span>
                ))}
              </div>
            </div>
          )}
        </aside>
      </div>

      <div className="rounded-2xl border border-rule bg-white/70 p-6 shadow-lift">
        <h3 className="font-display text-xl text-ink-900">评论树</h3>
        <div className="mt-4">
          <CommentTree comments={data.comments} />
        </div>
      </div>
    </section>
  );
}
