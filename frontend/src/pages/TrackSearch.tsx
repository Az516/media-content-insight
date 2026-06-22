import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { extractApiError } from '@/api/client';
import { createTask, getTask } from '@/api/tasks';
import { Icon } from '@/components/icons';
import { PageTitle, Panel, PrimaryButton, StatusTag } from '@/components/ui';
import { platformLabels, platformOptions, type PlatformKey } from '@/data/workbench';
import type { Task, TaskStatus } from '@/types/models';

const LAST_TASK_STORAGE_KEY = 'media-content-insight:last-track-task-id';
const POLL_INTERVAL_MS = 2_000;

const STATUS_LABEL: Record<TaskStatus, string> = {
  pending: '排队中',
  running: '采集中',
  success: '已完成',
  failed: '失败',
};

const STATUS_TONE: Record<TaskStatus, 'amber' | 'green' | 'red' | 'slate'> = {
  pending: 'amber',
  running: 'amber',
  success: 'green',
  failed: 'red',
};

function readStoredTaskId(): number | null {
  const raw = window.localStorage.getItem(LAST_TASK_STORAGE_KEY);
  const parsed = raw ? Number(raw) : Number.NaN;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function formatTime(value: string | null | undefined): string {
  if (!value) return '-';
  return value.replace('T', ' ').slice(0, 16);
}

function taskDescription(task: Task): string {
  if (task.status === 'success') return `采集完成，共获得 ${task.note_count} 条笔记。`;
  if (task.status === 'failed') return '采集失败，请查看任务详情中的失败原因。';
  if (task.status === 'pending') return '任务已创建，正在等待采集进程启动。';
  return '采集进行中，页面会每 2 秒自动刷新状态。';
}

function LoadingMark(): JSX.Element {
  return (
    <span className="relative grid h-9 w-9 place-items-center rounded-full bg-amber-50 text-amber-700 ring-1 ring-amber-200">
      <span className="absolute h-9 w-9 animate-ping rounded-full bg-amber-200/60" />
      <Icon name="radar" className="relative h-5 w-5 animate-spin" />
    </span>
  );
}

function CurrentTaskCard({
  task,
  loading,
  error,
  onRefresh,
}: {
  task: Task | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}): JSX.Element {
  if (loading && !task) {
    return (
      <Panel className="p-6">
        <div className="flex items-center gap-4">
          <LoadingMark />
          <div>
            <h2 className="text-lg font-semibold text-slate-950">正在恢复最近采集任务</h2>
            <p className="mt-1 text-sm text-slate-500">正在读取本地任务状态，请稍候。</p>
          </div>
        </div>
      </Panel>
    );
  }

  if (!task) {
    return (
      <Panel className="p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-950">当前采集任务</h2>
            <p className="mt-1 text-sm text-slate-500">还没有正在跟踪的任务，输入关键词即可开始。</p>
          </div>
          <StatusTag tone="slate">未开始</StatusTag>
        </div>
      </Panel>
    );
  }

  const isWorking = task.status === 'pending' || task.status === 'running';
  const actionDisabled = task.status !== 'success';

  return (
    <Panel className="overflow-hidden">
      <div className="flex flex-col gap-5 p-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <h2 className="mb-4 text-lg font-semibold text-slate-950">当前采集任务</h2>
          <div className="flex flex-wrap items-center gap-3">
            {isWorking ? <LoadingMark /> : null}
            <StatusTag tone={STATUS_TONE[task.status]}>{STATUS_LABEL[task.status]}</StatusTag>
            <span className="text-sm font-semibold text-slate-500">任务 #{task.id}</span>
            <span className="text-sm text-slate-400">{platformLabels[task.platform]}</span>
          </div>
          <h2 className="mt-4 text-[30px] font-semibold leading-tight text-slate-950 md:text-[36px]">
            「{task.keyword || '-'}」
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-500">{taskDescription(task)}</p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Link
            to={`/tasks/${task.id}/notes`}
            onClick={(event) => {
              if (actionDisabled) event.preventDefault();
            }}
            className={`rounded-xl px-4 py-2.5 text-sm font-semibold transition ${
              actionDisabled
                ? 'cursor-not-allowed bg-slate-100 text-slate-400'
                : 'bg-blue-600 text-white hover:bg-blue-700'
            }`}
          >
            查看素材池
          </Link>
          <Link
            to={`/tasks/${task.id}/insights`}
            onClick={(event) => {
              if (actionDisabled) event.preventDefault();
            }}
            className={`rounded-xl border px-4 py-2.5 text-sm font-semibold transition ${
              actionDisabled
                ? 'cursor-not-allowed border-slate-200 text-slate-400'
                : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
            }`}
          >
            评论洞察
          </Link>
          <Link
            to={`/tasks/${task.id}/report`}
            onClick={(event) => {
              if (actionDisabled) event.preventDefault();
            }}
            className={`rounded-xl border px-4 py-2.5 text-sm font-semibold transition ${
              actionDisabled
                ? 'cursor-not-allowed border-slate-200 text-slate-400'
                : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
            }`}
          >
            智能报告
          </Link>
          <Link
            to={`/tasks/${task.id}`}
            className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-blue-600 transition hover:bg-blue-50"
          >
            任务详情
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-2 border-t border-slate-200 bg-slate-50/70 md:grid-cols-4">
        <div className="border-r border-slate-200 px-5 py-4">
          <div className="text-xs font-semibold text-slate-500">状态</div>
          <div className="mt-1 text-xl font-semibold text-slate-950">{STATUS_LABEL[task.status]}</div>
        </div>
        <div className="border-r border-slate-200 px-5 py-4">
          <div className="text-xs font-semibold text-slate-500">笔记数</div>
          <div className="mt-1 text-xl font-semibold tabular-nums text-slate-950">{task.note_count ?? 0}</div>
        </div>
        <div className="border-r border-slate-200 px-5 py-4">
          <div className="text-xs font-semibold text-slate-500">采集上限</div>
          <div className="mt-1 text-xl font-semibold tabular-nums text-slate-950">{task.max_notes ?? 20}</div>
        </div>
        <div className="px-5 py-4">
          <div className="text-xs font-semibold text-slate-500">创建时间</div>
          <div className="mt-1 text-xl font-semibold tabular-nums text-slate-950">{formatTime(task.created_at)}</div>
        </div>
      </div>

      {error ? (
        <div className="flex flex-col gap-3 border-t border-rose-100 bg-rose-50 px-5 py-4 text-sm text-rose-700 sm:flex-row sm:items-center sm:justify-between">
          <span>{error}</span>
          <button
            className="rounded-lg border border-rose-200 bg-white px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-50"
            type="button"
            onClick={onRefresh}
          >
            重新读取
          </button>
        </div>
      ) : null}
    </Panel>
  );
}

export default function TrackSearch(): JSX.Element {
  const [keyword, setKeyword] = useState('智能教学');
  const [selected, setSelected] = useState<PlatformKey>('xhs');
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [trackedTaskId, setTrackedTaskId] = useState<number | null>(() => readStoredTaskId());
  const [trackedTask, setTrackedTask] = useState<Task | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);
  const [taskLoading, setTaskLoading] = useState(trackedTaskId !== null);
  const [refreshNonce, setRefreshNonce] = useState(0);

  const activeOption = platformOptions.find((item) => item.key === selected);
  const canSubmit = Boolean(activeOption?.crawlerSupported) && keyword.trim().length > 0 && !isSubmitting;

  const refreshTrackedTask = useCallback(() => {
    setRefreshNonce((value) => value + 1);
  }, []);

  useEffect(() => {
    if (trackedTaskId === null) {
      setTrackedTask(null);
      setTaskLoading(false);
      setTaskError(null);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const load = async (): Promise<void> => {
      setTaskLoading(true);
      try {
        const nextTask = await getTask(trackedTaskId);
        if (cancelled) return;
        setTrackedTask(nextTask);
        setTaskError(null);
        if (nextTask.status === 'pending' || nextTask.status === 'running') {
          timer = setTimeout(load, POLL_INTERVAL_MS);
        }
      } catch (err) {
        if (cancelled) return;
        const apiError = extractApiError(err);
        setTaskError(apiError.message || '读取任务状态失败，请稍后重试。');
        timer = setTimeout(load, POLL_INTERVAL_MS);
      } finally {
        if (!cancelled) setTaskLoading(false);
      }
    };

    void load();

    return () => {
      cancelled = true;
      if (timer !== null) clearTimeout(timer);
    };
  }, [trackedTaskId, refreshNonce]);

  const submitText = useMemo(() => {
    if (isSubmitting) return '创建中';
    if (trackedTask?.status === 'pending' || trackedTask?.status === 'running') return '继续采集';
    return '开始采集';
  }, [isSubmitting, trackedTask]);

  async function handleSubmit(): Promise<void> {
    const nextKeyword = keyword.trim();
    if (!canSubmit || nextKeyword.length === 0) return;

    setSubmitted(nextKeyword);
    setError(null);
    setIsSubmitting(true);
    try {
      const result = await createTask(nextKeyword, 20, selected);
      window.localStorage.setItem(LAST_TASK_STORAGE_KEY, String(result.task_id));
      setTrackedTaskId(result.task_id);
      setTrackedTask(null);
      setTaskLoading(true);
      setRefreshNonce((value) => value + 1);
    } catch (err) {
      const apiError = extractApiError(err);
      const detail = apiError.detail as { task_id?: number } | undefined;
      if (detail?.task_id) {
        window.localStorage.setItem(LAST_TASK_STORAGE_KEY, String(detail.task_id));
        setTrackedTaskId(detail.task_id);
        setRefreshNonce((value) => value + 1);
      }
      const suffix = detail?.task_id ? ` 当前任务：${detail.task_id}` : '';
      setError(`${apiError.message || '创建采集任务失败，请确认后端服务已启动。'}${suffix}`);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageTitle title="关键词采集" />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(280px,360px)]">
        <Panel className="p-5 sm:p-8">
          <label className="text-sm font-semibold text-slate-500" htmlFor="track-keyword">
            赛道 / 关键词
          </label>
          <div className="mt-3 flex flex-col gap-4 md:flex-row">
            <input
              id="track-keyword"
              className="h-14 min-w-0 flex-1 rounded-2xl border border-slate-200 bg-white px-5 text-[18px] font-semibold text-slate-950 outline-none transition placeholder:text-slate-300 focus:border-blue-300 focus:ring-4 focus:ring-blue-50"
              value={keyword}
              placeholder="输入赛道或关键词"
              onChange={(event) => setKeyword(event.target.value)}
            />
            <PrimaryButton icon="search" disabled={!canSubmit} onClick={handleSubmit}>
              <span className="inline-flex items-center gap-2">
                {isSubmitting ? (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/45 border-t-white" />
                ) : null}
                {submitText}
              </span>
            </PrimaryButton>
          </div>

          <div className="mt-8">
            <h2 className="text-lg font-semibold text-slate-950">平台选择</h2>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
              {platformOptions.map((platform) => {
                const active = selected === platform.key;
                const disabled = !platform.crawlerSupported;
                return (
                  <button
                    key={platform.key}
                    className={`flex min-h-28 flex-col justify-between rounded-2xl border p-4 text-left transition ${
                      active
                        ? 'border-teal-300 bg-teal-50 text-teal-950 ring-2 ring-teal-100'
                        : disabled
                          ? 'cursor-not-allowed border-slate-200 bg-slate-50 text-slate-400'
                          : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300'
                    }`}
                    type="button"
                    disabled={disabled}
                    onClick={() => setSelected(platform.key)}
                  >
                    <span className="text-base font-semibold">{platform.label}</span>
                    <span className="mt-2 text-xs leading-5">{platform.description}</span>
                    <span className="mt-3 flex items-center gap-2 text-sm">
                      <span className={`h-2 w-2 rounded-full ${active ? 'bg-emerald-500' : disabled ? 'bg-slate-300' : 'bg-blue-400'}`} />
                      {disabled ? '暂未接入' : active ? '已纳入分析' : '可采集'}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {submitted && isSubmitting ? (
            <div className="mt-8 flex items-center gap-3 rounded-2xl bg-blue-50 px-5 py-4 text-sm font-medium text-blue-700">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-blue-200 border-t-blue-700" />
              正在创建「{submitted}」真实采集任务，页面会停留在这里并自动跟踪状态。
            </div>
          ) : null}
          {error ? (
            <div className="mt-4 rounded-2xl bg-rose-50 px-5 py-4 text-sm font-medium text-rose-700">
              {error}
            </div>
          ) : null}
        </Panel>

        <Panel className="p-5 sm:p-8">
          <h2 className="text-lg font-semibold text-slate-950">采集设置</h2>
          <div className="mt-6 space-y-5 text-sm text-slate-600">
            <div className="flex items-center justify-between gap-4">
              <span>单次最多读取</span>
              <StatusTag tone="slate">20 条</StatusTag>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span>公开内容拉取</span>
              <StatusTag tone="green">已接入</StatusTag>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span>当前平台</span>
              <StatusTag tone="blue">{activeOption?.label ?? '小红书'}</StatusTag>
            </div>
            <div className="flex items-center justify-between gap-4">
              <span>本地归档</span>
              <StatusTag tone="blue">本地数据库</StatusTag>
            </div>
          </div>
          <div className="mt-10 border-t border-slate-200 pt-6">
            <h3 className="text-sm font-semibold text-slate-500">最近搜索</h3>
            <div className="mt-4 space-y-3">
              {['智能教学', '本地生活获客', '母婴早教'].map((item) => (
                <button
                  key={item}
                  className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm text-slate-600 transition hover:bg-slate-50"
                  type="button"
                  onClick={() => setKeyword(item)}
                >
                  {item}
                  <Icon name="chevron" className="h-4 w-4 text-slate-300" />
                </button>
              ))}
            </div>
          </div>
        </Panel>
      </div>

      <CurrentTaskCard
        task={trackedTask}
        loading={taskLoading}
        error={taskError}
        onRefresh={refreshTrackedTask}
      />
    </div>
  );
}
