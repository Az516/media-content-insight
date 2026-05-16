import { useParams } from 'react-router-dom';

/**
 * 路由占位组件 (`frontend/src/components/Placeholder.tsx`)。
 *
 * 任务 1.5 仅注册 7 条主路由 + `*` 兜底,实际页面在 §9.x 中接入。
 * 这里展示当前路由名称与已解析的路由参数,方便联调期肉眼确认路由表完整。
 */
export interface PlaceholderProps {
  /** 占位区分名,例如 `Home` / `TaskDetail` / `NotFound`。 */
  name: string;
}

export function Placeholder({ name }: PlaceholderProps): JSX.Element {
  const params = useParams();
  const paramEntries = Object.entries(params);

  return (
    <section
      data-testid={`placeholder-${name}`}
      className="rounded-lg border border-dashed border-slate-300 bg-white p-6 shadow-sm"
    >
      <h1 className="text-lg font-semibold text-slate-800">
        占位页面:{name}
      </h1>
      <p className="mt-2 text-sm text-slate-500">
        此页面将在任务 9.x 中实现实际内容。
      </p>
      {paramEntries.length > 0 && (
        <dl className="mt-4 text-sm text-slate-600">
          {paramEntries.map(([key, value]) => (
            <div key={key} className="flex gap-2">
              <dt className="font-medium">{key}:</dt>
              <dd className="font-mono">{String(value)}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

export default Placeholder;
