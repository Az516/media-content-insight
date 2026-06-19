import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';

import { createAiReport, getAiReport, getTask } from '@/api/tasks';
import MarkdownView from '@/components/MarkdownView';
import type { AIProvider, AIReport, AIReportSummary } from '@/types/models';

type ProviderOption = {
  provider: AIProvider;
  model: string;
  label: string;
};

const PROVIDER_OPTIONS: ProviderOption[] = [
  { provider: 'deepseek', model: 'deepseek-chat', label: 'DeepSeek · deepseek-chat' },
  { provider: 'openai', model: 'gpt-4o-mini', label: 'OpenAI · gpt-4o-mini' },
  { provider: 'gemini', model: 'gemini-1.5-flash', label: 'Gemini · gemini-1.5-flash' },
];

function formatTime(value: string | null | undefined): string {
  if (!value) return '-';
  return value.replace('T', ' ');
}

export default function Report(): JSX.Element {
  const { taskId } = useParams();

  const [reports, setReports] = useState<AIReportSummary[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [activeReport, setActiveReport] = useState<AIReport | null>(null);
  const [providerChoice, setProviderChoice] = useState<ProviderOption>(PROVIDER_OPTIONS[0]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshHistory = useCallback(async (): Promise<AIReportSummary[]> => {
    if (!taskId) return [];
    const task = await getTask(Number(taskId));
    setReports(task.reports ?? []);
    return task.reports ?? [];
  }, [taskId]);

  useEffect(() => {
    if (!taskId) return;
    setLoading(true);
    setError(null);
    refreshHistory()
      .then((list) => {
        if (list.length > 0) {
          setActiveId(list[0].id);
        }
      })
      .catch(() => setError('加载历史报告失败'))
      .finally(() => setLoading(false));
  }, [taskId, refreshHistory]);

  useEffect(() => {
    if (activeId == null) {
      setActiveReport(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getAiReport(activeId)
      .then((r) => {
        if (!cancelled) setActiveReport(r);
      })
      .catch(() => {
        if (!cancelled) setError('加载报告正文失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  async function handleGenerate(): Promise<void> {
    if (!taskId) return;
    setGenerating(true);
    setError(null);
    try {
      const res = await createAiReport(
        Number(taskId),
        providerChoice.provider,
        providerChoice.model,
      );
      const next = await refreshHistory();
      const matched = next.find((r) => r.id === res.report_id);
      setActiveId(matched?.id ?? next[0]?.id ?? res.report_id);
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: { message?: string } } } })
        ?.response?.data?.detail;
      const message =
        typeof detail === 'object' && detail !== null
          ? (detail as { message?: string }).message
          : null;
      setError(message ?? '生成 AI 报告失败，请稍后重试');
    } finally {
      setGenerating(false);
    }
  }

  const empty = !loading && reports.length === 0 && !error;

  const headerSub = useMemo(() => {
    if (loading && !activeReport) return '加载中…';
    if (reports.length === 0) return '尚未生成任何 AI 报告';
    return `已有 ${reports.length} 份报告`;
  }, [loading, activeReport, reports.length]);

  return (
    <section className="space-y-6">
      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight text-slate-900">AI 内容洞察报告</h2>
            <p className="mt-1 text-sm text-slate-500">{headerSub}</p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
              <span className="text-slate-500">模型</span>
              <select
                className="bg-transparent text-sm outline-none"
                value={`${providerChoice.provider}|${providerChoice.model}`}
                onChange={(e) => {
                  const [provider, model] = e.target.value.split('|');
                  const found = PROVIDER_OPTIONS.find(
                    (o) => o.provider === provider && o.model === model,
                  );
                  if (found) setProviderChoice(found);
                }}
              >
                {PROVIDER_OPTIONS.map((opt) => (
                  <option key={opt.label} value={`${opt.provider}|${opt.model}`}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>

            <button
              onClick={handleGenerate}
              disabled={generating}
              className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {generating ? '生成中…' : reports.length > 0 ? '重新生成' : '生成 AI 报告'}
            </button>
          </div>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}
      </div>

      {empty && (
        <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-12 text-center">
          <p className="text-sm text-slate-600">
            暂无报告。选好模型后点击右上角「生成 AI 报告」开始。
          </p>
        </div>
      )}

      {reports.length > 0 && (
        <div className="grid gap-6 lg:grid-cols-[16rem_minmax(0,1fr)]">
          <aside className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-3 text-xs font-medium uppercase tracking-wider text-slate-400">
              历史报告
            </div>
            <ul className="space-y-1.5">
              {reports.map((r) => {
                const isActive = r.id === activeId;
                return (
                  <li key={r.id}>
                    <button
                      onClick={() => setActiveId(r.id)}
                      className={`w-full rounded-xl px-3 py-2 text-left text-sm transition ${
                        isActive
                          ? 'bg-slate-900 text-white shadow-sm'
                          : 'text-slate-700 hover:bg-slate-100'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium">
                          {r.provider}
                          <span className={`ml-1 text-xs ${isActive ? 'text-slate-300' : 'text-slate-500'}`}>
                            · {r.model}
                          </span>
                        </span>
                        <span className={`text-[10px] ${isActive ? 'text-slate-300' : 'text-slate-400'}`}>
                          v{r.prompt_version}
                        </span>
                      </div>
                      <div className={`mt-0.5 text-[11px] ${isActive ? 'text-slate-300' : 'text-slate-500'}`}>
                        {formatTime(r.created_at)}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </aside>

          <div>
            {loading && !activeReport ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
                加载中…
              </div>
            ) : activeReport ? (
              <MarkdownView content={activeReport.report_md} />
            ) : (
              <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-10 text-center text-sm text-slate-500">
                请选择左侧任一报告查看正文。
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
