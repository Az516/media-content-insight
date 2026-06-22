import type { ReactNode } from 'react';

import { Icon, type IconName } from '@/components/icons';
import { platformLabels, type PlatformKey } from '@/data/workbench';

export function Panel({
  children,
  className = '',
}: {
  children: ReactNode;
  className?: string;
}): JSX.Element {
  return (
    <section
      className={`rounded-[22px] border border-slate-300/70 bg-white shadow-panel ring-1 ring-white/80 ${className}`}
    >
      {children}
    </section>
  );
}

export function PageTitle({
  title,
  action,
  description,
}: {
  title: string;
  action?: ReactNode;
  description?: ReactNode;
}): JSX.Element {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[27px] font-semibold leading-tight tracking-normal text-slate-950 md:text-[32px]">
          {title}
        </h1>
        {description && <div className="mt-2 text-sm leading-6 text-slate-500">{description}</div>}
      </div>
      {action}
    </div>
  );
}

export function IconBubble({
  icon,
  tone = 'green',
  className = '',
}: {
  icon: IconName;
  tone?: 'blue' | 'green' | 'amber' | 'violet';
  className?: string;
}): JSX.Element {
  const tones = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-emerald-50 text-emerald-700',
    amber: 'bg-amber-50 text-amber-700',
    violet: 'bg-violet-50 text-blue-600',
  };

  return (
    <span
      className={`grid h-16 w-16 shrink-0 place-items-center rounded-full ring-1 ring-white/80 ${tones[tone]} ${className}`}
    >
      <Icon name={icon} className="h-8 w-8" />
    </span>
  );
}

export function StatusTag({
  children,
  tone,
}: {
  children: ReactNode;
  tone: 'amber' | 'green' | 'blue' | 'red' | 'slate';
}): JSX.Element {
  const tones = {
    amber: 'bg-amber-50 text-amber-700 ring-amber-200/70',
    green: 'bg-emerald-50 text-emerald-700 ring-emerald-200/70',
    blue: 'bg-blue-50 text-blue-700 ring-blue-200/70',
    red: 'bg-rose-50 text-rose-700 ring-rose-200/70',
    slate: 'bg-slate-100 text-slate-600 ring-slate-200',
  };

  return (
    <span
      className={`inline-flex min-w-[64px] items-center justify-center rounded-full px-3 py-1 text-sm font-medium ring-1 ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function PlatformBadge({ platform }: { platform: PlatformKey }): JSX.Element {
  const tones: Record<PlatformKey, string> = {
    xhs: 'bg-rose-500 text-white',
    dy: 'bg-slate-950 text-white',
    ks: 'bg-orange-500 text-white',
    bili: 'bg-sky-500 text-white',
    wb: 'bg-amber-500 text-white',
    tieba: 'bg-blue-500 text-white',
    zhihu: 'bg-indigo-500 text-white',
    wechat: 'bg-green-500 text-white',
  };

  return (
    <span className={`inline-grid h-6 w-6 place-items-center rounded-md text-[10px] font-bold ${tones[platform]}`}>
      {platformLabels[platform].slice(0, 1)}
    </span>
  );
}

export function PrimaryButton({
  children,
  icon,
  onClick,
  disabled = false,
}: {
  children: ReactNode;
  icon?: IconName;
  onClick?: () => void;
  disabled?: boolean;
}): JSX.Element {
  return (
    <button
      className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 text-sm font-semibold text-white shadow-button transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      disabled={disabled}
      type="button"
      onClick={onClick}
    >
      {icon && <Icon name={icon} className="h-4 w-4" />}
      {children}
    </button>
  );
}

export function SecondaryButton({
  children,
  icon,
  onClick,
}: {
  children: ReactNode;
  icon?: IconName;
  onClick?: () => void;
}): JSX.Element {
  return (
    <button
      className="inline-flex h-10 items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 text-sm font-semibold text-blue-600 shadow-[0_1px_2px_rgba(15,23,42,0.06)] transition hover:border-blue-300 hover:bg-blue-50"
      type="button"
      onClick={onClick}
    >
      {icon && <Icon name={icon} className="h-4 w-4" />}
      {children}
    </button>
  );
}
