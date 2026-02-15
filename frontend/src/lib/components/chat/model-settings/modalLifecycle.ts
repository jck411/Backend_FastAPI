interface ModalVisibilityOptions {
  open: boolean;
  wasOpen: boolean;
  onOpened: () => void;
  onClosed: () => void;
}

export function applyModalVisibility({
  open,
  wasOpen,
  onOpened,
  onClosed,
}: ModalVisibilityOptions): boolean {
  if (open && !wasOpen) {
    onOpened();
    return true;
  }

  if (!open && wasOpen) {
    onClosed();
    return false;
  }

  return wasOpen;
}

interface CloseModalWithFlushOptions {
  closing: boolean;
  saving: boolean;
  setClosing: (value: boolean) => void;
  flushSave: () => Promise<boolean>;
  onClosed: () => void;
}

export async function closeModalWithFlush({
  closing,
  saving,
  setClosing,
  flushSave,
  onClosed,
}: CloseModalWithFlushOptions): Promise<void> {
  if (closing || saving) {
    return;
  }

  setClosing(true);
  try {
    const success = await flushSave();
    if (success) {
      onClosed();
    }
  } finally {
    setClosing(false);
  }
}
