import { ChevronDown, SlidersHorizontal, Terminal } from 'lucide-react';
import type { ModelStatus } from '@/api/client';
import { Tooltip } from '@/components/ui/tooltip';

interface DesktopComposerControlsProps {
  modelStatus: ModelStatus | null;
  onModelClick: () => void;
  onSettingsClick: () => void;
  showTerminal: boolean;
  terminalOpen: boolean;
  onTerminalClick: () => void;
}

function formatProviderLabel(provider: string | undefined): string | null {
  if (!provider) return null;
  if (provider === 'local') return 'Local';
  return provider.charAt(0).toUpperCase() + provider.slice(1);
}

/** Minimal footer inside the card: model + a gear + terminal (Cursor-style). */
export function DesktopComposerControls({
  modelStatus,
  onModelClick,
  onSettingsClick,
  showTerminal,
  terminalOpen,
  onTerminalClick,
}: DesktopComposerControlsProps) {
  const modelLabel =
    modelStatus?.model_name?.split('/').pop() || modelStatus?.model_name || 'Model';
  const providerLabel = formatProviderLabel(modelStatus?.provider);

  return (
    <div className="desktop-composer-controls">
      <Tooltip
        content={modelStatus?.model_name ? `Model: ${modelStatus.model_name}` : 'Switch model'}
      >
        <button type="button" onClick={onModelClick} className="desktop-model-trigger">
          <span className="desktop-model-trigger-name">{modelLabel}</span>
          {providerLabel ? (
            <span className="desktop-model-trigger-provider">{providerLabel}</span>
          ) : null}
          <ChevronDown className="desktop-model-trigger-chevron" aria-hidden />
        </button>
      </Tooltip>

      <div className="desktop-composer-control-icons">
        <Tooltip content="Run settings">
          <button
            type="button"
            onClick={onSettingsClick}
            className="desktop-icon-btn shrink-0"
            aria-label="Run settings"
          >
            <SlidersHorizontal className="h-3.5 w-3.5" />
          </button>
        </Tooltip>

        {showTerminal ? (
          <Tooltip content="Terminal panel">
            <button
              type="button"
              onClick={onTerminalClick}
              data-active={terminalOpen ? 'true' : 'false'}
              className="desktop-icon-btn shrink-0"
              aria-label="Terminal panel"
              aria-pressed={terminalOpen}
            >
              <Terminal className="h-3.5 w-3.5" />
            </button>
          </Tooltip>
        ) : null}
      </div>
    </div>
  );
}
