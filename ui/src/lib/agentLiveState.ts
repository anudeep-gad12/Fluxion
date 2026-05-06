import { useEffect, useMemo, useState } from 'react';
import type { AgentToolCall, AgentUIState } from '@/types/agent';

export type AgentLivePhase =
  | 'initializing'
  | 'running'
  | 'planning'
  | 'tool_calling'
  | 'synthesizing'
  | 'paused'
  | 'complete'
  | 'error'
  | 'cancelled';

interface AgentPhaseMeta {
  label: string;
  words: string[];
  animated: boolean;
  accentClassName: string;
  indicatorClassName: string;
  borderClassName: string;
  loaderGradientClassName: string;
  glowClassName: string;
  chipClassName: string;
}

export interface AgentHudDetail {
  summary: string;
  target?: string;
  toolName?: string;
}

export interface DerivedAgentPhase extends AgentPhaseMeta {
  phase: AgentLivePhase;
  detail: AgentHudDetail;
  isContextWarning: boolean;
  isCompactionWarning: boolean;
}

const PHASE_META: Record<AgentLivePhase, AgentPhaseMeta> = {
  initializing: {
    label: 'warming up',
    words: ['warming up', 'booting', 'spinning up', 'loading', 'waking', 'syncing'],
    animated: true,
    accentClassName: 'text-sky-300',
    indicatorClassName: 'bg-sky-400/90',
    borderClassName: 'border-sky-500/30',
    loaderGradientClassName: 'from-sky-500 via-cyan-300 to-sky-500',
    glowClassName: 'from-sky-500/12 via-cyan-400/6 to-transparent',
    chipClassName: 'border-sky-500/15 bg-sky-500/8 text-sky-100/90',
  },
  running: {
    label: 'agenting',
    words: ['agenting', 'working', 'routing', 'scanning', 'tracing', 'probing', 'exploring', 'threading', 'digging', 'moving'],
    animated: true,
    accentClassName: 'text-cyan-300',
    indicatorClassName: 'bg-cyan-400/90',
    borderClassName: 'border-cyan-500/30',
    loaderGradientClassName: 'from-cyan-500 via-sky-300 to-cyan-500',
    glowClassName: 'from-cyan-500/12 via-sky-400/6 to-transparent',
    chipClassName: 'border-cyan-500/15 bg-cyan-500/8 text-cyan-100/90',
  },
  planning: {
    label: 'llming',
    words: ['llming', 'thinking', 'mapping', 'reasoning', 'sketching', 'framing', 'parsing', 'lining up', 'modeling', 'shaping'],
    animated: true,
    accentClassName: 'text-sky-300',
    indicatorClassName: 'bg-sky-300/90',
    borderClassName: 'border-sky-500/30',
    loaderGradientClassName: 'from-sky-500 via-cyan-300 to-sky-500',
    glowClassName: 'from-sky-500/12 via-cyan-400/6 to-transparent',
    chipClassName: 'border-sky-500/15 bg-sky-500/8 text-sky-100/90',
  },
  tool_calling: {
    label: 'tooling',
    words: ['tooling', 'patching', 'probing', 'reading', 'grepping', 'checking', 'extracting', 'fetching', 'running', 'inspecting'],
    animated: true,
    accentClassName: 'text-amber-300',
    indicatorClassName: 'bg-amber-300/90',
    borderClassName: 'border-amber-500/30',
    loaderGradientClassName: 'from-amber-500 via-orange-300 to-amber-500',
    glowClassName: 'from-amber-500/12 via-orange-400/6 to-transparent',
    chipClassName: 'border-amber-500/15 bg-amber-500/8 text-amber-100/90',
  },
  synthesizing: {
    label: 'writing',
    words: ['writing', 'landing', 'wrapping', 'composing', 'assembling', 'weaving', 'closing', 'finishing', 'summarizing', 'delivering'],
    animated: true,
    accentClassName: 'text-emerald-300',
    indicatorClassName: 'bg-emerald-300/90',
    borderClassName: 'border-emerald-500/30',
    loaderGradientClassName: 'from-emerald-500 via-lime-300 to-emerald-500',
    glowClassName: 'from-emerald-500/12 via-lime-400/6 to-transparent',
    chipClassName: 'border-emerald-500/15 bg-emerald-500/8 text-emerald-100/90',
  },
  paused: {
    label: 'paused',
    words: ['paused'],
    animated: false,
    accentClassName: 'text-amber-300',
    indicatorClassName: 'bg-amber-300/90',
    borderClassName: 'border-amber-500/30',
    loaderGradientClassName: 'from-amber-500 via-orange-300 to-amber-500',
    glowClassName: 'from-amber-500/10 via-orange-400/4 to-transparent',
    chipClassName: 'border-amber-500/15 bg-amber-500/8 text-amber-100/90',
  },
  complete: {
    label: 'done',
    words: ['done'],
    animated: false,
    accentClassName: 'text-emerald-300',
    indicatorClassName: 'bg-emerald-400/90',
    borderClassName: 'border-emerald-500/30',
    loaderGradientClassName: 'from-emerald-500 via-lime-300 to-emerald-500',
    glowClassName: 'from-emerald-500/10 via-lime-400/4 to-transparent',
    chipClassName: 'border-emerald-500/15 bg-emerald-500/8 text-emerald-100/90',
  },
  error: {
    label: 'error',
    words: ['error'],
    animated: false,
    accentClassName: 'text-red-300',
    indicatorClassName: 'bg-red-400/90',
    borderClassName: 'border-red-500/30',
    loaderGradientClassName: 'from-red-500 via-red-300 to-red-500',
    glowClassName: 'from-red-500/10 via-red-400/4 to-transparent',
    chipClassName: 'border-red-500/15 bg-red-500/8 text-red-100/90',
  },
  cancelled: {
    label: 'cancelled',
    words: ['cancelled'],
    animated: false,
    accentClassName: 'text-zinc-300',
    indicatorClassName: 'bg-zinc-500/90',
    borderClassName: 'border-zinc-500/30',
    loaderGradientClassName: 'from-zinc-500 via-zinc-300 to-zinc-500',
    glowClassName: 'from-zinc-500/10 via-zinc-400/4 to-transparent',
    chipClassName: 'border-zinc-500/15 bg-zinc-500/8 text-zinc-100/90',
  },
};

const TOOL_VERBS: Record<string, string> = {
  read_file: 'reading',
  write_file: 'writing',
  edit_file: 'patching',
  glob: 'matching',
  grep: 'grepping',
  list_directory: 'listing',
  web_search: 'searching',
  web_extract: 'extracting',
  bash: 'running',
  bash_execute: 'running',
  python_execute: 'executing',
  python_local: 'executing',
  python_daytona: 'executing',
  view_image: 'inspecting',
};

function hashString(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}

function isString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function firstString(values: unknown[]): string | undefined {
  for (const value of values) {
    if (isString(value)) {
      return value.trim();
    }
    if (Array.isArray(value)) {
      const nested = firstString(value);
      if (nested) return nested;
    }
  }
  return undefined;
}

function prettifyToolName(toolName?: string): string | undefined {
  if (!toolName) return undefined;
  return toolName.replace(/_/g, ' ');
}

function compactWhitespace(value: string): string {
  return value.replace(/\s+/g, ' ').trim();
}

function truncateMiddle(value: string, maxLength: number): string {
  if (value.length <= maxLength) return value;
  const head = Math.max(8, Math.floor(maxLength * 0.55));
  const tail = Math.max(6, maxLength - head - 1);
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}

function truncateTail(value: string, maxLength: number): string {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, Math.max(0, maxLength - 1))}…`;
}

function shortenPath(value: string, maxLength = 42): string {
  const normalized = compactWhitespace(value);
  if (normalized.length <= maxLength) return normalized;
  const parts = normalized.split('/').filter(Boolean);
  if (parts.length >= 2) {
    const candidate = `…/${parts.slice(-2).join('/')}`;
    if (candidate.length <= maxLength) return candidate;
  }
  return truncateMiddle(normalized, maxLength);
}

function shortenQuery(value: string, maxLength = 44): string {
  return truncateTail(compactWhitespace(value), maxLength);
}

function shortenCommand(value: string, maxLength = 40): string {
  return truncateTail(compactWhitespace(value), maxLength);
}

function shortenUrl(value: string, maxLength = 42): string {
  try {
    const url = new URL(value);
    const path = url.pathname === '/' ? '' : url.pathname;
    return truncateTail(`${url.hostname}${path}`, maxLength);
  } catch {
    return truncateTail(compactWhitespace(value), maxLength);
  }
}

function extractToolTarget(toolCall: AgentToolCall): string | undefined {
  const args = toolCall.arguments || {};
  const pathLike = firstString([
    args.path,
    args.file_path,
    args.target_path,
    args.directory,
    args.root_path,
    args.pattern,
    args.image_path,
  ]);

  switch (toolCall.tool_name) {
    case 'read_file':
    case 'write_file':
    case 'edit_file':
    case 'glob':
    case 'grep':
    case 'list_directory':
    case 'view_image':
      return pathLike ? shortenPath(pathLike) : undefined;
    case 'web_search': {
      const query = firstString([args.query, args.q]);
      return query ? `“${shortenQuery(query)}”` : undefined;
    }
    case 'web_extract': {
      const url = firstString([args.url, args.urls]);
      return url ? shortenUrl(url) : undefined;
    }
    case 'bash':
    case 'bash_execute': {
      const command = firstString([args.command, args.cmd]);
      return command ? shortenCommand(command) : undefined;
    }
    case 'python_execute':
    case 'python_local':
    case 'python_daytona': {
      const code = firstString([args.code]);
      return code ? shortenCommand(code) : undefined;
    }
    default:
      return pathLike ? shortenPath(pathLike) : undefined;
  }
}

function findActiveToolCall(agentState: AgentUIState): AgentToolCall | undefined {
  const currentStepId = `step-${agentState.currentStep}`;
  const liveCalls = agentState.toolCalls.filter(
    (toolCall) =>
      (toolCall.status === 'running' || toolCall.status === 'pending')
      && (toolCall.step_id === currentStepId || agentState.currentStep === 0)
  );

  if (liveCalls.length > 0) {
    return liveCalls[liveCalls.length - 1];
  }

  for (let index = agentState.toolCalls.length - 1; index >= 0; index -= 1) {
    const toolCall = agentState.toolCalls[index];
    if (toolCall.status === 'running' || toolCall.status === 'pending') {
      return toolCall;
    }
  }
  return undefined;
}

function deriveAgentDetail(agentState: AgentUIState, phase: AgentLivePhase): AgentHudDetail {
  const activeToolCall = findActiveToolCall(agentState);
  if (activeToolCall) {
    const target = extractToolTarget(activeToolCall);
    return {
      summary: TOOL_VERBS[activeToolCall.tool_name] || prettifyToolName(activeToolCall.tool_name) || 'working',
      target,
      toolName: prettifyToolName(activeToolCall.tool_name),
    };
  }

  switch (phase) {
    case 'synthesizing':
      return { summary: 'assembling response' };
    case 'planning':
      return { summary: `reasoning through step ${Math.max(agentState.currentStep, 1)}` };
    case 'running':
      return { summary: `moving through step ${Math.max(agentState.currentStep, 1)}` };
    case 'paused':
      return { summary: 'waiting for resume' };
    case 'error':
      return { summary: 'run failed before completion' };
    case 'cancelled':
      return { summary: 'run cancelled by user' };
    case 'complete':
      return { summary: 'response delivered' };
    default:
      return { summary: 'preparing run state' };
  }
}

export function deriveAgentPhase(agentState: AgentUIState): DerivedAgentPhase {
  let phase: AgentLivePhase;

  if (!agentState.isActive && agentState.agentState === 'complete') {
    phase = 'complete';
  } else if (!agentState.isActive && agentState.agentState === 'error') {
    phase = 'error';
  } else if (!agentState.isActive && agentState.agentState === 'cancelled') {
    phase = 'cancelled';
  } else if (agentState.agentState === 'paused') {
    phase = 'paused';
  } else if (agentState.answerBuffer) {
    phase = 'synthesizing';
  } else if (agentState.toolCalls.some((toolCall) => toolCall.status === 'running' || toolCall.status === 'pending')) {
    phase = 'tool_calling';
  } else if (agentState.thinkingBuffer) {
    phase = 'planning';
  } else if (agentState.isActive) {
    phase = 'running';
  } else {
    phase = 'initializing';
  }

  const contextUtilization = agentState.context_usage?.utilization_pct_effective ?? 0;
  const compactionCount = (agentState.compaction_count ?? agentState.context_usage?.compactions_so_far) ?? 0;

  return {
    phase,
    detail: deriveAgentDetail(agentState, phase),
    isContextWarning: contextUtilization >= 80,
    isCompactionWarning: compactionCount >= 2,
    ...PHASE_META[phase],
  };
}

export function useDerivedAgentPhase(agentState: AgentUIState, runId: string): DerivedAgentPhase & { activeWord: string } {
  const phase = useMemo(() => deriveAgentPhase(agentState), [agentState]);
  const rotationSeed = `${runId}:${phase.phase}:${agentState.currentStep}:${agentState.toolCalls.length}:${agentState.answerBuffer ? 1 : 0}`;
  const [wordIndex, setWordIndex] = useState(0);

  useEffect(() => {
    const seededIndex = phase.words.length > 0 ? hashString(rotationSeed) % phase.words.length : 0;
    setWordIndex(seededIndex);
  }, [phase.words, rotationSeed]);

  useEffect(() => {
    if (!agentState.isActive || !phase.animated || phase.words.length <= 1) {
      return;
    }
    const interval = window.setInterval(() => {
      setWordIndex((current) => (current + 1) % phase.words.length);
    }, 1400);
    return () => window.clearInterval(interval);
  }, [agentState.isActive, phase.animated, phase.words]);

  return {
    ...phase,
    activeWord: phase.words[wordIndex] || phase.label,
  };
}

export function formatAgentDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainingSeconds}s`;
}

export function formatAgentCost(cost: number): string {
  if (cost === 0) return '$0';
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

export function formatAgentTokens(tokens: number): string {
  return tokens.toLocaleString();
}
