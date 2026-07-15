<script setup lang="ts">
import { computed, onMounted, ref, watch, type Component } from "vue";
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
  ExternalLink,
  FileArchive,
  FileText,
  Folder,
  Gauge,
  HardDrive,
  Heart,
  Home,
  LayoutDashboard,
  ListRestart,
  MemoryStick,
  PackagePlus,
  Play,
  Plus,
  RefreshCw,
  Search,
  Server,
  Settings,
  ShieldCheck,
  Trash2,
  UploadCloud,
  Users,
  X,
} from "@lucide/vue";
import catLogo from "./assets/cat-logo.svg";
import catPaw from "./assets/cat-paw.svg";
import catMascot from "./assets/ksylian-cat.png";

type ServerState = "online" | "deploying" | "offline";
type TabId = "overview" | "servers" | "modpacks" | "files" | "backups" | "settings";
type CurseForgeKind = "mods" | "modpacks";
type CurseForgeLoader = "any" | "forge" | "fabric" | "quilt" | "neoforge";
type CurseForgeSort = "popularity" | "updated" | "name" | "downloads";

interface GameServer {
  id: string;
  name: string;
  pack: string;
  version: string;
  state: ServerState;
  players: string;
  ram: string;
  cpu: number;
  disk: string;
  address: string;
}

interface BackupItem {
  id: string;
  name: string;
  size: string;
  created: string;
  server_id: string;
}

interface ModItem {
  id: string;
  name: string;
  status: string;
  tag: "required" | "update" | "review";
}

interface FileItem {
  name: string;
  meta: string;
  kind: "folder" | "file";
}

interface DashboardPayload {
  servers: GameServer[];
  logs: string[];
  backups: BackupItem[];
  mods: ModItem[];
  files: FileItem[];
}

interface SettingsPayload {
  has_curseforge_api_key: boolean;
  curseforge_api_key_mask: string;
}

interface CurseForgeProject {
  id: number;
  name: string;
  slug: string;
  summary: string;
  type: CurseForgeKind;
  downloads: number;
  date_modified: string;
  icon_url: string;
  website_url: string;
  latest_file_id: number | null;
  game_versions: string[];
  loaders: string[];
}

interface CurseForgeSearchPayload {
  items: CurseForgeProject[];
  total_count: number;
  has_api_key: boolean;
}

const navItems: Array<{ id: TabId; label: string; icon: Component }> = [
  { id: "overview", label: "Обзор", icon: LayoutDashboard },
  { id: "servers", label: "Серверы", icon: Server },
  { id: "modpacks", label: "CurseForge", icon: PackagePlus },
  { id: "files", label: "Файлы", icon: Folder },
  { id: "backups", label: "Бэкапы", icon: Archive },
  { id: "settings", label: "Настройки", icon: Settings },
];

const tabCopy: Record<TabId, { title: string; eyebrow: string }> = {
  overview: { title: "Панель управления серверами", eyebrow: "Minecraft orchestration" },
  servers: { title: "Серверы", eyebrow: "instances" },
  modpacks: { title: "CurseForge", eyebrow: "integration" },
  files: { title: "Файловый менеджер", eyebrow: "server files" },
  backups: { title: "Резервные копии", eyebrow: "snapshots" },
  settings: { title: "Настройки", eyebrow: "configuration" },
};

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

const routePaths: Record<TabId, string> = {
  overview: "/",
  servers: "/servers",
  modpacks: "/modpacks",
  files: "/files",
  backups: "/backups",
  settings: "/settings",
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
const isSavingSettings = ref(false);
const apiError = ref("");
const settingsMessage = ref("");
const curseForgeApiKey = ref("");
const settings = ref<SettingsPayload>({
  has_curseforge_api_key: false,
  curseforge_api_key_mask: "",
});
const curseForgeKind = ref<CurseForgeKind>("modpacks");
const curseForgeQuery = ref("");
const curseForgeVersion = ref("1.20.1");
const curseForgeLoader = ref<CurseForgeLoader>("fabric");
const curseForgeSort = ref<CurseForgeSort>("popularity");
const curseForgeItems = ref<CurseForgeProject[]>([]);
const selectedCurseForgeProject = ref<CurseForgeProject | null>(null);
const isCurseForgeLoading = ref(false);
const curseForgeError = ref("");
const selectedServerId = ref("");
const selectedServerLogs = ref<string[]>(fallbackLogs);
const isCreateServerOpen = ref(false);
const newServer = ref({
  name: "",
  pack: "",
  version: "1.20.1",
  address: "",
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
const curseForgeKindLabel = computed(() =>
  curseForgeKind.value === "modpacks" ? "сборок" : "модов",
);
const selectedProjectVersions = computed(() =>
  selectedCurseForgeProject.value?.game_versions.slice(0, 6).join(", ") || "версии не указаны",
);
const selectedProjectLoaders = computed(() =>
  selectedCurseForgeProject.value?.loaders.join(", ") || "любой совместимый лоадер",
);
const activeTab = computed<TabId>(() => {
  if (route.name === "server-detail") {
    return "servers";
  }
  return (route.name as TabId | undefined) ?? "overview";
});
const serverView = computed<"list" | "detail">(() =>
  route.name === "server-detail" ? "detail" : "list",
);
const activeTabCopy = computed(() => tabCopy[activeTab.value]);
const pageEyebrow = computed(() =>
  activeTab.value === "servers" && serverView.value === "detail" ? "server control" : activeTabCopy.value.eyebrow,
);
const pageTitle = computed(() =>
  activeTab.value === "servers" && serverView.value === "detail" && selectedServer.value
    ? selectedServer.value.name
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

async function openServerPanel(serverId: string) {
  selectedServerId.value = serverId;
  await router.push(`/servers/${serverId}`);
}

function backToServerList() {
  router.push("/servers");
}

function selectTab(tabId: TabId) {
  router.push(routePaths[tabId]);
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("ru-RU", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function formatDate(value: string) {
  if (!value) {
    return "дата неизвестна";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "дата неизвестна";
  }

  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short", year: "numeric" }).format(date);
}

function setCurseForgeKind(kind: CurseForgeKind) {
  curseForgeKind.value = kind;
  selectedCurseForgeProject.value = null;
}

async function searchCurseForge() {
  isCurseForgeLoading.value = true;
  curseForgeError.value = "";
  apiError.value = "";

  const params = new URLSearchParams({
    kind: curseForgeKind.value,
    query: curseForgeQuery.value,
    minecraft_version: curseForgeVersion.value,
    loader: curseForgeLoader.value,
    sort: curseForgeSort.value,
    page_size: "24",
  });

  try {
    const data = await requestJson<CurseForgeSearchPayload>(`/api/curseforge/search?${params.toString()}`);
    curseForgeItems.value = data.items;
    selectedCurseForgeProject.value = data.items[0] ?? null;
    if (!data.items.length) {
      curseForgeError.value = "По таким фильтрам ничего не найдено";
    }
  } catch (error) {
    curseForgeItems.value = [];
    selectedCurseForgeProject.value = null;
    curseForgeError.value = settings.value.has_curseforge_api_key
      ? "Не удалось получить каталог CurseForge. Проверь ключ или попробуй другие фильтры"
      : "Добавь CurseForge API key в настройках, чтобы открыть каталог";
    console.error(error);
  } finally {
    isCurseForgeLoading.value = false;
  }
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
      body: JSON.stringify(newServer.value),
    });
    isCreateServerOpen.value = false;
    newServer.value = { name: "", pack: "", version: "1.20.1", address: "" };
    await loadDashboard();
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
    if (tabId === "modpacks" && !curseForgeItems.value.length && !isCurseForgeLoading.value) {
      searchCurseForge();
    }
  },
);

onMounted(() => {
  loadDashboard();
  loadSettings().then(() => {
    if (activeTab.value === "modpacks") {
      searchCurseForge();
    }
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
          :class="{ active: activeTab === item.id }"
          type="button"
          @click="selectTab(item.id)"
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

    <section class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">{{ pageEyebrow }}</p>
          <h1>{{ pageTitle }}</h1>
        </div>

        <div class="topbar-actions">
          <button class="primary-button" type="button" @click="isCreateServerOpen = true">
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

          <section v-if="activeTab === 'modpacks'" class="panel curseforge-panel">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">curseforge</p>
                <h2>Интеграция CurseForge</h2>
              </div>
              <button class="icon-button" type="button" title="Обновить каталог" @click="searchCurseForge">
                <RefreshCw :size="18" />
              </button>
            </div>

            <form class="catalog-toolbar" @submit.prevent="searchCurseForge">
              <div class="segmented-control" aria-label="Тип проекта">
                <button
                  type="button"
                  :class="{ active: curseForgeKind === 'modpacks' }"
                  @click="setCurseForgeKind('modpacks')"
                >
                  Сборки
                </button>
                <button
                  type="button"
                  :class="{ active: curseForgeKind === 'mods' }"
                  @click="setCurseForgeKind('mods')"
                >
                  Моды
                </button>
              </div>

              <label class="catalog-search">
                <Search :size="18" />
                <input v-model="curseForgeQuery" type="search" placeholder="Поиск по CurseForge" />
              </label>

              <label>
                <span>Версия</span>
                <select v-model="curseForgeVersion">
                  <option value="">Любая</option>
                  <option value="1.21.1">1.21.1</option>
                  <option value="1.20.1">1.20.1</option>
                  <option value="1.19.2">1.19.2</option>
                  <option value="1.18.2">1.18.2</option>
                </select>
              </label>

              <label>
                <span>Лоадер</span>
                <select v-model="curseForgeLoader">
                  <option value="any">Любой</option>
                  <option value="fabric">Fabric</option>
                  <option value="forge">Forge</option>
                  <option value="neoforge">NeoForge</option>
                  <option value="quilt">Quilt</option>
                </select>
              </label>

              <label>
                <span>Сортировка</span>
                <select v-model="curseForgeSort">
                  <option value="popularity">Популярные</option>
                  <option value="downloads">Скачивания</option>
                  <option value="updated">Недавно обновлены</option>
                  <option value="name">По названию</option>
                </select>
              </label>

              <button class="primary-button" type="submit" :disabled="isCurseForgeLoading">
                <Search :size="18" />
                <span>{{ isCurseForgeLoading ? 'Ищу' : 'Найти' }}</span>
              </button>
            </form>

            <div v-if="curseForgeError" class="catalog-notice">
              {{ curseForgeError }}
            </div>

            <div class="catalog-layout">
              <section class="catalog-results" :aria-label="`Каталог ${curseForgeKindLabel}`">
                <button
                  v-for="project in curseForgeItems"
                  :key="project.id"
                  class="project-card"
                  :class="{ selected: selectedCurseForgeProject?.id === project.id }"
                  type="button"
                  @click="selectedCurseForgeProject = project"
                >
                  <img v-if="project.icon_url" :src="project.icon_url" alt="" />
                  <span v-else class="project-icon-fallback">
                    <PackagePlus :size="22" />
                  </span>
                  <div>
                    <strong>{{ project.name }}</strong>
                    <p>{{ project.summary || 'Описание пока не заполнено автором проекта' }}</p>
                    <span>
                      {{ formatNumber(project.downloads) }} скачиваний · {{ formatDate(project.date_modified) }}
                    </span>
                  </div>
                </button>

                <article v-if="isCurseForgeLoading" class="project-card muted">
                  <span class="project-icon-fallback">
                    <RefreshCw :size="22" />
                  </span>
                  <div>
                    <strong>Загружаю каталог</strong>
                    <p>Подбираю проекты по текущим фильтрам.</p>
                  </div>
                </article>
              </section>

              <aside class="project-details">
                <template v-if="selectedCurseForgeProject">
                  <div class="project-details-head">
                    <img v-if="selectedCurseForgeProject.icon_url" :src="selectedCurseForgeProject.icon_url" alt="" />
                    <span v-else class="project-icon-fallback">
                      <PackagePlus :size="24" />
                    </span>
                    <div>
                      <p class="eyebrow">{{ selectedCurseForgeProject.type === 'modpacks' ? 'modpack' : 'mod' }}</p>
                      <h3>{{ selectedCurseForgeProject.name }}</h3>
                    </div>
                  </div>

                  <p class="project-summary">{{ selectedCurseForgeProject.summary }}</p>

                  <dl class="project-facts">
                    <div>
                      <dt>Скачивания</dt>
                      <dd>{{ formatNumber(selectedCurseForgeProject.downloads) }}</dd>
                    </div>
                    <div>
                      <dt>Версии</dt>
                      <dd>{{ selectedProjectVersions }}</dd>
                    </div>
                    <div>
                      <dt>Лоадеры</dt>
                      <dd>{{ selectedProjectLoaders }}</dd>
                    </div>
                    <div>
                      <dt>Обновлено</dt>
                      <dd>{{ formatDate(selectedCurseForgeProject.date_modified) }}</dd>
                    </div>
                  </dl>

                  <div class="project-actions">
                    <a
                      v-if="selectedCurseForgeProject.website_url"
                      class="ghost-button"
                      :href="selectedCurseForgeProject.website_url"
                      target="_blank"
                      rel="noreferrer"
                    >
                      <ExternalLink :size="17" />
                      <span>Открыть CurseForge</span>
                    </a>
                    <button class="primary-button" type="button" disabled>
                      <PackagePlus :size="18" />
                      <span>Подключить позже</span>
                    </button>
                  </div>
                </template>

                <template v-else>
                  <div class="empty-details">
                    <PackagePlus :size="28" />
                    <strong>Выбери проект</strong>
                    <span>Здесь появятся версии, лоадеры, скачивания и ссылка на CurseForge.</span>
                  </div>
                </template>
              </aside>
            </div>
          </section>

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

          <section v-if="activeTab === 'settings'" class="panel settings-panel">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">configuration</p>
                <h2>Настройки проекта</h2>
              </div>
              <button class="icon-button" type="button" title="Обновить" @click="loadDashboard">
                <RefreshCw :size="18" />
              </button>
            </div>
            <div class="settings-layout">
              <form class="settings-form" @submit.prevent="saveSettings">
                <div class="settings-section-head">
                  <div>
                    <p class="eyebrow">curseforge</p>
                    <h3>Интеграция с каталогом</h3>
                  </div>
                  <span class="settings-status" :class="{ connected: settings.has_curseforge_api_key }">
                    {{ settings.has_curseforge_api_key ? 'Подключено' : 'Не подключено' }}
                  </span>
                </div>

                <div class="settings-current">
                  <span>Текущий ключ</span>
                  <strong>
                    {{ settings.has_curseforge_api_key ? settings.curseforge_api_key_mask : 'не задан' }}
                  </strong>
                </div>

                <label>
                  <span>CurseForge API key</span>
                  <input
                    v-model="curseForgeApiKey"
                    autocomplete="off"
                    spellcheck="false"
                    type="password"
                    placeholder="Вставь новый ключ"
                  />
                </label>

                <p class="settings-hint">
                  Ключ хранится только на backend. В браузер возвращается только статус и маска.
                </p>

                <div class="form-actions">
                  <button class="ghost-button" type="button" @click="clearCurseForgeKey">
                    Очистить
                  </button>
                  <button class="primary-button" type="submit" :disabled="isSavingSettings">
                    <ShieldCheck :size="18" />
                    <span>{{ isSavingSettings ? 'Сохраняю' : 'Сохранить' }}</span>
                  </button>
                </div>
                <p v-if="settingsMessage" class="settings-message">{{ settingsMessage }}</p>
              </form>

              <section class="settings-summary" aria-label="Системная информация">
                <div class="settings-section-head">
                  <div>
                    <p class="eyebrow">system</p>
                    <h3>Окружение</h3>
                  </div>
                </div>
                <dl>
                  <div>
                    <dt>Backend</dt>
                    <dd>Подключён через /api</dd>
                  </div>
                  <div>
                    <dt>Deploy</dt>
                    <dd>GitHub tag → self-hosted runner</dd>
                  </div>
                  <div>
                    <dt>Frontend port</dt>
                    <dd>8088</dd>
                  </div>
                  <div>
                    <dt>Backend port</dt>
                    <dd>8090</dd>
                  </div>
                </dl>
              </section>
            </div>
          </section>
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

    <div v-if="isCreateServerOpen" class="modal-layer" role="dialog" aria-modal="true" aria-labelledby="create-server-title">
      <section class="modal-panel">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">new instance</p>
            <h2 id="create-server-title">Новый сервер</h2>
          </div>
          <button class="icon-button" type="button" title="Закрыть" @click="isCreateServerOpen = false">
            <X :size="18" />
          </button>
        </div>

        <form class="server-form" @submit.prevent="createServer">
          <label>
            <span>Название</span>
            <input v-model="newServer.name" required type="text" placeholder="Например, Ksy Survival" />
          </label>
          <label>
            <span>Сборка</span>
            <input v-model="newServer.pack" required type="text" placeholder="CurseForge pack или manifest" />
          </label>
          <label>
            <span>Версия Minecraft</span>
            <input v-model="newServer.version" required type="text" placeholder="1.20.1" />
          </label>
          <label>
            <span>Адрес</span>
            <input v-model="newServer.address" type="text" placeholder="server.ksylian.ru:25566" />
          </label>

          <p class="form-note">
            Сейчас форма готовит контракт интерфейса. Для реального создания ещё нужен provisioner,
            который будет скачивать сборку, выделять порт, создавать папку и systemd-службу.
          </p>

          <div class="form-actions">
            <button class="ghost-button" type="button" @click="isCreateServerOpen = false">Отмена</button>
            <button class="primary-button" type="submit">
              <Plus :size="18" />
              <span>Создать</span>
            </button>
          </div>
        </form>
      </section>
    </div>

    <span class="build-badge">{{ buildLabel }}</span>
  </main>
</template>
