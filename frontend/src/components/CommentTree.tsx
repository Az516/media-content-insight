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
 * 渲染单条评论的元数据行 `like_count赞 · create_time`,
 * 仅展示非 null / 非 undefined 的字段。
 */
function formatMeta(comment: Comment): string {
  const parts: string[] = [];
  parts.push(`${comment.like_count ?? 0}赞`);
  if (comment.create_time) {
    parts.push(comment.create_time);
  }
  return parts.join(' · ');
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
    ? 'rounded-md border border-amber-200 bg-amber-50 p-3'
    : 'rounded-md p-3';

  return (
    <div className={containerClass} data-testid="comment-row">
      <div className="flex items-center text-sm font-medium text-slate-800">
        <span>{comment.nickname || '匿名'}</span>
        {isHot && (
          <span
            data-testid="hot-badge"
            className="ml-2 inline-block px-2 py-0.5 text-xs rounded-full bg-amber-200 text-amber-900"
          >
            热门
          </span>
        )}
      </div>
      <p className="mt-1 whitespace-pre-line text-sm text-slate-700">
        {comment.content || '-'}
      </p>
      <p className="mt-1 text-xs text-slate-500">[ {formatMeta(comment)} ]</p>
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
        className="text-slate-500 text-sm py-6 text-center"
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
              <ul role="list" className="ml-6 mt-2 space-y-2">
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
