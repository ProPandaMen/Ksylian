<script setup lang="ts">
import { Cpu, Gauge, HardDrive, MemoryStick } from "@lucide/vue";
import type { DiskUsage, HostMonitoring, ServerState } from "../types";

defineProps<{
  monitoring: HostMonitoring;
  monitoringStatus: { label: string; tone: string };
  stateLabels: Record<ServerState, string>;
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
    <section class="monitor-section" aria-label="Состояние хоста">
      <div class="monitor-section-head">
        <h3>Хост</h3>
        <span class="monitor-status" :class="monitoringStatus.tone">{{ monitoringStatus.label }}</span>
      </div>

      <div class="monitor-row">
        <span>Имя</span>
        <strong>{{ monitoring.hostname }}</strong>
      </div>
      <div class="monitor-row">
        <span>Работает</span>
        <strong>{{ monitoring.uptime }}</strong>
      </div>
      <div class="monitor-row">
        <span>Снято</span>
        <strong>{{ monitoring.collected_at || 'только что' }}</strong>
      </div>
    </section>

    <section class="monitor-section" aria-label="Ресурсы">
      <div class="monitor-section-head">
        <h3>Ресурсы</h3>
      </div>

      <div class="monitor-metric-row">
        <Cpu :size="18" />
        <span>CPU</span>
        <strong>{{ monitoring.cpu_percent }}%</strong>
        <small>{{ monitoring.cpu_cores }} ядер · load {{ monitoring.load_average.join(' / ') }}</small>
      </div>
      <div class="monitor-metric-row">
        <MemoryStick :size="18" />
        <span>RAM</span>
        <strong>{{ monitoring.memory.percent }}%</strong>
        <small>{{ monitoring.memory.used_label }} / {{ monitoring.memory.total_label }}</small>
      </div>
      <div class="monitor-metric-row">
        <HardDrive :size="18" />
        <span>Swap</span>
        <strong>{{ monitoring.swap.percent }}%</strong>
        <small>{{ monitoring.swap.used_label }} / {{ monitoring.swap.total_label }}</small>
      </div>
      <div class="monitor-metric-row">
        <Gauge :size="18" />
        <span>Температура</span>
        <strong>{{ monitoring.temperature }}</strong>
        <small>{{ monitoring.collected_at || 'только что' }}</small>
      </div>
    </section>

    <section class="monitor-columns">
      <section class="monitor-section" aria-label="Диски">
        <div class="monitor-section-head">
          <h3>Диски</h3>
        </div>

        <div class="disk-list">
          <article v-for="disk in monitoring.disks" :key="disk.mount" class="disk-row">
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
          </article>
          <article v-if="!monitoring.disks.length" class="monitor-empty-row">
            <HardDrive :size="18" />
            <div>
              <strong>Диски пока не прочитаны</strong>
              <span>Agent не вернул mount points</span>
            </div>
          </article>
        </div>
      </section>

      <section class="monitor-section" aria-label="Сервисы">
        <div class="monitor-section-head">
          <h3>Сервисы</h3>
        </div>

        <div class="service-list">
          <article v-for="service in monitoring.services" :key="service.id" class="service-row">
            <span class="server-state" :class="service.state"></span>
            <div class="service-name">
              <strong>{{ service.name }}</strong>
            </div>
            <div>
              <span>Статус</span>
              <strong>{{ stateLabels[service.state] }}</strong>
            </div>
            <div>
              <span>CPU</span>
              <strong>{{ service.cpu }}%</strong>
            </div>
            <div>
              <span>RAM</span>
              <strong>{{ service.ram }}</strong>
            </div>
          </article>
        </div>
      </section>
    </section>

    <section class="monitor-section" aria-label="Топ процессов">
      <div class="monitor-section-head">
        <h3>Топ процессов</h3>
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
