import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { getTask, listTasks } from '@/api/tasks';
import { PageTitle, Panel, StatusTag } from '@/components/ui';
import type { Task } from '@/types/models';

export default function Reports(): JSX.Element {
  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listTasks()
      .then(async (res) => {
        if (cancelled) return;
        const latestSuccess = (res.items ?? []).find((item) => item.status === 'success');
        if (latestSuccess) {
          const detail = await getTask(latestSuccess.id);
          if (!cancelled) setTask(detail);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      <PageTitle title="真实报告" />
      <div className="grid gap-6 xl:grid-cols-[390px_minmax(0,1fr)]">
        <Panel className="p-8">
          <h2 className="text-xl font-semibold text-slate-950">最新任务摘要</h2>
          {loading ? (
            <div className="mt-7 text-sm text-slate-500">加载真实任务...</div>
          ) : task ? (
            <div className="mt-7 space-y-5">
              <SummaryRow label="关键词" value={`「${task.keyword}」`} />
              <SummaryRow label="笔记数" value={`${task.note_count} 条`} />
              <SummaryRow label="评论数" value={`${task.summary.total_comments} 条`} />
              <SummaryRow label="报告数" value={`${task.reports.length} 份`} />
              <StatusTag tone="green">真实数据</StatusTag>
            </div>
          ) : (
            <div className="mt-7 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-sm leading-6 text-slate-500">
              暂无已完成任务，因此没有真实报告可展示。
            </div>
          )}
        </Panel>
        <Panel className="p-8">
          <h2 className="text-2xl font-semibold text-slate-950">智能报告历史</h2>
          {task ? (
            task.reports.length > 0 ? (
              <div className="mt-6 divide-y divide-slate-200">
                {task.reports.map((report) => (
                  <article key={report.id} className="flex flex-wrap items-center justify-between gap-4 py-5 first:pt-0">
                    <div>
                      <div className="font-semibold text-slate-950">
                        {report.provider} · {report.model}
                      </div>
                      <div className="mt-1 text-sm text-slate-500">
                        {report.created_at.replace('T', ' ')} · {report.prompt_version}
                      </div>
                    </div>
                    <Link className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-blue-600" to={`/tasks/${task.id}/report`}>
                      查看报告
                    </Link>
                  </article>
                ))}
              </div>
            ) : (
              <div className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-sm leading-6 text-slate-500">
                这个任务还没有生成智能报告。
                <div>
                  <Link className="mt-4 inline-flex rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white" to={`/tasks/${task.id}/report`}>
                    去生成报告
                  </Link>
                </div>
              </div>
            )
          ) : (
            <div className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-sm leading-6 text-slate-500">
              完成一次真实采集后，报告入口会出现在这里。
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="border-b border-slate-200 pb-5 last:border-b-0">
      <div className="text-sm text-slate-500">{label}</div>
      <div className="mt-2 font-semibold leading-6 text-slate-950">{value}</div>
    </div>
  );
}
