import { useState, useCallback } from 'react';
import 'katex/dist/katex.min.css';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';

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

/** Custom theme overriding oneDark to match zinc palette */
const codeTheme = {
  ...oneDark,
  'pre[class*="language-"]': {
    ...oneDark['pre[class*="language-"]'],
    background: '#18181b', // zinc-900
    margin: 0,
    padding: '1rem',
    borderRadius: 0,
    fontSize: '0.8125rem',
    lineHeight: '1.6',
  },
  'code[class*="language-"]': {
    ...oneDark['code[class*="language-"]'],
    background: 'transparent',
    fontSize: '0.8125rem',
  },
};

function SyntaxCodeBlock({
  language,
  code,
}: {
  language: string;
  code: string;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [code]);

  return (
    <div className="group relative my-4 border border-zinc-800 overflow-hidden">
      {/* Language label + copy button */}
      <div className="flex items-center justify-between bg-zinc-800/80 px-3 py-1.5">
        <span className="text-[11px] font-mono text-zinc-500">
          {language || 'text'}
        </span>
        <button
          onClick={handleCopy}
          className="text-zinc-500 text-[11px] font-mono hover:text-zinc-200 transition-colors"
          title="Copy code"
        >
          {copied ? '✓ copied' : 'copy'}
        </button>
      </div>
      <SyntaxHighlighter
        style={codeTheme}
        language={language || 'text'}
        PreTag="div"
        wrapLongLines
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

/** Fallback code block for when no language is detected */
function PlainCodeBlock({ children }: { children: React.ReactNode }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    const text = extractTextFromChildren(children);
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [children]);

  return (
    <div className="group relative my-4 border border-zinc-800 overflow-hidden">
      <div className="flex items-center justify-between bg-zinc-800/80 px-3 py-1.5">
        <span className="text-[11px] font-mono text-zinc-500">text</span>
        <button
          onClick={handleCopy}
          className="text-zinc-500 text-[11px] font-mono hover:text-zinc-200 transition-colors"
          title="Copy code"
        >
          {copied ? '✓ copied' : 'copy'}
        </button>
      </div>
      <pre className="overflow-x-auto bg-zinc-900 p-4 text-[13px] leading-relaxed text-zinc-100">
        {children}
      </pre>
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
            // Detect language from className (e.g., "language-python")
            const match = /language-(\w+)/.exec(className || '');
            const isInline = !className;

            if (isInline) {
              return (
                <code className="rounded-none bg-zinc-800 px-1 py-0.5 text-sm text-zinc-300" {...props}>
                  {children}
                </code>
              );
            }

            // Block code with syntax highlighting
            const codeStr = extractTextFromChildren(children).replace(/\n$/, '');
            return (
              <SyntaxCodeBlock
                language={match ? match[1] : ''}
                code={codeStr}
              />
            );
          },
          pre({ children }) {
            // If child is a SyntaxCodeBlock (from code handler above), render it directly
            // without wrapping in another <pre>
            const child = children as React.ReactElement;
            if (child?.type === SyntaxCodeBlock) {
              return <>{children}</>;
            }
            return <PlainCodeBlock>{children}</PlainCodeBlock>;
          },
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
}
