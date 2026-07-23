<script setup lang="ts">
import { Cpu, Gauge, HardDrive, MemoryStick } from "@lucide/vue";
import type { DiskUsage, HostMonitoring, MonitoringHistoryPoint, ServerState } from "../types";

defineProps<{
  monitoring: HostMonitoring;
  metricHistory: MonitoringHistoryPoint[];
  monitoringStatus: { label: string; tone: string };
  stateLabels: Record<ServerState, string>;
}>();

type MetricKey = "cpu" | "memory" | "swap" | "temperature";

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

function diskBarStyle(percent: number) {
  return {
    "--disk-used": `${clampPercent(percent)}%`,
  };
}

function chartValues(history: MonitoringHistoryPoint[], key: MetricKey) {
  const values = history
    .map((point) => point[key])
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));

  return values.length ? values : [0];
}

function chartPath(history: MonitoringHistoryPoint[], key: MetricKey, maxValue = 100) {
  const values = chartValues(history, key);
  const width = 220;
  const height = 58;
  const safeMax = Math.max(1, maxValue);
  const points = values.length === 1 ? [values[0], values[0]] : values;

  return points
    .map((value, index) => {
      const x = (index / Math.max(1, points.length - 1)) * width;
      const y = height - (Math.min(safeMax, Math.max(0, value)) / safeMax) * height;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}

function chartAreaPath(history: MonitoringHistoryPoint[], key: MetricKey, maxValue = 100) {
  const line = chartPath(history, key, maxValue);
  return `${line} L 220 58 L 0 58 Z`;
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

      <div class="resource-chart-grid">
        <article class="resource-chart-card">
          <div class="resource-chart-head">
            <Cpu :size="18" />
            <span>CPU</span>
            <strong>{{ monitoring.cpu_percent }}%</strong>
          </div>
          <svg class="resource-chart" viewBox="0 0 220 58" preserveAspectRatio="none" aria-hidden="true">
            <path class="resource-chart-area" :d="chartAreaPath(metricHistory, 'cpu')" />
            <path class="resource-chart-line" :d="chartPath(metricHistory, 'cpu')" />
          </svg>
          <small>{{ monitoring.cpu_cores }} ядер · load {{ monitoring.load_average.join(' / ') }}</small>
        </article>

        <article class="resource-chart-card">
          <div class="resource-chart-head">
            <MemoryStick :size="18" />
            <span>RAM</span>
            <strong>{{ monitoring.memory.percent }}%</strong>
          </div>
          <svg class="resource-chart" viewBox="0 0 220 58" preserveAspectRatio="none" aria-hidden="true">
            <path class="resource-chart-area" :d="chartAreaPath(metricHistory, 'memory')" />
            <path class="resource-chart-line" :d="chartPath(metricHistory, 'memory')" />
          </svg>
          <small>{{ monitoring.memory.used_label }} / {{ monitoring.memory.total_label }}</small>
        </article>

        <article class="resource-chart-card">
          <div class="resource-chart-head">
            <HardDrive :size="18" />
            <span>Swap</span>
            <strong>{{ monitoring.swap.percent }}%</strong>
          </div>
          <svg class="resource-chart" viewBox="0 0 220 58" preserveAspectRatio="none" aria-hidden="true">
            <path class="resource-chart-area" :d="chartAreaPath(metricHistory, 'swap')" />
            <path class="resource-chart-line" :d="chartPath(metricHistory, 'swap')" />
          </svg>
          <small>{{ monitoring.swap.used_label }} / {{ monitoring.swap.total_label }}</small>
        </article>

        <article class="resource-chart-card">
          <div class="resource-chart-head">
            <Gauge :size="18" />
            <span>Температура</span>
            <strong>{{ monitoring.temperature }}</strong>
          </div>
          <svg class="resource-chart" viewBox="0 0 220 58" preserveAspectRatio="none" aria-hidden="true">
            <path class="resource-chart-area" :d="chartAreaPath(metricHistory, 'temperature')" />
            <path class="resource-chart-line" :d="chartPath(metricHistory, 'temperature')" />
          </svg>
          <small>{{ monitoring.collected_at || 'только что' }}</small>
        </article>
      </div>
    </section>

    <section class="monitor-columns">
      <section class="monitor-section" aria-label="Диски">
        <div class="monitor-section-head">
          <h3>Диски</h3>
        </div>

        <div class="disk-list">
          <article v-for="disk in monitoring.disks" :key="disk.mount" class="disk-card">
            <div class="disk-card-main">
              <div class="disk-card-title">
                <strong>{{ disk.mount }}</strong>
                <span>{{ disk.filesystem }}</span>
              </div>
              <strong class="disk-card-percent">{{ clampPercent(disk.percent) }}%</strong>
            </div>

            <div class="disk-bar" :style="diskBarStyle(disk.percent)" aria-hidden="true">
              <span></span>
            </div>

            <dl class="disk-card-stats">
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
          <article v-for="service in monitoring.services" :key="service.id" class="service-card">
            <div class="service-card-main">
              <span class="server-state" :class="service.state"></span>
              <div class="service-name">
                <strong>{{ service.name }}</strong>
                <span>{{ stateLabels[service.state] }}</span>
              </div>
            </div>

            <dl class="service-card-stats">
              <div>
                <dt>CPU</dt>
                <dd>{{ service.cpu }}%</dd>
              </div>
              <div>
                <dt>RAM</dt>
                <dd>{{ service.ram }}</dd>
              </div>
            </dl>
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
