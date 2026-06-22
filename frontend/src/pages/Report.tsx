import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';

import { extractApiError } from '@/api/client';
import {
  createAiReport,
  generateContentDraft,
  generateContentOutline,
  generateCreativeDirections,
  generateTopicRecommendations,
  getAiReport,
  getTask,
} from '@/api/tasks';
import MarkdownView from '@/components/MarkdownView';
import type {
  AIProvider,
  AIReport,
  AIReportSummary,
  ContentDraft,
  ContentOutline,
  CreativeDirection,
  TopicRecommendation,
} from '@/types/models';

type ProviderOption = {
  provider: AIProvider;
  model: string;
  label: string;
};

type WorkflowView = 'topics' | 'directions' | 'outline' | 'draft' | 'report';
type LoadingStage = 'topics' | 'directions' | 'outline' | 'draft' | null;

const PROVIDER_OPTIONS: ProviderOption[] = [
  { provider: 'deepseek', model: 'deepseek-chat', label: 'DeepSeek Chat' },
  { provider: 'deepseek', model: 'gpt-5.5', label: 'GPT 5.5' },
  { provider: 'deepseek', model: 'gemini-3', label: 'Gemini 3' },
  { provider: 'deepseek', model: 'claude-opus-4.8', label: 'Claude Opus 4.8' },
];

function formatTime(value: string | null | undefined): string {
  if (!value) return '-';
  return value.replace('T', ' ');
}

function modelLabel(model: string): string {
  return PROVIDER_OPTIONS.find((option) => option.model === model)?.label ?? model;
}

function safeArray<T>(value: T[] | undefined | null): T[] {
  return Array.isArray(value) ? value : [];
}

function friendlyAiError(message: string | undefined, fallback: string): string {
  if (!message) return fallback;
  if (message.toLowerCase().includes('timeout')) {
    return 'AI 生成耗时超过预期，请稍后再试；如果数据量较大，建议先减少采集条数。';
  }
  return message;
}

export default function Report(): JSX.Element {
  const { taskId } = useParams();
  const numericTaskId = Number(taskId);

  const [reports, setReports] = useState<AIReportSummary[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [activeReport, setActiveReport] = useState<AIReport | null>(null);
  const [providerChoice, setProviderChoice] = useState<ProviderOption>(PROVIDER_OPTIONS[1]);
  const [view, setView] = useState<WorkflowView>('topics');
  const [topics, setTopics] = useState<TopicRecommendation[]>([]);
  const [directions, setDirections] = useState<CreativeDirection[]>([]);
  const [outline, setOutline] = useState<ContentOutline | null>(null);
  const [draft, setDraft] = useState<ContentDraft | null>(null);
  const [selectedTopic, setSelectedTopic] = useState<TopicRecommendation | null>(null);
  const [selectedDirection, setSelectedDirection] = useState<CreativeDirection | null>(null);
  const [selectedTitleIndex, setSelectedTitleIndex] = useState(0);
  const [loadingStage, setLoadingStage] = useState<LoadingStage>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshHistory = useCallback(async (): Promise<AIReportSummary[]> => {
    if (!Number.isFinite(numericTaskId)) return [];
    const task = await getTask(numericTaskId);
    setReports(task.reports ?? []);
    return task.reports ?? [];
  }, [numericTaskId]);

  useEffect(() => {
    setError(null);
    refreshHistory()
      .then((list) => {
        if (list.length > 0) setActiveId(list[0].id);
      })
      .catch(() => setError('加载分析底稿失败'));
  }, [refreshHistory]);

  useEffect(() => {
    if (activeId == null) {
      setActiveReport(null);
      return;
    }
    let cancelled = false;
    setReportLoading(true);
    getAiReport(activeId)
      .then((report) => {
        if (!cancelled) setActiveReport(report);
      })
      .catch(() => {
        if (!cancelled) setError('加载完整分析报告失败');
      })
      .finally(() => {
        if (!cancelled) setReportLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  function generateReportInBackground(): void {
    if (!Number.isFinite(numericTaskId) || reports.length > 0) return;

    void createAiReport(numericTaskId, providerChoice.provider, providerChoice.model)
      .then(async (reportResult) => {
        const nextReports = await refreshHistory();
        if (activeId == null) {
          const matched = nextReports.find((report) => report.id === reportResult.report_id);
          setActiveId(matched?.id ?? nextReports[0]?.id ?? reportResult.report_id);
        }
      })
      .catch(() => {
        // 完整报告是辅助入口，不阻塞选题主流程。
      });
  }

  async function handleGenerateTopics(): Promise<void> {
    if (!Number.isFinite(numericTaskId)) return;
    setLoadingStage('topics');
    setError(null);
    try {
      const result = await generateTopicRecommendations(numericTaskId, providerChoice.model);
      setTopics(safeArray(result.items));
      setSelectedTopic(null);
      setDirections([]);
      setSelectedDirection(null);
      setOutline(null);
      setDraft(null);
      setSelectedTitleIndex(0);
      setView('topics');
      generateReportInBackground();
    } catch (err) {
      const apiError = extractApiError(err);
      setError(friendlyAiError(apiError.message, '生成选题推荐失败，请稍后重试'));
    } finally {
      setLoadingStage(null);
    }
  }

  async function handleSelectTopic(topic: TopicRecommendation): Promise<void> {
    if (!Number.isFinite(numericTaskId)) return;
    setSelectedTopic(topic);
    setSelectedDirection(null);
    setDirections([]);
    setOutline(null);
    setDraft(null);
    setSelectedTitleIndex(0);
    setView('directions');
    setLoadingStage('directions');
    setError(null);
    try {
      const result = await generateCreativeDirections(numericTaskId, topic, providerChoice.model);
      setDirections(safeArray(result.items));
    } catch (err) {
      const apiError = extractApiError(err);
      setError(friendlyAiError(apiError.message, '生成创作角度失败，请稍后重试'));
    } finally {
      setLoadingStage(null);
    }
  }

  async function handleSelectDirection(direction: CreativeDirection): Promise<void> {
    if (!Number.isFinite(numericTaskId) || !selectedTopic) return;
    setSelectedDirection(direction);
    setOutline(null);
    setDraft(null);
    setSelectedTitleIndex(0);
    setView('outline');
    setLoadingStage('outline');
    setError(null);
    try {
      const result = await generateContentOutline(
        numericTaskId,
        selectedTopic,
        direction,
        providerChoice.model,
      );
      setOutline({
        titles: safeArray(result.titles),
        outline: safeArray(result.outline),
        cover_copy: safeArray(result.cover_copy),
        comment_guide: safeArray(result.comment_guide),
        tags: safeArray(result.tags),
        evidence: result.evidence ?? '',
      });
    } catch (err) {
      const apiError = extractApiError(err);
      setError(friendlyAiError(apiError.message, '生成内容大纲失败，请稍后重试'));
    } finally {
      setLoadingStage(null);
    }
  }

  async function handleGenerateDraft(): Promise<void> {
    if (!Number.isFinite(numericTaskId) || !selectedTopic || !selectedDirection || !outline) return;
    setDraft(null);
    setView('draft');
    setLoadingStage('draft');
    setError(null);
    try {
      const selectedTitle = outline.titles[selectedTitleIndex]?.text ?? null;
      const result = await generateContentDraft(
        numericTaskId,
        selectedTopic,
        selectedDirection,
        outline,
        selectedTitle,
        providerChoice.model,
      );
      setDraft({
        title: result.title ?? selectedTitle ?? '',
        cover: result.cover ?? '',
        body: result.body ?? '',
        tags: safeArray(result.tags),
        checks: safeArray(result.checks),
      });
    } catch (err) {
      const apiError = extractApiError(err);
      setError(friendlyAiError(apiError.message, '生成文案草稿失败，请稍后重试'));
    } finally {
      setLoadingStage(null);
    }
  }

  const headerSub = useMemo(() => {
    if (topics.length === 0) return '点击生成后，AI 会基于真实采集数据逐层生成选题、角度、大纲和草稿';
    return `已生成 ${topics.length} 个选题推荐`;
  }, [topics.length]);

  return (
    <section className="space-y-5 pb-6">
      <div className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight text-slate-900">AI 选题推荐</h2>
            <p className="mt-1 text-sm text-slate-500">{headerSub}</p>
          </div>

          <div className="flex w-full flex-wrap items-center gap-3 md:w-auto">
            <label className="flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 md:flex-none">
              <span className="text-slate-500">模型</span>
              <select
                className="min-w-0 bg-transparent text-sm outline-none"
                value={providerChoice.model}
                onChange={(event) => {
                  const found = PROVIDER_OPTIONS.find((option) => option.model === event.target.value);
                  if (found) setProviderChoice(found);
                }}
              >
                {PROVIDER_OPTIONS.map((option) => (
                  <option key={option.model} value={option.model}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <button
              type="button"
              onClick={() => setView('report')}
              disabled={!activeReport}
              className="h-10 flex-1 rounded-xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-45 md:flex-none"
            >
              查看完整分析报告
            </button>

            <button
              onClick={handleGenerateTopics}
              disabled={loadingStage === 'topics'}
              className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60 md:flex-none"
            >
              {loadingStage === 'topics' && (
                <span className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
              )}
              {loadingStage === 'topics' ? '生成中...' : topics.length > 0 ? '重新生成选题' : '生成选题推荐'}
            </button>
          </div>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}
      </div>

      <div className="rounded-3xl border border-slate-200 bg-white p-3 shadow-sm sm:p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <label className="flex min-w-0 flex-1 items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 md:max-w-xl">
            <span className="shrink-0 text-slate-400">分析底稿</span>
            <select
              className="min-w-0 flex-1 truncate bg-transparent text-sm font-medium text-slate-700 outline-none"
              value={activeId ?? ''}
              onChange={(event) => setActiveId(Number(event.target.value))}
              disabled={reports.length === 0}
            >
              {reports.length === 0 ? (
                <option value="">暂无分析底稿</option>
              ) : (
                reports.map((report) => (
                  <option key={report.id} value={report.id}>
                    {modelLabel(report.model)} · {formatTime(report.created_at)}
                  </option>
                ))
              )}
            </select>
          </label>

          <div className="flex flex-wrap gap-2">
            {[
              ['topics', '选题推荐'],
              ['directions', '创作角度'],
              ['outline', '内容大纲'],
              ['draft', '文案草稿'],
            ].map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setView(key as WorkflowView)}
                className={`h-10 rounded-xl px-4 text-sm font-medium transition ${
                  view === key
                    ? 'bg-slate-900 text-white'
                    : 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {view === 'topics' && (
        <div className="space-y-5">
          {loadingStage === 'topics' ? (
            <LoadingCard
              text="AI 正在读取采集结果，提炼高热话题和可创作选题..."
              steps={['整理笔记与评论热度', '判断用户需求和情绪', '生成 5 个选题推荐']}
            />
          ) : topics.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-12 text-center">
              <p className="text-sm text-slate-600">
                这里会展示 AI 基于真实采集数据生成的选题推荐。点击右上角开始生成。
              </p>
            </div>
          ) : (
            <div className="grid gap-4 xl:grid-cols-2">
              {topics.map((topic) => (
                <article key={topic.id} className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-xs font-semibold text-blue-600">推荐分 {topic.score}</div>
                      <h3 className="mt-2 text-xl font-semibold tracking-tight text-slate-900">{topic.title}</h3>
                      <p className="mt-2 text-sm leading-6 text-slate-600">{topic.summary}</p>
                    </div>
                    <div className="rounded-2xl bg-slate-900 px-3 py-2 text-center text-white">
                      <div className="text-2xl font-semibold">{topic.score}</div>
                      <div className="text-[10px] text-slate-300">score</div>
                    </div>
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                    {safeArray(topic.metrics).map((metric) => (
                      <div key={`${topic.id}-${metric.label}`} className="rounded-xl bg-slate-50 px-3 py-2">
                        <div className="text-[11px] text-slate-400">{metric.label}</div>
                        <div className="mt-0.5 text-sm font-semibold text-slate-800">{metric.value}</div>
                      </div>
                    ))}
                  </div>

                  <div className="mt-4 space-y-2 text-sm leading-6 text-slate-600">
                    <p><span className="font-semibold text-slate-900">数据依据：</span>{topic.evidence}</p>
                    <p><span className="font-semibold text-slate-900">适合人群：</span>{topic.audience}</p>
                    <p><span className="font-semibold text-slate-900">风险提醒：</span>{topic.risk}</p>
                  </div>

                  <button
                    type="button"
                    onClick={() => void handleSelectTopic(topic)}
                    className="mt-5 h-11 w-full rounded-2xl bg-slate-900 text-sm font-semibold text-white transition hover:bg-slate-800"
                  >
                    生成创作角度
                  </button>
                </article>
              ))}
            </div>
          )}
        </div>
      )}

      {view === 'directions' && (
        <div className="space-y-5">
          <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <button type="button" onClick={() => setView('topics')} className="text-sm font-medium text-blue-600">
              返回选题推荐
            </button>
            <h3 className="mt-4 text-2xl font-semibold tracking-tight text-slate-900">
              {selectedTopic?.title ?? '请先选择一个选题'}
            </h3>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{selectedTopic?.summary}</p>
          </div>

          {loadingStage === 'directions' ? (
            <LoadingCard
              text="AI 正在围绕当前选题拆解不同创作角度..."
              steps={['识别选题核心矛盾', '匹配目标人群', '生成差异化表达角度']}
            />
          ) : directions.length === 0 ? (
            <EmptyStep text="请先在选题推荐里选择一个选题，AI 会继续生成不同创作角度。" />
          ) : (
            <div className="grid gap-4 xl:grid-cols-2">
              {directions.map((direction) => (
                <article key={direction.id} className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="text-xs font-semibold text-slate-400">{direction.type}</div>
                  <h4 className="mt-2 text-xl font-semibold text-slate-900">{direction.title}</h4>
                  <p className="mt-3 rounded-2xl bg-slate-50 px-4 py-3 text-sm font-medium leading-6 text-slate-700">
                    {direction.hook}
                  </p>
                  <div className="mt-4 space-y-2 text-sm leading-6 text-slate-600">
                    <p><span className="font-semibold text-slate-900">内容承诺：</span>{direction.promise}</p>
                    <p><span className="font-semibold text-slate-900">适合人群：</span>{direction.audience}</p>
                    <p><span className="font-semibold text-slate-900">数据证据：</span>{direction.evidence}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleSelectDirection(direction)}
                    className="mt-5 h-11 w-full rounded-2xl bg-slate-900 text-sm font-semibold text-white transition hover:bg-slate-800"
                  >
                    生成内容大纲
                  </button>
                </article>
              ))}
            </div>
          )}
        </div>
      )}

      {view === 'outline' && (
        <div className="space-y-5">
          <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <button type="button" onClick={() => setView('directions')} className="text-sm font-medium text-blue-600">
              换一个创作角度
            </button>
            <h3 className="mt-4 text-2xl font-semibold tracking-tight text-slate-900">
              {selectedDirection?.title ?? '请先选择一个创作角度'}
            </h3>
            <p className="mt-2 text-sm text-slate-500">{selectedTopic?.title} · {selectedDirection?.type}</p>
          </div>

          {loadingStage === 'outline' ? (
            <LoadingCard
              text="AI 正在把创作角度展开成标题、结构和发布素材..."
              steps={['生成标题候选', '组织正文结构', '补充封面文案和互动引导']}
            />
          ) : !outline ? (
            <EmptyStep text="选择创作角度后，这里会出现标题候选、内容结构、封面文案和评论引导。" />
          ) : (
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(22rem,0.8fr)]">
              <div className="space-y-5">
                <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex items-center justify-between gap-3">
                    <h4 className="text-lg font-semibold text-slate-900">标题候选</h4>
                    <button
                      type="button"
                      onClick={() => void handleGenerateDraft()}
                      className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
                    >
                      生成完整文案
                    </button>
                  </div>
                  <div className="mt-4 grid gap-3">
                    {safeArray(outline.titles).map((title, index) => (
                      <button
                        key={`${title.text}-${index}`}
                        type="button"
                        onClick={() => setSelectedTitleIndex(index)}
                        className={`rounded-2xl border px-4 py-3 text-left transition ${
                          selectedTitleIndex === index
                            ? 'border-slate-900 bg-slate-900 text-white'
                            : 'border-slate-200 bg-white text-slate-800 hover:bg-slate-50'
                        }`}
                      >
                        <div className="text-sm font-semibold">{title.text}</div>
                        <div className={`mt-1 text-xs ${selectedTitleIndex === index ? 'text-slate-300' : 'text-slate-500'}`}>
                          {title.reason}
                        </div>
                      </button>
                    ))}
                  </div>
                </section>

                <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                  <h4 className="text-lg font-semibold text-slate-900">内容大纲</h4>
                  <div className="mt-5 space-y-4">
                    {safeArray(outline.outline).map((block, index) => (
                      <div key={`${block.title}-${index}`} className="grid gap-3 border-t border-slate-100 pt-4 first:border-t-0 first:pt-0 md:grid-cols-[5rem_minmax(0,1fr)]">
                        <div className="text-sm font-semibold text-blue-600">0{index + 1}</div>
                        <div>
                          <div className="font-semibold text-slate-900">{block.title}</div>
                          <ul className="mt-2 space-y-1 text-sm leading-6 text-slate-600">
                            {safeArray(block.points).map((point) => <li key={point}>· {point}</li>)}
                          </ul>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              </div>

              <aside className="space-y-5">
                <InfoPanel title="封面文案" items={outline.cover_copy} />
                <InfoPanel title="评论区引导" items={outline.comment_guide} />
                <InfoPanel title="标签建议" items={outline.tags.map((tag) => `#${tag}`)} />
                <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                  <h4 className="text-lg font-semibold text-slate-900">数据依据</h4>
                  <p className="mt-3 text-sm leading-6 text-slate-600">{outline.evidence}</p>
                </section>
              </aside>
            </div>
          )}
        </div>
      )}

      {view === 'draft' && (
        <div>
          {loadingStage === 'draft' ? (
            <LoadingCard
              text="AI 正在根据已选标题和大纲生成完整文案..."
              steps={['扩写正文', '调整小红书语气', '生成发布前检查项']}
            />
          ) : !draft ? (
            <EmptyStep text="请先在内容大纲中点击“生成完整文案”。" />
          ) : (
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(22rem,0.8fr)]">
              <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <button type="button" onClick={() => setView('outline')} className="text-sm font-medium text-blue-600">
                  返回大纲
                </button>
                <div className="mt-5 flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="text-sm font-semibold text-slate-400">小红书文案草稿</div>
                    <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">{draft.title}</h3>
                  </div>
                  <button
                    type="button"
                    onClick={() => void navigator.clipboard?.writeText(`${draft.title}\n\n${draft.body}`)}
                    className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
                  >
                    复制文案
                  </button>
                </div>
                <div className="mt-6 space-y-5">
                  <TextBlock label="封面文案" content={draft.cover} large />
                  <TextBlock label="正文" content={draft.body} />
                  <InfoPanel title="标签" items={safeArray(draft.tags).map((tag) => `#${tag}`)} />
                </div>
              </section>
              <aside className="space-y-5">
                <InfoPanel title="发布前检查" items={safeArray(draft.checks)} />
                {outline && <InfoPanel title="标题备选" items={outline.titles.map((item) => item.text)} />}
              </aside>
            </div>
          )}
        </div>
      )}

      {view === 'report' && (
        <div className="space-y-4">
          <button type="button" onClick={() => setView('topics')} className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700">
            返回选题推荐
          </button>
          {reportLoading && !activeReport ? (
            <LoadingCard text="加载完整分析报告..." />
          ) : activeReport ? (
            <MarkdownView content={activeReport.report_md} />
          ) : (
            <EmptyStep text="暂无完整分析报告，请先生成选题推荐。" />
          )}
        </div>
      )}
    </section>
  );
}

function LoadingCard({ text, steps = [] }: { text: string; steps?: string[] }): JSX.Element {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-slate-900">
          <span className="h-6 w-6 rounded-full border-2 border-white/25 border-t-white animate-spin" />
        </div>
        <div>
          <div className="text-base font-semibold text-slate-900">{text}</div>
          <div className="mt-1 text-sm text-slate-500">通常需要几十秒，结果生成后会自动展示。</div>
        </div>
      </div>
      {steps.length > 0 && (
        <div className="mt-6 grid gap-3 md:grid-cols-3">
          {steps.map((step, index) => (
            <div key={step} className="rounded-2xl bg-slate-50 px-4 py-3">
              <div className="text-xs font-semibold text-blue-600">0{index + 1}</div>
              <div className="mt-1 text-sm font-medium text-slate-700">{step}</div>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-200">
                <div
                  className="h-full rounded-full bg-slate-900 animate-pulse"
                  style={{ width: `${Math.max(35, 85 - index * 18)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function EmptyStep({ text }: { text: string }): JSX.Element {
  return (
    <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-10 text-center text-sm text-slate-500">
      {text}
    </div>
  );
}

function InfoPanel({ title, items }: { title: string; items: string[] }): JSX.Element {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <h4 className="text-lg font-semibold text-slate-900">{title}</h4>
      <div className="mt-4 flex flex-wrap gap-2">
        {safeArray(items).map((item) => (
          <span key={item} className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-700">{item}</span>
        ))}
      </div>
    </section>
  );
}

function TextBlock({ label, content, large = false }: { label: string; content: string; large?: boolean }): JSX.Element {
  return (
    <div className="rounded-2xl border border-slate-200 p-4">
      <div className="text-xs font-semibold text-slate-400">{label}</div>
      <div className={`mt-3 whitespace-pre-wrap text-slate-700 ${large ? 'text-lg font-semibold' : 'text-sm leading-7'}`}>
        {content}
      </div>
    </div>
  );
}
