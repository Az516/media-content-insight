import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * MarkdownView (task 8.5).
 *
 * Renders an AI report's Markdown body in an editorial layout that
 * matches the rest of the Editorial Research Lab visual system —
 * Fraunces serif headings, claret pull quotes, JetBrains Mono for
 * inline code. The wrapper uses `prose` semantics so headings,
 * lists, blockquotes and tables stay legible without our needing to
 * style every element manually.
 */
export default function MarkdownView({ content }: { content: string }): JSX.Element {
  return (
    <article
      className="overflow-x-auto rounded-3xl border border-rule bg-white/80 px-8 py-8 shadow-paper sm:px-10
        prose prose-neutral max-w-none
        prose-headings:font-display prose-headings:tracking-tightish prose-headings:text-ink-900
        prose-h1:text-4xl prose-h1:font-medium prose-h1:mb-6
        prose-h2:text-2xl prose-h2:font-medium prose-h2:mt-10 prose-h2:mb-3 prose-h2:border-b prose-h2:border-rule prose-h2:pb-2
        prose-h3:text-lg prose-h3:font-medium prose-h3:text-claret-500 prose-h3:mt-6 prose-h3:mb-2
        prose-p:text-ink-700 prose-p:leading-relaxed
        prose-strong:text-ink-900
        prose-li:text-ink-700 prose-li:marker:text-claret-500
        prose-a:text-claret-500 prose-a:no-underline hover:prose-a:underline
        prose-blockquote:border-l-2 prose-blockquote:border-claret-500 prose-blockquote:bg-paper-50 prose-blockquote:text-ink-700 prose-blockquote:not-italic
        prose-code:font-mono prose-code:text-claret-600 prose-code:bg-paper-100 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:before:content-none prose-code:after:content-none
        prose-pre:bg-ink-900 prose-pre:text-paper-50 prose-pre:rounded-2xl
        prose-hr:border-rule
        prose-table:border-collapse prose-th:border prose-th:border-rule prose-th:bg-paper-50 prose-th:px-3 prose-th:py-2 prose-td:border prose-td:border-rule prose-td:px-3 prose-td:py-2"
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </article>
  );
}
