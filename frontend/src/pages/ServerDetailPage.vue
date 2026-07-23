<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import {
  CircleStop,
  Cpu,
  FileText,
  Folder,
  HardDrive,
  ListRestart,
  MemoryStick,
  Package,
  Play,
  RefreshCw,
  Users,
} from "@lucide/vue";
import { stateLabels, useDashboardStore } from "../composables/useDashboardStore";
import { requestJson } from "../services/api";
import type { RconCommandResult } from "../types";
import { serverDetailTabs, type ServerDetailTab } from "./serverDetailTabs";

const route = useRoute();
const store = useDashboardStore();
const activeServerDetailTab = ref<ServerDetailTab>("overview");
const logConsole = ref<HTMLPreElement | null>(null);
const shouldStickToLogBottom = ref(true);
const isLogAutoScrollPaused = ref(false);
const logSearch = ref("");
const rconCommand = ref("");
const rconOutput = ref("");
const rconHistory = ref<string[]>([]);
const isRconSending = ref(false);
const newFolderName = ref("");
const fileEditorContent = ref("");
const fileSearchQuery = ref("");
const fileUploadInput = ref<HTMLInputElement | null>(null);
const modUploadInput = ref<HTMLInputElement | null>(null);
const modBulkUpdateInput = ref<HTMLInputElement | null>(null);
const modUpdateInput = ref<HTMLInputElement | null>(null);
const pendingModUpdatePath = ref("");
const logLevels = ref<Record<"INFO" | "WARN" | "ERROR" | "FATAL", boolean>>({
  INFO: true,
  WARN: true,
  ERROR: true,
  FATAL: true,
});
let logSocket: WebSocket | undefined;

const filteredServerLogs = computed(() => {
  const query = logSearch.value.trim().toLowerCase();
  return store.selectedServerLogs.value.filter((line) => {
    const upperLine = line.toUpperCase();
    const hasKnownLevel = Object.keys(logLevels.value).some((level) => upperLine.includes(level));
    const matchesLevel = Object.entries(logLevels.value).some(
      ([level, enabled]) => enabled && upperLine.includes(level),
    );
    const matchesSearch = !query || line.toLowerCase().includes(query);
    return matchesSearch && (!hasKnownLevel || matchesLevel);
  });
});

function updateLogStickiness() {
  if (isLogAutoScrollPaused.value) {
    shouldStickToLogBottom.value = false;
    return;
  }
  const consoleElement = logConsole.value;
  if (!consoleElement) {
    shouldStickToLogBottom.value = true;
    return;
  }

  const distanceFromBottom = consoleElement.scrollHeight - consoleElement.scrollTop - consoleElement.clientHeight;
  shouldStickToLogBottom.value = distanceFromBottom < 48;
}

async function scrollLogsIfNeeded() {
  if (isLogAutoScrollPaused.value || !shouldStickToLogBottom.value) {
    return;
  }

  await nextTick();
  const consoleElement = logConsole.value;
  if (consoleElement) {
    consoleElement.scrollTop = consoleElement.scrollHeight;
  }
}

async function loadCurrentTabData() {
  const serverId = typeof route.params.serverId === "string" ? route.params.serverId : "";
  store.selectedServerId.value = serverId;
  if (!serverId) {
    return;
  }

  if (activeServerDetailTab.value === "logs") {
    await store.loadServerLogs(serverId);
    await scrollLogsIfNeeded();
  }
  if (activeServerDetailTab.value === "diagnostics") {
    await store.loadServerCrashReports(serverId);
  }
  if (activeServerDetailTab.value === "files") {
    await store.loadServerFiles(serverId);
  }
  if (activeServerDetailTab.value === "mods") {
    await store.loadServerMods(serverId);
  }
  if (activeServerDetailTab.value === "settings") {
    await store.loadServerConfig(serverId);
  }
}

async function refreshLogs() {
  await store.loadServerLogs();
  await scrollLogsIfNeeded();
}

function startLogStream() {
  const serverId = typeof route.params.serverId === "string" ? route.params.serverId : "";
  const token = window.localStorage.getItem("ksylian_auth_token") || "";
  if (logSocket || activeServerDetailTab.value !== "logs" || !serverId || !token) {
    return;
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  logSocket = new WebSocket(`${protocol}//${window.location.host}/api/servers/${serverId}/logs/ws?token=${encodeURIComponent(token)}`);
  logSocket.onmessage = async (event) => {
    const payload = JSON.parse(event.data) as { lines?: string[] };
    if (Array.isArray(payload.lines)) {
      store.selectedServerLogs.value = payload.lines;
      await scrollLogsIfNeeded();
    }
  };
  logSocket.onclose = () => {
    logSocket = undefined;
  };
}

function stopLogStream() {
  if (logSocket) {
    logSocket.close();
    logSocket = undefined;
  }
}

function toggleLogAutoScroll() {
  isLogAutoScrollPaused.value = !isLogAutoScrollPaused.value;
  if (!isLogAutoScrollPaused.value) {
    shouldStickToLogBottom.value = true;
    scrollLogsIfNeeded();
  }
}

async function downloadFullLogs() {
  const server = store.selectedServer.value;
  if (!server) {
    return;
  }
  const headers = new Headers();
  const token = window.localStorage.getItem("ksylian_auth_token");
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`/api/servers/${server.id}/logs/download`, { headers });
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${server.name}-logs.txt`;
  link.click();
  URL.revokeObjectURL(url);
}

async function sendRconCommand() {
  const server = store.selectedServer.value;
  const command = rconCommand.value.trim();
  if (!server || !command || isRconSending.value) {
    return;
  }
  isRconSending.value = true;
  try {
    const result = await requestJson<RconCommandResult>(`/api/servers/${server.id}/rcon/command`, {
      method: "POST",
      body: JSON.stringify({ command }),
    });
    rconOutput.value = result.output || "Команда выполнена";
    rconHistory.value = [command, ...rconHistory.value.filter((item) => item !== command)].slice(0, 12);
    rconCommand.value = "";
    await refreshLogs();
  } catch (error) {
    rconOutput.value = "RCON недоступен или команда не выполнена";
    console.error(error);
  } finally {
    isRconSending.value = false;
  }
}

function openParentFolder() {
  const current = store.selectedServerFilePath.value;
  if (!current) {
    return;
  }
  const parent = current.split("/").slice(0, -1).join("/");
  store.loadServerFiles(undefined, parent);
}

async function openFileEntry(path: string, kind: "folder" | "file") {
  if (kind === "folder") {
    await store.loadServerFiles(undefined, path);
    return;
  }
  await store.openServerFile(path);
  fileEditorContent.value = store.selectedServerFileContent.value?.encoding === "text"
    ? store.selectedServerFileContent.value.content
    : "";
}

async function createFolder() {
  const name = newFolderName.value.trim();
  if (!name) {
    return;
  }
  const base = store.selectedServerFilePath.value;
  await store.runFileAction("mkdir", [base, name].filter(Boolean).join("/"));
  newFolderName.value = "";
}

async function searchFiles() {
  await store.searchServerFiles(fileSearchQuery.value);
}

async function saveOpenedFile() {
  await store.saveServerFile(fileEditorContent.value);
}

async function uploadSelectedFiles(event: Event) {
  const input = event.target as HTMLInputElement;
  const selectedFiles = Array.from(input.files || []);
  for (const file of selectedFiles) {
    await store.uploadServerFile(file);
  }
  input.value = "";
}

async function installSelectedMods(event: Event) {
  const input = event.target as HTMLInputElement;
  const selectedFiles = Array.from(input.files || []).filter((file) => file.name.endsWith(".jar"));
  await store.installServerMods(selectedFiles);
  input.value = "";
}

async function bulkUpdateSelectedMods(event: Event) {
  const input = event.target as HTMLInputElement;
  const selectedFiles = Array.from(input.files || []).filter((file) => file.name.endsWith(".jar"));
  await store.bulkUpdateServerMods(selectedFiles);
  input.value = "";
}

function chooseModUpdate(path: string) {
  pendingModUpdatePath.value = path;
  modUpdateInput.value?.click();
}

async function updateSelectedMod(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file && pendingModUpdatePath.value) {
    await store.updateServerMod(pendingModUpdatePath.value, file);
  }
  pendingModUpdatePath.value = "";
  input.value = "";
}

async function downloadServerFile(path: string) {
  await store.openServerFile(path);
  const file = store.selectedServerFileContent.value;
  if (!file) {
    return;
  }
  const bytes = file.encoding === "base64"
    ? Uint8Array.from(atob(file.content), (char) => char.charCodeAt(0))
    : new TextEncoder().encode(file.content);
  const blob = new Blob([bytes]);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = file.name;
  link.click();
  URL.revokeObjectURL(url);
}

function selectServerDetailTab(tabId: ServerDetailTab) {
  activeServerDetailTab.value = tabId;
}

watch(
  () => route.params.serverId,
  async () => {
    shouldStickToLogBottom.value = true;
    stopLogStream();
    await loadCurrentTabData();
    if (activeServerDetailTab.value === "logs") {
      startLogStream();
    }
  },
);

watch(
  () => activeServerDetailTab.value,
  async (tabId) => {
    if (tabId === "logs") {
      shouldStickToLogBottom.value = true;
      startLogStream();
      await refreshLogs();
      return;
    }

    stopLogStream();
    if (tabId === "diagnostics") {
      await store.loadServerCrashReports();
    }
    if (tabId === "files") {
      await store.loadServerFiles();
    }
    if (tabId === "mods") {
      await store.loadServerMods();
    }
    if (tabId === "settings") {
      await store.loadServerConfig();
    }
  },
);

watch(
  () => store.selectedServerLogs.value.length,
  () => {
    scrollLogsIfNeeded();
  },
);

onMounted(async () => {
  await loadCurrentTabData();
  if (activeServerDetailTab.value === "logs") {
    startLogStream();
  }
});

onUnmounted(stopLogStream);
</script>

<template>
  <section v-if="store.selectedServer.value" class="server-control">
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
      <section class="server-detail-section">
        <div class="server-detail-section-head">
          <h3>Управление</h3>
          <span class="state-label" :class="store.selectedServer.value.state">
            {{ stateLabels[store.selectedServer.value.state] }}
          </span>
        </div>

        <div class="server-detail-row">
          <span>Адрес</span>
          <strong>{{ store.selectedServer.value.address }}</strong>
        </div>
        <div class="server-detail-row">
          <span>Тип</span>
          <strong>{{ store.selectedServer.value.pack }}</strong>
        </div>
        <div class="server-detail-row">
          <span>Код выхода</span>
          <strong>{{ store.selectedServer.value.exit_code ?? '—' }}</strong>
        </div>
        <div v-if="store.selectedServer.value.last_event" class="server-detail-row">
          <span>Последнее событие</span>
          <strong>{{ store.selectedServer.value.last_event }}</strong>
        </div>
        <div v-if="store.selectedServer.value.warnings?.length" class="server-warning-list">
          <strong v-for="warning in store.selectedServer.value.warnings" :key="warning">{{ warning }}</strong>
        </div>
        <div class="server-detail-actions">
          <button class="icon-button" type="button" title="Запустить" @click="store.runServerAction(store.selectedServer.value.id, 'start')">
            <Play :size="17" />
          </button>
          <button class="icon-button" type="button" title="Перезагрузить" @click="store.runServerAction(store.selectedServer.value.id, 'restart')">
            <ListRestart :size="17" />
          </button>
          <button class="icon-button" type="button" title="Обновить файлы сервера" @click="store.runServerAction(store.selectedServer.value.id, 'update')">
            <RefreshCw :size="17" />
          </button>
          <button class="icon-button" type="button" title="Откатить последнее обновление" @click="store.runServerAction(store.selectedServer.value.id, 'rollback')">
            <ListRestart :size="17" />
          </button>
          <button class="icon-button danger" type="button" title="Остановить" @click="store.runServerAction(store.selectedServer.value.id, 'stop')">
            <CircleStop :size="17" />
          </button>
        </div>
      </section>

      <section class="server-detail-section">
        <div class="server-detail-section-head">
          <h3>Ресурсы</h3>
        </div>
        <article class="server-resource-row">
          <Cpu :size="20" />
          <span>Процессор</span>
          <strong>{{ store.selectedServer.value.cpu }}%</strong>
        </article>
        <article class="server-resource-row">
          <MemoryStick :size="20" />
          <span>Оперативка</span>
          <strong>{{ store.selectedServer.value.ram }}</strong>
        </article>
        <article class="server-resource-row">
          <HardDrive :size="20" />
          <span>Память</span>
          <strong>{{ store.selectedServer.value.disk }}</strong>
        </article>
        <article class="server-resource-row">
          <Users :size="20" />
          <span>Онлайн</span>
          <strong>{{ store.selectedServer.value.players }}</strong>
        </article>
      </section>

      <section class="server-detail-section">
        <div class="server-detail-section-head">
          <h3>Основная информация</h3>
        </div>
        <div class="server-detail-row">
          <span>Версия Minecraft</span>
          <strong>{{ store.selectedServer.value.version }}</strong>
        </div>
        <div class="server-detail-row">
          <span>Пакет</span>
          <strong>{{ store.selectedServer.value.pack }}</strong>
        </div>
        <div class="server-detail-row">
          <span>Статус</span>
          <strong>{{ stateLabels[store.selectedServer.value.state] }}</strong>
        </div>
      </section>
    </section>

    <section v-if="activeServerDetailTab === 'logs'" class="server-tab-panel">
      <section class="server-detail-section terminal-panel server-logs-panel">
        <div class="server-detail-section-head">
          <h3>Логи</h3>
          <div class="panel-actions">
            <button class="ghost-button compact" type="button" @click="toggleLogAutoScroll">
              <span>{{ isLogAutoScrollPaused ? 'Продолжить' : 'Пауза' }}</span>
            </button>
            <button class="ghost-button compact" type="button" @click="downloadFullLogs">
              <span>Скачать</span>
            </button>
            <button class="ghost-button compact" type="button" @click="refreshLogs">
              <RefreshCw :size="16" />
              <span>{{ store.isLogLoading.value ? 'Загрузка' : 'Обновить' }}</span>
            </button>
          </div>
        </div>
        <div class="log-toolbar">
          <input v-model="logSearch" type="search" placeholder="Поиск по логам" />
          <label v-for="(_, level) in logLevels" :key="level">
            <input v-model="logLevels[level]" type="checkbox" />
            <span>{{ level }}</span>
          </label>
        </div>
        <form class="rcon-command-row" @submit.prevent="sendRconCommand">
          <input v-model="rconCommand" type="text" placeholder="say Привет" :disabled="isRconSending" />
          <button class="primary-button compact" type="submit" :disabled="!rconCommand.trim() || isRconSending">
            <span>{{ isRconSending ? 'Отправляю' : 'Отправить' }}</span>
          </button>
        </form>
        <div v-if="rconHistory.length || rconOutput" class="rcon-history">
          <button
            v-for="command in rconHistory"
            :key="command"
            class="ghost-button compact"
            type="button"
            @click="rconCommand = command"
          >
            <span>{{ command }}</span>
          </button>
          <p v-if="rconOutput">{{ rconOutput }}</p>
        </div>
        <pre ref="logConsole" @scroll="updateLogStickiness"><code v-for="(line, index) in filteredServerLogs" :key="`${index}-${line}`">{{ line }}
</code><code v-if="!filteredServerLogs.length">{{ store.selectedServerLogs.value.length ? 'Нет строк под выбранные фильтры.' : 'Логов для выбранного сервера пока нет.' }}
</code></pre>
      </section>
    </section>

    <section v-if="activeServerDetailTab === 'diagnostics'" class="server-tab-panel">
      <section class="server-detail-section">
        <div class="server-detail-section-head">
          <h3>Отчёты о падениях</h3>
          <button class="ghost-button compact" type="button" @click="store.loadServerCrashReports()">
            <RefreshCw :size="16" />
            <span>{{ store.isCrashReportLoading.value ? 'Загрузка' : 'Обновить' }}</span>
          </button>
        </div>
        <div class="crash-report-list">
          <article v-for="report in store.selectedServerCrashReports.value" :key="report.name" class="crash-report-row">
            <div>
              <strong>{{ report.name }}</strong>
              <span>{{ report.created }} · {{ report.size }}</span>
            </div>
            <div class="crash-report-analysis">
              <p>{{ report.probable_cause || report.summary || 'Краткая причина не найдена' }}</p>
              <span v-if="report.conflicting_mod">{{ report.conflicting_mod }}</span>
              <span v-if="report.missing_dependency">{{ report.missing_dependency }}</span>
              <span v-if="report.client_only_mod">{{ report.client_only_mod }}</span>
              <details v-if="report.stack_trace?.length">
                <summary>Stack trace</summary>
                <code v-for="line in report.stack_trace" :key="line">{{ line }}</code>
              </details>
              <details v-if="report.recent_changes?.length">
                <summary>Последние изменения</summary>
                <code v-for="line in report.recent_changes" :key="line">{{ line }}</code>
              </details>
            </div>
          </article>
          <article v-if="!store.selectedServerCrashReports.value.length" class="server-empty-state">
            <div>
              <strong>Отчётов о падениях нет</strong>
              <span>Когда сервер упадёт с отчётом, он появится здесь.</span>
            </div>
          </article>
        </div>
      </section>
    </section>

    <section v-if="activeServerDetailTab === 'files'" class="server-tab-panel">
      <section class="server-detail-section server-files-panel">
        <div class="server-detail-section-head">
          <div>
            <h3>Файлы</h3>
            <span>{{ store.selectedServerFilePath.value || '/' }}</span>
          </div>
          <div class="panel-actions">
            <input ref="fileUploadInput" type="file" multiple class="visually-hidden" @change="uploadSelectedFiles" />
            <button class="ghost-button compact" type="button" @click="fileUploadInput?.click()">
              <span>Загрузить</span>
            </button>
            <button class="ghost-button compact" type="button" :disabled="!store.selectedServerFilePath.value" @click="openParentFolder">
              <span>Назад</span>
            </button>
            <button class="ghost-button compact" type="button" @click="store.loadServerFiles()">
              <RefreshCw :size="16" />
              <span>{{ store.isFileLoading.value ? 'Загрузка' : 'Обновить' }}</span>
            </button>
          </div>
        </div>
        <form class="file-create-row" @submit.prevent="createFolder">
          <input v-model="newFolderName" type="text" placeholder="Новая папка" />
          <button class="primary-button compact" type="submit" :disabled="!newFolderName.trim()">Создать</button>
        </form>
        <form class="file-create-row" @submit.prevent="searchFiles">
          <input v-model="fileSearchQuery" type="search" placeholder="Поиск по файлам" />
          <button class="ghost-button compact" type="submit" :disabled="fileSearchQuery.trim().length < 2">Найти</button>
        </form>
        <div v-if="store.selectedServerFileSearchResults.value.length" class="server-search-results">
          <button
            v-for="result in store.selectedServerFileSearchResults.value"
            :key="`${result.path}:${result.line}`"
            type="button"
            @click="openFileEntry(result.path, 'file')"
          >
            <strong>{{ result.path }}:{{ result.line }}</strong>
            <span>{{ result.preview }}</span>
          </button>
        </div>
        <div class="server-file-list">
          <article v-for="entry in store.selectedServerFiles.value" :key="entry.path" class="server-file-row">
            <button type="button" @click="openFileEntry(entry.path, entry.kind)">
              <Folder v-if="entry.kind === 'folder'" :size="18" />
              <FileText v-else :size="18" />
              <span>{{ entry.name }}</span>
            </button>
            <small>{{ entry.size }} · {{ entry.modified }}</small>
            <div class="server-file-actions">
              <button
                v-if="entry.kind === 'file'"
                class="ghost-button compact"
                type="button"
                @click="downloadServerFile(entry.path)"
              >
                Скачать
              </button>
              <button
                v-if="entry.kind === 'file' && (entry.name.endsWith('.zip') || entry.name.endsWith('.tar.gz'))"
                class="ghost-button compact"
                type="button"
                @click="store.runFileAction('extract', entry.path)"
              >
                Распаковать
              </button>
              <button class="ghost-button compact danger" type="button" @click="store.runFileAction('delete', entry.path)">
                Удалить
              </button>
            </div>
          </article>
          <article v-if="!store.selectedServerFiles.value.length" class="server-empty-state">
            <div>
              <strong>Папка пуста</strong>
              <span>Файлы появятся здесь после создания или загрузки через agent API.</span>
            </div>
          </article>
        </div>
        <div v-if="store.selectedServerFileContent.value" class="file-editor-panel">
          <div class="server-detail-section-head">
            <div>
              <h3>{{ store.selectedServerFileContent.value.name }}</h3>
              <span>{{ store.selectedServerFileContent.value.syntax }}</span>
            </div>
            <button
              class="primary-button compact"
              type="button"
              :disabled="store.selectedServerFileContent.value.encoding !== 'text' || store.isFileSaving.value"
              @click="saveOpenedFile"
            >
              {{ store.isFileSaving.value ? 'Сохраняю' : 'Сохранить' }}
            </button>
          </div>
          <textarea
            v-if="store.selectedServerFileContent.value.encoding === 'text'"
            v-model="fileEditorContent"
            class="config-editor"
            :class="`syntax-${store.selectedServerFileContent.value.syntax}`"
            spellcheck="false"
          ></textarea>
          <p v-else class="server-muted-note">Бинарный файл открыт только для чтения.</p>
        </div>
      </section>
    </section>

    <section v-if="activeServerDetailTab === 'mods'" class="server-tab-panel">
      <section class="server-detail-section">
        <div class="server-detail-section-head">
          <h3>Установленные моды</h3>
          <div class="panel-actions">
            <input ref="modUploadInput" type="file" multiple accept=".jar" class="visually-hidden" @change="installSelectedMods" />
            <input ref="modBulkUpdateInput" type="file" multiple accept=".jar" class="visually-hidden" @change="bulkUpdateSelectedMods" />
            <input ref="modUpdateInput" type="file" accept=".jar" class="visually-hidden" @change="updateSelectedMod" />
            <button class="ghost-button compact" type="button" @click="modUploadInput?.click()">Установить JAR</button>
            <button class="ghost-button compact" type="button" @click="modBulkUpdateInput?.click()">Обновить JAR</button>
            <button class="ghost-button compact" type="button" @click="store.runBulkModAction('disable')">Отключить все</button>
            <button class="ghost-button compact" type="button" @click="store.runBulkModAction('enable')">Включить все</button>
            <button class="ghost-button compact" type="button" @click="store.loadServerMods()">
              <RefreshCw :size="16" />
              <span>{{ store.isModLoading.value ? 'Сканирую' : 'Сканировать' }}</span>
            </button>
          </div>
        </div>
        <div class="server-mod-list">
          <article v-for="mod in store.selectedServerMods.value" :key="mod.path" class="server-mod-row" :class="{ disabled: !mod.enabled }">
            <Package :size="20" />
            <div>
              <strong>{{ mod.name }}</strong>
              <span>{{ mod.id }} · {{ mod.version || 'без версии' }} · {{ mod.loader }}</span>
              <small>{{ mod.filename }} · {{ mod.size }}</small>
              <em v-for="warning in mod.warnings" :key="warning">{{ warning }}</em>
            </div>
            <div class="server-mod-actions">
              <button class="ghost-button compact" type="button" @click="store.runModAction(mod.enabled ? 'disable' : 'enable', mod.path)">
                {{ mod.enabled ? 'Отключить' : 'Включить' }}
              </button>
              <button class="ghost-button compact" type="button" @click="chooseModUpdate(mod.path)">Обновить</button>
              <button class="ghost-button compact" type="button" @click="store.runModAction('pin', mod.path)">Зафиксировать</button>
              <button class="ghost-button compact danger" type="button" @click="store.runModAction('delete', mod.path)">Удалить</button>
            </div>
          </article>
          <article v-if="!store.selectedServerMods.value.length" class="server-empty-state">
            <div>
              <strong>Моды не найдены</strong>
              <span>Сканер читает JAR-файлы из папки mods.</span>
            </div>
          </article>
        </div>
      </section>
    </section>

    <section v-if="activeServerDetailTab === 'backups'" class="server-tab-panel">
      <section class="server-detail-section">
        <div class="server-detail-section-head">
          <h3>Бэкапы</h3>
          <button class="primary-button compact" type="button" @click="store.createServerBackup()">
            Создать безопасный бэкап
          </button>
        </div>
        <div class="server-backup-list">
          <article
            v-for="backup in store.backups.value.filter((item) => item.server_id === store.selectedServer.value?.id)"
            :key="backup.id"
            class="server-backup-row"
          >
            <div>
              <strong>{{ backup.name }}</strong>
              <span>{{ backup.created }} · {{ backup.size }}</span>
              <small v-if="backup.checksum">SHA-256 {{ backup.checksum.slice(0, 18) }}…</small>
            </div>
          </article>
          <article v-if="!store.backups.value.some((item) => item.server_id === store.selectedServer.value?.id)" class="server-empty-state">
            <div>
              <strong>Бэкапов пока нет</strong>
              <span>Создай первый backup перед изменениями мира или модов.</span>
            </div>
          </article>
        </div>
      </section>
    </section>

    <section v-if="activeServerDetailTab === 'settings'" class="server-tab-panel">
      <section class="server-detail-section server-config-panel">
        <div class="server-detail-section-head">
          <h3>server.properties</h3>
          <div class="panel-actions">
            <button class="ghost-button compact" type="button" @click="store.loadServerConfig()">
              <RefreshCw :size="16" />
              <span>{{ store.isConfigLoading.value ? 'Загрузка' : 'Обновить' }}</span>
            </button>
            <button class="primary-button compact" type="button" :disabled="store.isConfigSaving.value" @click="store.saveServerConfig">
              <span>{{ store.isConfigSaving.value ? 'Сохраняю' : 'Сохранить' }}</span>
            </button>
          </div>
        </div>
        <textarea
          v-model="store.selectedServerConfig.value"
          class="config-editor"
          spellcheck="false"
          :disabled="store.isConfigLoading.value || store.isConfigSaving.value"
          placeholder="server.properties пока не загружен"
        ></textarea>
      </section>
    </section>
  </section>
</template>
