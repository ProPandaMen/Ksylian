<script setup lang="ts">
import { X } from "@lucide/vue";
import { useToasts } from "../composables/useToasts";

const { toasts, dismissToast } = useToasts();
</script>

<template>
  <div class="toast-stack" aria-live="polite" aria-label="Уведомления">
    <article v-for="toast in toasts" :key="toast.id" class="toast-card" :class="toast.tone">
      <span class="toast-dot"></span>
      <p>{{ toast.text }}</p>
      <button class="toast-close" type="button" title="Закрыть" @click="dismissToast(toast.id)">
        <X :size="16" />
      </button>
    </article>
  </div>
</template>
