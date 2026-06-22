import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { getTask, listTasks } from '@/api/tasks';
import { Icon } from '@/components/icons';
import { PageTitle, Panel, StatusTag } from '@/components/ui';
import type { Task, TaskListItem, TaskStatus } from '@/types/models';

const POLL_INTERVAL_MS = 2_000;

const STATUS_LABEL: Record<TaskStatus, string> = {
  pending: '排队中',
  running: '采集中',
  success: '已完成',
  failed: '失败',
};

function statusTone(status: TaskStatus): 'amber' | 'green' | 'red' | 'slate' {
  if (status === 'success') return 'green';
  if (status === 'failed') return 'red';
  if (status === 'running') return 'amber';
  return 'slate';
}

function formatTime(value: string | null | undefined): string {
  if (!value) return '-';
  return value.replace('T', ' ').slice(0, 16);
}

function getTaskProgress(task: TaskListItem | null): number {
  if (!task) return 0;
  if (task.status === 'success') return 100;
  if (task.status === 'failed') return 100;
  if (task.note_count > 0) return Math.min(88, Math.max(18, task.note_count * 5));
  if (task.status === 'running') return 34;
  return 12;
}

function MetricPill({ label, value }: { label: string; value: number }): JSX.Element {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white/74 px-4 py-3 shadow-[0_1px_0_rgba(255,255,255,0.9)_inset]">
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold leading-none text-slate-950 tabular-nums">{value}</div>
    </div>
  );
}

export default function Workspace(): JSX.Element {
  const [tasks, setTasks] = useState<TaskListItem[]>([]);
  const [latestTask, setLatestTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const load = async (): Promise<void> => {
      setLoading(true);
      try {
        const res = await listTasks();
        if (cancelled) return;
        const items = res.items ?? [];
        setTasks(items);
        const latestSuccess = items.find((item) => item.status === 'success');
        if (latestSuccess) {
          const detail = await getTask(latestSuccess.id);
          if (!cancelled) setLatestTask(detail);
        } else if (!cancelled) {
          setLatestTask(null);
        }
        const hasActiveTask = items.some((task) => task.status === 'running' || task.status === 'pending');
        if (hasActiveTask) {
          timer = setTimeout(load, POLL_INTERVAL_MS);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();

    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, []);

  const totals = useMemo(() => {
    const running = tasks.filter((task) => task.status === 'running' || task.status === 'pending').length;
    const failed = tasks.filter((task) => task.status === 'failed').length;
    const success = tasks.filter((task) => task.status === 'success');
    const notes = success.reduce((sum, task) => sum + (task.note_count ?? 0), 0);
    return { running, failed, success: success.length, notes };
  }, [tasks]);

  const activeTask = useMemo(
    () => tasks.find((task) => task.status === 'running') ?? tasks.find((task) => task.status === 'pending') ?? null,
    [tasks],
  );
  const progress = getTaskProgress(activeTask);
  const latestKeyword = latestTask?.keyword ?? tasks.find((task) => task.status === 'success')?.keyword ?? '-';

  return (
    <div>
      <PageTitle
        title="真实采集工作台"
        description={`${totals.running} 个任务采集中 · ${totals.notes} 条笔记已入库 · 最新结果：${latestKeyword}`}
        action={
          <Link
            className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-sm font-semibold text-white shadow-button transition hover:bg-blue-700"
            to="/track-search"
          >
            <Icon name="search" className="h-4 w-4" />
            新建采集
          </Link>
        }
      />

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px] xl:grid-cols-[minmax(0,1fr)_360px]">
        <Panel className="overflow-hidden p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="text-sm font-semibold text-slate-500">当前运行</div>
              <div className="mt-2 flex flex-wrap items-center gap-3">
                <h2 className="text-[28px] font-semibold leading-tight text-slate-950">
                  {activeTask ? `「${activeTask.keyword}」` : '暂无运行任务'}
                </h2>
                {activeTask && <StatusTag tone={statusTone(activeTask.status)}>{STATUS_LABEL[activeTask.status]}</StatusTag>}
              </div>
            </div>
            <Link
              className={`inline-flex h-10 items-center justify-center rounded-xl px-4 text-sm font-semibold transition ${
                activeTask
                  ? 'bg-slate-950 text-white hover:bg-slate-800'
                  : 'border border-slate-300 bg-white text-slate-400'
              }`}
              to={activeTask ? `/tasks/${activeTask.id}` : '/track-search'}
            >
              {activeTask ? '查看任务' : '去创建任务'}
            </Link>
          </div>

          {activeTask ? (
            <div className="mt-6">
              <div className="grid gap-4 md:grid-cols-3">
                <div>
                  <div className="text-xs font-medium text-slate-500">开始时间</div>
                  <div className="mt-1 text-sm font-semibold text-slate-800">{formatTime(activeTask.started_at ?? activeTask.created_at)}</div>
                </div>
                <div>
                  <div className="text-xs font-medium text-slate-500">已采笔记</div>
                  <div className="mt-1 text-sm font-semibold text-slate-800">{activeTask.note_count ?? 0} 条</div>
                </div>
                <div>
                  <div className="text-xs font-medium text-slate-500">任务状态</div>
                  <div className="mt-1 text-sm font-semibold text-slate-800">本地采集通道正常</div>
                </div>
              </div>
              <div className="mt-6">
                <div className="mb-2 flex items-center justify-between text-xs font-medium text-slate-500">
                  <span>采集进度</span>
                  <span>{progress}%</span>
                </div>
                <div className="h-2 rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-teal-500 to-blue-600"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            </div>
          ) : (
            <div className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-5 py-6 text-sm leading-6 text-slate-500">
              当前没有正在运行的采集任务。新建关键词后，这里会优先显示实时任务状态和产出进度。
            </div>
          )}
        </Panel>

        <div className="grid grid-cols-2 gap-3">
          <MetricPill label="真实任务" value={tasks.length} />
          <MetricPill label="已入库笔记" value={totals.notes} />
          <MetricPill label="运行中" value={totals.running} />
          <MetricPill label="失败" value={totals.failed} />
        </div>
      </section>

      <section className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Panel className="p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h2 className="text-[22px] font-semibold tracking-normal text-slate-950">最近真实任务</h2>
            <Link className="text-sm font-semibold text-blue-600 hover:text-blue-700" to="/track-search">
              新建采集
            </Link>
          </div>

          {loading ? (
            <div className="mt-6 rounded-2xl bg-slate-50 p-6 text-center text-sm text-slate-500">加载真实任务...</div>
          ) : tasks.length === 0 ? (
            <div className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
              <div className="text-base font-semibold text-slate-900">还没有真实采集数据</div>
              <Link className="mt-4 inline-flex rounded-xl bg-blue-600 px-5 py-2 text-sm font-semibold text-white" to="/track-search">
                去采集关键词
              </Link>
            </div>
          ) : (
            <div className="mt-5 divide-y divide-slate-200">
              {tasks.slice(0, 5).map((task, index) => (
                <article key={task.id} className="flex flex-col gap-3 py-4 first:pt-0 md:flex-row md:items-center">
                  <div className="flex min-w-0 flex-1 items-center gap-4">
                    <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-blue-50 text-sm font-semibold text-blue-600">
                      {index + 1}
                    </div>
                    <div className="min-w-0">
                      <h3 className="truncate text-base font-semibold text-slate-950">「{task.keyword}」</h3>
                      <div className="mt-1 text-xs text-slate-500">
                        {formatTime(task.created_at)} · {task.note_count ?? 0} 条笔记
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 md:w-[210px] md:justify-end">
                    <StatusTag tone={statusTone(task.status)}>{STATUS_LABEL[task.status]}</StatusTag>
                    <Link className="text-sm font-semibold text-blue-600 hover:text-blue-700" to={`/tasks/${task.id}`}>
                      查看
                    </Link>
                    <Icon name="chevron" className="hidden h-5 w-5 text-slate-400 md:block" />
                  </div>
                </article>
              ))}
            </div>
          )}
        </Panel>

        <Panel className="flex flex-col p-5 sm:p-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-sm font-semibold text-slate-500">最新真实结果</div>
              <h2 className="mt-2 text-[24px] font-semibold tracking-normal text-slate-950">
                {latestTask ? `「${latestTask.keyword}」` : '暂无结果'}
              </h2>
            </div>
            {latestTask && <StatusTag tone="green">可分析</StatusTag>}
          </div>

          {latestTask ? (
            <div className="mt-6 flex flex-1 flex-col">
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-2xl bg-slate-50 p-4">
                  <div className="text-sm text-slate-500">笔记</div>
                  <div className="mt-1 text-2xl font-semibold text-slate-950 tabular-nums">{latestTask.note_count}</div>
                </div>
                <div className="rounded-2xl bg-slate-50 p-4">
                  <div className="text-sm text-slate-500">评论</div>
                  <div className="mt-1 text-2xl font-semibold text-slate-950 tabular-nums">
                    {latestTask.summary.total_comments}
                  </div>
                </div>
              </div>
              <div className="mt-5 rounded-2xl bg-emerald-50/70 px-4 py-3 text-sm leading-6 text-emerald-900">
                推荐下一步：先查看素材池筛选高质量笔记，再进入评论洞察提炼选题角度。
              </div>
              <div className="mt-5 grid gap-3">
                <Link className="rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-blue-600 transition hover:border-blue-300 hover:bg-blue-50" to={`/tasks/${latestTask.id}/notes`}>
                  查看素材池
                </Link>
                <Link className="rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-blue-600 transition hover:border-blue-300 hover:bg-blue-50" to={`/tasks/${latestTask.id}/insights`}>
                  评论洞察
                </Link>
                <Link className="rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-blue-600 transition hover:border-blue-300 hover:bg-blue-50" to={`/tasks/${latestTask.id}/report`}>
                  生成报告
                </Link>
              </div>
            </div>
          ) : (
            <div className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-sm leading-6 text-slate-500">
              暂无已完成任务。完成采集后，这里会显示最新关键词、笔记评论统计和下一步分析入口。
            </div>
          )}

          <div className="mt-6 border-t border-slate-200 pt-5 text-sm text-slate-500">
            <div className="flex items-center gap-3">
              <Icon name="shield" className="h-5 w-5 text-slate-400" />
              仅展示本地采集和本地分析结果
            </div>
          </div>
        </Panel>
      </section>
    </div>
  );
}
