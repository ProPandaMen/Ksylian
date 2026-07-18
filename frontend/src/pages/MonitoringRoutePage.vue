<script setup lang="ts">
import { onMounted } from "vue";
import { stateLabels, useDashboardStore } from "../composables/useDashboardStore";
import MonitoringPage from "./MonitoringPage.vue";

const store = useDashboardStore();

onMounted(() => {
  store.loadMonitoring();
});
</script>

<template>
  <MonitoringPage
    :monitoring="store.monitoring.value"
    :monitoring-status="store.monitoringStatus.value"
    :state-labels="stateLabels"
  />
</template>
