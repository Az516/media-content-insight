import { useId, useMemo, useState, type FormEvent } from 'react';

/**
 * KeywordInput (`frontend/src/components/KeywordInput.tsx`)。
 *
 * 任务 8.2 / 需求 1.1, 17.3, 17.4:
 * - 关键词受控,`trim` 后非空且长度 ≤ 50 才允许提交。
 * - `maxNotes` 受控为整数,范围 `[1, 20]`;非整数 / `<1` / `>20` 时禁用提交按钮
 *   并显示对应文案(`>20` → 「单次采集上限 20 条」、`<1` → 「单次采集至少 1 条」、
 *   非整数 → 「请输入整数」)。
 * - 关键词 trim 后长度 > 50 时显示「关键词长度需 ≤ 50」。
 *
 * 提交时回调 `onSubmit({ keyword, maxNotes })`,其中 `keyword` 为 trim 后的字符串,
 * `maxNotes` 为已解析为整数的合法值;父组件可通过 `isBusy` 在采集运行期间禁用整个表单
 * (需求 2.3 在 `Home.tsx` 中使用)。
 */
export interface KeywordInputProps {
  /** 通过校验后的提交回调。 */
  onSubmit: (payload: { keyword: string; maxNotes: number }) => void;
  /** `maxNotes` 输入框的初始值,默认 20。 */
  defaultMaxNotes?: number;
  /** 当系统中已有 running 任务时父组件传 true,禁用整张表单(需求 2.3)。 */
  isBusy?: boolean;
}

/** 关键词最大长度(需求 1.1 / 1.4)。 */
const KEYWORD_MAX_LEN = 50;
/** `maxNotes` 取值上限(需求 17.3,与后端 `OVER_LIMIT` 校验对齐)。 */
const MAX_NOTES_UPPER = 20;
/** `maxNotes` 取值下限。 */
const MAX_NOTES_LOWER = 1;

/** 仅匹配可正负的整数字面量,允许 `parseInt` 后落在 `[1, 20]` 才算合法。 */
const INTEGER_RE = /^-?\d+$/;

interface MaxNotesValidation {
  /** 解析得到的整数值,无法解析或非整数时为 `null`。 */
  parsed: number | null;
  /** 是否落在 `[1, 20]` 闭区间。 */
  inRange: boolean;
  /** 输入框下方提示文案,无错误或空输入时为 `null`。 */
  helperText: string | null;
}

/** 计算 `maxNotes` 输入框的校验结果与提示文案。 */
function validateMaxNotes(raw: string): MaxNotesValidation {
  // 空字符串:按钮禁用,但不展示提示文案以避免初始即报错。
  if (raw === '') {
    return { parsed: null, inRange: false, helperText: null };
  }
  // 非整数字面量(含小数、空白、非数字字符)统一提示「请输入整数」。
  if (!INTEGER_RE.test(raw)) {
    return { parsed: null, inRange: false, helperText: '请输入整数' };
  }
  const parsed = Number.parseInt(raw, 10);
  if (parsed > MAX_NOTES_UPPER) {
    return { parsed, inRange: false, helperText: '单次采集上限 20 条' };
  }
  if (parsed < MAX_NOTES_LOWER) {
    return { parsed, inRange: false, helperText: '单次采集至少 1 条' };
  }
  return { parsed, inRange: true, helperText: null };
}

interface KeywordValidation {
  trimmed: string;
  /** 是否非空且长度 ≤ 50。 */
  ok: boolean;
  /** 仅在长度 > 50 时给出提示;为空时不展示提示但按钮仍禁用。 */
  helperText: string | null;
}

/** 计算关键词输入的校验结果与提示文案。 */
function validateKeyword(raw: string): KeywordValidation {
  const trimmed = raw.trim();
  if (trimmed.length === 0) {
    return { trimmed, ok: false, helperText: null };
  }
  if (trimmed.length > KEYWORD_MAX_LEN) {
    return { trimmed, ok: false, helperText: '关键词长度需 ≤ 50' };
  }
  return { trimmed, ok: true, helperText: null };
}

export function KeywordInput({
  onSubmit,
  defaultMaxNotes = MAX_NOTES_UPPER,
  isBusy = false,
}: KeywordInputProps): JSX.Element {
  const keywordId = useId();
  const maxNotesId = useId();
  const keywordHelperId = `${keywordId}-helper`;
  const maxNotesHelperId = `${maxNotesId}-helper`;

  const [keyword, setKeyword] = useState<string>('');
  // `maxNotesInput` 保持字符串,使「非整数」与「越界整数」可被独立校验。
  const [maxNotesInput, setMaxNotesInput] = useState<string>(
    String(defaultMaxNotes),
  );

  const keywordValidation = useMemo(() => validateKeyword(keyword), [keyword]);
  const maxNotesValidation = useMemo(
    () => validateMaxNotes(maxNotesInput),
    [maxNotesInput],
  );

  const canSubmit =
    !isBusy && keywordValidation.ok && maxNotesValidation.inRange;

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!canSubmit || maxNotesValidation.parsed === null) {
      return;
    }
    onSubmit({
      keyword: keywordValidation.trimmed,
      maxNotes: maxNotesValidation.parsed,
    });
  }

  return (
    <form
      onSubmit={handleSubmit}
      data-testid="keyword-input"
      className="flex flex-col gap-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:items-start"
    >
      <div className="flex flex-1 flex-col gap-1">
        <label
          htmlFor={keywordId}
          className="text-sm font-medium text-slate-700"
        >
          关键词
        </label>
        <input
          id={keywordId}
          type="text"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          disabled={isBusy}
          maxLength={200}
          placeholder="输入小红书话题关键词,1-50 个字符"
          aria-invalid={keywordValidation.helperText !== null}
          aria-describedby={
            keywordValidation.helperText ? keywordHelperId : undefined
          }
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus:border-rose-400 focus:ring-2 focus:ring-rose-200 disabled:cursor-not-allowed disabled:bg-slate-100"
        />
        {keywordValidation.helperText !== null && (
          <p
            id={keywordHelperId}
            role="alert"
            className="text-xs text-rose-600"
          >
            {keywordValidation.helperText}
          </p>
        )}
      </div>

      <div className="flex w-full flex-col gap-1 sm:w-40">
        <label
          htmlFor={maxNotesId}
          className="text-sm font-medium text-slate-700"
        >
          采集数量
        </label>
        <input
          id={maxNotesId}
          type="number"
          inputMode="numeric"
          step={1}
          min={MAX_NOTES_LOWER}
          max={MAX_NOTES_UPPER}
          value={maxNotesInput}
          onChange={(event) => setMaxNotesInput(event.target.value)}
          disabled={isBusy}
          aria-invalid={maxNotesValidation.helperText !== null}
          aria-describedby={
            maxNotesValidation.helperText ? maxNotesHelperId : undefined
          }
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition focus:border-rose-400 focus:ring-2 focus:ring-rose-200 disabled:cursor-not-allowed disabled:bg-slate-100"
        />
        {maxNotesValidation.helperText !== null && (
          <p
            id={maxNotesHelperId}
            role="alert"
            className="text-xs text-rose-600"
          >
            {maxNotesValidation.helperText}
          </p>
        )}
      </div>

      <div className="flex flex-col justify-end sm:pt-6">
        <button
          type="submit"
          disabled={!canSubmit}
          aria-disabled={!canSubmit}
          className="inline-flex items-center justify-center rounded-md bg-rose-500 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-rose-600 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          开始采集
        </button>
      </div>
    </form>
  );
}

export default KeywordInput;
