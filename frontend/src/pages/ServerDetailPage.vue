<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import {
  CircleStop,
  Cpu,
  HardDrive,
  ListRestart,
  MemoryStick,
  Play,
  RefreshCw,
  Users,
} from "@lucide/vue";
import { stateLabels, useDashboardStore } from "../composables/useDashboardStore";
import { requestJson } from "../services/api";
import type { RconCommandResult } from "../types";

type ServerDetailTab = "overview" | "logs" | "diagnostics" | "settings";

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
const logLevels = ref<Record<"INFO" | "WARN" | "ERROR" | "FATAL", boolean>>({
  INFO: true,
  WARN: true,
  ERROR: true,
  FATAL: true,
});
let logSocket: WebSocket | undefined;

const serverDetailTabs: Array<{ id: ServerDetailTab; label: string }> = [
  { id: "overview", label: "Информация" },
  { id: "logs", label: "Логи" },
  { id: "diagnostics", label: "Диагностика" },
  { id: "settings", label: "Настройки" },
];

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
