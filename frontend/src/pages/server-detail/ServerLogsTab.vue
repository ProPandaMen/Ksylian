<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { RefreshCw } from "@lucide/vue";
import { useServerRequests } from "../../composables/dashboard/servers";
import { useDashboardStore } from "../../composables/useDashboardStore";

const route = useRoute();
const store = useDashboardStore();
const serverRequests = useServerRequests();
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

async function refreshLogs() {
  await store.loadServerLogs();
  await scrollLogsIfNeeded();
}

function startLogStream() {
  const serverId = typeof route.params.serverId === "string" ? route.params.serverId : "";
  const token = window.localStorage.getItem("ksylian_auth_token") || "";
  if (logSocket || !serverId || !token) {
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
    const result = await serverRequests.rconCommand(server.id, command);
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

watch(
  () => store.selectedServerLogs.value.length,
  () => {
    scrollLogsIfNeeded();
  },
);

onMounted(async () => {
  shouldStickToLogBottom.value = true;
  await refreshLogs();
  startLogStream();
});

onUnmounted(stopLogStream);
</script>

<template>
  <section class="server-tab-panel">
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
</template>
