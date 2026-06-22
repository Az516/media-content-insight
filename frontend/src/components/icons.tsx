import type { SVGProps } from 'react';

export type IconName =
  | 'home'
  | 'search'
  | 'target'
  | 'file'
  | 'user'
  | 'chart'
  | 'link'
  | 'document'
  | 'radar'
  | 'shield'
  | 'send'
  | 'chevron'
  | 'doubleChevron'
  | 'check'
  | 'edit'
  | 'spark';

const paths: Record<IconName, JSX.Element> = {
  home: (
    <>
      <path d="m3.5 10.5 8.5-7 8.5 7" />
      <path d="M5.5 9.5V20h5v-6h3v6h5V9.5" />
    </>
  ),
  search: (
    <>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="m15.5 15.5 5 5" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
    </>
  ),
  file: (
    <>
      <path d="M7 3.5h6l4 4V20H7z" />
      <path d="M13 3.5V8h4" />
      <path d="M9.5 12h5M9.5 15h5" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5.5 20c.9-4 3-6 6.5-6s5.6 2 6.5 6" />
    </>
  ),
  chart: (
    <>
      <path d="M5 20V9" />
      <path d="M12 20V4" />
      <path d="M19 20v-7" />
    </>
  ),
  link: (
    <>
      <path d="M9.5 8.5 8 10a4 4 0 0 0 5.7 5.7l1.5-1.5" />
      <path d="m14.5 15.5 1.5-1.5A4 4 0 0 0 10.3 8.3L8.8 9.8" />
    </>
  ),
  document: (
    <>
      <path d="M7 4h8l2 2v14H7z" />
      <path d="M10 10h4M10 13h4M10 16h2" />
    </>
  ),
  radar: (
    <>
      <path d="M12 5a7 7 0 1 0 7 7" />
      <path d="M12 2v4M20 12h2" />
      <circle cx="12" cy="12" r="3" />
      <path d="m14 10 5-5" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3.5 19 6v5.5c0 4.4-2.8 7.1-7 9-4.2-1.9-7-4.6-7-9V6z" />
      <path d="m9 12 2 2 4-4" />
    </>
  ),
  send: (
    <>
      <path d="M4 11.5 20 4l-7.5 16-2-6.5z" />
      <path d="m10.5 13.5 4-4" />
    </>
  ),
  chevron: <path d="m9 5 7 7-7 7" />,
  doubleChevron: (
    <>
      <path d="m13 8-4 4 4 4" />
      <path d="m18 8-4 4 4 4" />
    </>
  ),
  check: <path d="m5 12 4 4 10-10" />,
  edit: (
    <>
      <path d="M5 19h4l10-10-4-4L5 15z" />
      <path d="m13 7 4 4" />
    </>
  ),
  spark: (
    <>
      <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />
      <path d="M19 16v4M17 18h4" />
    </>
  ),
};

export function Icon({
  name,
  className,
  ...props
}: SVGProps<SVGSVGElement> & { name: IconName }): JSX.Element {
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
      viewBox="0 0 24 24"
      {...props}
    >
      {paths[name]}
    </svg>
  );
}
