<script setup lang="ts">
import type { Component } from "vue";
import catLogo from "../assets/cat-logo.svg";
import catMascot from "../assets/ksylian-cat.png";
import type { TabId } from "../types";

defineProps<{
  activeTab: TabId;
  navItems: Array<{ id: TabId; label: string; icon: Component; disabled?: boolean }>;
}>();

const emit = defineEmits<{
  select: [tabId: TabId];
}>();
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-mark">
        <img :src="catLogo" alt="" />
      </div>
      <div>
        <strong>Ksylian</strong>
        <span>server panel</span>
      </div>
    </div>

    <nav class="nav-list" aria-label="Основная навигация">
      <button
        v-for="item in navItems"
        :key="item.label"
        class="nav-item"
        :class="{ active: activeTab === item.id, disabled: item.disabled }"
        type="button"
        :disabled="item.disabled"
        :title="item.disabled ? 'Ждем доступ к CurseForge API' : item.label"
        @click="emit('select', item.id)"
      >
        <component :is="item.icon" :size="18" />
        <span>{{ item.label }}</span>
      </button>
    </nav>

    <section class="mascot-card">
      <img :src="catMascot" alt="Розовый кот-талисман Ksylian" />
      <div>
        <strong>Ксю-контроль</strong>
        <span>3 мира под присмотром</span>
      </div>
    </section>
  </aside>
</template>
