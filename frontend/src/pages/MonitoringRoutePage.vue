<script setup lang="ts">
import { onMounted, onUnmounted } from "vue";
import { stateLabels, useDashboardStore } from "../composables/useDashboardStore";
import MonitoringPage from "./MonitoringPage.vue";

const store = useDashboardStore();
let refreshTimer: number | undefined;

onMounted(() => {
  store.loadMonitoring();
  refreshTimer = window.setInterval(() => {
    if (!store.isMonitoringLoading.value) {
      store.loadMonitoring();
    }
  }, 5000);
});

onUnmounted(() => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer);
  }
});
</script>

<template>
  <MonitoringPage
    :monitoring="store.monitoring.value"
    :metric-history="store.monitoringHistory.value"
    :monitoring-status="store.monitoringStatus.value"
    :state-labels="stateLabels"
  />
</template>
