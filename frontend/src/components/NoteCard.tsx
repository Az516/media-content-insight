/**
 * NoteCard (`frontend/src/components/NoteCard.tsx`)。
 *
 * 笔记卡片(封面 + 标题 + 互动数),用于素材池 `/tasks/:taskId/notes` 的网格列表(任务 9.4)。
 *
 * 需求映射:
 * - 17.5 / 11.7:展示 `cover_url`、`title`、`liked_count`、`collected_count`、`comment_count`,
 *   并在用户点击时通过 `onClick(note_id)` 上抛,供父组件路由跳转到 `/tasks/:taskId/notes/:noteId`。
 * - 17.6:任一字段缺失或为 null 时显示占位符(空封面用占位图、空数值显示「-」),
 *   且不抛出渲染异常。这里同时对运行时的 `null` / `undefined` / `NaN` 做兜底,
 *   覆盖后端 schema 之外的脏数据(例如重试期间的不完整记录)。
 *
 * 设计要点:
 * - 整卡可点击 + 键盘可达:使用原生 `<button type="button">`,天然支持 `Tab` 聚焦
 *   与 `Enter` / `Space` 键触发,无需自行处理 `role` / `tabIndex` / `onKeyDown`。
 * - 封面 `<img>` 加载失败时(URL 有效但资源 404 / 防盗链)通过 `onError` 兜底到占位图,
 *   并清空 `onerror` 防止占位图本身异常时陷入死循环。
 * - 数值字段使用类型守卫 `Number.isFinite`,既覆盖 `null` / `undefined`,
 *   也避免 `NaN` 直接被字符串化输出。
 */

import { useState } from 'react';

import { proxiedMediaUrl } from '@/api/client';
import type { NoteSummary } from '@/types/models';

/** 数值 / 标题字段缺失时的统一占位符。 */
const FALLBACK_TEXT = '-';

/**
 * 内联 SVG 占位封面(灰底 + 中文「无封面」)。
 *
 * 使用 data URI 而非外链资源,确保离线 / 网络异常情况下占位图始终可用,
 * 同时与需求 17.6「不抛渲染异常」相一致。
 */
const PLACEHOLDER_COVER_DATA_URI = `data:image/svg+xml;utf8,${encodeURIComponent(
  "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 120 120'><rect width='120' height='120' fill='#e2e8f0'/><text x='60' y='66' fill='#94a3b8' font-size='14' text-anchor='middle' font-family='PingFang SC, Microsoft YaHei, sans-serif'>无封面</text></svg>",
)}`;

export interface NoteCardProps {
  /** 笔记摘要(对齐 `GET /api/tasks/{id}/notes` 列表项)。 */
  note: NoteSummary;
  /** 卡片点击回调,参数为 `note_id`,供父组件路由跳转(任务 9.4)。 */
  onClick?: (noteId: string) => void;
}

/** 数值字段格式化:有限数字直接输出,其余(null / undefined / NaN)统一显示 `-`。 */
function formatCount(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? String(value)
    : FALLBACK_TEXT;
}

export function NoteCard({ note, onClick }: NoteCardProps): JSX.Element {
  const [imageFailed, setImageFailed] = useState(false);

  const handleClick = (): void => {
    onClick?.(note.note_id);
  };

  // `cover_url` 既要兜空字符串、也要兜 null / undefined,统一用 `||`。
  const coverSrc = proxiedMediaUrl(note.cover_url) || PLACEHOLDER_COVER_DATA_URI;
  // `title` 同理:空字符串、空白字符串、null 都视为缺失。
  const trimmedTitle = note.title?.trim();
  const displayTitle = trimmedTitle ? trimmedTitle : FALLBACK_TEXT;

  return (
    <button
      type="button"
      data-testid="note-card"
      onClick={handleClick}
      className="group flex w-full flex-col overflow-hidden rounded-2xl border border-rule bg-white/80 text-left shadow-lift transition hover:-translate-y-0.5 hover:shadow-paper focus:outline-none focus-visible:ring-2 focus-visible:ring-claret-400 focus-visible:ring-offset-2"
    >
      <div className="relative overflow-hidden bg-paper-100">
        <img
          src={coverSrc}
          alt={trimmedTitle ? trimmedTitle : '笔记封面'}
          loading="lazy"
          className="aspect-[4/5] w-full object-cover transition duration-500 group-hover:scale-[1.03]"
          onError={(event) => {
            const img = event.currentTarget;
            img.onerror = null;
            setImageFailed(true);
            img.src = PLACEHOLDER_COVER_DATA_URI;
          }}
        />
        {imageFailed && note.cover_url && (
          <span className="absolute bottom-2 left-2 rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-medium text-ink-500 shadow-sm">
            图片不可访问
          </span>
        )}
        {note.type === 'video' && (
          <span className="absolute left-2.5 top-2.5 inline-flex items-center gap-1 rounded-full bg-ink-900/85 px-2 py-0.5 text-[10px] font-medium text-paper-50 backdrop-blur">
            ▶ 视频
          </span>
        )}
      </div>
      <div className="space-y-2.5 p-4">
        <h3
          title={displayTitle}
          className="line-clamp-2 font-display text-[15px] font-medium leading-snug tracking-tightish text-ink-900"
        >
          {displayTitle}
        </h3>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] tabular-nums text-ink-500">
          <span aria-label="点赞数" className="inline-flex items-center gap-1">
            <span className="text-claret-500">♥</span>
            {formatCount(note.liked_count)}
          </span>
          <span aria-label="收藏数" className="inline-flex items-center gap-1">
            <span className="text-ink-700">✦</span>
            {formatCount(note.collected_count)}
          </span>
          <span aria-label="评论数" className="inline-flex items-center gap-1">
            <span className="text-ink-700">¶</span>
            {formatCount(note.comment_count)}
          </span>
        </div>
        {note.author?.nickname && (
          <div className="truncate border-t border-rule pt-2 text-[11px] text-ink-400">
            作者 {note.author.nickname}
          </div>
        )}
      </div>
    </button>
  );
}

export default NoteCard;
