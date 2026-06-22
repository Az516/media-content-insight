import { useCallback, useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';

import { getTask } from '@/api/tasks';
import { usePolling } from '@/hooks/usePolling';
import type { Task, TaskStatus } from '@/types/models';

const POLL_INTERVAL_MS = 2_000;

const STATUS_LABEL: Record<TaskStatus, string> = {
  pending: '排队中',
  running: '采集中',
  success: '已完成',
  failed: '失败',
};

const STATUS_TONE: Record<TaskStatus, string> = {
  pending: 'bg-paper-200 text-ink-700 ring-rule',
  running: 'bg-sage-50 text-sage-600 ring-sage-100',
  success: 'bg-paper-100 text-ink-900 ring-rule',
  failed: 'bg-claret-50 text-claret-600 ring-claret-100',
};

/**
 * Map known `error_msg` prefixes to human-friendly remediation
 * guidance (requirement 8.6).
 */
function failureHint(errorMsg: string | null | undefined): string {
  if (!errorMsg) return '请查看详情或稍后重试。';
  const lower = errorMsg.toLowerCase();
  if (lower.startsWith('login_expired')) {
    return '登录态已失效，请重新登录目标平台并更新 Cookie。';
  }
  if (lower.startsWith('risk_control')) {
    return '触发风控，请暂停采集等待冷却或人工处理。';
  }
  if (lower.startsWith('timeout')) {
    return '采集超时，请缩小关键词范围或稍后重试。';
  }
  if (lower.startsWith('no_notes_returned')) {
    return '本次未采集到任何笔记，请更换关键词后重试。';
  }
  return '出现未预期错误，请查看任务详情或联系管理员。';
}

function StatusBadge({ status }: { status: TaskStatus }): JSX.Element {
  const tone = STATUS_TONE[status] ?? 'bg-paper-100 text-ink-700 ring-rule';
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 font-mono text-[11px] font-medium uppercase tracking-wider ring-1 ring-inset ${tone}`}
    >
      {status === 'running' && (
        <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-sage-500" />
      )}
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

function Stat({ label, value }: { label: string; value: string | number }): JSX.Element {
  return (
    <div className="rounded-2xl border border-rule bg-white/70 px-4 py-3 shadow-lift">
      <div className="font-mono text-[10.5px] font-medium uppercase tracking-[0.2em] text-ink-500">
        {label}
      </div>
      <div className="mt-1 font-display text-2xl font-medium tabular-nums text-ink-900">{value}</div>
    </div>
  );
}

export default function TaskDetail(): JSX.Element {
  const { taskId } = useParams();
  const id = Number(taskId);

  const fetcher = useCallback(() => getTask(id), [id]);
  const isTerminal = useCallback(
    (t: Task) => t.status === 'success' || t.status === 'failed',
    [],
  );

  const { data: task, loading, error, refetch } = usePolling<Task>(
    fetcher,
    POLL_INTERVAL_MS,
    isTerminal,
  );

  const summary = task?.summary;

  const headerSub = useMemo(() => {
    if (!task) return loading ? '加载中…' : '任务未找到';
    if (task.status === 'success') return `共采集 ${task.note_count} 条笔记`;
    if (task.status === 'running') return '采集进行中，页面每 2 秒自动刷新';
    if (task.status === 'failed') return failureHint(task.error_msg);
    return '排队中，请稍候';
  }, [task, loading]);

  if (!task && loading) {
    return (
      <div className="rounded-3xl border border-rule bg-white/70 p-10 text-center text-sm text-ink-500 shadow-lift">
        加载任务详情…
      </div>
    );
  }

  if (!task) {
    return (
      <div className="rounded-3xl border border-claret-100 bg-claret-50 p-8 text-sm text-claret-600 shadow-lift">
        任务不存在或已被删除。
      </div>
    );
  }

  const actionDisabled = task.status !== 'success';

  return (
    <section className="space-y-8">
      <div className="overflow-hidden rounded-3xl border border-rule bg-white/80 shadow-paper">
        <div className="flex flex-wrap items-start justify-between gap-6 p-8">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-3">
              <StatusBadge status={task.status} />
              <span className="text-sm font-semibold text-ink-400">
                任务 #{task.id}
              </span>
            </div>
            <h2 className="mt-4 truncate font-display text-4xl font-medium tracking-tightish text-ink-900">
              「{task.keyword || '-'}」
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-500">
              {headerSub}
            </p>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            <Link
              to={`/tasks/${task.id}/notes`}
              className={`rounded-xl px-5 py-2.5 text-sm font-medium transition ${
                actionDisabled
                  ? 'cursor-not-allowed bg-paper-100 text-ink-400'
                  : 'bg-ink-900 text-paper-50 hover:bg-claret-500'
              }`}
              onClick={(e) => {
                if (actionDisabled) e.preventDefault();
              }}
            >
              查看素材池 →
            </Link>
            <Link
              to={`/tasks/${task.id}/insights`}
              className={`rounded-xl border px-5 py-2.5 text-sm font-medium transition ${
                actionDisabled
                  ? 'cursor-not-allowed border-rule text-ink-400'
                  : 'border-rule text-ink-700 hover:bg-paper-50'
              }`}
              onClick={(e) => {
                if (actionDisabled) e.preventDefault();
              }}
            >
              评论洞察
            </Link>
            <Link
              to={`/tasks/${task.id}/report`}
              className={`rounded-xl border px-5 py-2.5 text-sm font-medium transition ${
                actionDisabled
                  ? 'cursor-not-allowed border-rule text-ink-400'
                  : 'border-claret-200 bg-claret-50 text-claret-600 hover:bg-claret-100'
              }`}
              onClick={(e) => {
                if (actionDisabled) e.preventDefault();
              }}
            >
              智能报告
            </Link>
          </div>
        </div>

        {error && (
          <div className="flex items-center justify-between gap-4 border-t border-claret-100 bg-claret-50/70 px-8 py-3 text-sm text-claret-600">
            <span>轮询出错：{error.message}。已暂停自动刷新。</span>
            <button
              onClick={refetch}
              className="rounded-lg border border-claret-200 bg-white px-3 py-1 text-xs font-medium text-claret-600 hover:bg-claret-50"
            >
              重试
            </button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="状态" value={STATUS_LABEL[task.status] ?? task.status} />
        <Stat label="笔记数" value={task.note_count ?? 0} />
        <Stat label="采集上限" value={task.max_notes ?? 20} />
        <Stat label="创建时间" value={task.created_at?.replace('T', ' ').slice(0, 16) ?? '-'} />
      </div>

      {summary && task.status === 'success' && (
        <div className="rounded-3xl border border-rule bg-white/80 p-8 shadow-paper">
          <div className="flex items-center justify-between border-b border-rule pb-3">
            <h3 className="font-display text-2xl text-ink-900">汇总</h3>
            <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-500">
              数据汇总
            </span>
          </div>
          <div className="mt-6 grid grid-cols-1 gap-8 md:grid-cols-3">
            <div>
              <div className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-500">
                总点赞数
              </div>
              <div className="mt-1 font-display text-4xl font-medium tabular-nums text-ink-900">
                {summary.total_likes.toLocaleString()}
              </div>
            </div>
            <div>
              <div className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-500">
                总评论数
              </div>
              <div className="mt-1 font-display text-4xl font-medium tabular-nums text-ink-900">
                {summary.total_comments.toLocaleString()}
              </div>
            </div>
            <div>
              <div className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-500">
                高产作者
              </div>
              <ul className="mt-2 space-y-1.5 text-sm">
                {summary.top_authors.length === 0 && (
                  <li className="text-ink-400">暂无</li>
                )}
                {summary.top_authors.map((a) => (
                  <li key={a.user_id} className="flex items-center justify-between">
                    <span className="truncate text-ink-700">{a.nickname || a.user_id}</span>
                    <span className="font-mono text-xs tabular-nums text-ink-500">
                      {a.note_count} 篇
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {task.status === 'failed' && task.error_msg && (
        <div className="rounded-3xl border border-claret-100 bg-claret-50 p-6 shadow-lift">
          <div className="font-display text-lg text-claret-600">失败原因</div>
          <code className="mt-3 block whitespace-pre-wrap break-all rounded-xl bg-white px-4 py-3 font-mono text-xs leading-relaxed text-claret-700">
            {task.error_msg}
          </code>
        </div>
      )}
    </section>
  );
}
