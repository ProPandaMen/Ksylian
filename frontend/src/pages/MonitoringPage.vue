<script setup lang="ts">
import { computed } from "vue";
import { AlertTriangle, CheckCircle2, Cpu, Gauge, HardDrive, MemoryStick, Network, ServerCog } from "@lucide/vue";
import type { DiskUsage, HostMonitoring, MonitoringHistoryPoint, ServerState } from "../types";

const props = defineProps<{
  monitoring: HostMonitoring;
  metricHistory: MonitoringHistoryPoint[];
  monitoringStatus: { label: string; tone: string };
  stateLabels: Record<ServerState, string>;
}>();

type MetricKey = "cpu" | "memory" | "swap" | "temperature";
type InsightTone = "ok" | "warning" | "danger";

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

function metricTone(percent: number) {
  if (percent >= 90) {
    return "danger";
  }
  if (percent >= 75) {
    return "warning";
  }
  return "ok";
}

function historyWindowLabel(history: MonitoringHistoryPoint[]) {
  if (history.length <= 1) {
    return "нужны ещё снимки";
  }
  const seconds = Math.max(0, Math.round((history.at(-1)!.timestamp - history[0].timestamp) / 1000));
  if (seconds >= 60) {
    return `${Math.round(seconds / 60)} мин`;
  }
  return `${seconds} сек`;
}

function mainDisk(disks: DiskUsage[]) {
  const rootDisk = disks.find((disk) => disk.mount === "/");
  if (rootDisk) {
    return rootDisk;
  }
  return disks.reduce<DiskUsage | null>((selected, disk) => {
    if (!selected) {
      return disk;
    }
    return disk.percent > selected.percent ? disk : selected;
  }, null);
}

function runningServices(monitoring: HostMonitoring) {
  return monitoring.services.filter((service) => service.state === "running").length;
}

function serviceHealthLabel(monitoring: HostMonitoring) {
  if (!monitoring.services.length) {
    return "нет данных";
  }
  return `${runningServices(monitoring)} / ${monitoring.services.length}`;
}

function serviceTone(service: HostMonitoring["services"][number]) {
  if (service.state === "crashed") {
    return "danger";
  }
  if (service.state !== "running") {
    return "warning";
  }
  if (service.cpu >= 75) {
    return "warning";
  }
  return "ok";
}

function processTone(process: HostMonitoring["top_processes"][number]) {
  if (process.cpu >= 90 || process.memory >= 50) {
    return "danger";
  }
  if (process.cpu >= 60 || process.memory >= 25) {
    return "warning";
  }
  return "ok";
}

function compactIps(ips: string[]) {
  if (!ips.length) {
    return "IP не найден";
  }
  return ips.slice(0, 2).join(" · ");
}

function metricUnit(key: MetricKey) {
  return key === "temperature" ? "°C" : "%";
}

function trendLabel(history: MonitoringHistoryPoint[], key: MetricKey) {
  const values = chartValues(history, key);
  if (values.length < 4) {
    return "тренд появится позже";
  }
  const start = values.slice(0, Math.max(1, Math.floor(values.length / 3)));
  const end = values.slice(-Math.max(1, Math.floor(values.length / 3)));
  const startAverage = start.reduce((sum, value) => sum + value, 0) / start.length;
  const endAverage = end.reduce((sum, value) => sum + value, 0) / end.length;
  const delta = Math.round(endAverage - startAverage);
  if (Math.abs(delta) < 4) {
    return "стабильно";
  }
  const unit = metricUnit(key);
  return delta > 0 ? `растёт на ${delta}${unit}` : `снижается на ${Math.abs(delta)}${unit}`;
}

function metricWindowLabel(history: MonitoringHistoryPoint[], key: MetricKey) {
  const values = chartValues(history, key);
  const min = Math.round(Math.min(...values));
  const max = Math.round(Math.max(...values));
  if (values.length <= 1) {
    return "ждём историю";
  }
  const unit = metricUnit(key);
  return `${min}-${max}${unit} · ${trendLabel(history, key)}`;
}

const monitoringInsights = computed(() => {
  const monitoring = props.monitoring;
  const insights: Array<{ tone: InsightTone; title: string; detail: string }> = [];

  if (monitoring.cpu_percent >= 90) {
    insights.push({
      tone: "danger",
      title: "CPU близко к пределу",
      detail: `${monitoring.cpu_percent}% сейчас · ${trendLabel(props.metricHistory, "cpu")}`,
    });
  } else if (monitoring.cpu_percent >= 75) {
    insights.push({
      tone: "warning",
      title: "CPU требует внимания",
      detail: `${monitoring.cpu_percent}% сейчас · ${trendLabel(props.metricHistory, "cpu")}`,
    });
  }

  if (monitoring.memory.percent >= 90) {
    insights.push({
      tone: "danger",
      title: "RAM почти исчерпана",
      detail: `${monitoring.memory.used_label} из ${monitoring.memory.total_label} · ${trendLabel(props.metricHistory, "memory")}`,
    });
  } else if (monitoring.memory.percent >= 75) {
    insights.push({
      tone: "warning",
      title: "RAM растёт",
      detail: `${monitoring.memory.percent}% занято · ${trendLabel(props.metricHistory, "memory")}`,
    });
  }

  if (monitoring.swap.percent >= 50) {
    insights.push({
      tone: monitoring.swap.percent >= 75 ? "danger" : "warning",
      title: "Активно используется Swap",
      detail: `${monitoring.swap.used_label} из ${monitoring.swap.total_label}`,
    });
  }

  monitoring.disks
    .filter((disk) => disk.percent >= 75)
    .slice(0, 3)
    .forEach((disk) => {
      insights.push({
        tone: disk.percent >= 90 ? "danger" : "warning",
        title: `Диск ${disk.mount} заполнен`,
        detail: `${clampPercent(disk.percent)}% занято · свободно ${freeLabel(disk)}`,
      });
    });

  const unhealthyServices = monitoring.services.filter((service) => service.state !== "running");
  if (unhealthyServices.length) {
    insights.push({
      tone: "warning",
      title: "Есть неработающие сервисы",
      detail: unhealthyServices.map((service) => service.name).slice(0, 3).join(", "),
    });
  }

  const hotProcess = monitoring.top_processes.find((process) => process.cpu >= 75);
  if (hotProcess) {
    insights.push({
      tone: hotProcess.cpu >= 90 ? "danger" : "warning",
      title: "Процесс забирает CPU",
      detail: `${hotProcess.name} · ${hotProcess.cpu}% CPU · PID ${hotProcess.pid}`,
    });
  }

  if (!insights.length) {
    insights.push({
      tone: "ok",
      title: "Критичных признаков нет",
      detail: "CPU, RAM, диски и сервисы выглядят штатно на последнем снимке.",
    });
  }

  return insights.slice(0, 5);
});

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
    <section class="monitor-hero" aria-label="Сводка мониторинга">
      <div class="monitor-hero-main">
        <span class="monitor-status" :class="monitoringStatus.tone">{{ monitoringStatus.label }}</span>
        <h2>{{ monitoring.hostname }}</h2>
        <p>
          Работает {{ monitoring.uptime }} · {{ compactIps(monitoring.ip_addresses) }} · снято
          {{ monitoring.collected_at || 'только что' }}
        </p>
      </div>

      <div class="monitor-summary-grid">
        <article class="monitor-summary-card" :class="metricTone(monitoring.cpu_percent)">
          <Cpu :size="18" />
          <span>CPU</span>
          <strong>{{ monitoring.cpu_percent }}%</strong>
          <small>{{ monitoring.cpu_cores }} ядер · load {{ monitoring.load_average.join(' / ') }}</small>
        </article>
        <article class="monitor-summary-card" :class="metricTone(monitoring.memory.percent)">
          <MemoryStick :size="18" />
          <span>RAM</span>
          <strong>{{ monitoring.memory.percent }}%</strong>
          <small>{{ monitoring.memory.used_label }} / {{ monitoring.memory.total_label }}</small>
        </article>
        <article class="monitor-summary-card" :class="mainDisk(monitoring.disks) ? metricTone(mainDisk(monitoring.disks)!.percent) : 'ok'">
          <HardDrive :size="18" />
          <span>Диск</span>
          <strong>{{ mainDisk(monitoring.disks) ? `${clampPercent(mainDisk(monitoring.disks)!.percent)}%` : 'n/a' }}</strong>
          <small>{{ mainDisk(monitoring.disks)?.mount || 'mount points не найдены' }}</small>
        </article>
        <article class="monitor-summary-card" :class="monitoring.services.length && runningServices(monitoring) === monitoring.services.length ? 'ok' : 'warning'">
          <ServerCog :size="18" />
          <span>Сервисы</span>
          <strong>{{ serviceHealthLabel(monitoring) }}</strong>
          <small>работают сейчас</small>
        </article>
      </div>
    </section>

    <section class="monitor-section" aria-label="Ресурсы">
      <div class="monitor-section-head">
        <div>
          <h3>История нагрузки</h3>
          <p>{{ metricHistory.length }} точек · окно {{ historyWindowLabel(metricHistory) }} · обновление каждые 5 сек</p>
        </div>
      </div>

      <div class="resource-chart-grid">
        <article class="resource-chart-card" :class="metricTone(monitoring.cpu_percent)">
          <div class="resource-chart-head">
            <Cpu :size="18" />
            <span>CPU</span>
            <strong>{{ monitoring.cpu_percent }}%</strong>
          </div>
          <svg class="resource-chart" viewBox="0 0 220 58" preserveAspectRatio="none" aria-hidden="true">
            <path class="resource-chart-area" :d="chartAreaPath(metricHistory, 'cpu')" />
            <path class="resource-chart-line" :d="chartPath(metricHistory, 'cpu')" />
          </svg>
          <div class="resource-chart-meta">
            <small>{{ monitoring.cpu_cores }} ядер · load {{ monitoring.load_average.join(' / ') }}</small>
            <span>{{ metricWindowLabel(metricHistory, 'cpu') }}</span>
          </div>
        </article>

        <article class="resource-chart-card" :class="metricTone(monitoring.memory.percent)">
          <div class="resource-chart-head">
            <MemoryStick :size="18" />
            <span>RAM</span>
            <strong>{{ monitoring.memory.percent }}%</strong>
          </div>
          <svg class="resource-chart" viewBox="0 0 220 58" preserveAspectRatio="none" aria-hidden="true">
            <path class="resource-chart-area" :d="chartAreaPath(metricHistory, 'memory')" />
            <path class="resource-chart-line" :d="chartPath(metricHistory, 'memory')" />
          </svg>
          <div class="resource-chart-meta">
            <small>{{ monitoring.memory.used_label }} / {{ monitoring.memory.total_label }}</small>
            <span>{{ metricWindowLabel(metricHistory, 'memory') }}</span>
          </div>
        </article>

        <article class="resource-chart-card" :class="metricTone(monitoring.swap.percent)">
          <div class="resource-chart-head">
            <HardDrive :size="18" />
            <span>Swap</span>
            <strong>{{ monitoring.swap.percent }}%</strong>
          </div>
          <svg class="resource-chart" viewBox="0 0 220 58" preserveAspectRatio="none" aria-hidden="true">
            <path class="resource-chart-area" :d="chartAreaPath(metricHistory, 'swap')" />
            <path class="resource-chart-line" :d="chartPath(metricHistory, 'swap')" />
          </svg>
          <div class="resource-chart-meta">
            <small>{{ monitoring.swap.used_label }} / {{ monitoring.swap.total_label }}</small>
            <span>{{ metricWindowLabel(metricHistory, 'swap') }}</span>
          </div>
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
          <div class="resource-chart-meta">
            <small>{{ monitoring.collected_at || 'только что' }}</small>
            <span>{{ metricWindowLabel(metricHistory, 'temperature') }}</span>
          </div>
        </article>
      </div>
    </section>

    <section class="monitor-section" aria-label="Что требует внимания">
      <div class="monitor-section-head">
        <div>
          <h3>Требует внимания</h3>
          <p>Автоматическая интерпретация последнего снимка</p>
        </div>
      </div>

      <div class="monitor-insight-list">
        <article v-for="insight in monitoringInsights" :key="`${insight.title}-${insight.detail}`" class="monitor-insight-card" :class="insight.tone">
          <CheckCircle2 v-if="insight.tone === 'ok'" :size="18" />
          <AlertTriangle v-else :size="18" />
          <div>
            <strong>{{ insight.title }}</strong>
            <span>{{ insight.detail }}</span>
          </div>
        </article>
      </div>
    </section>

    <section class="monitor-columns">
      <section class="monitor-section" aria-label="Диски">
        <div class="monitor-section-head">
          <div>
            <h3>Диски</h3>
            <p>{{ monitoring.disks.length }} точек монтирования</p>
          </div>
        </div>

        <div class="disk-list">
          <article v-for="disk in monitoring.disks" :key="disk.mount" class="disk-card" :class="metricTone(disk.percent)">
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
          <div>
            <h3>Сервисы</h3>
            <p>{{ serviceHealthLabel(monitoring) }} работают</p>
          </div>
        </div>

        <div class="service-list">
          <article v-for="service in monitoring.services" :key="service.id" class="service-card" :class="serviceTone(service)">
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
        <div>
          <h3>Топ процессов</h3>
          <p>по CPU на момент последнего снимка</p>
        </div>
        <Network :size="18" />
      </div>

      <div class="process-table">
        <div class="process-row head">
          <span>PID</span>
          <span>Процесс</span>
          <span>CPU</span>
          <span>RAM</span>
        </div>
        <div v-for="process in monitoring.top_processes" :key="process.pid" class="process-row" :class="processTone(process)">
          <span>{{ process.pid }}</span>
          <strong>{{ process.name }}</strong>
          <span class="process-metric" data-label="CPU">{{ process.cpu }}%</span>
          <span class="process-metric" data-label="RAM">{{ process.memory }}%</span>
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
