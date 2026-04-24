/**
 * Tool call visualization — CLI command output style.
 * Displays tool execution as terminal command output.
 */

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { approveAgentToolCall, denyAgentToolCall } from '@/api/client';
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
      <pre className="text-xs text-zinc-300 overflow-x-auto font-mono leading-relaxed bg-zinc-900 border border-zinc-800 p-2">
        <code>{code}</code>
      </pre>
      {output && (
        <pre className="text-xs text-zinc-400 overflow-x-auto font-mono leading-relaxed whitespace-pre-wrap bg-zinc-800/50 p-2">
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

function DiffBlock({ diff }: { diff: string }) {
  const { beforeLabel, afterLabel, rows } = parseUnifiedDiff(diff);

  return (
    <div className="max-h-96 overflow-auto bg-zinc-950 border border-zinc-800 font-mono text-xs">
      <div className="grid grid-cols-2 sticky top-0 z-10 bg-zinc-950 border-b border-zinc-800 text-zinc-500">
        <div className="px-2 py-1 border-r border-zinc-800 truncate">{beforeLabel}</div>
        <div className="px-2 py-1 truncate">{afterLabel}</div>
      </div>
      <div>
        {rows.map((row, index) => {
          if (row.kind === 'hunk') {
            return (
              <div
                key={`${index}-${row.oldText}`}
                className="px-2 py-0.5 text-cyan-400 bg-cyan-950/20 border-y border-cyan-900/30"
              >
                {row.oldText}
              </div>
            );
          }

          const oldClass =
            row.kind === 'remove' || row.kind === 'change'
              ? 'bg-red-950/30 text-red-300'
              : row.kind === 'add'
                ? 'text-zinc-700'
                : 'text-zinc-400';
          const newClass =
            row.kind === 'add' || row.kind === 'change'
              ? 'bg-emerald-950/30 text-emerald-300'
              : row.kind === 'remove'
                ? 'text-zinc-700'
                : 'text-zinc-400';

          return (
            <div key={`${index}-${row.oldText}-${row.newText}`} className="grid grid-cols-2">
              <pre
                className={cn(
                  'px-2 py-0.5 whitespace-pre-wrap break-words min-h-[1.25rem] border-r border-zinc-900',
                  oldClass
                )}
              >
                {row.oldText}
              </pre>
              <pre
                className={cn(
                  'px-2 py-0.5 whitespace-pre-wrap break-words min-h-[1.25rem]',
                  newClass
                )}
              >
                {row.newText}
              </pre>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [deciding, setDeciding] = useState<'approve' | 'deny' | null>(null);

  const status = STATUS_MARKERS[toolCall.status];
  const prefix = TOOL_PREFIXES[toolCall.tool_name] || toolCall.tool_name;
  const isRunning = toolCall.status === 'running';
  const isPython = toolCall.tool_name === 'python_execute';
  const hasResult =
    toolCall.result_summary && toolCall.result_summary.length > 0;
  const hasDiff =
    typeof toolCall.result_data === 'string' &&
    toolCall.result_data.startsWith('--- ') &&
    toolCall.result_data.includes('\n+++ ');
  const showExpandButton =
    hasResult && !isPython && toolCall.result_summary!.length > 150;

  const pythonOutput = isPython && hasResult ? toolCall.result_summary : undefined;
  const argStr = formatArguments(toolCall.tool_name, toolCall.arguments);
  const needsApproval = toolCall.status === 'pending' && toolCall.approval_required;

  const decide = async (decision: 'approve' | 'deny') => {
    setDeciding(decision);
    try {
      if (decision === 'approve') {
        await approveAgentToolCall(toolCall.run_id, toolCall.id);
      } else {
        await denyAgentToolCall(toolCall.run_id, toolCall.id);
      }
    } finally {
      setDeciding(null);
    }
  };

  return (
    <div className="font-mono text-xs space-y-1">
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
        <div className="ml-4 border border-amber-500/20 bg-amber-500/5 p-2 space-y-2">
          <div className="text-amber-300/80">
            approval required
            {toolCall.permission_level && (
              <span className="text-amber-500/50"> · {toolCall.permission_level}</span>
            )}
          </div>
          {typeof toolCall.diff_preview === 'string' && toolCall.diff_preview && (
            <DiffBlock diff={toolCall.diff_preview} />
          )}
          <div className="flex items-center gap-2">
            <button
              onClick={() => decide('approve')}
              disabled={deciding !== null}
              className="text-emerald-400 hover:text-emerald-300 disabled:text-zinc-600"
            >
              {deciding === 'approve' ? '[approving...]' : '[approve]'}
            </button>
            <button
              onClick={() => decide('deny')}
              disabled={deciding !== null}
              className="text-red-400 hover:text-red-300 disabled:text-zinc-600"
            >
              {deciding === 'deny' ? '[denying...]' : '[deny]'}
            </button>
          </div>
        </div>
      )}

      {/* Result (non-python) */}
      {hasResult && !isPython && (
        <div className="ml-4">
          <div
            className={cn(
              'text-zinc-400 whitespace-pre-wrap',
              !expanded && 'line-clamp-3'
            )}
          >
            {toolCall.result_summary}
          </div>
          {showExpandButton && (
            <button
              className="text-zinc-600 hover:text-zinc-400 mt-0.5"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? '[-less]' : '[+more]'}
            </button>
          )}
        </div>
      )}

      {/* Full write/edit diff after execution */}
      {hasDiff && (
        <div className="ml-4">
          <DiffBlock diff={toolCall.result_data!} />
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
