<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";
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

type ServerDetailTab = "overview" | "logs" | "settings";

const route = useRoute();
const store = useDashboardStore();
const activeServerDetailTab = ref<ServerDetailTab>("overview");
const logConsole = ref<HTMLPreElement | null>(null);
const shouldStickToLogBottom = ref(true);
let logRefreshTimer: number | undefined;

const serverDetailTabs: Array<{ id: ServerDetailTab; label: string }> = [
  { id: "overview", label: "Информация" },
  { id: "logs", label: "Логи" },
  { id: "settings", label: "Настройки" },
];

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
  if (activeServerDetailTab.value === "settings") {
    await store.loadServerConfig(serverId);
  }
}

async function refreshLogs() {
  await store.loadServerLogs();
  await scrollLogsIfNeeded();
}

async function silentRefreshLogs() {
  await store.refreshServerLogs();
  await scrollLogsIfNeeded();
}

function startLogAutoRefresh() {
  if (logRefreshTimer || activeServerDetailTab.value !== "logs") {
    return;
  }

  logRefreshTimer = window.setInterval(() => {
    silentRefreshLogs();
  }, 2500);
}

function stopLogAutoRefresh() {
  if (logRefreshTimer) {
    window.clearInterval(logRefreshTimer);
    logRefreshTimer = undefined;
  }
}

function selectServerDetailTab(tabId: ServerDetailTab) {
  activeServerDetailTab.value = tabId;
}

watch(
  () => route.params.serverId,
  async () => {
    shouldStickToLogBottom.value = true;
    await loadCurrentTabData();
  },
);

watch(
  () => activeServerDetailTab.value,
  async (tabId) => {
    if (tabId === "logs") {
      shouldStickToLogBottom.value = true;
      startLogAutoRefresh();
      await refreshLogs();
      return;
    }

    stopLogAutoRefresh();
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
    startLogAutoRefresh();
  }
});

onUnmounted(stopLogAutoRefresh);
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
        <div class="server-detail-actions">
          <button class="icon-button" type="button" title="Запустить" @click="store.runServerAction(store.selectedServer.value.id, 'start')">
            <Play :size="17" />
          </button>
          <button class="icon-button" type="button" title="Перезагрузить" @click="store.runServerAction(store.selectedServer.value.id, 'restart')">
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
          <button class="ghost-button compact" type="button" @click="refreshLogs">
            <RefreshCw :size="16" />
            <span>{{ store.isLogLoading.value ? 'Загрузка' : 'Обновить' }}</span>
          </button>
        </div>
        <pre ref="logConsole" @scroll="updateLogStickiness"><code v-for="(line, index) in store.selectedServerLogs.value" :key="`${index}-${line}`">{{ line }}
</code><code v-if="!store.selectedServerLogs.value.length">Логов для выбранного сервера пока нет.
</code></pre>
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
