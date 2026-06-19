import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { createTask, listTasks } from '@/api/tasks';
import KeywordInput from '@/components/KeywordInput';
import type { TaskListItem } from '@/types/models';

function formatTime(value: string | null | undefined): string {
  if (!value) return '-';
  return value.replace('T', ' ').slice(0, 16);
}

function StatusPill({ status }: { status: TaskListItem['status'] }): JSX.Element {
  const palette: Record<TaskListItem['status'], string> = {
    pending: 'bg-paper-200 text-ink-700 ring-rule',
    running: 'bg-sage-50 text-sage-600 ring-sage-100',
    success: 'bg-paper-100 text-ink-900 ring-rule',
    failed: 'bg-claret-50 text-claret-600 ring-claret-100',
  };
  const labels: Record<TaskListItem['status'], string> = {
    pending: '排队中',
    running: '采集中',
    success: '完成',
    failed: '失败',
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[10.5px] font-medium ring-1 ring-inset ${palette[status]}`}
    >
      {status === 'running' && (
        <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-sage-500" />
      )}
      {labels[status]}
    </span>
  );
}

export default function Home(): JSX.Element {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [runningTaskId, setRunningTaskId] = useState<number | null>(null);
  const [recent, setRecent] = useState<TaskListItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listTasks()
      .then((res) => {
        const items = res.items ?? [];
        setRecent(items.slice(0, 10));
        const running = items.find((t) => t.status === 'running');
        setRunningTaskId(running?.id ?? null);
      })
      .catch(() => {
        /* silently ignore — the empty state covers it */
      });
  }, []);

  return (
    <div className="space-y-12">
      {/* ─────────────── Hero / submit ─────────────── */}
      <section className="relative overflow-hidden rounded-[28px] border border-rule bg-paper-50/80 px-8 pb-10 pt-12 shadow-paper sm:px-12 sm:pt-16">
        {/* Decorative geometry — controlled, not chaotic. */}
        <div
          aria-hidden
          className="pointer-events-none absolute -right-8 -top-8 h-48 w-48 rounded-full bg-claret-500/8 blur-3xl"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute right-12 top-10 select-none font-display text-[180px] font-light leading-none text-claret-500/8"
        >
          ※
        </div>

        <div className="relative max-w-3xl">
          <div className="flex items-center gap-3 text-[11px] font-mono uppercase tracking-[0.25em] text-ink-500">
            <span className="h-[2px] w-8 bg-claret-500" />
            <span>Issue · 2026 · Vol.01</span>
          </div>
          <h1
            className="mt-5 font-display text-5xl font-medium leading-[1.05] tracking-tightish text-ink-900 sm:text-[58px]"
            style={{ fontVariationSettings: '"opsz" 96, "SOFT" 50' }}
          >
            内容洞察，
            <br className="hidden sm:block" />
            从一个关键词开始。
            <span className="font-display italic text-claret-500">.</span>
          </h1>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-ink-500">
            输入一个平台话题词，本地化采集最多 20 条内容与热门评论，
            自动归档为可分析的素材池、评论洞察与 AI 选题报告。
          </p>
        </div>

        <div className="relative mt-10 animate-fade-up" style={{ animationDelay: '120ms' }}>
          <KeywordInput
            isBusy={busy || runningTaskId !== null}
            onSubmit={async ({ keyword, maxNotes }) => {
              setBusy(true);
              setError(null);
              try {
                const result = await createTask(keyword, maxNotes);
                const taskId = result.task_id;
                navigate(`/tasks/${taskId}`);
              } catch (err) {
                const detail = (err as { response?: { data?: { detail?: { message?: string } } } })
                  ?.response?.data?.detail;
                const message =
                  typeof detail === 'object' && detail !== null
                    ? (detail as { message?: string }).message
                    : null;
                setError(message ?? '创建采集任务失败，请稍后重试');
              } finally {
                setBusy(false);
              }
            }}
          />

          {runningTaskId !== null && (
            <div className="mt-4 flex items-center gap-3 rounded-xl border border-sage-100 bg-sage-50 px-4 py-3 text-sm text-sage-600">
              <span className="h-2 w-2 animate-pulse-dot rounded-full bg-sage-500" />
              <span>
                任务 <span className="font-mono">#{runningTaskId}</span> 正在采集，
                等其结束后再提交新任务。
              </span>
              <Link
                to={`/tasks/${runningTaskId}`}
                className="ml-auto text-xs font-medium text-sage-600 underline-offset-4 hover:underline"
              >
                查看进度 →
              </Link>
            </div>
          )}

          {error && (
            <div className="mt-4 rounded-xl border border-claret-100 bg-claret-50 px-4 py-3 text-sm text-claret-600">
              {error}
            </div>
          )}
        </div>
      </section>

      {/* ─────────────── Three pillars ─────────────── */}
      <section className="grid gap-6 md:grid-cols-3">
        {[
          {
            ord: '01',
            title: '素材池',
            desc: '一次采集 ≤ 20 条笔记，归档为本地 JSON，附热门评论树。',
          },
          {
            ord: '02',
            title: '评论洞察',
            desc: '高频词、情感分布、Top 评论 — 看清话题底色与受众张力。',
          },
          {
            ord: '03',
            title: 'AI 报告',
            desc: '选题方向、内容结构、互动公式 — 一份可复用的内容备忘录。',
          },
        ].map((item, idx) => (
          <article
            key={item.ord}
            className="animate-fade-up rounded-2xl border border-rule bg-white/70 p-6 shadow-lift transition hover:-translate-y-0.5 hover:shadow-paper"
            style={{ animationDelay: `${200 + idx * 80}ms` }}
          >
            <div className="font-mono text-xs uppercase tracking-[0.2em] text-claret-500">
              {item.ord}
            </div>
            <h3 className="mt-3 font-display text-2xl font-medium tracking-tightish text-ink-900">
              {item.title}
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-ink-500">{item.desc}</p>
          </article>
        ))}
      </section>

      {/* ─────────────── Recent issues ─────────────── */}
      <section>
        <div className="mb-6 flex items-end justify-between gap-4">
          <div>
            <div className="font-mono text-xs uppercase tracking-[0.25em] text-ink-500">
              Archive
            </div>
            <h2 className="mt-1 font-display text-3xl font-medium tracking-tightish text-ink-900">
              最近的采集
            </h2>
          </div>
          <Link
            to="/tasks"
            className="text-sm text-ink-500 underline-offset-4 hover:text-ink-900 hover:underline"
          >
            查看全部 →
          </Link>
        </div>

        {recent.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-rule bg-paper-50 p-10 text-center text-sm text-ink-500">
            还没有任务。输入一个关键词，开启第一份洞察。
          </div>
        ) : (
          <ul className="divide-y divide-rule overflow-hidden rounded-2xl border border-rule bg-white/70 shadow-lift">
            {recent.map((t, idx) => (
              <li key={t.id}>
                <Link
                  to={`/tasks/${t.id}`}
                  className="flex items-center gap-4 px-5 py-4 transition hover:bg-paper-50"
                >
                  <span className="font-mono text-xs tabular-nums text-ink-400">
                    {String(idx + 1).padStart(2, '0')}
                  </span>
                  <span className="flex-1 truncate font-display text-lg text-ink-900">
                    「{t.keyword || '-'}」
                  </span>
                  <span className="hidden text-xs tabular-nums text-ink-500 md:inline">
                    {t.note_count ?? 0} 条
                  </span>
                  <span className="hidden font-mono text-[11px] tabular-nums text-ink-400 sm:inline">
                    {formatTime(t.created_at)}
                  </span>
                  <StatusPill status={t.status} />
                  <span className="text-ink-400">→</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
