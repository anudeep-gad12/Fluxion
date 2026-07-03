import { useEffect, useRef } from 'react';

import { openNativeWorkspacePicker } from '@/lib/platform';

/**
 * Headless bridge to the native macOS folder picker: when `open` flips true
 * the native dialog opens, the selection (if any) is passed to `onSelect`,
 * and `open` is reset. Renders nothing.
 */
export function WorkspacePickerDialog({
  open,
  onOpenChange,
  onSelect,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (path: string) => void;
}) {
  const onSelectRef = useRef(onSelect);
  const onOpenChangeRef = useRef(onOpenChange);

  useEffect(() => {
    onSelectRef.current = onSelect;
    onOpenChangeRef.current = onOpenChange;
  }, [onOpenChange, onSelect]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void openNativeWorkspacePicker().then((selectedPath) => {
      if (cancelled) return;
      if (selectedPath) {
        onSelectRef.current(selectedPath);
      }
      onOpenChangeRef.current(false);
    });
    return () => {
      cancelled = true;
    };
  }, [open]);

  return null;
}
