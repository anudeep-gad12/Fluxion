import 'katex/dist/katex.min.css';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

/**
 * Fix common LaTeX issues that cause KaTeX parsing errors.
 */
function fixLatexIssues(content: string): string {
  let result = content;

  // Remove trailing \\ before \end{...} in align/matrix/etc environments
  // This is a common error that causes KaTeX to fail
  result = result.replace(/\\\\\s*\\end\{/g, '\\end{');

  // Also handle cases with newline between \\ and \end
  result = result.replace(/\\\\\s*\n\s*\\end\{/g, '\n\\end{');

  return result;
}

/**
 * Normalize various LaTeX math delimiter formats to standard $$ and $ delimiters
 * that remark-math recognizes.
 */
function normalizeMathDelimiters(content: string): string {
  let result = content;

  const toBlockMath = (math: string) => {
    const fixedMath = fixLatexIssues(math.trim());
    return `\n$$\n${fixedMath}\n$$\n`;
  };

  const toInlineMath = (math: string) => `$${math.trim()}$`;

  // Normalize $$ ... $$ to fenced block math with line breaks
  result = result.replace(/\$\$([\s\S]*?)\$\$/g, (_, math) => toBlockMath(math));

  // Handle JSON-escaped delimiters (\\[ ... \\] and \\( ... \\))
  result = result.replace(/\\\\\[((?:.|\n)*?)\\\\\]/g, (_, math) => toBlockMath(math));
  result = result.replace(/\\\\\(((?:.|\n)*?)\\\\\)/g, (_, math) => toInlineMath(math));

  // Convert \[ ... \] to $$ ... $$ (display math)
  // Use [\s\S]*? to match any character including newlines, non-greedy
  result = result.replace(/\\\[([\s\S]*?)\\\]/g, (_, math) => toBlockMath(math));

  // Convert \( ... \) to $ ... $ (inline math)
  // Use [\s\S]*? to handle potential nested content
  result = result.replace(/\\\(([\s\S]*?)\\\)/g, (_, math) => toInlineMath(math));

  return result;
}

function coerceString(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value === null || value === undefined) return '';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function extractAnswer(rawAnswer: string): string {
  if (!rawAnswer) return '';

  try {
    const parsed = JSON.parse(rawAnswer);
    if (typeof parsed === 'string') return parsed.trim();
    if (parsed.content) return coerceString(parsed.content).trim();
    if (parsed.answer) return coerceString(parsed.answer).trim();
    if (parsed.final_answer) return coerceString(parsed.final_answer).trim();
    if (parsed.result) return coerceString(parsed.result).trim();
    if (parsed.response) return coerceString(parsed.response).trim();
    if (parsed.text) return coerceString(parsed.text).trim();
    if (parsed.conclusion) return coerceString(parsed.conclusion).trim();
  } catch {
    // Not JSON
  }

  return rawAnswer.trim();
}

export function AnswerMarkdown({ content }: { content: string }) {
  const safeContent = content || '';
  const normalizedContent = normalizeMathDelimiters(safeContent);

  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          code({ className, children, ...props }) {
            // In react-markdown v9, inline detection is based on whether
            // the code is wrapped in a <pre> (handled separately)
            const isInline = !className;
            if (isInline) {
              return (
                <code className="rounded bg-slate-100 px-1 py-0.5 text-sm text-slate-800" {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
          pre({ children }) {
            return (
              <pre className="my-4 overflow-x-auto rounded-lg bg-slate-900 p-4 text-sm text-slate-100">
                {children}
              </pre>
            );
          },
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
}
