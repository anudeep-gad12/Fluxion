/**
 * Tool call formatting helpers + flat unified diff view.
 * Moved from ToolCallCard when the transcript went Claude-Code style.
 */

import { useState } from 'react';
import { cn } from '@/lib/utils';
import type { AgentToolCall } from '@/types/agent';

export const TOOL_PREFIXES: Record<string, string> = {
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

export const COMMAND_TOOL_NAMES = new Set(['exec_command', 'write_stdin']);

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

export function formatBytes(bytes: number | undefined): string {
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

type DiffLine = {
  kind: 'context' | 'add' | 'remove' | 'hunk';
  text: string;
};

function parseUnifiedDiffLines(diff: string): DiffLine[] {
  const lines = diff.split('\n');
  const result: DiffLine[] = [];

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line && index === lines.length - 1) continue;
    if (line.startsWith('--- ') || line.startsWith('+++ ')) continue;

    if (line.startsWith('@@')) {
      result.push({ kind: 'hunk', text: line });
      continue;
    }
    if (line.startsWith('-')) {
      result.push({ kind: 'remove', text: line.slice(1) || ' ' });
      continue;
    }
    if (line.startsWith('+')) {
      result.push({ kind: 'add', text: line.slice(1) || ' ' });
      continue;
    }
    const text = line.startsWith(' ') ? line.slice(1) : line;
    result.push({ kind: 'context', text: text || ' ' });
  }

  return result;
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

/** Flat single-column unified diff, clamped with an `… +N lines` expander. */
export function UnifiedDiffView({
  diff,
  compact = false,
}: {
  diff: string;
  compact?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const lines = parseUnifiedDiffLines(diff);
  const maxRows = compact ? 8 : 12;
  const overflow = lines.length - maxRows;
  const clamped = overflow > 0 && !expanded;
  const visible = clamped ? lines.slice(0, maxRows) : lines;

  return (
    <div className="tr-diff">
      {visible.map((line, index) => {
        if (line.kind === 'hunk') {
          return (
            <div key={`${index}-hunk`} className="tr-diff-hunk">
              {line.text}
            </div>
          );
        }
        const prefix = line.kind === 'add' ? '+' : line.kind === 'remove' ? '-' : ' ';
        return (
          <pre
            key={`${index}-${line.kind}`}
            className={cn(
              'tr-diff-line',
              line.kind === 'add' && 'tr-diff-add',
              line.kind === 'remove' && 'tr-diff-remove',
            )}
          >
            {prefix} {line.text}
          </pre>
        );
      })}
      {overflow > 0 && (
        <button
          type="button"
          className="tr-more"
          onClick={() => setExpanded((current) => !current)}
        >
          {clamped ? `… +${overflow} lines` : 'collapse'}
        </button>
      )}
    </div>
  );
}
