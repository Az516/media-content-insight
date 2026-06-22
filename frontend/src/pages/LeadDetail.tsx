import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { getInsights, listTasks } from '@/api/tasks';
import { Icon } from '@/components/icons';
import { PageTitle, Panel, PlatformBadge, PrimaryButton, SecondaryButton, StatusTag } from '@/components/ui';
import { platformLabels } from '@/data/workbench';
import { createOutreachDrafts } from '@/data/outreachDrafts';
import type { CommentInsights, HotComment, TaskListItem } from '@/types/models';

export default function LeadDetail(): JSX.Element {
  const [task, setTask] = useState<TaskListItem | null>(null);
  const [insights, setInsights] = useState<CommentInsights | null>(null);
  const [loading, setLoading] = useState(true);
  const [draftMessage, setDraftMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listTasks()
      .then(async (res) => {
        if (cancelled) return;
        const latestSuccess = (res.items ?? []).find((item) => item.status === 'success') ?? null;
        setTask(latestSuccess);
        if (latestSuccess) {
          const data = await getInsights(latestSuccess.id);
          if (!cancelled) setInsights(data);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const comments = insights?.top_hot_comments ?? [];

  function generateDrafts(selectedComments: HotComment[], mode: 'comment' | 'dm' | 'both'): void {
    if (!task || selectedComments.length === 0) return;
    const channels = mode === 'both' ? (['comment', 'dm'] as const) : ([mode] as const);
    createOutreachDrafts(task, selectedComments, [...channels]);
    const channelText = mode === 'both' ? '评论和私信' : mode === 'comment' ? '评论' : '私信';
    setDraftMessage(`已生成 ${selectedComments.length} 条${channelText}草稿，等待人工审核。`);
  }

  return (
    <div>
      <PageTitle title="真实热门评论" />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_390px]">
        <Panel className="p-8">
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div>
              <div className="flex items-center gap-3 text-sm text-slate-500">
                {task?.platform ? (
                  <PlatformBadge platform={task.platform} />
                ) : (
                  <span className="inline-grid h-6 w-6 place-items-center rounded-md bg-rose-500 text-[10px] font-bold text-white">
                    小
                  </span>
                )}
                {task?.platform ? platformLabels[task.platform] : '小红书'} · {task ? `任务 #${task.id}` : '暂无任务'}
              </div>
              <h2 className="mt-4 text-3xl font-semibold text-slate-950">
                {task ? `「${task.keyword}」评论样本` : '暂无真实评论'}
              </h2>
              <p className="mt-3 max-w-2xl text-[16px] leading-7 text-slate-500">
                这里展示采集到的真实热门评论，可自动生成待审核触达草稿。草稿只进入人工确认流程，不会直接发送到平台。
              </p>
            </div>
            {task && <StatusTag tone="green">{comments.length} 条热门评论</StatusTag>}
          </div>

          {draftMessage && (
            <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800 ring-1 ring-emerald-200">
              <span>{draftMessage}</span>
              <Link className="font-semibold text-emerald-900 hover:text-emerald-700" to="/draft-review">
                去审核草稿
              </Link>
            </div>
          )}

          {!loading && comments.length > 0 && (
            <div className="mt-8 flex flex-wrap gap-3">
              <PrimaryButton icon="spark" onClick={() => generateDrafts(comments, 'both')}>
                为全部热门评论生成草稿
              </PrimaryButton>
              <SecondaryButton icon="edit" onClick={() => generateDrafts(comments, 'comment')}>
                只生成评论草稿
              </SecondaryButton>
              <SecondaryButton icon="send" onClick={() => generateDrafts(comments, 'dm')}>
                只生成私信草稿
              </SecondaryButton>
            </div>
          )}

          {loading ? (
            <div className="mt-10 rounded-2xl bg-slate-50 p-8 text-center text-sm text-slate-500">
              加载真实评论...
            </div>
          ) : comments.length === 0 ? (
            <div className="mt-10 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-10 text-center text-sm text-slate-500">
              暂无热门评论数据。完成一次带评论采集后会出现在这里。
            </div>
          ) : (
            <div className="mt-10 divide-y divide-slate-200">
              {comments.map((comment) => (
                <article key={comment.comment_id} className="py-6 first:pt-0">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="font-semibold text-slate-950">{comment.nickname || '匿名用户'}</div>
                    <div className="text-sm font-semibold tabular-nums text-rose-600">
                      {comment.like_count ?? 0} 赞
                    </div>
                  </div>
                  <p className="mt-3 text-[16px] leading-7 text-slate-700">{comment.content || '-'}</p>
                  <div className="mt-4 flex flex-wrap items-center gap-4">
                    {task && (
                      <Link
                        className="inline-flex text-sm font-semibold text-blue-600 hover:text-blue-700"
                        to={`/tasks/${task.id}/notes/${comment.note_id}`}
                      >
                        查看对应笔记
                      </Link>
                    )}
                    <button
                      className="inline-flex items-center gap-1.5 text-sm font-semibold text-emerald-700 hover:text-emerald-800"
                      type="button"
                      onClick={() => generateDrafts([comment], 'comment')}
                    >
                      <Icon name="edit" className="h-4 w-4" />
                      生成评论草稿
                    </button>
                    <button
                      className="inline-flex items-center gap-1.5 text-sm font-semibold text-emerald-700 hover:text-emerald-800"
                      type="button"
                      onClick={() => generateDrafts([comment], 'dm')}
                    >
                      <Icon name="send" className="h-4 w-4" />
                      生成私信草稿
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </Panel>

        <Panel className="p-8">
          <div className="grid h-16 w-16 place-items-center rounded-full bg-emerald-50 text-emerald-700">
            <Icon name="spark" className="h-8 w-8" />
          </div>
          <h2 className="mt-8 text-2xl font-semibold text-slate-950">触达边界</h2>
          <p className="mt-4 text-[16px] leading-7 text-slate-500">
            当前支持自动生成评论/私信草稿，并进入人工审核。没有官方授权发送能力前，系统不会代替账号自动评论或自动私信。
          </p>
          <div className="mt-8 rounded-2xl bg-amber-50 p-5 text-sm leading-6 text-amber-700">
            如果后续接入平台官方接口，需要保留人工确认、频控、敏感词审核和失败回执，才能从草稿流转到真实发送。
          </div>
          <Link
            className="mt-6 inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-slate-950 px-5 text-sm font-semibold text-white transition hover:bg-slate-800"
            to="/draft-review"
          >
            <Icon name="file" className="h-4 w-4" />
            查看草稿审核
          </Link>
        </Panel>
      </div>
    </div>
  );
}
