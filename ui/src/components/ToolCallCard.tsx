/**
 * Tool call visualization — CLI command output style.
 * Displays tool execution as terminal command output.
 */

import { cn } from '@/lib/utils';
import type { AgentToolCall, AgentToolCallStatus } from '@/types/agent';

interface ToolCallCardProps {
  toolCall: AgentToolCall;
}

const STATUS_MARKERS: Record<AgentToolCallStatus, { marker: string; color: string }> = {
  pending: { marker: '⋯', color: 'text-zinc-600' },
  running: { marker: '→', color: 'text-amber-500' },
  success: { marker: '✓', color: 'text-emerald-600' },
  error: { marker: '✗', color: 'text-red-500/70' },
  timeout: { marker: '⏎', color: 'text-amber-600' },
  interrupted: { marker: '✗', color: 'text-zinc-500' },
};

const TOOL_PREFIXES: Record<string, string> = {
  web_search: 'search',
  web_extract: 'extract',
  python_execute: 'python',
  read_file: 'read',
  list_directory: 'list',
  write_file: 'write',
  edit_file: 'edit',
  grep: 'grep',
  glob: 'glob',
  bash: 'bash',
};

function formatArguments(
  toolName: string,
  args: Record<string, unknown>
): string {
  if (args.query) return `"${args.query}"`;
  if (args.url) return args.url as string;
  if (args.urls) return `${(args.urls as string[]).length} URLs`;
  if (args.file_path) return args.file_path as string;
  if (args.path) return args.path as string;
  if (args.pattern) return args.pattern as string;
  if (args.command) return args.command as string;
  if (toolName === 'python_execute') return '';
  return JSON.stringify(args);
}

function PythonCodeBlock({ code, output }: { code: string; output?: string }) {
  return (
    <div className="space-y-1 ml-4">
      <pre className="overflow-x-auto border-l border-zinc-800/90 pl-3 text-xs font-mono leading-relaxed text-zinc-300">
        <code>{code}</code>
      </pre>
      {output && (
        <pre className="overflow-x-auto whitespace-pre-wrap border-l border-zinc-900/90 pl-3 text-xs font-mono leading-relaxed text-zinc-400">
          <code>{output}</code>
        </pre>
      )}
    </div>
  );
}

type DiffRow = {
  kind: 'context' | 'add' | 'remove' | 'change' | 'hunk';
  oldText?: string;
  newText?: string;
};

function parseUnifiedDiff(diff: string): {
  beforeLabel: string;
  afterLabel: string;
  rows: DiffRow[];
} {
  const lines = diff.split('\n');
  const beforeLabel =
    lines.find((line) => line.startsWith('--- '))?.replace(/^---\s+/, '') || 'before';
  const afterLabel =
    lines.find((line) => line.startsWith('+++ '))?.replace(/^\+\+\+\s+/, '') || 'after';
  const rows: DiffRow[] = [];

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line && index === lines.length - 1) continue;
    if (line.startsWith('--- ') || line.startsWith('+++ ')) continue;

    if (line.startsWith('@@')) {
      rows.push({ kind: 'hunk', oldText: line, newText: line });
      continue;
    }

    if (line.startsWith('-')) {
      const next = lines[index + 1];
      if (next?.startsWith('+') && !next.startsWith('+++')) {
        rows.push({
          kind: 'change',
          oldText: line.slice(1) || ' ',
          newText: next.slice(1) || ' ',
        });
        index += 1;
      } else {
        rows.push({ kind: 'remove', oldText: line.slice(1) || ' ', newText: '' });
      }
      continue;
    }

    if (line.startsWith('+')) {
      rows.push({ kind: 'add', oldText: '', newText: line.slice(1) || ' ' });
      continue;
    }

    const text = line.startsWith(' ') ? line.slice(1) : line;
    rows.push({ kind: 'context', oldText: text || ' ', newText: text || ' ' });
  }

  return { beforeLabel, afterLabel, rows };
}

function cellClass(kind: DiffRow['kind'], side: 'old' | 'new'): string {
  if (kind === 'hunk') return '';
  if (kind === 'remove') return side === 'old' ? 'tool-diff-cell-remove' : 'tool-diff-cell-empty';
  if (kind === 'add') return side === 'new' ? 'tool-diff-cell-add' : 'tool-diff-cell-empty';
  if (kind === 'change') {
    return side === 'old' ? 'tool-diff-cell-change-old' : 'tool-diff-cell-change-new';
  }
  return 'tool-diff-cell-muted';
}

export function resolveUnifiedDiff(toolCall: AgentToolCall): string | null {
  const candidates: string[] = [];
  if (typeof toolCall.diff_preview === 'string' && toolCall.diff_preview.trim()) {
    candidates.push(toolCall.diff_preview);
  }
  if (typeof toolCall.result_data === 'string' && toolCall.result_data.trim()) {
    candidates.push(toolCall.result_data);
  }

  for (const candidate of candidates) {
    if (candidate.startsWith('--- ') && candidate.includes('\n+++ ')) {
      return candidate;
    }
    try {
      const parsed = JSON.parse(candidate) as { diff?: string; preview?: string };
      const nested = parsed.diff ?? parsed.preview;
      if (typeof nested === 'string' && nested.includes('+++ ')) {
        return nested;
      }
    } catch {
      // Not JSON — keep scanning candidates.
    }
  }

  return null;
}

export function UnifiedDiffView({
  diff,
  compact = false,
}: {
  diff: string;
  compact?: boolean;
}) {
  const { beforeLabel, afterLabel, rows } = parseUnifiedDiff(diff);

  return (
    <div className={cn('tool-diff', compact && 'tool-diff-compact')}>
      <div className="tool-diff-header">
        <div className="tool-diff-header-cell">{beforeLabel}</div>
        <div className="tool-diff-header-cell">{afterLabel}</div>
      </div>
      <div>
        {rows.map((row, index) => {
          if (row.kind === 'hunk') {
            return (
              <div key={`${index}-${row.oldText}`} className="tool-diff-hunk">
                {row.oldText}
              </div>
            );
          }

          return (
            <div key={`${index}-${row.oldText}-${row.newText}`} className="tool-diff-row">
              <pre className={cn('tool-diff-cell tool-diff-cell-old', cellClass(row.kind, 'old'))}>
                {row.oldText}
              </pre>
              <pre className={cn('tool-diff-cell', cellClass(row.kind, 'new'))}>
                {row.newText}
              </pre>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function BashOutputBlock({
  output,
}: {
  output: NonNullable<AgentToolCall['bash_output']>;
}) {
  const hasStdout = output.stdout.trim().length > 0;
  const hasStderr = output.stderr.trim().length > 0;

  return (
    <div className="ml-4 space-y-1">
      <div className="flex gap-3 text-zinc-600">
        {typeof output.exit_code === 'number' && <span>exit {output.exit_code}</span>}
        {output.truncated && <span className="text-amber-500/80">truncated</span>}
      </div>
      {hasStdout && (
        <div>
          <div className="mb-0.5 text-[10px] uppercase tracking-wide text-zinc-600">stdout</div>
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap border-l border-zinc-800/90 pl-3 text-zinc-300">
            {output.stdout}
          </pre>
        </div>
      )}
      {hasStderr && (
        <div>
          <div className="mb-0.5 text-[10px] uppercase tracking-wide text-red-500/60">stderr</div>
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap border-l border-red-500/24 pl-3 text-red-300">
            {output.stderr}
          </pre>
        </div>
      )}
    </div>
  );
}

export function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const status = STATUS_MARKERS[toolCall.status];
  const prefix = TOOL_PREFIXES[toolCall.tool_name] || toolCall.tool_name;
  const isRunning = toolCall.status === 'running';
  const isPython = toolCall.tool_name === 'python_execute';
  const isBash = toolCall.tool_name === 'bash';
  const hasResult =
    toolCall.result_summary && toolCall.result_summary.length > 0;
  const unifiedDiff = resolveUnifiedDiff(toolCall);

  const pythonOutput = isPython && hasResult ? toolCall.result_summary : undefined;
  const argStr = formatArguments(toolCall.tool_name, toolCall.arguments);
  const needsApproval = toolCall.status === 'pending' && toolCall.approval_required;

  return (
    <div className="desktop-tool-call font-mono text-xs space-y-1">
      {/* Command line */}
      <div className="flex items-start gap-2">
        <span className={cn('select-none shrink-0', status.color)}>{status.marker}</span>
        <span className="text-zinc-500">{prefix}</span>
        {argStr && <span className="text-zinc-300 break-all">{argStr}</span>}
        {toolCall.duration_ms && (
          <span className="text-zinc-600 ml-auto shrink-0">{toolCall.duration_ms}ms</span>
        )}
        {isRunning && (
          <span className="flex items-center gap-1.5 text-amber-500/70 ml-auto shrink-0">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
            running
          </span>
        )}
      </div>

      {/* Python code block */}
      {isPython && typeof toolCall.arguments.code === 'string' && (
        <PythonCodeBlock
          code={toolCall.arguments.code}
          output={pythonOutput}
        />
      )}

      {/* Approval prompt */}
      {needsApproval && (
        <div className="ml-4 border-l border-amber-500/24 pl-3">
          <div className="text-amber-300/80">
            approval required
            {toolCall.permission_level && (
              <span className="text-amber-500/50"> · {toolCall.permission_level}</span>
            )}
            <span className="text-zinc-500"> · use HUD</span>
          </div>
        </div>
      )}

      {/* Result (non-python) */}
      {hasResult && !isPython && (
        <div className="ml-4">
          <div className="text-zinc-400 whitespace-pre-wrap">
            {toolCall.result_summary}
          </div>
        </div>
      )}

      {isBash && toolCall.bash_output && <BashOutputBlock output={toolCall.bash_output} />}

      {/* Full write/edit diff after execution */}
      {unifiedDiff && (
        <div className="ml-4">
          <UnifiedDiffView diff={unifiedDiff} />
        </div>
      )}

      {/* Error */}
      {toolCall.error_message && (
        <div className="ml-4 text-zinc-500">
          err: {toolCall.error_message}
        </div>
      )}
    </div>
  );
}
