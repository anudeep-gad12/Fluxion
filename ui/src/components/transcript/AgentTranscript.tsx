/**
 * Flat Claude-Code-style agent transcript.
 * Replaces the AgentStepsPanel timeline (spine/dots/badges) with marker lines.
 * Step grouping logic is preserved exactly — historical runs must render the same.
 */

import { useMemo, useState } from 'react';
import { AnswerMarkdown } from '@/components/AnswerMarkdown';
import { BrailleSpinner } from '@/components/transcript/BrailleSpinner';
import { ToolCallLine } from '@/components/transcript/ToolCallLine';
import { MarkerLine } from '@/components/transcript/TranscriptLine';
import { sanitizeThinking } from '@/lib/utils';
import type { AgentToolCall, AgentUIState } from '@/types/agent';

function ThinkingLine({
  content,
  isLive,
  expanded,
  onToggle,
}: {
  content: string;
  isLive: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="tr-item">
      <button type="button" className="tr-thinking-toggle" onClick={onToggle}>
        <span className="tr-marker" data-tone={isLive ? 'running' : 'pending'} aria-hidden>
          ⏺
        </span>
        <span className="tr-thinking-label">Thinking…</span>
      </button>
      {expanded && (
        <div className="tr-thinking-content">
          <AnswerMarkdown content={content} />
          {isLive && (
            <span className="agent-caret ml-1" />
          )}
        </div>
      )}
    </div>
  );
}

function WaitingLine() {
  return (
    <MarkerLine marker={<BrailleSpinner />} tone="default">
      <span className="tr-thinking-label">Waiting for the first trace…</span>
    </MarkerLine>
  );
}

interface AgentTranscriptProps {
  agentState: AgentUIState;
}

export function AgentTranscript({ agentState }: AgentTranscriptProps) {
  const {
    steps,
    toolCalls,
    thinkingBuffer,
    currentStep,
    isActive,
    injectedSteers,
    systemEvents = [],
    assistantUpdates = [],
  } = agentState;
  const [expandedThinking, setExpandedThinking] = useState<Record<number, boolean>>({});

  const stepIdToNumber: Record<string, number> = {};
  steps.forEach((step) => {
    stepIdToNumber[step.id] = step.step_number;
    stepIdToNumber[`step-${step.step_number}`] = step.step_number;
  });

  const toolCallsByStep = toolCalls.reduce(
    (acc, toolCall) => {
      const stepNum = stepIdToNumber[toolCall.step_id] ?? currentStep;
      if (!acc[stepNum]) acc[stepNum] = [];
      acc[stepNum].push(toolCall);
      return acc;
    },
    {} as Record<number, AgentToolCall[]>
  );

  const assistantUpdatesByStep = assistantUpdates.reduce(
    (acc, update) => {
      const stepNum = update.step_number ?? currentStep;
      if (!acc[stepNum]) acc[stepNum] = [];
      acc[stepNum].push(update);
      return acc;
    },
    {} as Record<number, typeof assistantUpdates>
  );

  const thinkingContentByStep = useMemo(() => {
    const map: Record<number, { content: string; isLive: boolean }> = {};
    for (const step of steps) {
      const historicalThinking = sanitizeThinking(step.thinking_text || '').trim();
      if (historicalThinking) {
        map[step.step_number] = { content: historicalThinking, isLive: false };
      }
    }
    const liveThinking = sanitizeThinking(thinkingBuffer).trim();
    if (isActive && currentStep > 0 && liveThinking) {
      map[currentStep] = { content: liveThinking, isLive: true };
    }
    return map;
  }, [steps, thinkingBuffer, isActive, currentStep]);

  if (steps.length === 0 && systemEvents.length === 0) {
    return null;
  }

  return (
    <div className="tr-stream mb-5">
      {systemEvents.map((event, index) => (
        <MarkerLine key={`system-${event.seq ?? index}`} tone="system">
          {event.message}
        </MarkerLine>
      ))}

      {steps.map((step) => {
        const isCurrentStep = step.step_number === currentStep;
        const stepToolCalls = toolCallsByStep[step.step_number] || [];
        const stepAssistantUpdates = assistantUpdatesByStep[step.step_number] || [];
        const thinkingEntry = thinkingContentByStep[step.step_number];
        const stepSteers = injectedSteers.filter((steer) => steer.step_number === step.step_number);
        const itemsCount = stepSteers.length + stepAssistantUpdates.length + (thinkingEntry ? 1 : 0) + stepToolCalls.length;

        return (
          <div key={step.id} className="tr-step">
            {stepSteers.map((steer, index) => (
              <MarkerLine key={`steer-${step.step_number}-${index}`} marker=">" tone="steer">
                {steer.content}
              </MarkerLine>
            ))}

            {thinkingEntry && (
              <ThinkingLine
                content={thinkingEntry.content}
                isLive={thinkingEntry.isLive}
                expanded={!!expandedThinking[step.step_number]}
                onToggle={() =>
                  setExpandedThinking((current) => ({
                    ...current,
                    [step.step_number]: !current[step.step_number],
                  }))
                }
              />
            )}

            {stepAssistantUpdates.map((update, index) => (
              <MarkerLine key={`assistant-update-${step.step_number}-${update.seq ?? index}`}>
                {update.content}
              </MarkerLine>
            ))}

            {stepToolCalls.map((toolCall) => (
              <ToolCallLine key={toolCall.id} toolCall={toolCall} />
            ))}

            {itemsCount === 0 && isCurrentStep && isActive && <WaitingLine />}
          </div>
        );
      })}

      {steps.length === 0 && isActive && <WaitingLine />}
    </div>
  );
}
