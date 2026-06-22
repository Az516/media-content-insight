import { Link } from 'react-router-dom';

import { Icon } from '@/components/icons';
import { PageTitle, Panel, StatusTag } from '@/components/ui';
import { platformOptions } from '@/data/workbench';

const crawlerPlatforms = platformOptions.filter((platform) => platform.crawlerSupported);

export default function Integrations(): JSX.Element {
  return (
    <div>
      <PageTitle title="真实数据连接状态" />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
        <Panel className="p-5 sm:p-7">
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div>
              <h2 className="text-xl font-semibold text-slate-950">本地采集引擎</h2>
              <p className="mt-1 text-sm text-slate-500">
                本地浏览器登录态 · 本地数据库归档 · 关键词搜索 + 评论
              </p>
            </div>
            <StatusTag tone="green">已接入采集</StatusTag>
          </div>

          <div className="mt-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {crawlerPlatforms.map((platform) => (
              <div key={platform.key} className="rounded-2xl bg-slate-50 p-4 ring-1 ring-slate-100">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-base font-semibold text-slate-950">{platform.label}</div>
                  <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
                </div>
                <div className="mt-2 text-xs leading-5 text-slate-500">{platform.description}</div>
              </div>
            ))}
          </div>

          <div className="mt-7 grid gap-4 sm:grid-cols-2">
            <div className="rounded-2xl bg-white p-5 ring-1 ring-slate-200">
              <div className="text-sm text-slate-500">单次上限</div>
              <div className="mt-2 font-semibold text-slate-950">20 条内容</div>
            </div>
            <div className="rounded-2xl bg-white p-5 ring-1 ring-slate-200">
              <div className="text-sm text-slate-500">数据范围</div>
              <div className="mt-2 font-semibold text-slate-950">公开内容 + 评论</div>
            </div>
          </div>

          <div className="mt-7 flex flex-wrap items-center justify-between gap-4 border-t border-slate-200 pt-5">
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Icon name="shield" className="h-5 w-5" />
              只做本地读取与分析，不展示发送能力
            </div>
            <Link className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-blue-600" to="/track-search">
              发起采集
            </Link>
          </div>
        </Panel>

        <Panel className="p-5 sm:p-7">
          <StatusTag tone="slate">未接入</StatusTag>
          <h2 className="mt-5 text-xl font-semibold text-slate-950">官方授权与发送能力</h2>
          <p className="mt-3 text-sm leading-6 text-slate-500">
            公众号采集、官方评论发送、私信发送目前没有真实后端链路，因此不展示模拟授权状态。
          </p>
          <div className="mt-6 rounded-2xl bg-slate-50 p-5 text-sm leading-6 text-slate-600">
            如果后续接入官方接口，应先补后端接口、授权表、额度表和审计日志，再打开对应前端入口。
          </div>
        </Panel>
      </div>
    </div>
  );
}
