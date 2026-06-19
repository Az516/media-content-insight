import type { Comment, CommentNode } from '@/types/models';

/**
 * CommentTree (`frontend/src/components/CommentTree.tsx`)。
 *
 * 任务 8.4:笔记详情页评论树组件,渲染一级评论 + 二级评论的两层嵌套结构。
 *
 * 需求映射:
 * - 12.5  在 `/tasks/:taskId/notes/:noteId` 页面的评论区使用本组件渲染评论树。
 * - 12.6  对 `is_top_hot = 1` 的评论附加显式「热门」徽标 + 差异化背景;
 *         `is_top_hot = 0` 的评论不出现该标识。
 * - 12.7  当 `comments` 数组为空时渲染「暂无评论」占位文案,且不渲染空白容器。
 *
 * 设计文档 §5.2 中虽然标注了可选 `highlightHot?: boolean`,但需求 12.6 要求
 * 「热门」标识本身就由数据驱动(`is_top_hot`),不需要外部开关;此处保持组件接口
 * 与本任务描述一致,只接受 `comments`。
 */

/** CommentTree 组件的 props。 */
export interface CommentTreeProps {
  /** 一级评论数组(每项的 `sub_comments` 内含二级评论)。 */
  comments: CommentNode[];
}

/**
 * 单条评论的视觉容器,一级 / 二级评论共用。
 *
 * `is_top_hot` 为真时:
 * - 容器使用 `bg-amber-50 + border-amber-200` 形成与普通评论的差异化背景;
 * - 在昵称右侧追加「热门」徽标。
 */
function CommentRow({ comment }: { comment: Comment }): JSX.Element {
  const isHot = Boolean(comment.is_top_hot);
  const containerClass = isHot
    ? 'relative rounded-xl border border-claret-100 bg-claret-50/60 p-4'
    : 'rounded-xl border border-rule bg-white/50 p-4';

  return (
    <div className={containerClass} data-testid="comment-row">
      {isHot && (
        <span
          aria-hidden
          className="absolute -left-0.5 top-3 h-6 w-[3px] rounded-r bg-claret-500"
        />
      )}
      <div className="flex items-center gap-2 text-sm">
        <span className="font-medium text-ink-900">
          {comment.nickname || '匿名'}
        </span>
        {isHot && (
          <span
            data-testid="hot-badge"
            className="inline-flex items-center rounded-full bg-claret-500 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-paper-50"
          >
            hot
          </span>
        )}
      </div>
      <p className="mt-1.5 whitespace-pre-line text-sm leading-relaxed text-ink-700">
        {comment.content || '-'}
      </p>
      <p className="mt-2 font-mono text-[11px] tabular-nums text-ink-500">
        ♥ {comment.like_count ?? 0}
        {comment.create_time ? ` · ${comment.create_time}` : ''}
      </p>
    </div>
  );
}

/**
 * 评论树主组件。
 *
 * - `comments.length === 0` 时只渲染单一占位元素,不再渲染外层 `<ul>` 容器
 *   (满足需求 12.7「不渲染空白评论容器」)。
 * - 否则渲染顶层 `<ul role="list">`,每项 `<li>` 内含评论体;
 *   当某条一级评论存在 `sub_comments` 且非空时,再嵌套一层 `<ul>` 渲染二级评论。
 */
export function CommentTree({ comments }: CommentTreeProps): JSX.Element {
  if (comments.length === 0) {
    return (
      <div
        data-testid="comment-tree-empty"
        className="rounded-2xl border border-dashed border-rule bg-paper-50 py-10 text-center text-sm text-ink-500"
      >
        暂无评论
      </div>
    );
  }

  return (
    <ul role="list" className="space-y-3" data-testid="comment-tree">
      {comments.map((comment) => {
        const hasSub =
          Array.isArray(comment.sub_comments) && comment.sub_comments.length > 0;
        return (
          <li key={comment.comment_id}>
            <CommentRow comment={comment} />
            {hasSub && (
              <ul
                role="list"
                className="ml-6 mt-2 space-y-2 border-l border-rule pl-4"
              >
                {comment.sub_comments!.map((sub) => (
                  <li key={sub.comment_id}>
                    <CommentRow comment={sub} />
                  </li>
                ))}
              </ul>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export default CommentTree;
