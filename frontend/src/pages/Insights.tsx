import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { getInsights } from '@/api/tasks';
import type { CommentInsights } from '@/types/models';

function SentimentBar({
  sentiment,
}: {
  sentiment: CommentInsights['sentiment'];
}): JSX.Element {
  const positive = Math.max(0, sentiment?.positive ?? 0);
  const neutral = Math.max(0, sentiment?.neutral ?? 0);
  const negative = Math.max(0, sentiment?.negative ?? 0);
  const total = positive + neutral + negative || 1;
  const segments = [
    { key: 'positive', label: '正向', value: positive / total, tone: 'bg-sage-500' },
    { key: 'neutral', label: '中性', value: neutral / total, tone: 'bg-ink-400' },
    { key: 'negative', label: '负向', value: negative / total, tone: 'bg-claret-500' },
  ];
  return (
    <div>
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-paper-200">
        {segments.map((s) => (
          <div
            key={s.key}
            className={`${s.tone} transition-all`}
            style={{ width: `${(s.value * 100).toFixed(2)}%` }}
            aria-label={`${s.label} ${(s.value * 100).toFixed(0)}%`}
          />
        ))}
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
        {segments.map((s) => (
          <div key={s.key} className="rounded-lg bg-white/60 px-2 py-1.5 ring-1 ring-rule">
            <span className="text-ink-500">{s.label}</span>{' '}
            <span className="font-mono tabular-nums text-ink-900">
              {Math.round(s.value * 100)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Insights(): JSX.Element {
  const { taskId } = useParams();
  const [data, setData] = useState<CommentInsights | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!taskId) return;
    setLoading(true);
    getInsights(Number(taskId))
      .then(setData)
      .finally(() => setLoading(false));
  }, [taskId]);

  if (loading || !data) {
    return (
      <div className="rounded-2xl border border-rule bg-white/70 p-10 text-center text-sm text-ink-500">
        {loading ? '加载评论洞察…' : '暂无数据'}
      </div>
    );
  }

  const empty = !data.total_comments;
  const maxCount = Math.max(1, ...(data.top_keywords ?? []).map((w) => w.count));

  return (
    <section className="space-y-8">
      <div>
        <div className="flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.25em] text-ink-500">
          <Link to={`/tasks/${taskId}`} className="hover:text-ink-900">
            ← Task #{taskId}
          </Link>
          <span className="text-ink-400">/</span>
          <span>评论洞察</span>
        </div>
        <h2 className="mt-2 font-display text-4xl font-medium tracking-tightish text-ink-900">
          评论洞察
        </h2>
        <p className="mt-1 text-sm text-ink-500">
          高频词、情感倾向与热门评论 —— 看清话题底色。
        </p>
      </div>

      {empty ? (
        <div className="rounded-2xl border border-dashed border-rule bg-paper-50 p-12 text-center text-sm text-ink-500">
          本次任务没有抓到评论，可能是关键词命中的内容偏冷。
        </div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-2xl border border-rule bg-white/70 p-5 shadow-lift">
              <div className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-500">
                Total
              </div>
              <div className="mt-2 font-display text-4xl font-medium tabular-nums text-ink-900">
                {data.total_comments.toLocaleString()}
              </div>
              <div className="mt-1 text-xs text-ink-500">评论总数</div>
            </div>
            <div className="rounded-2xl border border-rule bg-white/70 p-5 shadow-lift md:col-span-2 lg:col-span-3">
              <div className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-500">
                Sentiment · 情感分布
              </div>
              <div className="mt-4">
                <SentimentBar sentiment={data.sentiment} />
              </div>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
            <div className="rounded-2xl border border-rule bg-white/70 p-5 shadow-lift">
              <div className="flex items-center justify-between">
                <h3 className="font-display text-xl text-ink-900">高频词</h3>
                <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-500">
                  Top {data.top_keywords?.length ?? 0}
                </span>
              </div>
              {data.top_keywords?.length ? (
                <ul className="mt-4 space-y-2">
                  {data.top_keywords.slice(0, 20).map((item) => (
                    <li key={item.word} className="flex items-center gap-3">
                      <span className="w-20 truncate font-display text-sm text-ink-900">
                        {item.word}
                      </span>
                      <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-paper-200">
                        <div
                          className="h-full bg-claret-500"
                          style={{
                            width: `${(item.count / maxCount) * 100}%`,
                          }}
                        />
                      </div>
                      <span className="w-10 text-right font-mono text-xs tabular-nums text-ink-500">
                        {item.count}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-4 text-sm text-ink-500">暂无高频词</p>
              )}
            </div>

            <div className="rounded-2xl border border-rule bg-white/70 p-5 shadow-lift">
              <div className="flex items-center justify-between">
                <h3 className="font-display text-xl text-ink-900">热门评论</h3>
                <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-ink-500">
                  Top {data.top_hot_comments?.length ?? 0}
                </span>
              </div>
              {data.top_hot_comments?.length ? (
                <ul className="mt-4 space-y-3">
                  {data.top_hot_comments.map((c) => (
                    <li
                      key={c.comment_id}
                      className="rounded-xl bg-paper-50 px-4 py-3"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-medium text-ink-900">
                          {c.nickname || '匿名'}
                        </span>
                        <span className="font-mono tabular-nums text-claret-500">
                          ♥ {c.like_count ?? 0}
                        </span>
                      </div>
                      <p className="mt-1.5 text-sm leading-relaxed text-ink-700">
                        {c.content || '-'}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-4 text-sm text-ink-500">暂无热门评论</p>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
