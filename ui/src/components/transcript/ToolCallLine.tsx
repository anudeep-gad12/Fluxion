/**
 * Tool call as a Claude-Code-style transcript line:
 *   ⏺ read(orchestrator/app.py) (2.1s)
 *     ⎿ Read 412 lines
 */

import { ImagePreviewStrip } from '@/components/ImagePreviewStrip';
import {
  COMMAND_TOOL_NAMES,
  TOOL_PREFIXES,
  formatArguments,
  formatBytes,
  resolveUnifiedDiff,
  toolCategory,
  UnifiedDiffView,
} from '@/components/transcript/toolFormat';
import {
  ClampedText,
  MarkerLine,
  ResultBlock,
  type MarkerTone,
} from '@/components/transcript/TranscriptLine';
import type { AgentToolCall, AgentToolCallStatus } from '@/types/agent';

const STATUS_TONES: Record<AgentToolCallStatus, MarkerTone> = {
  pending: 'pending',
  running: 'running',
  success: 'success',
  error: 'error',
  timeout: 'error',
  interrupted: 'pending',
};

function formatDuration(durationMs: number): string {
  if (durationMs < 1000) return `${durationMs}ms`;
  return `${(durationMs / 1000).toFixed(1)}s`;
}

export function ToolCallLine({ toolCall }: { toolCall: AgentToolCall }) {
  const tone = STATUS_TONES[toolCall.status];
  const prefix = TOOL_PREFIXES[toolCall.tool_name] || toolCall.tool_name;
  const isCommandTool = COMMAND_TOOL_NAMES.has(toolCall.tool_name);
  const argStr = formatArguments(toolCall.tool_name, toolCall.arguments);
  const needsApproval = toolCall.status === 'pending' && toolCall.approval_required;
  const hasResult = !!toolCall.result_summary && toolCall.result_summary.length > 0;
  const unifiedDiff = resolveUnifiedDiff(toolCall);
  const bashOutput = isCommandTool ? toolCall.bash_output : undefined;
  const hasStdout = !!bashOutput && bashOutput.stdout.trim().length > 0;
  const hasStderr = !!bashOutput && bashOutput.stderr.trim().length > 0;
  const emptyCommandOutput =
    !!bashOutput && !hasStdout && !hasStderr && toolCall.status === 'success';

  return (
    <div className="tr-item" data-tool={toolCategory(toolCall.tool_name)}>
      <MarkerLine tone={tone} mono>
        <span className="tr-tool-name">{prefix}</span>
        {argStr && <span className="tr-tool-args">({argStr})</span>}
        {toolCall.duration_ms ? (
          <span className="tr-tool-meta"> ({formatDuration(toolCall.duration_ms)})</span>
        ) : null}
      </MarkerLine>

      {needsApproval && (
        <ResultBlock>
          <span className="tr-warning">
            approval required
            {toolCall.permission_level ? ` · ${toolCall.permission_level}` : ''}
          </span>
        </ResultBlock>
      )}

      {hasResult && (
        <ResultBlock>
          <ClampedText text={toolCall.result_summary!} maxLines={3} />
        </ResultBlock>
      )}

      {bashOutput && (
        <>
          {typeof bashOutput.exit_code === 'number' && bashOutput.exit_code !== 0 && (
            <ResultBlock>
              <span className="tr-danger">exit {bashOutput.exit_code}</span>
              {bashOutput.truncated ? <span className="tr-warning"> · truncated</span> : null}
            </ResultBlock>
          )}
          {emptyCommandOutput && !hasResult && (
            <ResultBlock>(no output)</ResultBlock>
          )}
          {hasStdout && (
            <ResultBlock>
              <ClampedText text={bashOutput.stdout} maxLines={3} />
            </ResultBlock>
          )}
          {hasStderr && (
            <ResultBlock className="tr-danger">
              <ClampedText text={bashOutput.stderr} maxLines={3} className="tr-danger" />
            </ResultBlock>
          )}
        </>
      )}

      {toolCall.artifacts && toolCall.artifacts.length > 0 && (
        <ResultBlock>
          <div className="space-y-0.5">
            {toolCall.artifacts.map((artifact, index) => {
              const path = artifact.artifact_path || artifact.file_path || 'artifact';
              const size = formatBytes(artifact.byte_count);
              const href = artifact.artifact_path
                ? [
                    `/api/agent/runs/${encodeURIComponent(toolCall.run_id)}/artifacts/read`,
                    `artifact_path=${encodeURIComponent(artifact.artifact_path)}`,
                  ].join('?')
                : null;
              return (
                <div key={`${path}-${index}`} className="min-w-0">
                  {href ? (
                    <a
                      href={href}
                      target="_blank"
                      rel="noreferrer"
                      className="break-all underline underline-offset-2 hover:text-[var(--desktop-text-secondary)]"
                    >
                      {path}
                    </a>
                  ) : (
                    <span className="break-all">{path}</span>
                  )}
                  {artifact.artifact_type ? ` · ${artifact.artifact_type}` : ''}
                  {size ? ` · ${size}` : ''}
                </div>
              );
            })}
          </div>
        </ResultBlock>
      )}

      {toolCall.images && toolCall.images.length > 0 && (
        <ResultBlock>
          <ImagePreviewStrip images={toolCall.images} thumbnailClassName="h-16 w-16" />
        </ResultBlock>
      )}

      {unifiedDiff && (
        <ResultBlock>
          <UnifiedDiffView diff={unifiedDiff} />
        </ResultBlock>
      )}

      {toolCall.error_message && (
        <ResultBlock className="tr-danger">
          <ClampedText text={toolCall.error_message} maxLines={3} className="tr-danger" />
        </ResultBlock>
      )}
    </div>
  );
}
