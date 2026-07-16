import { ref } from "vue";

export type ToastTone = "success" | "error" | "info";

export interface ToastMessage {
  id: number;
  tone: ToastTone;
  text: string;
}

const toasts = ref<ToastMessage[]>([]);
let toastId = 0;

function dismissToast(id: number) {
  toasts.value = toasts.value.filter((toast) => toast.id !== id);
}

function showToast(text: string, tone: ToastTone = "info") {
  const id = ++toastId;
  toasts.value = [...toasts.value, { id, tone, text }].slice(-4);
  window.setTimeout(() => dismissToast(id), 4200);
}

export function useToasts() {
  return {
    toasts,
    showToast,
    dismissToast,
  };
}
