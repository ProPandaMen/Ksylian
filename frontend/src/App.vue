<script setup lang="ts">
import { computed, onMounted } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import { RefreshCw } from "@lucide/vue";
import AppSidebar from "./components/AppSidebar.vue";
import ToastStack from "./components/ToastStack.vue";
import { useDashboardStore } from "./composables/useDashboardStore";
import { navItems, routePaths, tabCopy } from "./navigation";
import type { TabId } from "./types";

const route = useRoute();
const router = useRouter();
const store = useDashboardStore();

const appVersionLabel = __APP_VERSION__.startsWith("v") || __APP_VERSION__ === "dev"
  ? __APP_VERSION__
  : `v${__APP_VERSION__}`;
const buildLabel = `${appVersionLabel} · ${__BUILD_SHA__}`;

const activeTab = computed<TabId>(() => {
  if (route.name === "server-detail" || route.name === "server-new") {
    return "servers";
  }
  return (route.name as TabId | undefined) ?? "servers";
});

const activeTabCopy = computed(() => tabCopy[activeTab.value]);
const pageEyebrow = computed(() => {
  if (route.name === "server-detail") {
    return "server control";
  }
  if (route.name === "server-new") {
    return "new instance";
  }
  return activeTabCopy.value.eyebrow;
});
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
  if (navItems.find((item) => item.id === tabId)?.disabled) {
    return;
  }
  router.push(routePaths[tabId]);
}

onMounted(() => {
  const routeServerId = typeof route.params.serverId === "string" ? route.params.serverId : "";
  store.loadDashboard(routeServerId);
  store.loadSettings();
});
</script>

<template>
  <main class="app-shell">
    <div class="scene-orb orb-one"></div>
    <div class="scene-orb orb-two"></div>
    <div class="scene-orb orb-three"></div>
    <div class="scene-ribbon ribbon-one"></div>
    <div class="scene-ribbon ribbon-two"></div>

    <AppSidebar :active-tab="activeTab" :nav-items="navItems" @select="selectTab" />

    <section class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">{{ pageEyebrow }}</p>
          <h1>{{ pageTitle }}</h1>
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
