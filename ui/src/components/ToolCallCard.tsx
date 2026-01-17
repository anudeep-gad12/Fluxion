/**
 * Tool call visualization card.
 * Displays tool execution status, arguments, and results.
 */

import { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  Search,
  FileText,
  Code,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import type { AgentToolCall, AgentToolCallStatus } from '@/types/agent';

interface ToolCallCardProps {
  toolCall: AgentToolCall;
}

const TOOL_ICONS: Record<string, typeof Search> = {
  web_search: Search,
  web_extract: FileText,
  python_execute: Code,
};

const STATUS_CONFIG: Record<
  AgentToolCallStatus,
  {
    icon: typeof Loader2;
    color: string;
    bgColor: string;
    label: string;
  }
> = {
  pending: {
    icon: Clock,
    color: 'text-slate-500',
    bgColor: 'bg-slate-100',
    label: 'Pending',
  },
  running: {
    icon: Loader2,
    color: 'text-blue-500',
    bgColor: 'bg-blue-50',
    label: 'Running',
  },
  success: {
    icon: CheckCircle2,
    color: 'text-emerald-500',
    bgColor: 'bg-emerald-50',
    label: 'Success',
  },
  error: {
    icon: XCircle,
    color: 'text-red-500',
    bgColor: 'bg-red-50',
    label: 'Error',
  },
  timeout: {
    icon: Clock,
    color: 'text-amber-500',
    bgColor: 'bg-amber-50',
    label: 'Timeout',
  },
  interrupted: {
    icon: XCircle,
    color: 'text-slate-500',
    bgColor: 'bg-slate-50',
    label: 'Interrupted',
  },
};

function formatToolName(name: string): string {
  return name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatArguments(
  toolName: string,
  args: Record<string, unknown>
): string {
  // Pretty format for display (non-python tools)
  if (args.query) return `"${args.query}"`;
  if (args.url) return args.url as string;
  if (args.urls) return `${(args.urls as string[]).length} URLs`;
  // For python_execute, we render code separately
  if (toolName === 'python_execute') return '';
  return JSON.stringify(args);
}

function PythonCodeBlock({ code, output }: { code: string; output?: string }) {
  return (
    <div className="space-y-2">
      {/* Code Input */}
      <div className="bg-slate-900 rounded-md overflow-hidden">
        <div className="px-3 py-1.5 bg-slate-800 text-slate-400 text-xs font-medium border-b border-slate-700">
          Python Code
        </div>
        <pre className="p-3 text-xs text-slate-100 overflow-x-auto font-mono leading-relaxed">
          <code>{code}</code>
        </pre>
      </div>

      {/* Output */}
      {output && (
        <div className="bg-slate-800 rounded-md overflow-hidden">
          <div className="px-3 py-1.5 bg-slate-700 text-slate-300 text-xs font-medium border-b border-slate-600">
            Output
          </div>
          <pre className="p-3 text-xs text-emerald-300 overflow-x-auto font-mono leading-relaxed whitespace-pre-wrap">
            <code>{output}</code>
          </pre>
        </div>
      )}
    </div>
  );
}

export function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);

  const ToolIcon = TOOL_ICONS[toolCall.tool_name] || Code;
  const statusConfig = STATUS_CONFIG[toolCall.status];
  const StatusIcon = statusConfig.icon;

  const isRunning = toolCall.status === 'running';
  const isPython = toolCall.tool_name === 'python_execute';
  const hasResult =
    toolCall.result_summary && toolCall.result_summary.length > 0;
  const showExpandButton =
    hasResult && !isPython && toolCall.result_summary!.length > 150;

  // For python, extract output from result_summary if available
  const pythonOutput = isPython && hasResult ? toolCall.result_summary : undefined;

  return (
    <Card
      className={cn(
        'transition-all duration-200',
        statusConfig.bgColor,
        isRunning && 'animate-pulse'
      )}
    >
      <CardContent className="p-3">
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <ToolIcon className={cn('h-4 w-4', statusConfig.color)} />
            <span className="font-medium text-sm">
              {formatToolName(toolCall.tool_name)}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {toolCall.duration_ms && (
              <span className="text-xs text-slate-500">
                {toolCall.duration_ms}ms
              </span>
            )}
            <Badge
              variant="outline"
              className={cn('text-xs', statusConfig.color)}
            >
              <StatusIcon
                className={cn('h-3 w-3 mr-1', isRunning && 'animate-spin')}
              />
              {statusConfig.label}
            </Badge>
          </div>
        </div>

        {/* Python Code Block */}
        {isPython && typeof toolCall.arguments.code === 'string' && (
          <PythonCodeBlock
            code={toolCall.arguments.code}
            output={pythonOutput}
          />
        )}

        {/* Arguments (non-python tools) */}
        {!isPython && (
          <div className="text-xs text-slate-600 mb-2 font-mono bg-white/50 rounded px-2 py-1">
            {formatArguments(toolCall.tool_name, toolCall.arguments)}
          </div>
        )}

        {/* Result (non-python tools) */}
        {hasResult && !isPython && (
          <div className="mt-2">
            <div
              className={cn(
                'text-xs text-slate-700 bg-white/70 rounded p-2',
                !expanded && 'line-clamp-3'
              )}
            >
              {toolCall.result_summary}
            </div>
            {showExpandButton && (
              <Button
                variant="ghost"
                size="sm"
                className="mt-1 h-6 text-xs"
                onClick={() => setExpanded(!expanded)}
              >
                {expanded ? (
                  <>
                    <ChevronDown className="h-3 w-3 mr-1" />
                    Show less
                  </>
                ) : (
                  <>
                    <ChevronRight className="h-3 w-3 mr-1" />
                    Show more
                  </>
                )}
              </Button>
            )}
          </div>
        )}

        {/* Error */}
        {toolCall.error_message && (
          <div className="mt-2 text-xs text-red-600 bg-red-50 rounded p-2">
            {toolCall.error_message}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
