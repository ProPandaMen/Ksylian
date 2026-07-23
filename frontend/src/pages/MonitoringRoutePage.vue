<script setup lang="ts">
import { onMounted, onUnmounted } from "vue";
import { stateLabels, useDashboardStore } from "../composables/useDashboardStore";
import MonitoringPage from "./MonitoringPage.vue";

const store = useDashboardStore();
let refreshTimer: number | undefined;
let historyTimer: number | undefined;

onMounted(() => {
  store.loadMonitoring();
  store.loadMonitoringHistory(store.monitoringWindow.value);
  refreshTimer = window.setInterval(() => {
    if (!store.isMonitoringLoading.value) {
      store.loadMonitoring();
    }
  }, 5000);
  historyTimer = window.setInterval(() => {
    if (!store.isMonitoringHistoryLoading.value) {
      store.loadMonitoringHistory(store.monitoringWindow.value);
    }
  }, 30000);
});

onUnmounted(() => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer);
  }
  if (historyTimer) {
    window.clearInterval(historyTimer);
  }
});
</script>

<template>
  <MonitoringPage
    :monitoring="store.monitoring.value"
    :metric-history="store.monitoringHistory.value"
    :history-meta="store.monitoringHistoryMeta.value"
    :selected-window="store.monitoringWindow.value"
    :is-history-loading="store.isMonitoringHistoryLoading.value"
    :monitoring-status="store.monitoringStatus.value"
    :state-labels="stateLabels"
    @change-window="store.loadMonitoringHistory"
    @refresh-history="store.loadMonitoringHistory(store.monitoringWindow.value)"
  />
</template>
