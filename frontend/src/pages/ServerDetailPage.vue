<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ArrowLeft,
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
const router = useRouter();
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

function backToServerList() {
  router.push("/servers");
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
    <div class="server-control-header">
      <button class="ghost-button compact" type="button" @click="backToServerList">
        <ArrowLeft :size="16" />
        <span>К списку</span>
      </button>
      <div class="server-control-actions">
        <button class="ghost-button compact" type="button" @click="store.loadDashboard(store.selectedServer.value?.id)">
          <RefreshCw :size="16" />
          <span>Обновить</span>
        </button>
      </div>
    </div>

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
      <section class="server-hero panel">
        <div class="server-hero-main">
          <span class="server-state" :class="store.selectedServer.value.state"></span>
          <div>
            <p class="eyebrow">{{ store.selectedServer.value.pack }}</p>
            <h2>{{ store.selectedServer.value.name }}</h2>
            <p>{{ store.selectedServer.value.version }} · {{ store.selectedServer.value.address }}</p>
          </div>
        </div>
        <div class="server-actions">
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

      <section class="server-detail-grid">
        <article class="metric-tile">
          <Cpu :size="20" />
          <span>Процессор</span>
          <strong>{{ store.selectedServer.value.cpu }}%</strong>
        </article>
        <article class="metric-tile mint">
          <MemoryStick :size="20" />
          <span>Оперативка</span>
          <strong>{{ store.selectedServer.value.ram }}</strong>
        </article>
        <article class="metric-tile amber">
          <HardDrive :size="20" />
          <span>Память</span>
          <strong>{{ store.selectedServer.value.disk }}</strong>
        </article>
        <article class="metric-tile graphite">
          <Users :size="20" />
          <span>Онлайн</span>
          <strong>{{ store.selectedServer.value.players }}</strong>
        </article>
      </section>
      <section class="panel server-info-panel">
        <p class="eyebrow">connection</p>
        <h2>Основная информация</h2>
        <div class="server-info-grid">
          <div>
            <span>Адрес</span>
            <strong>{{ store.selectedServer.value.address }}</strong>
          </div>
          <div>
            <span>Тип</span>
            <strong>{{ store.selectedServer.value.pack }}</strong>
          </div>
          <div>
            <span>Версия Minecraft</span>
            <strong>{{ store.selectedServer.value.version }}</strong>
          </div>
          <div>
            <span>Статус</span>
            <strong>{{ stateLabels[store.selectedServer.value.state] }}</strong>
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
      <section class="panel server-config-panel">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">minecraft config</p>
            <h2>server.properties</h2>
          </div>
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
        <p class="settings-hint">
          Изменения в server.properties обычно применяются после перезапуска Minecraft-сервера.
        </p>
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
