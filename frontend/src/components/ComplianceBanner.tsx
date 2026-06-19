/**
 * ComplianceBanner.
 *
 * Locked compliance copy (requirement 18.2) rendered as a sticky
 * editorial strip at the very top of the page. No close affordance,
 * no truncation. Visual treatment is intentionally restrained — a
 * single claret marker (※) and a paper-toned surface keeps the
 * banner authoritative without screaming.
 */

const COMPLIANCE_TEXT =
  '本工具仅供学习研究和小规模数据分析,适用于多平台公开内容洞察,请遵守各平台条款,不得用于自动化营销、批量发布或商业用途';

export function ComplianceBanner(): JSX.Element {
  return (
    <div
      role="region"
      aria-label="合规提示"
      data-testid="compliance-banner"
      className="sticky top-0 z-50 w-full border-b border-rule bg-paper-50/95 backdrop-blur-sm"
    >
      <div className="mx-auto flex max-w-6xl items-center gap-3 px-6 py-2.5">
        <span
          aria-hidden
          className="font-display text-base font-medium leading-none text-claret-500"
        >
          ※
        </span>
        <p className="whitespace-normal break-words text-[12.5px] leading-relaxed text-ink-700">
          {COMPLIANCE_TEXT}
        </p>
      </div>
    </div>
  );
}

export default ComplianceBanner;
