<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ArrowLeft,
  CircleStop,
  Cpu,
  HardDrive,
  ListRestart,
  MemoryStick,
  Play,
  Plus,
  RefreshCw,
  Server,
  Trash2,
  Users,
  X,
} from "@lucide/vue";
import AppSidebar from "./components/AppSidebar.vue";
import { navItems, routePaths, tabCopy } from "./navigation";
import CurseForgePage from "./pages/CurseForgePage.vue";
import MonitoringPage from "./pages/MonitoringPage.vue";
import NewServerPage from "./pages/NewServerPage.vue";
import SettingsPage from "./pages/SettingsPage.vue";
import type {
  BackupItem,
  DashboardPayload,
  FileItem,
  GameServer,
  HostMonitoring,
  ModItem,
  NewServerDraft,
  ServerConfigPayload,
  SettingsPayload,
  AgentStatus,
  ServerState,
  TabId,
} from "./types";

const emptyServers: GameServer[] = [];
const emptyLogs: string[] = [];
const emptyBackups: BackupItem[] = [];
const emptyMods: ModItem[] = [];
const emptyFiles: FileItem[] = [];
type ToastTone = "success" | "error" | "info";

interface ToastMessage {
  id: number;
  tone: ToastTone;
  text: string;
}

const stateLabels: Record<ServerState, string> = {
  online: "Онлайн",
  deploying: "Разворачивается",
  offline: "Выключен",
};

const serverTypeLabels: Record<NewServerDraft["type"], string> = {
  vanilla: "Vanilla",
  fabric: "Fabric",
  forge: "Forge",
  neoforge: "NeoForge",
  quilt: "Quilt",
  paper: "Paper / Purpur",
  purpur: "Paper / Purpur",
};

const route = useRoute();
const router = useRouter();
const appVersionLabel = __APP_VERSION__.startsWith("v") || __APP_VERSION__ === "dev"
  ? __APP_VERSION__
  : `v${__APP_VERSION__}`;
const buildLabel = `${appVersionLabel} · ${__BUILD_SHA__}`;
const servers = ref<GameServer[]>(emptyServers);
const logs = ref<string[]>(emptyLogs);
const backups = ref<BackupItem[]>(emptyBackups);
const mods = ref<ModItem[]>(emptyMods);
const files = ref<FileItem[]>(emptyFiles);
const isLoading = ref(true);
const isDashboardLoaded = ref(false);
const isLogLoading = ref(false);
const isMonitoringLoading = ref(false);
const isSavingSettings = ref(false);
const toasts = ref<ToastMessage[]>([]);
let toastId = 0;
const curseForgeApiKey = ref("");
const defaultAgentStatus: AgentStatus = {
  configured: false,
  available: false,
  status: "not_configured",
  message: "",
};
const agentStatus = ref<AgentStatus>(defaultAgentStatus);
const settings = ref<SettingsPayload>({
  has_curseforge_api_key: false,
  curseforge_api_key_mask: "",
  agent: defaultAgentStatus,
});
const selectedServerId = ref("");
const selectedServerLogs = ref<string[]>(emptyLogs);
type ServerDetailTab = "overview" | "logs" | "settings";
const activeServerDetailTab = ref<ServerDetailTab>("overview");
const logConsole = ref<HTMLPreElement | null>(null);
const shouldStickToLogBottom = ref(true);
let logRefreshTimer: number | undefined;
const selectedServerConfig = ref("");
const isConfigLoading = ref(false);
const isConfigSaving = ref(false);
const monitoring = ref<HostMonitoring>({
  hostname: "server",
  ip_addresses: [],
  uptime: "0m",
  load_average: [0, 0, 0],
  cpu_percent: 0,
  cpu_cores: 1,
  memory: { used: 0, total: 1, percent: 0, used_label: "0 MB", total_label: "0 MB" },
  swap: { used: 0, total: 0, percent: 0, used_label: "0 MB", total_label: "0 MB" },
  disks: [],
  top_processes: [],
  services: [],
  temperature: "n/a",
  collected_at: "",
});
const newServer = ref<NewServerDraft>({
  name: "",
  type: "vanilla",
  version: "",
});

function dismissToast(id: number) {
  toasts.value = toasts.value.filter((toast) => toast.id !== id);
}

function showToast(text: string, tone: ToastTone = "info") {
  const id = ++toastId;
  toasts.value = [...toasts.value, { id, tone, text }].slice(-4);
  window.setTimeout(() => dismissToast(id), 4200);
}

const onlineServersCount = computed(
  () => servers.value.filter((server) => server.state !== "offline").length,
);
const offlineServersCount = computed(
  () => servers.value.filter((server) => server.state === "offline").length,
);
const deployingServersCount = computed(
  () => servers.value.filter((server) => server.state === "deploying").length,
);
const stableServersCount = computed(
  () => servers.value.filter((server) => server.state === "online").length,
);
const selectedServer = computed(
  () => servers.value.find((server) => server.id === selectedServerId.value) ?? servers.value[0],
);
const isDashboardInitialLoading = computed(() => isLoading.value && !isDashboardLoaded.value);
const isAgentUnavailable = computed(() => agentStatus.value.configured && !agentStatus.value.available);
const monitoringStatus = computed(() => {
  if (isAgentUnavailable.value) {
    return { label: "Agent недоступен", tone: "danger" };
  }
  const maxDisk = Math.max(0, ...monitoring.value.disks.map((disk) => disk.percent));
  const maxUsage = Math.max(monitoring.value.cpu_percent, monitoring.value.memory.percent, maxDisk);
  if (maxUsage >= 90) {
    return { label: "Критичная нагрузка", tone: "danger" };
  }
  if (maxUsage >= 75) {
    return { label: "Нужно внимание", tone: "warning" };
  }
  return { label: "Нагрузка в норме", tone: "ok" };
});
const activeTab = computed<TabId>(() => {
  if (route.name === "server-detail" || route.name === "server-new") {
    return "servers";
  }
  return (route.name as TabId | undefined) ?? "servers";
});
const serverView = computed<"list" | "detail" | "new">(() =>
  route.name === "server-detail" ? "detail" : route.name === "server-new" ? "new" : "list",
);
const activeTabCopy = computed(() => tabCopy[activeTab.value]);
const pageEyebrow = computed(() =>
  activeTab.value === "servers" && serverView.value === "detail"
    ? "server control"
    : activeTab.value === "servers" && serverView.value === "new"
      ? "new instance"
      : activeTabCopy.value.eyebrow,
);
const pageTitle = computed(() =>
  activeTab.value === "servers" && serverView.value === "detail" && selectedServer.value
    ? selectedServer.value.name
    : activeTab.value === "servers" && serverView.value === "new"
      ? "Новый сервер"
    : activeTabCopy.value.title,
);
const serverDetailTabs: Array<{ id: ServerDetailTab; label: string }> = [
  { id: "overview", label: "Информация" },
  { id: "logs", label: "Логи" },
  { id: "settings", label: "Настройки" },
];

async function requestJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`API returned ${response.status}`);
  }

  return response.json() as Promise<T>;
}

async function loadDashboard() {
  isLoading.value = true;

  try {
    const data = await requestJson<DashboardPayload>("/api/dashboard");
    servers.value = data.servers;
    logs.value = data.logs;
    backups.value = data.backups;
    mods.value = data.mods;
    files.value = data.files;
    agentStatus.value = data.agent;
    const routeServerId = typeof route.params.serverId === "string" ? route.params.serverId : "";
    const nextServerId = routeServerId || selectedServerId.value || data.servers[0]?.id || "";
    if (nextServerId) {
      selectedServerId.value = nextServerId;
    }
    if (route.name === "server-detail" && selectedServerId.value) {
      await loadServerDetailData(selectedServerId.value);
    }
  } catch (error) {
    showToast("Backend пока недоступен, данные не обновлены", "error");
    console.error(error);
  } finally {
    isLoading.value = false;
    isDashboardLoaded.value = true;
  }
}

async function loadSettings() {
  try {
    settings.value = await requestJson<SettingsPayload>("/api/settings");
    agentStatus.value = settings.value.agent;
  } catch (error) {
    showToast("Не удалось загрузить настройки", "error");
    console.error(error);
  }
}

async function loadAgentStatus() {
  try {
    agentStatus.value = await requestJson<AgentStatus>("/api/agent/status");
    settings.value = {
      ...settings.value,
      agent: agentStatus.value,
    };
  } catch (error) {
    showToast("Не удалось проверить Host Agent", "error");
    console.error(error);
  }
}

async function loadServerDetailData(serverId = selectedServerId.value) {
  if (!serverId) {
    return;
  }
  if (activeServerDetailTab.value === "logs") {
    await loadServerLogs(serverId);
  }
  if (activeServerDetailTab.value === "settings") {
    await loadServerConfig(serverId);
  }
}

async function loadServerLogs(serverId = selectedServerId.value) {
  if (!serverId) {
    selectedServerLogs.value = [];
    return;
  }

  selectedServerId.value = serverId;
  isLogLoading.value = true;

  try {
    selectedServerLogs.value = await requestJson<string[]>(`/api/servers/${serverId}/logs`);
    await scrollLogsIfNeeded();
  } catch (error) {
    showToast("Не удалось загрузить логи выбранного сервера", "error");
    selectedServerLogs.value = [];
    console.error(error);
  } finally {
    isLogLoading.value = false;
  }
}

async function refreshServerLogs() {
  if (
    serverView.value !== "detail" ||
    activeServerDetailTab.value !== "logs" ||
    !selectedServerId.value ||
    isLogLoading.value
  ) {
    return;
  }

  try {
    selectedServerLogs.value = await requestJson<string[]>(`/api/servers/${selectedServerId.value}/logs`);
    await scrollLogsIfNeeded();
  } catch (error) {
    console.error(error);
  }
}

function updateLogStickiness() {
  const consoleElement = logConsole.value;
  if (!consoleElement) {
    shouldStickToLogBottom.value = true;
    return;
  }

  const distanceFromBottom = consoleElement.scrollHeight - consoleElement.scrollTop - consoleElement.clientHeight;
  shouldStickToLogBottom.value = distanceFromBottom < 48;
}

async function scrollLogsIfNeeded() {
  if (!shouldStickToLogBottom.value) {
    return;
  }

  await nextTick();
  const consoleElement = logConsole.value;
  if (consoleElement) {
    consoleElement.scrollTop = consoleElement.scrollHeight;
  }
}

function startLogAutoRefresh() {
  if (logRefreshTimer || serverView.value !== "detail" || activeServerDetailTab.value !== "logs") {
    return;
  }

  logRefreshTimer = window.setInterval(() => {
    refreshServerLogs();
  }, 2500);
}

function stopLogAutoRefresh() {
  if (logRefreshTimer) {
    window.clearInterval(logRefreshTimer);
    logRefreshTimer = undefined;
  }
}

async function loadServerConfig(serverId = selectedServerId.value) {
  if (!serverId) {
    selectedServerConfig.value = "";
    return;
  }

  isConfigLoading.value = true;
  try {
    const payload = await requestJson<ServerConfigPayload>(`/api/servers/${serverId}/config`);
    selectedServerConfig.value = payload.content;
  } catch (error) {
    showToast("Не удалось загрузить server.properties", "error");
    selectedServerConfig.value = "";
    console.error(error);
  } finally {
    isConfigLoading.value = false;
  }
}

async function saveServerConfig() {
  if (!selectedServerId.value) {
    return;
  }

  isConfigSaving.value = true;
  try {
    const payload = await requestJson<ServerConfigPayload>(`/api/servers/${selectedServerId.value}/config`, {
      method: "PUT",
      body: JSON.stringify({ content: selectedServerConfig.value }),
    });
    selectedServerConfig.value = payload.content;
    showToast("server.properties сохранён", "success");
  } catch (error) {
    showToast("Не удалось сохранить server.properties", "error");
    console.error(error);
  } finally {
    isConfigSaving.value = false;
  }
}

function selectServerDetailTab(tabId: ServerDetailTab) {
  activeServerDetailTab.value = tabId;
}

async function loadMonitoring() {
  isMonitoringLoading.value = true;

  try {
    monitoring.value = await requestJson<HostMonitoring>("/api/monitoring");
    await loadAgentStatus();
  } catch (error) {
    await loadAgentStatus();
    showToast("Не удалось загрузить мониторинг: Host Agent недоступен", "error");
    console.error(error);
  } finally {
    isMonitoringLoading.value = false;
  }
}

async function openServerPanel(serverId: string) {
  selectedServerId.value = serverId;
  await router.push(`/servers/${serverId}`);
}

function backToServerList() {
  router.push("/servers");
}

function openNewServerPage() {
  router.push("/servers/new");
}

function selectTab(tabId: TabId) {
  if (navItems.find((item) => item.id === tabId)?.disabled) {
    return;
  }
  router.push(routePaths[tabId]);
}

async function runServerAction(serverId: string, action: "start" | "restart" | "stop" | "backup") {
  try {
    await requestJson(`/api/servers/${serverId}/actions/${action}`, { method: "POST" });
    await loadDashboard();
  } catch (error) {
    showToast("Не удалось выполнить действие", "error");
    console.error(error);
  }
}

async function createServer() {
  try {
    await requestJson("/api/servers", {
      method: "POST",
      body: JSON.stringify({
        name: newServer.value.name,
        type: newServer.value.type === "purpur" ? "paper" : newServer.value.type,
        pack: serverTypeLabels[newServer.value.type],
        version: newServer.value.version,
        address: "",
      }),
    });
    newServer.value = { name: "", type: "vanilla", version: "" };
    await loadDashboard();
    await router.push("/servers");
    showToast("Сервер создан и готов к запуску", "success");
  } catch (error) {
    showToast("Не удалось подготовить сервер", "error");
    console.error(error);
  }
}

async function deleteServer(serverId: string) {
  const server = servers.value.find((item) => item.id === serverId);
  const confirmed = window.confirm(
    `Удалить ${server?.name ?? "сервер"} из панели? Сервис будет остановлен и отключен от автозапуска, файлы мира останутся на диске.`,
  );
  if (!confirmed) {
    return;
  }

  try {
    await requestJson(`/api/servers/${serverId}`, { method: "DELETE" });
    await loadDashboard();
    showToast(`${server?.name ?? "Сервер"} удалён из панели`, "success");
  } catch (error) {
    showToast("Не удалось удалить сервер через agent", "error");
    console.error(error);
  }
}

async function createBackup(serverId = selectedServer.value?.id ?? servers.value[0]?.id ?? "ksy-vanilla") {
  try {
    await requestJson(`/api/backups?server_id=${encodeURIComponent(serverId)}`, { method: "POST" });
    await loadDashboard();
    showToast("Резервная копия создана", "success");
  } catch (error) {
    showToast("Не удалось создать резервную копию", "error");
    console.error(error);
  }
}

async function checkMods() {
  try {
    await requestJson("/api/mods/check", { method: "POST" });
    await loadDashboard();
    showToast("Проверка модов запущена", "success");
  } catch (error) {
    showToast("Не удалось проверить обновления модов", "error");
    console.error(error);
  }
}

async function saveSettings() {
  isSavingSettings.value = true;

  try {
    settings.value = await requestJson<SettingsPayload>("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ curseforge_api_key: curseForgeApiKey.value }),
    });
    curseForgeApiKey.value = "";
    showToast(
      settings.value.has_curseforge_api_key ? "Ключ CurseForge сохранён" : "Ключ CurseForge очищен",
      "success",
    );
  } catch (error) {
    showToast("Не удалось сохранить ключ CurseForge", "error");
    console.error(error);
  } finally {
    isSavingSettings.value = false;
  }
}

async function clearCurseForgeKey() {
  curseForgeApiKey.value = "";
  await saveSettings();
}

async function restartAgent() {
  try {
    agentStatus.value = await requestJson<AgentStatus>("/api/agent/restart", { method: "POST" });
    settings.value = {
      ...settings.value,
      agent: agentStatus.value,
    };
    showToast("Host Agent перезапускается", "success");
    window.setTimeout(() => {
      loadAgentStatus();
      loadDashboard();
      if (activeTab.value === "monitoring") {
        loadMonitoring();
      }
    }, 1600);
  } catch (error) {
    showToast("Не удалось перезапустить Host Agent из панели", "error");
    console.error(error);
  }
}

watch(
  () => route.params.serverId,
  async (serverId) => {
    if (typeof serverId === "string" && serverId) {
      shouldStickToLogBottom.value = true;
      await loadServerDetailData(serverId);
    }
  },
);

watch(
  () => [serverView.value, activeServerDetailTab.value] as const,
  ([view, tabId]) => {
    if (view === "detail" && tabId === "logs") {
      shouldStickToLogBottom.value = true;
      startLogAutoRefresh();
      refreshServerLogs();
      return;
    }

    stopLogAutoRefresh();
  },
);

watch(
  () => activeServerDetailTab.value,
  (tabId) => {
    if (serverView.value !== "detail") {
      return;
    }
    if (tabId === "settings") {
      loadServerConfig();
    }
    if (tabId === "logs") {
      shouldStickToLogBottom.value = true;
      loadServerLogs();
    }
  },
);

watch(
  () => selectedServerLogs.value.length,
  () => {
    scrollLogsIfNeeded();
  },
);

watch(
  () => activeTab.value,
  (tabId) => {
    if (tabId === "monitoring") {
      loadMonitoring();
    }
  },
);

onMounted(() => {
  loadDashboard();
  if (serverView.value === "detail" && activeServerDetailTab.value === "logs") {
    startLogAutoRefresh();
  }
  if (activeTab.value === "monitoring") {
    loadMonitoring();
  }
  loadSettings().then(() => {
    return undefined;
  });
});

onUnmounted(() => {
  stopLogAutoRefresh();
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

      <section v-if="isAgentUnavailable" class="agent-alert panel">
        <div>
          <p class="eyebrow">host agent</p>
          <h2>Agent недоступен</h2>
          <p>
            Backend не может получить реальные серверы и метрики. Демо-данные скрыты,
            чтобы не путать их с настоящим состоянием хоста.
          </p>
        </div>
        <div class="agent-alert-actions">
          <button class="ghost-button compact" type="button" @click="loadAgentStatus">
            <RefreshCw :size="16" />
            <span>Проверить</span>
          </button>
          <button class="primary-button" type="button" @click="restartAgent">
            <RefreshCw :size="16" />
            <span>Перезапустить agent</span>
          </button>
        </div>
      </section>

      <section class="content-grid single-column">
        <div class="main-column">
          <NewServerPage
            v-if="activeTab === 'servers' && serverView === 'new'"
            v-model="newServer"
            @cancel="backToServerList"
            @submit="createServer"
          />

          <section
            v-if="activeTab === 'servers' && serverView === 'list' && isDashboardInitialLoading"
            class="server-summary-grid"
            aria-label="Загрузка сводки серверов"
          >
            <article v-for="item in 4" :key="item" class="summary-tile skeleton-tile">
              <span class="skeleton-line short"></span>
              <strong class="skeleton-number"></strong>
            </article>
          </section>

          <section v-else-if="activeTab === 'servers' && serverView === 'list'" class="server-summary-grid" aria-label="Сводка серверов">
            <article class="summary-tile">
              <span>Стабильно работают</span>
              <strong>{{ stableServersCount }}</strong>
            </article>
            <article class="summary-tile amber">
              <span>Перезагружаются</span>
              <strong>{{ deployingServersCount }}</strong>
            </article>
            <article class="summary-tile graphite">
              <span>Выключены</span>
              <strong>{{ offlineServersCount }}</strong>
            </article>
            <article class="summary-tile violet">
              <span>Всего серверов</span>
              <strong>{{ servers.length }}</strong>
            </article>
          </section>

          <section v-if="activeTab === 'servers' && serverView === 'list'" class="panel">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">instances</p>
                <h2>Полный список серверов</h2>
              </div>
              <div class="panel-actions">
                <button class="ghost-button compact" type="button" @click="loadDashboard">
                  <RefreshCw :size="16" />
                  <span>Обновить</span>
                </button>
                <button class="primary-button compact" type="button" @click="openNewServerPage">
                  <Plus :size="16" />
                  <span>Новый сервер</span>
                </button>
              </div>
            </div>

            <div v-if="isDashboardInitialLoading" class="server-list" aria-label="Загрузка серверов">
              <article v-for="item in 3" :key="item" class="server-row skeleton-row">
                <div class="server-main">
                  <span class="skeleton-dot"></span>
                  <div>
                    <span class="skeleton-line title"></span>
                    <span class="skeleton-line"></span>
                  </div>
                </div>
                <div class="server-metrics">
                  <span class="skeleton-pill"></span>
                  <span class="skeleton-pill"></span>
                  <span class="skeleton-pill"></span>
                </div>
                <div class="server-actions">
                  <span v-for="button in 4" :key="button" class="skeleton-button"></span>
                </div>
                <div class="progress-line static skeleton-progress">
                  <span></span>
                </div>
              </article>
            </div>

            <div v-else class="server-list">
              <article
                v-for="server in servers"
                :key="server.id"
                class="server-row"
                :class="{ selected: selectedServerId === server.id }"
                role="button"
                tabindex="0"
                @click="openServerPanel(server.id)"
                @keydown.enter.prevent="openServerPanel(server.id)"
                @keydown.space.prevent="openServerPanel(server.id)"
              >
                <div class="server-main">
                  <span class="server-state" :class="server.state"></span>
                  <div class="server-copy">
                    <div class="server-title-line">
                      <h3>{{ server.name }}</h3>
                    </div>
                    <p>{{ server.address }}</p>
                    <div class="server-tags" aria-label="Основная информация">
                      <span>{{ server.pack }}</span>
                      <span>Minecraft {{ server.version }}</span>
                    </div>
                  </div>
                </div>

                <div class="server-metrics">
                  <span>{{ server.players }}</span>
                  <span>{{ server.ram }}</span>
                  <span>{{ server.disk }}</span>
                </div>

                <div class="server-actions" :aria-label="`Действия для ${server.name}`">
                  <button
                    class="icon-button"
                    type="button"
                    :title="server.state === 'offline' ? 'Запустить' : 'Остановить'"
                    @click.stop="runServerAction(server.id, server.state === 'offline' ? 'start' : 'stop')"
                  >
                    <Play v-if="server.state === 'offline'" :size="17" />
                    <CircleStop v-else :size="17" />
                  </button>
                  <button
                    class="icon-button"
                    type="button"
                    title="Перезагрузить"
                    @click.stop="runServerAction(server.id, 'restart')"
                  >
                    <ListRestart :size="17" />
                  </button>
                  <button
                    v-if="activeTab === 'servers'"
                    class="icon-button danger"
                    type="button"
                    title="Удалить"
                    @click.stop="deleteServer(server.id)"
                  >
                    <Trash2 :size="17" />
                  </button>
                </div>

                <div class="progress-line">
                  <span :style="{ width: `${server.cpu}%` }"></span>
                </div>

                <span class="state-label" :class="server.state">{{ stateLabels[server.state] }}</span>
              </article>
              <article v-if="!servers.length" class="server-empty-state">
                <div class="empty-icon">
                  <Server :size="28" />
                </div>
                <div>
                  <strong>Серверов пока нет</strong>
                  <span>
                    Создай первый Minecraft-сервер или подключи существующий через agent.
                  </span>
                </div>
                <button class="ghost-button compact" type="button" @click="openNewServerPage">
                  <Plus :size="18" />
                  <span>Создать сервер</span>
                </button>
              </article>
            </div>
          </section>

          <section v-if="activeTab === 'servers' && serverView === 'detail' && selectedServer" class="server-control">
            <div class="server-control-header">
              <button class="ghost-button compact" type="button" @click="backToServerList">
                <ArrowLeft :size="16" />
                <span>К списку</span>
              </button>
              <div class="server-control-actions">
                <button class="ghost-button compact" type="button" @click="loadDashboard">
                  <RefreshCw :size="16" />
                  <span>Обновить</span>
                </button>
              </div>
            </div>

            <section class="server-hero panel">
              <div class="server-hero-main">
                <span class="server-state" :class="selectedServer.state"></span>
                <div>
                  <p class="eyebrow">{{ selectedServer.pack }}</p>
                  <h2>{{ selectedServer.name }}</h2>
                  <p>{{ selectedServer.version }} · {{ selectedServer.address }}</p>
                </div>
              </div>
              <div class="server-actions">
                <button class="icon-button" type="button" title="Запустить" @click="runServerAction(selectedServer.id, 'start')">
                  <Play :size="17" />
                </button>
                <button class="icon-button" type="button" title="Перезагрузить" @click="runServerAction(selectedServer.id, 'restart')">
                  <ListRestart :size="17" />
                </button>
                <button class="icon-button danger" type="button" title="Остановить" @click="runServerAction(selectedServer.id, 'stop')">
                  <CircleStop :size="17" />
                </button>
              </div>
            </section>

            <nav class="server-tabs" aria-label="Разделы сервера">
              <button
                v-for="tab in serverDetailTabs"
                :key="tab.id"
                type="button"
                :class="{ active: activeServerDetailTab === tab.id }"
                @click="selectServerDetailTab(tab.id)"
              >
                {{ tab.label }}
              </button>
            </nav>

            <section v-if="activeServerDetailTab === 'overview'" class="server-tab-panel">
              <section class="server-detail-grid">
                <article class="metric-tile">
                  <Cpu :size="20" />
                  <span>Процессор</span>
                  <strong>{{ selectedServer.cpu }}%</strong>
                </article>
                <article class="metric-tile mint">
                  <MemoryStick :size="20" />
                  <span>Оперативка</span>
                  <strong>{{ selectedServer.ram }}</strong>
                </article>
                <article class="metric-tile amber">
                  <HardDrive :size="20" />
                  <span>Память</span>
                  <strong>{{ selectedServer.disk }}</strong>
                </article>
                <article class="metric-tile graphite">
                  <Users :size="20" />
                  <span>Онлайн</span>
                  <strong>{{ selectedServer.players }}</strong>
                </article>
              </section>
              <section class="panel server-info-panel">
                <p class="eyebrow">connection</p>
                <h2>Основная информация</h2>
                <div class="server-info-grid">
                  <div>
                    <span>Адрес</span>
                    <strong>{{ selectedServer.address }}</strong>
                  </div>
                  <div>
                    <span>Тип</span>
                    <strong>{{ selectedServer.pack }}</strong>
                  </div>
                  <div>
                    <span>Версия Minecraft</span>
                    <strong>{{ selectedServer.version }}</strong>
                  </div>
                  <div>
                    <span>Статус</span>
                    <strong>{{ stateLabels[selectedServer.state] }}</strong>
                  </div>
                </div>
              </section>
            </section>

            <section v-if="activeServerDetailTab === 'logs'" class="server-tab-panel">
              <section class="panel terminal-panel server-logs-panel">
                <div class="panel-heading">
                  <div>
                    <p class="eyebrow">server output</p>
                    <h2>Логи</h2>
                  </div>
                  <button class="ghost-button compact" type="button" @click="loadServerLogs()">
                    <RefreshCw :size="16" />
                    <span>{{ isLogLoading ? 'Загрузка' : 'Обновить' }}</span>
                  </button>
                </div>
                <pre ref="logConsole" @scroll="updateLogStickiness"><code v-for="(line, index) in selectedServerLogs" :key="`${index}-${line}`">{{ line }}
</code><code v-if="!selectedServerLogs.length">Логов для выбранного сервера пока нет.
</code></pre>
              </section>
            </section>

            <section v-if="activeServerDetailTab === 'settings'" class="server-tab-panel">
              <section class="panel server-config-panel">
                <div class="panel-heading">
                  <div>
                    <p class="eyebrow">minecraft config</p>
                    <h2>server.properties</h2>
                  </div>
                  <div class="panel-actions">
                    <button class="ghost-button compact" type="button" @click="loadServerConfig()">
                      <RefreshCw :size="16" />
                      <span>{{ isConfigLoading ? 'Загрузка' : 'Обновить' }}</span>
                    </button>
                    <button class="primary-button compact" type="button" :disabled="isConfigSaving" @click="saveServerConfig">
                      <span>{{ isConfigSaving ? 'Сохраняю' : 'Сохранить' }}</span>
                    </button>
                  </div>
                </div>
                <p class="settings-hint">
                  Изменения в server.properties обычно применяются после перезапуска Minecraft-сервера.
                </p>
                <textarea
                  v-model="selectedServerConfig"
                  class="config-editor"
                  spellcheck="false"
                  :disabled="isConfigLoading || isConfigSaving"
                  placeholder="server.properties пока не загружен"
                ></textarea>
              </section>
            </section>
          </section>

          <MonitoringPage
            v-if="activeTab === 'monitoring'"
            :monitoring="monitoring"
            :monitoring-status="monitoringStatus"
            :is-loading="isMonitoringLoading"
            :state-labels="stateLabels"
            @refresh="loadMonitoring"
          />

          <CurseForgePage v-if="activeTab === 'modpacks'" />

          <SettingsPage
            v-if="activeTab === 'settings'"
            v-model:curse-forge-api-key="curseForgeApiKey"
            :settings="settings"
            :is-saving="isSavingSettings"
            @refresh="loadDashboard"
            @refresh-agent="loadAgentStatus"
            @restart-agent="restartAgent"
            @save="saveSettings"
            @clear="clearCurseForgeKey"
          />
        </div>

      </section>
    </section>

    <div class="toast-stack" aria-live="polite" aria-label="Уведомления">
      <article v-for="toast in toasts" :key="toast.id" class="toast-card" :class="toast.tone">
        <span class="toast-dot"></span>
        <p>{{ toast.text }}</p>
        <button class="toast-close" type="button" title="Закрыть" @click="dismissToast(toast.id)">
          <X :size="16" />
        </button>
      </article>
    </div>

    <span class="build-badge">{{ buildLabel }}</span>
  </main>
</template>
