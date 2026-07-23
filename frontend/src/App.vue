<script setup lang="ts">
import { computed, onMounted, watch } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import { RefreshCw } from "@lucide/vue";
import AppSidebar from "./components/AppSidebar.vue";
import ToastStack from "./components/ToastStack.vue";
import { useAuthStore } from "./composables/useAuthStore";
import { useDashboardStore } from "./composables/useDashboardStore";
import { navItems, routePaths, tabCopy } from "./navigation";
import type { TabId } from "./types";

const route = useRoute();
const router = useRouter();
const store = useDashboardStore();
const auth = useAuthStore();

const appVersionLabel = __APP_VERSION__.startsWith("v") || __APP_VERSION__ === "dev"
  ? __APP_VERSION__
  : `v${__APP_VERSION__}`;

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
const isMonitoringPage = computed(() => route.name === "monitoring");
const isServerDetailPage = computed(() => route.name === "server-detail");
const isServerNestedPage = computed(() => route.name === "server-detail" || route.name === "server-new");

const activeTabCopy = computed(() => tabCopy[activeTab.value]);
const visibleNavItems = computed(() =>
  navItems.filter((item) => {
    if (item.id === "users") {
      return auth.isAdmin.value;
    }
    if (item.id === "modpacks") {
      return store.settings.value.curseforge_api_key_status === "valid";
    }
    return true;
  }),
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

function openServersPage() {
  router.push("/servers");
}

function logout() {
  auth.clearSession();
  router.push("/login");
}

function loadAppData() {
  if (isPublicLayout.value) {
    return;
  }
  if (!auth.user.value) {
    return;
  }
  const routeServerId = typeof route.params.serverId === "string" ? route.params.serverId : "";
  store.loadDashboard(routeServerId);
  store.loadSettings();
}

function redirectUnavailableRoutes() {
  if (route.name === "modpacks" && store.settings.value.curseforge_api_key_status !== "valid") {
    router.replace("/settings");
  }
}

onMounted(async () => {
  await auth.initializeAuth();
  loadAppData();
});

watch(
  () => route.name,
  () => {
    loadAppData();
    redirectUnavailableRoutes();
  },
);

watch(
  () => auth.user.value?.id,
  () => {
    loadAppData();
  },
);

watch(
  () => store.settings.value.curseforge_api_key_status,
  () => {
    redirectUnavailableRoutes();
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

    <AppSidebar
      :active-tab="activeTab"
      :nav-items="visibleNavItems"
      :user="auth.user.value"
      :version-label="appVersionLabel"
      @select="selectTab"
      @logout="logout"
    />

    <section class="workspace">
      <header class="topbar">
        <div class="topbar-title">
          <h1 v-if="isServerNestedPage" class="breadcrumb-title">
            <button type="button" @click="openServersPage">Серверы</button>
            <span aria-hidden="true">→</span>
            <span>{{ pageTitle }}</span>
          </h1>
          <h1 v-else>{{ pageTitle }}</h1>
        </div>
        <div v-if="isMonitoringPage || isServerDetailPage" class="topbar-actions">
          <button v-if="isMonitoringPage" class="ghost-button compact" type="button" @click="store.loadMonitoring">
            <RefreshCw :size="16" />
            <span>{{ store.isMonitoringLoading.value ? 'Обновляю' : 'Обновить' }}</span>
          </button>
          <button
            v-else
            class="ghost-button compact"
            type="button"
            @click="store.loadDashboard(store.selectedServer.value?.id)"
          >
            <RefreshCw :size="16" />
            <span>Обновить</span>
          </button>
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
  </main>
</template>
