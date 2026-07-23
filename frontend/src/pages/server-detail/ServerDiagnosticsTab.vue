<script setup lang="ts">
import { RefreshCw } from "@lucide/vue";
import { useDashboardStore } from "../../composables/useDashboardStore";

const store = useDashboardStore();
</script>

<template>
  <section class="server-tab-panel">
      <section class="server-detail-section">
        <div class="server-detail-section-head">
          <h3>Отчёты о падениях</h3>
          <button class="ghost-button compact" type="button" :aria-busy="store.isCrashReportLoading.value" @click="store.loadServerCrashReports()">
            <RefreshCw :class="{ spinning: store.isCrashReportLoading.value }" :size="16" />
            <span>Обновить</span>
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
</template>
