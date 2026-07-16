<script setup lang="ts">
import { Cpu, Gauge, HardDrive, MemoryStick, RefreshCw } from "@lucide/vue";
import type { DiskUsage, HostMonitoring, ServerState } from "../types";

defineProps<{
  monitoring: HostMonitoring;
  monitoringStatus: { label: string; tone: string };
  isLoading: boolean;
  stateLabels: Record<ServerState, string>;
}>();

const emit = defineEmits<{
  refresh: [];
}>();

function clampPercent(percent: number) {
  return Math.min(100, Math.max(0, Math.round(percent)));
}

function freeLabel(disk: DiskUsage) {
  const freeBytes = Math.max(0, disk.total - disk.used);
  if (freeBytes >= 1024 ** 3) {
    return `${(freeBytes / 1024 ** 3).toFixed(1)} GB`;
  }
  if (freeBytes >= 1024 ** 2) {
    return `${(freeBytes / 1024 ** 2).toFixed(1)} MB`;
  }
  return `${Math.round(freeBytes / 1024)} KB`;
}

function diskCircleStyle(percent: number) {
  const safePercent = clampPercent(percent);
  const circumference = 2 * Math.PI * 46;
  const usedLength = (safePercent / 100) * circumference;
  const freeLength = circumference - usedLength;
  return {
    "--disk-dash": `${usedLength} ${freeLength}`,
  };
}
</script>

<template>
  <section class="monitoring-page">
    <section class="panel monitor-hero">
      <div>
        <p class="eyebrow">host health</p>
        <h2>{{ monitoring.hostname }}</h2>
        <p>Работает {{ monitoring.uptime }}</p>
      </div>
      <div class="monitor-hero-actions">
        <span class="monitor-status" :class="monitoringStatus.tone">{{ monitoringStatus.label }}</span>
        <button class="ghost-button compact" type="button" @click="emit('refresh')">
          <RefreshCw :size="16" />
          <span>{{ isLoading ? 'Обновляю' : 'Обновить' }}</span>
        </button>
      </div>
    </section>

    <section class="monitor-grid">
      <article class="metric-tile">
        <Cpu :size="20" />
        <span>CPU</span>
        <strong>{{ monitoring.cpu_percent }}%</strong>
        <small>{{ monitoring.cpu_cores }} ядер · load {{ monitoring.load_average.join(' / ') }}</small>
      </article>
      <article class="metric-tile mint">
        <MemoryStick :size="20" />
        <span>RAM</span>
        <strong>{{ monitoring.memory.percent }}%</strong>
        <small>{{ monitoring.memory.used_label }} / {{ monitoring.memory.total_label }}</small>
      </article>
      <article class="metric-tile amber">
        <HardDrive :size="20" />
        <span>Swap</span>
        <strong>{{ monitoring.swap.percent }}%</strong>
        <small>{{ monitoring.swap.used_label }} / {{ monitoring.swap.total_label }}</small>
      </article>
      <article class="metric-tile graphite">
        <Gauge :size="20" />
        <span>Температура</span>
        <strong>{{ monitoring.temperature }}</strong>
        <small>Снято {{ monitoring.collected_at || 'только что' }}</small>
      </article>
    </section>

    <section class="monitor-columns">
      <section class="panel">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">storage</p>
            <h2>Диски</h2>
          </div>
        </div>
        <div class="disk-list">
          <article v-for="disk in monitoring.disks" :key="disk.mount" class="disk-card">
            <div class="disk-chart" :style="diskCircleStyle(disk.percent)" aria-hidden="true">
              <svg viewBox="0 0 120 120" role="img">
                <circle class="disk-ring free" cx="60" cy="60" r="46" />
                <circle class="disk-ring used" cx="60" cy="60" r="46" />
              </svg>
              <div class="disk-chart-label">
                <strong>{{ clampPercent(disk.percent) }}%</strong>
                <span>занято</span>
              </div>
            </div>
            <div class="disk-info">
              <div>
                <strong>{{ disk.mount }}</strong>
                <span>{{ disk.filesystem }}</span>
              </div>
              <dl>
                <div>
                  <dt>Занято</dt>
                  <dd>{{ disk.used_label }}</dd>
                </div>
                <div>
                  <dt>Свободно</dt>
                  <dd>{{ freeLabel(disk) }}</dd>
                </div>
                <div>
                  <dt>Всего</dt>
                  <dd>{{ disk.total_label }}</dd>
                </div>
              </dl>
            </div>
          </article>
          <article v-if="!monitoring.disks.length" class="stack-item muted">
            <HardDrive :size="18" />
            <div>
              <strong>Диски пока не прочитаны</strong>
              <span>Agent не вернул mount points</span>
            </div>
          </article>
        </div>
      </section>

      <section class="panel">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">systemd</p>
            <h2>Сервисы</h2>
          </div>
        </div>
        <div class="stack-list">
          <article v-for="service in monitoring.services" :key="service.id" class="stack-item service-item">
            <span class="server-state" :class="service.state"></span>
            <div>
              <strong>{{ service.name }}</strong>
              <span>{{ stateLabels[service.state] }} · CPU {{ service.cpu }}% · RAM {{ service.ram }}</span>
            </div>
          </article>
        </div>
      </section>
    </section>

    <section class="panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">processes</p>
          <h2>Топ процессов</h2>
        </div>
      </div>
      <div class="process-table">
        <div class="process-row head">
          <span>PID</span>
          <span>Процесс</span>
          <span>CPU</span>
          <span>RAM</span>
        </div>
        <div v-for="process in monitoring.top_processes" :key="process.pid" class="process-row">
          <span>{{ process.pid }}</span>
          <strong>{{ process.name }}</strong>
          <span>{{ process.cpu }}%</span>
          <span>{{ process.memory }}%</span>
          <small>{{ process.command }}</small>
        </div>
        <div v-if="!monitoring.top_processes.length" class="process-row">
          <span>-</span>
          <strong>Нет данных</strong>
          <span>-</span>
          <span>-</span>
        </div>
      </div>
    </section>
  </section>
</template>
