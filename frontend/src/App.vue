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

const fallbackServers: GameServer[] = [
  {
    id: "ksy-vanilla",
    name: "Ksy Vanilla+",
    pack: "Better MC Fabric",
    version: "1.20.1",
    state: "online",
    players: "12 / 48",
    ram: "8.2 / 16 GB",
    cpu: 34,
    disk: "42 GB",
    address: "play.ksylian.local:25565",
  },
  {
    id: "pink-nether",
    name: "Pink Nether",
    pack: "Prominence II",
    version: "1.20.1",
    state: "deploying",
    players: "0 / 32",
    ram: "2.1 / 12 GB",
    cpu: 18,
    disk: "18 GB",
    address: "pink.ksylian.local:25566",
  },
  {
    id: "archive-realm",
    name: "Archive Realm",
    pack: "Create: Perfect World",
    version: "1.19.2",
    state: "offline",
    players: "0 / 24",
    ram: "0 / 10 GB",
    cpu: 0,
    disk: "31 GB",
    address: "archive.ksylian.local:25567",
  },
];

const fallbackLogs = [
  "[23:04:11] Server thread/INFO Starting Minecraft server version 1.20.1",
  "[23:04:19] Loader/INFO Loaded 143 mods from CurseForge manifest",
  "[23:04:28] Backup/INFO Snapshot world-2026-07-15 completed",
  "[23:05:02] Proxy/INFO Velocity route registered: pink.ksylian.local",
  "[23:05:35] Mods/INFO 4 updates available for review",
];

const fallbackBackups: BackupItem[] = [
  { id: "backup-1", name: "world-before-update", size: "6.8 GB", created: "Сегодня, 22:40", server_id: "ksy-vanilla" },
  { id: "backup-2", name: "pink-nether-auto", size: "3.1 GB", created: "Сегодня, 20:15", server_id: "pink-nether" },
  { id: "backup-3", name: "archive-realm-monthly", size: "12.4 GB", created: "13 июля", server_id: "archive-realm" },
];

const fallbackMods: ModItem[] = [
  { id: "fabric-api", name: "Fabric API", status: "Обновлён", tag: "required" },
  { id: "voice-chat", name: "Simple Voice Chat", status: "Есть апдейт", tag: "update" },
  { id: "world-edit", name: "WorldEdit", status: "Обновлён", tag: "required" },
  { id: "dynmap", name: "Dynmap", status: "Проверить", tag: "review" },
];

const fallbackFiles: FileItem[] = [
  { name: "world", meta: "Папка мира", kind: "folder" },
  { name: "mods", meta: "143 файла", kind: "folder" },
  { name: "server.properties", meta: "1.2 KB", kind: "file" },
  { name: "latest.log", meta: "284 KB", kind: "file" },
];

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
const servers = ref<GameServer[]>(fallbackServers);
const logs = ref<string[]>(fallbackLogs);
const backups = ref<BackupItem[]>(fallbackBackups);
const mods = ref<ModItem[]>(fallbackMods);
const files = ref<FileItem[]>(fallbackFiles);
const isLoading = ref(false);
const isLogLoading = ref(false);
const isMonitoringLoading = ref(false);
const isSavingSettings = ref(false);
const apiError = ref("");
const settingsMessage = ref("");
const curseForgeApiKey = ref("");
const settings = ref<SettingsPayload>({
  has_curseforge_api_key: false,
  curseforge_api_key_mask: "",
});
const selectedServerId = ref("");
const selectedServerLogs = ref<string[]>(fallbackLogs);
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
  apiError.value = "";

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
    apiError.value = "Backend пока недоступен, показываю локальные данные";
    console.error(error);
  } finally {
    isLoading.value = false;
  }
}

async function loadSettings() {
  try {
    settings.value = await requestJson<SettingsPayload>("/api/settings");
  } catch (error) {
    apiError.value = "Не удалось загрузить настройки";
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
    apiError.value = "Не удалось загрузить логи выбранного сервера";
    selectedServerLogs.value = [];
    console.error(error);
  } finally {
    isLogLoading.value = false;
  }
}

async function loadMonitoring() {
  isMonitoringLoading.value = true;
  apiError.value = "";

  try {
    monitoring.value = await requestJson<HostMonitoring>("/api/monitoring");
  } catch (error) {
    apiError.value = "Не удалось загрузить мониторинг хоста";
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
    apiError.value = "Не удалось выполнить действие";
    console.error(error);
  }
}

async function createServer() {
  apiError.value = "";

  try {
    await requestJson("/api/servers", {
      method: "POST",
      body: JSON.stringify({
        name: newServer.value.name,
        pack: serverTypeLabels[newServer.value.type],
        version: newServer.value.version,
        address: "",
      }),
    });
    newServer.value = { name: "", type: "vanilla", version: "1.20.1" };
    await loadDashboard();
    await router.push("/servers");
  } catch (error) {
    apiError.value = "Создание настоящих серверов ещё требует provisioner на backend";
    console.error(error);
  }
}

async function deleteServer(serverId: string) {
  apiError.value = "";

  try {
    await requestJson(`/api/servers/${serverId}`, { method: "DELETE" });
    await loadDashboard();
  } catch (error) {
    apiError.value = "Удаление настоящих systemd-серверов пока заблокировано";
    console.error(error);
  }
}

async function createBackup(serverId = selectedServer.value?.id ?? servers.value[0]?.id ?? "ksy-vanilla") {
  try {
    await requestJson(`/api/backups?server_id=${encodeURIComponent(serverId)}`, { method: "POST" });
    await loadDashboard();
  } catch (error) {
    apiError.value = "Не удалось создать резервную копию";
    console.error(error);
  }
}

async function checkMods() {
  try {
    await requestJson("/api/mods/check", { method: "POST" });
    await loadDashboard();
  } catch (error) {
    apiError.value = "Не удалось проверить обновления модов";
    console.error(error);
  }
}

async function saveSettings() {
  isSavingSettings.value = true;
  settingsMessage.value = "";
  apiError.value = "";

  try {
    settings.value = await requestJson<SettingsPayload>("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ curseforge_api_key: curseForgeApiKey.value }),
    });
    curseForgeApiKey.value = "";
    settingsMessage.value = settings.value.has_curseforge_api_key
      ? "Ключ CurseForge сохранён"
      : "Ключ CurseForge очищен";
  } catch (error) {
    apiError.value = "Не удалось сохранить ключ CurseForge";
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
          <p v-if="apiError" class="api-error">{{ apiError }}</p>
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

          <section v-if="activeTab === 'servers' && serverView === 'list'" class="server-summary-grid" aria-label="Сводка серверов">
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

            <div class="server-list">
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
            :message="settingsMessage"
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

    <span class="build-badge">{{ buildLabel }}</span>
  </main>
</template>
