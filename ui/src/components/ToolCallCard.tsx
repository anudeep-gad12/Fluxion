/**
 * Tool call visualization — CLI command output style.
 * Displays tool execution as terminal command output.
 */

import { useState } from 'react';
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
};

function formatArguments(
  toolName: string,
  args: Record<string, unknown>
): string {
  if (args.query) return `"${args.query}"`;
  if (args.url) return args.url as string;
  if (args.urls) return `${(args.urls as string[]).length} URLs`;
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

export function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);

  const status = STATUS_MARKERS[toolCall.status];
  const prefix = TOOL_PREFIXES[toolCall.tool_name] || toolCall.tool_name;
  const isRunning = toolCall.status === 'running';
  const isPython = toolCall.tool_name === 'python_execute';
  const hasResult =
    toolCall.result_summary && toolCall.result_summary.length > 0;
  const showExpandButton =
    hasResult && !isPython && toolCall.result_summary!.length > 150;

  const pythonOutput = isPython && hasResult ? toolCall.result_summary : undefined;
  const argStr = formatArguments(toolCall.tool_name, toolCall.arguments);

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

      {/* Error */}
      {toolCall.error_message && (
        <div className="ml-4 text-zinc-500">
          err: {toolCall.error_message}
        </div>
      )}
    </div>
  );
}
