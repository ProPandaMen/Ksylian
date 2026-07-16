<script setup lang="ts">
import { useDashboardStore } from "../composables/useDashboardStore";
import SettingsPage from "./SettingsPage.vue";

const store = useDashboardStore();
</script>

<template>
  <SettingsPage
    v-model:curse-forge-api-key="store.curseForgeApiKey.value"
    :settings="store.settings.value"
    :is-saving="store.isSavingSettings.value"
    @refresh="store.loadDashboard"
    @refresh-agent="store.loadAgentStatus"
    @restart-agent="store.restartAgent"
    @save="store.saveSettings"
    @clear="store.clearCurseForgeKey"
  />
</template>
