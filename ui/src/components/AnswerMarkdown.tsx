import { useState, useCallback } from 'react';
import 'katex/dist/katex.min.css';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Check, Copy } from 'lucide-react';

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

/**
 * Strip thinking tags from content and extract ONLY the answer portion.
 *
 * This function handles:
 * - [THINK]...thinking...[/THINK]answer -> returns "answer"
 * - [THINK]...thinking... (no closing tag) -> returns "" (still thinking, no answer)
 * - No tags at all -> returns original content
 *
 * Handles:
 * - Case variations: [THINK], [think], [Think]
 * - Whitespace in tags: [ THINK ], [THINK ], [ /THINK]
 * - Legacy <think>...</think> format
 */
function stripThinkingTags(content: string): string {
  if (!content) return '';

  const thinkPattern = /\[\s*THINK\s*\]/i;
  const endThinkPattern = /\[\s*\/\s*THINK\s*\]/gi;

  const hasThinkOpen = thinkPattern.test(content);
  const hasThinkClose = /\[\s*\/\s*THINK\s*\]/i.test(content);

  if (hasThinkOpen) {
    if (hasThinkClose) {
      // Extract ONLY the content after the LAST [/THINK] tag
      const parts = content.split(endThinkPattern);
      if (parts.length > 1) {
        let result = parts[parts.length - 1].trim();
        // Clean up any remaining tags
        result = result.replace(/\[\s*THINK\s*\]/gi, '');
        result = result.replace(/\[\s*\/\s*THINK\s*\]/gi, '');
        return result.trim();
      }
      return '';
    } else {
      // Opening tag without closing - model is still thinking, no answer yet
      return '';
    }
  }

  // Check for legacy <think>...</think> format
  const legacyThinkPattern = /<\s*think\s*>/i;
  const legacyEndPattern = /<\s*\/\s*think\s*>/gi;

  const hasLegacyOpen = legacyThinkPattern.test(content);
  const hasLegacyClose = /<\s*\/\s*think\s*>/i.test(content);

  if (hasLegacyOpen) {
    if (hasLegacyClose) {
      const parts = content.split(legacyEndPattern);
      if (parts.length > 1) {
        let result = parts[parts.length - 1].trim();
        result = result.replace(/<\s*think\s*>/gi, '');
        result = result.replace(/<\s*\/\s*think\s*>/gi, '');
        result = result.replace(/<\s*answer\s*>/gi, '');
        result = result.replace(/<\s*\/\s*answer\s*>/gi, '');
        return result.trim();
      }
      return '';
    } else {
      return '';
    }
  }

  // No thinking tags found - return original content as-is
  return content.trim();
}

export function extractAnswer(rawAnswer: string): string {
  if (!rawAnswer) return '';

  let content = rawAnswer;

  try {
    const parsed = JSON.parse(rawAnswer);
    if (typeof parsed === 'string') content = parsed;
    else if (parsed.content) content = coerceString(parsed.content);
    else if (parsed.answer) content = coerceString(parsed.answer);
    else if (parsed.final_answer) content = coerceString(parsed.final_answer);
    else if (parsed.result) content = coerceString(parsed.result);
    else if (parsed.response) content = coerceString(parsed.response);
    else if (parsed.text) content = coerceString(parsed.text);
    else if (parsed.conclusion) content = coerceString(parsed.conclusion);
  } catch {
    // Not JSON, use raw content
  }

  // Strip any thinking tags and return clean answer
  return stripThinkingTags(content);
}

function CodeBlock({ children }: { children: React.ReactNode }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    const text = extractTextFromChildren(children);
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [children]);

  return (
    <div className="group relative my-4">
      <pre className="overflow-x-auto rounded-lg bg-slate-900 p-4 text-sm text-slate-100">
        {children}
      </pre>
      <button
        onClick={handleCopy}
        className="absolute right-2 top-2 p-1.5 rounded-md bg-slate-700/80 text-slate-300 opacity-0 group-hover:opacity-100 hover:bg-slate-600 hover:text-white transition-all"
        title="Copy code"
      >
        {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  );
}

/** Recursively extract text content from React children. */
function extractTextFromChildren(children: React.ReactNode): string {
  if (typeof children === 'string') return children;
  if (typeof children === 'number') return String(children);
  if (!children) return '';
  if (Array.isArray(children)) return children.map(extractTextFromChildren).join('');
  if (typeof children === 'object' && 'props' in children) {
    return extractTextFromChildren(children.props.children);
  }
  return '';
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
            return <CodeBlock>{children}</CodeBlock>;
          },
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
}
