<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  Archive,
  ArrowLeft,
  Box,
  CheckCircle2,
  ChevronRight,
  CircleStop,
  Clock3,
  Cpu,
  Download,
  FileArchive,
  FileText,
  Folder,
  Gauge,
  HardDrive,
  Home,
  ListRestart,
  MemoryStick,
  PackagePlus,
  Play,
  Plus,
  RefreshCw,
  Server,
  ShieldCheck,
  Trash2,
  UploadCloud,
  Users,
  X,
} from "@lucide/vue";
import catPaw from "./assets/cat-paw.svg";
import catMascot from "./assets/ksylian-cat.png";
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
  SettingsPayload,
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
const settings = ref<SettingsPayload>({
  has_curseforge_api_key: false,
  curseforge_api_key_mask: "",
});
const selectedServerId = ref("");
const selectedServerLogs = ref<string[]>(emptyLogs);
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
  version: "1.20.1",
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
const selectedServerBackups = computed(() =>
  backups.value.filter((backup) => backup.server_id === selectedServer.value?.id),
);
const isDashboardInitialLoading = computed(() => isLoading.value && !isDashboardLoaded.value);
const monitoringStatus = computed(() => {
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
  return (route.name as TabId | undefined) ?? "overview";
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
    const routeServerId = typeof route.params.serverId === "string" ? route.params.serverId : "";
    const nextServerId = routeServerId || selectedServerId.value || data.servers[0]?.id || "";
    if (nextServerId) {
      selectedServerId.value = nextServerId;
    }
    if (route.name === "server-detail" && selectedServerId.value) {
      await loadServerLogs(selectedServerId.value);
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
  } catch (error) {
    showToast("Не удалось загрузить настройки", "error");
    console.error(error);
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
  } catch (error) {
    showToast("Не удалось загрузить логи выбранного сервера", "error");
    selectedServerLogs.value = [];
    console.error(error);
  } finally {
    isLogLoading.value = false;
  }
}

async function loadMonitoring() {
  isMonitoringLoading.value = true;

  try {
    monitoring.value = await requestJson<HostMonitoring>("/api/monitoring");
  } catch (error) {
    showToast("Не удалось загрузить мониторинг хоста", "error");
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
    newServer.value = { name: "", type: "vanilla", version: "1.20.1" };
    await loadDashboard();
    await router.push("/servers");
    showToast("Каркас сервера создан", "success");
  } catch (error) {
    showToast("Не удалось создать каркас сервера", "error");
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

watch(
  () => route.params.serverId,
  async (serverId) => {
    if (typeof serverId === "string" && serverId) {
      await loadServerLogs(serverId);
    }
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
  if (activeTab.value === "monitoring") {
    loadMonitoring();
  }
  loadSettings().then(() => {
    return undefined;
  });
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

        <div class="topbar-actions">
          <button class="primary-button" type="button" @click="openNewServerPage">
            <Plus :size="18" />
            <span>Новый сервер</span>
          </button>
        </div>
      </header>

      <section v-if="activeTab === 'overview'" class="hero-panel">
        <div class="hero-copy">
          <div class="status-pill">
            <CheckCircle2 :size="16" />
            <span>{{ isLoading ? "Синхронизация с backend" : "Агент сервера активен" }}</span>
          </div>
          <h2>Выбираешь сборку, Ksylian разворачивает мир</h2>
          <p>
            Черновой интерфейс для установки CurseForge-сборок, управления процессами,
            бэкапов, логов, файлов и обновлений модов.
          </p>
          <div class="hero-actions">
            <button class="primary-button" type="button">
              <PackagePlus :size="18" />
              <span>Импорт CurseForge</span>
            </button>
            <button class="ghost-button" type="button">
              <UploadCloud :size="18" />
              <span>Загрузить manifest.json</span>
            </button>
          </div>
        </div>
        <div class="hero-mascot">
          <img :src="catMascot" alt="" />
        </div>
      </section>

      <section v-if="activeTab === 'overview'" class="stats-grid" aria-label="Сводка">
        <article class="stat-tile">
          <Server :size="20" />
          <span>Серверы</span>
          <strong>{{ onlineServersCount }}</strong>
        </article>
        <article class="stat-tile mint">
          <Gauge :size="20" />
          <span>Средняя нагрузка</span>
          <strong>17%</strong>
        </article>
        <article class="stat-tile amber">
          <HardDrive :size="20" />
          <span>Хранилище</span>
          <strong>72 GB</strong>
        </article>
        <article class="stat-tile graphite">
          <ShieldCheck :size="20" />
          <span>Последний бэкап</span>
          <strong>22:40</strong>
        </article>
      </section>

      <section class="content-grid" :class="{ 'single-column': activeTab !== 'overview' }">
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

          <section v-if="activeTab === 'overview' || (activeTab === 'servers' && serverView === 'list')" class="panel">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">instances</p>
                <h2>{{ activeTab === 'servers' ? 'Полный список серверов' : 'Серверы' }}</h2>
              </div>
              <button class="ghost-button compact" type="button" @click="loadDashboard">
                <RefreshCw :size="16" />
                <span>Обновить</span>
              </button>
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
              >
                <button class="server-main server-select" type="button" @click="openServerPanel(server.id)">
                  <span class="server-state" :class="server.state"></span>
                  <div>
                    <h3>{{ server.name }}</h3>
                    <p>{{ server.pack }} · {{ server.version }} · {{ server.address }}</p>
                  </div>
                </button>

                <div class="server-metrics">
                  <span>{{ server.players }}</span>
                  <span>{{ server.ram }}</span>
                  <span>{{ server.disk }}</span>
                </div>

                <div class="server-actions" :aria-label="`Действия для ${server.name}`">
                  <button
                    class="icon-button"
                    type="button"
                    title="Запустить"
                    @click="runServerAction(server.id, 'start')"
                  >
                    <Play :size="17" />
                  </button>
                  <button
                    class="icon-button"
                    type="button"
                    title="Перезагрузить"
                    @click="runServerAction(server.id, 'restart')"
                  >
                    <ListRestart :size="17" />
                  </button>
                  <button
                    class="icon-button danger"
                    type="button"
                    title="Остановить"
                    @click="runServerAction(server.id, 'stop')"
                  >
                    <CircleStop :size="17" />
                  </button>
                  <button class="icon-button" type="button" title="Открыть" @click="openServerPanel(server.id)">
                    <ChevronRight :size="17" />
                  </button>
                  <button
                    v-if="activeTab === 'servers'"
                    class="icon-button danger"
                    type="button"
                    title="Удалить"
                    @click="deleteServer(server.id)"
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

          <section v-if="activeTab === 'overview'" class="panel terminal-panel">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">live output</p>
                <h2>Логи</h2>
              </div>
              <button class="ghost-button compact" type="button">
                <Download :size="16" />
                <span>Скачать</span>
              </button>
            </div>
            <pre><code v-for="line in logs" :key="line">{{ line }}
</code></pre>
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
                <button class="primary-button" type="button" @click="createBackup(selectedServer.id)">
                  <FileArchive :size="18" />
                  <span>Бэкап</span>
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

            <section class="server-management-grid">
              <section class="panel terminal-panel">
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
                <pre><code v-for="line in selectedServerLogs" :key="line">{{ line }}
</code><code v-if="!selectedServerLogs.length">Логов для выбранного сервера пока нет.
</code></pre>
              </section>

              <div class="server-side-stack">
                <section class="panel">
                  <div class="panel-heading">
                    <div>
                      <p class="eyebrow">mods</p>
                      <h2>Моды</h2>
                    </div>
                    <button class="icon-button" type="button" title="Проверить обновления" @click="checkMods">
                      <PackagePlus :size="18" />
                    </button>
                  </div>
                  <div class="stack-list">
                    <article v-for="mod in mods" :key="mod.id" class="stack-item">
                      <Box :size="18" />
                      <div>
                        <strong>{{ mod.name }}</strong>
                        <span>{{ mod.status }}</span>
                      </div>
                      <i :class="mod.tag"></i>
                    </article>
                  </div>
                </section>

                <section class="panel">
                  <div class="panel-heading">
                    <div>
                      <p class="eyebrow">snapshots</p>
                      <h2>Бэкапы</h2>
                    </div>
                    <button class="icon-button" type="button" title="Создать бэкап" @click="createBackup(selectedServer.id)">
                      <FileArchive :size="18" />
                    </button>
                  </div>
                  <div class="stack-list">
                    <article v-for="backup in selectedServerBackups" :key="backup.id" class="stack-item">
                      <Archive :size="18" />
                      <div>
                        <strong>{{ backup.name }}</strong>
                        <span>{{ backup.size }} · {{ backup.created }}</span>
                      </div>
                    </article>
                    <article v-if="!selectedServerBackups.length" class="stack-item muted">
                      <Archive :size="18" />
                      <div>
                        <strong>Бэкапов пока нет</strong>
                        <span>Можно создать первый вручную</span>
                      </div>
                    </article>
                  </div>
                </section>
              </div>
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

          <section v-if="activeTab === 'backups'" class="panel">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">snapshots</p>
                <h2>Резервные копии</h2>
              </div>
              <button class="icon-button" type="button" title="Создать бэкап" @click="() => createBackup()">
                <FileArchive :size="18" />
              </button>
            </div>
            <div class="stack-list expanded-list">
              <article v-for="backup in backups" :key="backup.id" class="stack-item">
                <Archive :size="18" />
                <div>
                  <strong>{{ backup.name }}</strong>
                  <span>{{ backup.size }} · {{ backup.created }}</span>
                </div>
              </article>
            </div>
          </section>

          <section v-if="activeTab === 'files'" class="panel">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">server files</p>
                <h2>Файлы</h2>
              </div>
              <button class="icon-button" type="button" title="Домой">
                <Home :size="18" />
              </button>
            </div>
            <div class="file-list expanded-list">
              <button v-for="file in files" :key="file.name" type="button" class="file-row">
                <component :is="file.kind === 'folder' ? Folder : FileText" :size="18" />
                <span>{{ file.name }}</span>
                <small>{{ file.meta }}</small>
              </button>
            </div>
          </section>

          <SettingsPage
            v-if="activeTab === 'settings'"
            v-model:curse-forge-api-key="curseForgeApiKey"
            :settings="settings"
            :is-saving="isSavingSettings"
            @refresh="loadDashboard"
            @save="saveSettings"
            @clear="clearCurseForgeKey"
          />
        </div>

        <aside v-if="activeTab === 'overview'" class="side-column">
          <section class="panel">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">backups</p>
                <h2>Резервные копии</h2>
              </div>
              <button class="icon-button" type="button" title="Создать бэкап" @click="() => createBackup()">
                <FileArchive :size="18" />
              </button>
            </div>
            <div class="stack-list">
              <article v-for="backup in backups" :key="backup.id" class="stack-item">
                <Archive :size="18" />
                <div>
                  <strong>{{ backup.name }}</strong>
                  <span>{{ backup.size }} · {{ backup.created }}</span>
                </div>
              </article>
            </div>
          </section>

          <section class="panel">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">curseforge</p>
                <h2>Моды</h2>
              </div>
              <button class="icon-button" type="button" title="Проверить обновления" @click="checkMods">
                <RefreshCw :size="18" />
              </button>
            </div>
            <div class="stack-list">
              <article v-for="mod in mods" :key="mod.id" class="stack-item">
                <Box :size="18" />
                <div>
                  <strong>{{ mod.name }}</strong>
                  <span>{{ mod.status }}</span>
                </div>
                <i :class="mod.tag"></i>
              </article>
            </div>
          </section>

          <section class="panel">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">files</p>
                <h2>Файлы</h2>
              </div>
              <button class="icon-button" type="button" title="Домой">
                <Home :size="18" />
              </button>
            </div>
            <div class="file-list">
              <button v-for="file in files" :key="file.name" type="button" class="file-row">
                <component :is="file.kind === 'folder' ? Folder : FileText" :size="18" />
                <span>{{ file.name }}</span>
                <small>{{ file.meta }}</small>
              </button>
            </div>
          </section>

          <section class="love-note">
            <img :src="catPaw" alt="" />
            <span>Pink mode включён для Ксюши</span>
            <Clock3 :size="16" />
          </section>
        </aside>
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
