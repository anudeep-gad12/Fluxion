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
  read_file: 'read',
  list_directory: 'list',
  write_file: 'write',
  edit_file: 'edit',
  grep: 'grep',
  glob: 'glob',
  exec_command: 'exec',
  write_stdin: 'stdin',
  list_run_artifacts: 'artifacts',
  read_artifact: 'artifact',
};

const COMMAND_TOOL_NAMES = new Set(['exec_command', 'write_stdin']);

function normalizeToolArguments(
  rawArgs: Record<string, unknown> | string | null | undefined,
): Record<string, unknown> {
  if (!rawArgs) return {};
  if (typeof rawArgs === 'string') {
    try {
      const parsed = JSON.parse(rawArgs) as unknown;
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      return {};
    }
    return {};
  }
  return rawArgs;
}

function formatCommandArgument(args: Record<string, unknown>): string {
  const command = args.cmd ?? args.command;
  return typeof command === 'string' ? command : '';
}

function formatBytes(bytes: number | undefined): string {
  if (typeof bytes !== 'number' || !Number.isFinite(bytes)) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatArguments(
  toolName: string,
  rawArgs: Record<string, unknown> | string | null | undefined,
): string {
  const args = normalizeToolArguments(rawArgs);

  if (toolName === 'write_stdin') {
    if (typeof args.chars === 'string' && args.chars.trim()) {
      return args.chars;
    }
    if (typeof args.text === 'string' && args.text.trim()) {
      return args.text;
    }
    if (
      (typeof args.session_id === 'string' && args.session_id.trim()) ||
      typeof args.session_id === 'number'
    ) {
      return `session ${String(args.session_id)}`;
    }
    return '';
  }

  if (COMMAND_TOOL_NAMES.has(toolName)) {
    return formatCommandArgument(args);
  }

  if (args.query) return `"${args.query}"`;
  if (args.url) return args.url as string;
  if (args.urls) return `${(args.urls as string[]).length} URLs`;
  if (args.file_path) return args.file_path as string;
  if (args.path) return args.path as string;
  if (args.pattern) return args.pattern as string;
  if (typeof args.cmd === 'string') return args.cmd;
  if (typeof args.command === 'string') return args.command;
  return JSON.stringify(args);
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

function ArtifactRefs({
  artifacts,
  runId,
}: {
  artifacts: NonNullable<AgentToolCall['artifacts']>;
  runId: string;
}) {
  if (artifacts.length === 0) return null;
  return (
    <div className="ml-4 space-y-1 border-l border-sky-500/20 pl-3">
      <div className="text-[10px] uppercase tracking-wide text-sky-400/60">artifacts</div>
      {artifacts.map((artifact, index) => {
        const path = artifact.artifact_path || artifact.file_path || 'artifact';
        const size = formatBytes(artifact.byte_count);
        const href = artifact.artifact_path
          ? [
              `/api/agent/runs/${encodeURIComponent(runId)}/artifacts/read`,
              `artifact_path=${encodeURIComponent(artifact.artifact_path)}`,
            ].join('?')
          : null;
        return (
          <div
            key={`${path}-${index}`}
            className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-zinc-500"
          >
            {href ? (
              <a
                href={href}
                target="_blank"
                rel="noreferrer"
                className="text-zinc-300 break-all underline decoration-zinc-700 underline-offset-2 hover:text-sky-300"
              >
                {path}
              </a>
            ) : (
              <span className="text-zinc-300 break-all">{path}</span>
            )}
            {artifact.artifact_type && <span>{artifact.artifact_type}</span>}
            {size && <span>{size}</span>}
          </div>
        );
      })}
    </div>
  );
}

export function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const status = STATUS_MARKERS[toolCall.status];
  const prefix = TOOL_PREFIXES[toolCall.tool_name] || toolCall.tool_name;
  const isRunning = toolCall.status === 'running';
  const isCommandTool = COMMAND_TOOL_NAMES.has(toolCall.tool_name);
  const hasResult =
    toolCall.result_summary && toolCall.result_summary.length > 0;
  const unifiedDiff = resolveUnifiedDiff(toolCall);

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

      {/* Result */}
      {hasResult && (
        <div className="ml-4">
          <div className="text-zinc-400 whitespace-pre-wrap">
            {toolCall.result_summary}
          </div>
        </div>
      )}

      {isCommandTool && toolCall.bash_output && <BashOutputBlock output={toolCall.bash_output} />}

      {toolCall.artifacts && toolCall.artifacts.length > 0 && (
        <ArtifactRefs artifacts={toolCall.artifacts} runId={toolCall.run_id} />
      )}

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
