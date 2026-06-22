import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { listTasks } from '@/api/tasks';
import { Icon } from '@/components/icons';
import { PageTitle, Panel, StatusTag } from '@/components/ui';
import {
  listOutreachDrafts,
  type OutreachDraft,
  type OutreachDraftChannel,
  updateOutreachDraft,
} from '@/data/outreachDrafts';
import type { TaskListItem } from '@/types/models';

type DraftFilter = 'all' | OutreachDraftChannel;

const filterLabels: Record<DraftFilter, string> = {
  all: '全部',
  comment: '评论草稿',
  dm: '私信草稿',
};

function channelLabel(channel: OutreachDraftChannel): string {
  return channel === 'comment' ? '评论' : '私信';
}

async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', 'true');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  document.body.removeChild(textarea);
}

export default function DraftReview(): JSX.Element {
  const [latestTask, setLatestTask] = useState<TaskListItem | null>(null);
  const [drafts, setDrafts] = useState<OutreachDraft[]>([]);
  const [filter, setFilter] = useState<DraftFilter>('all');
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    setDrafts(listOutreachDrafts());
    listTasks().then((res) => {
      setLatestTask((res.items ?? []).find((item) => item.status === 'success') ?? null);
    });
  }, []);

  const filteredDrafts = useMemo(
    () => drafts.filter((draft) => filter === 'all' || draft.channel === filter),
    [drafts, filter],
  );

  const pendingCount = drafts.filter((draft) => draft.status === 'pending').length;
  const copiedCount = drafts.filter((draft) => draft.status === 'copied').length;
  const doneCount = drafts.filter((draft) => draft.status === 'done').length;

  function updateDraft(id: string, changes: Partial<OutreachDraft>): void {
    setDrafts(updateOutreachDraft(id, changes));
  }

  async function handleCopy(draft: OutreachDraft): Promise<void> {
    await copyText(draft.draft_text);
    updateDraft(draft.id, { status: 'copied' });
    setNotice(`已复制 1 条${channelLabel(draft.channel)}草稿。请在官方后台人工确认后发送。`);
  }

  return (
    <div>
      <PageTitle title="触达草稿审核" />
      <Panel className="p-8">
        <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div>
            <div className="grid h-16 w-16 place-items-center rounded-full bg-blue-50 text-blue-600">
              <Icon name="file" className="h-8 w-8" />
            </div>
            <h2 className="mt-6 text-2xl font-semibold text-slate-950">人工确认后再触达</h2>
            <p className="mt-4 max-w-2xl text-[16px] leading-7 text-slate-500">
              这里承接真实热门评论生成的评论/私信草稿。你可以编辑、复制并标记处理状态；系统不直接调用平台发送接口。
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link className="rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white" to="/leads">
                从热门评论生成草稿
              </Link>
              {latestTask ? (
                <Link
                  className="rounded-xl border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-blue-600"
                  to={`/tasks/${latestTask.id}/insights`}
                >
                  查看真实评论洞察
                </Link>
              ) : (
                <Link
                  className="rounded-xl border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-blue-600"
                  to="/track-search"
                >
                  先采集真实内容
                </Link>
              )}
            </div>
          </div>
          <div className="rounded-2xl bg-slate-50 p-6">
            <StatusTag tone="blue">{drafts.length} 条草稿</StatusTag>
            <h3 className="mt-5 text-lg font-semibold text-slate-950">审核状态</h3>
            <div className="mt-4 grid grid-cols-3 gap-3 text-center">
              <div className="rounded-xl bg-white p-3 ring-1 ring-slate-200">
                <div className="text-xl font-semibold text-slate-950">{pendingCount}</div>
                <div className="mt-1 text-xs text-slate-500">待审</div>
              </div>
              <div className="rounded-xl bg-white p-3 ring-1 ring-slate-200">
                <div className="text-xl font-semibold text-blue-700">{copiedCount}</div>
                <div className="mt-1 text-xs text-slate-500">已复制</div>
              </div>
              <div className="rounded-xl bg-white p-3 ring-1 ring-slate-200">
                <div className="text-xl font-semibold text-emerald-700">{doneCount}</div>
                <div className="mt-1 text-xs text-slate-500">已处理</div>
              </div>
            </div>
          </div>
        </div>

        {notice && (
          <div className="mt-8 rounded-xl bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800 ring-1 ring-emerald-200">
            {notice}
          </div>
        )}

        <div className="mt-10 flex flex-wrap gap-2">
          {(Object.keys(filterLabels) as DraftFilter[]).map((item) => (
            <button
              className={[
                'h-10 rounded-xl px-4 text-sm font-semibold transition',
                filter === item ? 'bg-slate-950 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
              ].join(' ')}
              key={item}
              type="button"
              onClick={() => setFilter(item)}
            >
              {filterLabels[item]}
            </button>
          ))}
        </div>

        {filteredDrafts.length === 0 ? (
          <div className="mt-8 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-10 text-center text-sm text-slate-500">
            当前没有可审核草稿。先到热门评论页，从真实评论生成待审草稿。
          </div>
        ) : (
          <div className="mt-8 space-y-5">
            {filteredDrafts.map((draft) => (
              <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.05)]" key={draft.id}>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusTag tone={draft.channel === 'comment' ? 'green' : 'blue'}>
                        {channelLabel(draft.channel)}
                      </StatusTag>
                      <StatusTag tone={draft.status === 'done' ? 'green' : draft.status === 'copied' ? 'blue' : 'slate'}>
                        {draft.status === 'done' ? '已处理' : draft.status === 'copied' ? '已复制' : '待审核'}
                      </StatusTag>
                    </div>
                    <h3 className="mt-4 text-lg font-semibold text-slate-950">
                      「{draft.task_keyword}」· {draft.source_nickname || '匿名用户'}
                    </h3>
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
                      原评论：{draft.source_content || '-'}
                    </p>
                  </div>
                  <Link
                    className="text-sm font-semibold text-blue-600 hover:text-blue-700"
                    to={`/tasks/${draft.task_id}/notes/${draft.source_note_id}`}
                  >
                    查看笔记
                  </Link>
                </div>

                <textarea
                  className="mt-5 min-h-[120px] w-full resize-y rounded-xl border border-slate-300 bg-slate-50 p-4 text-[15px] leading-7 text-slate-800 outline-none transition focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100"
                  value={draft.draft_text}
                  onChange={(event) => updateDraft(draft.id, { draft_text: event.target.value, status: 'pending' })}
                />
                <div className="mt-4 flex flex-wrap gap-3">
                  <button
                    className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-sm font-semibold text-white transition hover:bg-blue-700"
                    type="button"
                    onClick={() => void handleCopy(draft)}
                  >
                    <Icon name="send" className="h-4 w-4" />
                    复制草稿
                  </button>
                  <button
                    className="inline-flex h-10 items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
                    type="button"
                    onClick={() => updateDraft(draft.id, { status: 'done' })}
                  >
                    <Icon name="check" className="h-4 w-4" />
                    标记已处理
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
