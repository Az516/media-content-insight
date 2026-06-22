import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { getNote } from '@/api/tasks';
import { extractApiError, proxiedMediaUrl } from '@/api/client';
import CommentTree from '@/components/CommentTree';
import type { Author, NoteDetailResponse } from '@/types/models';

function isPlayableVideoUrl(value: string | null | undefined): boolean {
  if (!value) return false;
  try {
    const url = new URL(value);
    if (url.hostname.endsWith('xiaohongshu.com')) return false;
  } catch {
    return false;
  }
  return true;
}

function MediaPreview({
  coverUrl,
  videoUrl,
  title,
}: {
  coverUrl: string | null;
  videoUrl: string | null;
  title: string | null;
}): JSX.Element | null {
  const [coverFailed, setCoverFailed] = useState(false);
  const [videoFailed, setVideoFailed] = useState(false);
  const coverSrc = proxiedMediaUrl(coverUrl);
  const playableVideo = isPlayableVideoUrl(videoUrl) ? proxiedMediaUrl(videoUrl) : null;

  useEffect(() => {
    setCoverFailed(false);
    setVideoFailed(false);
  }, [coverUrl, videoUrl]);

  if (playableVideo && !videoFailed) {
    return (
      <video
        controls
        src={playableVideo}
        poster={coverSrc ?? undefined}
        className="aspect-video w-full rounded-2xl border border-rule bg-ink-900 object-cover shadow-lift"
        onError={() => setVideoFailed(true)}
      />
    );
  }

  if (coverSrc && !coverFailed) {
    return (
      <img
        src={coverSrc}
        alt={title ?? ''}
        className="max-h-[640px] w-full rounded-2xl border border-rule object-cover shadow-lift"
        onError={() => setCoverFailed(true)}
      />
    );
  }

  return null;
}

function profileMetricUnavailable(author: Author): boolean {
  return (author.fans_count ?? 0) === 0 && (author.follow_count ?? 0) === 0;
}

function formatProfileMetric(
  value: number | null | undefined,
  unavailable: boolean,
): string {
  if (unavailable) return '未采集';
  return typeof value === 'number' ? value.toLocaleString() : '未采集';
}

function AuthorPanel({ author }: { author: Author }): JSX.Element {
  const [avatarFailed, setAvatarFailed] = useState(false);
  const avatarSrc = proxiedMediaUrl(author.avatar);
  const unavailable = profileMetricUnavailable(author);
  const fallbackInitial = (author.nickname || author.user_id || '?').slice(0, 1);

  return (
    <div className="rounded-2xl border border-rule bg-white/70 p-5 shadow-lift">
      <div className="font-mono text-[10.5px] tracking-[0.2em] text-ink-500">
        作者
      </div>
      <div className="mt-3 flex items-center gap-3">
        {avatarSrc && !avatarFailed ? (
          <img
            src={avatarSrc}
            alt={author.nickname ?? ''}
            className="h-12 w-12 rounded-full border border-rule object-cover"
            onError={() => setAvatarFailed(true)}
          />
        ) : (
          <div className="flex h-12 w-12 items-center justify-center rounded-full border border-rule bg-paper-100 font-display text-claret-500">
            {fallbackInitial}
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
          <div
            className={`mt-1 font-mono tabular-nums text-ink-900 ${
              unavailable ? 'text-xs' : 'text-base'
            }`}
          >
            {formatProfileMetric(author.fans_count, unavailable)}
          </div>
        </div>
        <div className="rounded-lg bg-paper-50 px-2 py-2">
          <div className="text-ink-500">关注</div>
          <div
            className={`mt-1 font-mono tabular-nums text-ink-900 ${
              unavailable ? 'text-xs' : 'text-base'
            }`}
          >
            {formatProfileMetric(author.follow_count, unavailable)}
          </div>
        </div>
      </div>
      {unavailable && (
        <p className="mt-3 text-xs leading-relaxed text-ink-500">
          主页指标未采集，避免用 0 作为占位。
        </p>
      )}
    </div>
  );
}

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
      <div className="font-mono text-[10.5px] tracking-[0.2em] text-ink-500">
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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!noteId) return;
    setLoading(true);
    setError(null);
    getNote(noteId)
      .then(setData)
      .catch((err) => {
        const apiError = extractApiError(err);
        setError(apiError.code === 'NOTE_NOT_FOUND' ? '笔记不存在' : `加载笔记失败：${apiError.message}`);
        setData(null);
      })
      .finally(() => setLoading(false));
  }, [noteId]);

  if (loading || error || !data) {
    return (
      <div className="rounded-2xl border border-rule bg-white/70 p-10 text-center text-sm text-ink-500">
        {loading ? '加载笔记…' : error ?? '笔记不存在'}
      </div>
    );
  }

  const note = data.note;
  const author = data.author;
  const tagList = parseTags(note.tag_list);

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
        <div className="mt-3 flex flex-wrap items-center gap-3">
          {note.publish_time && (
            <p className="font-mono text-xs tabular-nums text-ink-500">
              发布于 {note.publish_time.replace('T', ' ').slice(0, 16)}
              {note.ip_location ? ` · ${note.ip_location}` : ''}
            </p>
          )}
          {note.source_url ? (
            <a
              className="inline-flex h-9 items-center justify-center rounded-xl border border-rule bg-white px-3 text-sm font-medium text-claret-500 shadow-lift transition hover:border-claret-200 hover:bg-claret-50"
              href={note.source_url}
              target="_blank"
              rel="noreferrer"
            >
              打开原帖
            </a>
          ) : null}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-6">
          <MediaPreview
            coverUrl={note.cover_url}
            videoUrl={note.video_url}
            title={note.title}
          />

          <div className="rounded-2xl border border-rule bg-white/70 p-6 shadow-lift">
            <p className="whitespace-pre-line text-[15px] leading-relaxed text-ink-700">
              {note.desc || '-'}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatBlock label="点赞" value={note.liked_count ?? 0} accent />
            <StatBlock label="收藏" value={note.collected_count ?? 0} />
            <StatBlock label="评论" value={note.comment_count ?? 0} />
            <StatBlock label="分享" value={note.share_count ?? 0} />
          </div>
        </div>

        <aside className="space-y-6">
          {author && <AuthorPanel author={author} />}

          {tagList.length > 0 && (
            <div className="rounded-2xl border border-rule bg-white/70 p-5 shadow-lift">
              <div className="font-mono text-[10.5px] tracking-[0.2em] text-ink-500">
                话题
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {tagList.map((t) => (
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
        <h3 className="font-display text-xl text-ink-900">评论</h3>
        <p className="mt-1 text-sm text-ink-500">
          已采集 {data.comments.length.toLocaleString()} 条，平台显示 {note.comment_count.toLocaleString()} 条
        </p>
        <div className="mt-4">
          <CommentTree comments={data.comments} />
        </div>
      </div>
    </section>
  );
}

function parseTags(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === 'string' && item.length > 0);
  if (typeof value !== 'string' || value.trim().length === 0) return [];
  try {
    const parsed = JSON.parse(value);
    if (Array.isArray(parsed)) return parsed.filter((item): item is string => typeof item === 'string' && item.length > 0);
  } catch {
    return [];
  }
  return [];
}
