/**
 * ComplianceBanner (`frontend/src/components/ComplianceBanner.tsx`)。
 *
 * 全局合规提示横幅,需求 17.7 / 18.1 / 18.2:
 * - 在所有页面顶部固定渲染,通过 `sticky top-0` 保证路由切换、页面滚动期间持续可见。
 * - 完整展示需求 18.2 锁定的固定文案,使用 `whitespace-normal` + `break-words`
 *   保证窄屏环境下文案换行而非被截断或省略;不使用 `truncate` / `text-ellipsis`。
 * - 不提供关闭 / 隐藏入口:组件内不存在 `useState`、`onClick` 或可切换可见性的属性。
 */

/** 需求 18.2 锁定的固定合规文案,任何场景下都不得被截断或省略。 */
const COMPLIANCE_TEXT =
  '本工具仅供学习研究和小规模数据分析,请遵守平台条款,不得用于自动化营销、批量发布或商业用途';

export function ComplianceBanner(): JSX.Element {
  return (
    <div
      role="region"
      aria-label="合规提示"
      data-testid="compliance-banner"
      className="sticky top-0 z-50 w-full border-b border-amber-200 bg-amber-100 text-amber-900 shadow-sm"
    >
      <p className="mx-auto max-w-5xl whitespace-normal break-words px-4 py-2 text-center text-sm leading-relaxed">
        {COMPLIANCE_TEXT}
      </p>
    </div>
  );
}

export default ComplianceBanner;
