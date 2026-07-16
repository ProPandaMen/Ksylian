<script setup lang="ts">
import { onMounted } from "vue";
import { themes, useAuthStore } from "../composables/useAuthStore";
import { useDashboardStore } from "../composables/useDashboardStore";
import SettingsPage from "./SettingsPage.vue";

const store = useDashboardStore();
const auth = useAuthStore();

onMounted(() => {
  store.loadUpdateStatus();
});
</script>

<template>
  <SettingsPage
    v-model:curse-forge-api-key="store.curseForgeApiKey.value"
    :settings="store.settings.value"
    :update-status="store.updateStatus.value"
    :is-saving="store.isSavingSettings.value"
    :is-update-loading="store.isUpdateLoading.value"
    :is-applying-update="store.isApplyingUpdate.value"
    :user="auth.user.value"
    :themes="themes"
    @refresh="store.loadDashboard"
    @refresh-agent="store.loadAgentStatus"
    @refresh-update="store.loadUpdateStatus"
    @restart-agent="store.restartAgent"
    @apply-update="store.applyUpdate"
    @update-theme="auth.updateTheme"
    @save="store.saveSettings"
    @clear="store.clearCurseForgeKey"
  />
</template>
