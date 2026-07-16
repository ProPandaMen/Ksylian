<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import { RefreshCw } from "@lucide/vue";
import AppSidebar from "./components/AppSidebar.vue";
import ToastStack from "./components/ToastStack.vue";
import { themes, useAuthStore } from "./composables/useAuthStore";
import { useDashboardStore } from "./composables/useDashboardStore";
import { navItems, routePaths, tabCopy } from "./navigation";
import type { TabId, ThemeName } from "./types";

const route = useRoute();
const router = useRouter();
const store = useDashboardStore();
const auth = useAuthStore();

const appVersionLabel = __APP_VERSION__.startsWith("v") || __APP_VERSION__ === "dev"
  ? __APP_VERSION__
  : `v${__APP_VERSION__}`;
const buildLabel = `${appVersionLabel} · ${__BUILD_SHA__}`;

const activeTab = computed<TabId>(() => {
  if (route.name === "users") {
    return "users";
  }
  if (route.name === "server-detail" || route.name === "server-new") {
    return "servers";
  }
  return (route.name as TabId | undefined) ?? "servers";
});
const isPublicLayout = computed(() => Boolean(route.meta.public));

const activeTabCopy = computed(() => tabCopy[activeTab.value]);
const visibleNavItems = computed(() =>
  navItems.filter((item) => item.id !== "users" || auth.isAdmin.value),
);
const pageTitle = computed(() => {
  if (route.name === "server-detail" && store.selectedServer.value) {
    return store.selectedServer.value.name;
  }
  if (route.name === "server-new") {
    return "Новый сервер";
  }
  return activeTabCopy.value.title;
});

function selectTab(tabId: TabId) {
  if (tabId === "users" && !auth.isAdmin.value) {
    return;
  }
  if (visibleNavItems.value.find((item) => item.id === tabId)?.disabled) {
    return;
  }
  router.push(routePaths[tabId]);
}

function logout() {
  auth.clearSession();
  router.push("/login");
}

function updateThemeFromEvent(event: Event) {
  auth.updateTheme((event.target as HTMLSelectElement).value as ThemeName);
}

function loadAppData() {
  if (isPublicLayout.value) {
    return;
  }
  const routeServerId = typeof route.params.serverId === "string" ? route.params.serverId : "";
  store.loadDashboard(routeServerId);
  store.loadSettings();
}

onMounted(() => {
  auth.initializeAuth();
  loadAppData();
});

watch(
  () => route.name,
  () => {
    loadAppData();
  },
);
</script>

<template>
  <RouterView v-if="isPublicLayout" />

  <main v-else class="app-shell">
    <div class="scene-orb orb-one"></div>
    <div class="scene-orb orb-two"></div>
    <div class="scene-orb orb-three"></div>
    <div class="scene-ribbon ribbon-one"></div>
    <div class="scene-ribbon ribbon-two"></div>

    <AppSidebar :active-tab="activeTab" :nav-items="visibleNavItems" @select="selectTab" />

    <section class="workspace">
      <header class="topbar">
        <div>
          <h1>{{ pageTitle }}</h1>
        </div>
        <div v-if="auth.user.value" class="user-menu">
          <span>{{ auth.user.value.display_name }}</span>
          <select :value="auth.user.value.theme" @change="updateThemeFromEvent">
            <option v-for="theme in themes" :key="theme.id" :value="theme.id">{{ theme.label }}</option>
          </select>
          <button class="ghost-button compact" type="button" @click="logout">Выйти</button>
        </div>
      </header>

      <section v-if="store.isAgentUnavailable.value" class="agent-alert panel">
        <div>
          <p class="eyebrow">host agent</p>
          <h2>Agent недоступен</h2>
          <p>
            Backend не может получить реальные серверы и метрики. Демо-данные скрыты,
            чтобы не путать их с настоящим состоянием хоста.
          </p>
        </div>
        <div class="agent-alert-actions">
          <button class="ghost-button compact" type="button" @click="store.loadAgentStatus">
            <RefreshCw :size="16" />
            <span>Проверить</span>
          </button>
          <button class="primary-button" type="button" @click="store.restartAgent">
            <RefreshCw :size="16" />
            <span>Перезапустить agent</span>
          </button>
        </div>
      </section>

      <section class="content-grid single-column">
        <div class="main-column">
          <RouterView />
        </div>
      </section>
    </section>

    <ToastStack />
    <span class="build-badge">{{ buildLabel }}</span>
  </main>
</template>
