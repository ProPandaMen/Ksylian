<script setup lang="ts">
import { LogOut } from "@lucide/vue";
import type { Component } from "vue";
import catLogo from "../assets/cat-logo.svg";
import type { AuthUser, TabId } from "../types";

defineProps<{
  activeTab: TabId;
  navItems: Array<{ id: TabId; label: string; icon: Component; disabled?: boolean }>;
  user: AuthUser | null;
}>();

const emit = defineEmits<{
  select: [tabId: TabId];
  logout: [];
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

    <div class="sidebar-footer">
      <section v-if="user" class="sidebar-user-card" aria-label="Профиль пользователя">
        <div>
          <strong>{{ user.display_name }}</strong>
          <span>{{ user.role === 'admin' ? 'Администратор' : 'Пользователь' }}</span>
        </div>
        <button class="icon-button" type="button" title="Выйти" @click="emit('logout')">
          <LogOut :size="17" />
        </button>
      </section>
    </div>
  </aside>
</template>
