<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { useDashboardStore } from "../composables/useDashboardStore";
import ServerBackupsTab from "./server-detail/ServerBackupsTab.vue";
import ServerDiagnosticsTab from "./server-detail/ServerDiagnosticsTab.vue";
import ServerFilesTab from "./server-detail/ServerFilesTab.vue";
import ServerLogsTab from "./server-detail/ServerLogsTab.vue";
import ServerModsTab from "./server-detail/ServerModsTab.vue";
import ServerOverviewTab from "./server-detail/ServerOverviewTab.vue";
import ServerPlayersTab from "./server-detail/ServerPlayersTab.vue";
import ServerSettingsTab from "./server-detail/ServerSettingsTab.vue";
import { serverDetailTabs, type ServerDetailTab } from "./serverDetailTabs";

const route = useRoute();
const store = useDashboardStore();
const activeServerDetailTab = ref<ServerDetailTab>("overview");

async function loadCurrentTabData() {
  const serverId = typeof route.params.serverId === "string" ? route.params.serverId : "";
  store.selectedServerId.value = serverId;
  if (!serverId) {
    return;
  }

  if (activeServerDetailTab.value === "logs") {
    await store.loadServerLogs(serverId);
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

function selectServerDetailTab(tabId: ServerDetailTab) {
  activeServerDetailTab.value = tabId;
}

watch(
  () => route.params.serverId,
  async () => {
    await loadCurrentTabData();
  },
);

watch(
  () => activeServerDetailTab.value,
  async () => {
    await loadCurrentTabData();
  },
);

onMounted(loadCurrentTabData);
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

    <ServerOverviewTab v-if="activeServerDetailTab === 'overview'" />
    <ServerPlayersTab v-if="activeServerDetailTab === 'players'" />
    <ServerLogsTab v-if="activeServerDetailTab === 'logs'" />
    <ServerDiagnosticsTab v-if="activeServerDetailTab === 'diagnostics'" />
    <ServerFilesTab v-if="activeServerDetailTab === 'files'" />
    <ServerModsTab v-if="activeServerDetailTab === 'mods'" />
    <ServerBackupsTab v-if="activeServerDetailTab === 'backups'" />
    <ServerSettingsTab v-if="activeServerDetailTab === 'settings'" />
  </section>
</template>
