'use client';

import { useEffect, useRef } from 'react';
import { InsightPanel } from '@/components/panels/InsightPanel';
import type { ChatMessage } from '@/types/chat';

type PanelTab = 'sources' | 'debug';

function isBelowXl() {
  return typeof window !== 'undefined' && window.matchMedia('(max-width: 1279px)').matches;
}

export function EvidencePanelShell({
  open,
  onClose,
  panelTab,
  onTabChange,
  debugMode,
  onToggleDebugMode,
  message,
  question,
  panelToggleRef,
}: {
  open: boolean;
  onClose: () => void;
  panelTab: PanelTab;
  onTabChange: (tab: PanelTab) => void;
  debugMode: boolean;
  onToggleDebugMode: (enabled: boolean) => void;
  message: ChatMessage | null;
  question: string | null;
  panelToggleRef: React.RefObject<HTMLButtonElement>;
}) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open || !isBelowXl()) {
      return;
    }

    closeButtonRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose();
        if (isBelowXl()) {
          panelToggleRef.current?.focus();
        }
      }
    }

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose, panelToggleRef]);

  useEffect(() => {
    if (!open || !isBelowXl()) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  if (!open) {
    return null;
  }

  return (
    <>
      <button
        type="button"
        aria-label="Close evidence panel"
        data-testid="evidence-panel-backdrop"
        onClick={onClose}
        className="fixed inset-0 z-40 bg-black/60 xl:hidden"
      />

      <div
        data-testid="evidence-panel-shell"
        className="fixed inset-y-0 right-0 z-50 flex w-[min(100%,28rem)] flex-col shadow-[-10px_0_32px_rgba(0,0,0,0.45)] sm:w-[min(100%,32rem)] md:w-[min(100%,36rem)] xl:static xl:z-auto xl:h-full xl:w-[380px] xl:max-w-none xl:shrink-0 xl:shadow-none"
      >
        <InsightPanel
          panelId="evidence-panel"
          panelLabel="Evidence and debug panel"
          panelTab={panelTab}
          onTabChange={onTabChange}
          debugMode={debugMode}
          onToggleDebugMode={onToggleDebugMode}
          message={message}
          question={question}
          onClose={onClose}
          closeButtonRef={closeButtonRef}
          className="h-full min-h-0"
        />
      </div>
    </>
  );
}
