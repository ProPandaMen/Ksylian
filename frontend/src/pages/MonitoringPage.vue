<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Cpu,
  Gauge,
  GripVertical,
  HardDrive,
  MemoryStick,
  Network,
  RotateCcw,
  Save,
  ServerCog,
  SlidersHorizontal,
  X,
} from "@lucide/vue";
import MetricChart from "../components/MetricChart.vue";
import { useAuthStore } from "../composables/useAuthStore";
import type {
  DiskUsage,
  HostMonitoring,
  MonitoringHistoryPayload,
  MonitoringHistoryPoint,
  MonitoringWindow,
  ServerState,
} from "../types";

const props = defineProps<{
  monitoring: HostMonitoring;
  metricHistory: MonitoringHistoryPoint[];
  historyMeta: MonitoringHistoryPayload;
  selectedWindow: MonitoringWindow;
  isHistoryLoading: boolean;
  monitoringStatus: { label: string; tone: string };
  stateLabels: Record<ServerState, string>;
}>();

const emit = defineEmits<{
  "change-window": [window: MonitoringWindow];
  "refresh-history": [];
}>();

type InsightTone = "ok" | "warning" | "danger";
type StaticBlockId =
  | "host"
  | "summary"
  | "charts.cpu"
  | "charts.memory"
  | "charts.disk"
  | "charts.temperatureSwap"
  | "services"
  | "processes";
type DiskBlockId = `disk:${string}`;
type BlockId = StaticBlockId | DiskBlockId;

const auth = useAuthStore();
const windows: Array<{ id: MonitoringWindow; label: string }> = [
  { id: "1h", label: "1 час" },
  { id: "6h", label: "6 часов" },
  { id: "24h", label: "24 часа" },
];
const layoutVersion = 3;
const blockLabels: Record<StaticBlockId, string> = {
  host: "Хост",
  summary: "Сводка",
  "charts.cpu": "CPU",
  "charts.memory": "RAM",
  "charts.disk": "Диски",
  "charts.temperatureSwap": "Температура и Swap",
  services: "Сервисы",
  processes: "Процессы",
};

const isEditingLayout = ref(false);
const savedBlocks = ref<BlockId[]>([]);
const draftBlocks = ref<BlockId[]>([]);
const draggedBlock = ref<BlockId | null>(null);

const visibleBlocks = computed(() => (isEditingLayout.value ? draftBlocks.value : savedBlocks.value));
const historyPoints = computed(() => props.metricHistory);
const diskBlocks = computed<BlockId[]>(() => props.monitoring.disks.map((disk) => diskBlockId(disk)));
const defaultBlocks = computed<BlockId[]>(() => [
  "host",
  "summary",
  "charts.cpu",
  "charts.memory",
  "charts.disk",
  "charts.temperatureSwap",
  "processes",
  ...diskBlocks.value,
  "services",
]);

function sanitizeBlocks(blocks: string[] | undefined | null): BlockId[] {
  const allowed = new Set(defaultBlocks.value);
  const result = (blocks || []).filter((block): block is BlockId => allowed.has(block as BlockId));
  defaultBlocks.value.forEach((block) => {
    if (!result.includes(block)) {
      result.push(block);
    }
  });
  return result;
}

function applyPreferences() {
  const storedLayout = auth.preferences.value.monitoring_layout;
  savedBlocks.value = storedLayout?.version === layoutVersion ? sanitizeBlocks(storedLayout.blocks) : [...defaultBlocks.value];
  if (!isEditingLayout.value) {
    draftBlocks.value = [...savedBlocks.value];
  }
}

onMounted(() => {
  applyPreferences();
});

watch(() => auth.preferences.value.monitoring_layout?.blocks, applyPreferences);
watch(() => props.monitoring.disks.map((disk) => disk.mount).join("|"), applyPreferences);

function startLayoutEdit() {
  draftBlocks.value = [...savedBlocks.value];
  isEditingLayout.value = true;
}

function cancelLayoutEdit() {
  draftBlocks.value = [...savedBlocks.value];
  isEditingLayout.value = false;
}

async function saveLayout() {
  savedBlocks.value = sanitizeBlocks(draftBlocks.value);
  await auth.updatePreferences({
    monitoring_layout: {
      version: layoutVersion,
      blocks: savedBlocks.value,
    },
  });
  isEditingLayout.value = false;
}

async function resetLayout() {
  draftBlocks.value = [...defaultBlocks.value];
  savedBlocks.value = [...defaultBlocks.value];
  await auth.updatePreferences({
    monitoring_layout: {
      version: layoutVersion,
      blocks: defaultBlocks.value,
    },
  });
  isEditingLayout.value = false;
}

function moveBlock(block: BlockId, direction: -1 | 1) {
  const index = draftBlocks.value.indexOf(block);
  const target = index + direction;
  if (index < 0 || target < 0 || target >= draftBlocks.value.length) {
    return;
  }
  const next = [...draftBlocks.value];
  [next[index], next[target]] = [next[target], next[index]];
  draftBlocks.value = next;
}

function startDrag(block: BlockId, event: DragEvent) {
  draggedBlock.value = block;
  event.dataTransfer?.setData("text/plain", block);
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
  }
}

function reorderDraggedBlock(target: BlockId) {
  if (!draggedBlock.value || draggedBlock.value === target) {
    return;
  }
  const next = draftBlocks.value.filter((block) => block !== draggedBlock.value);
  const targetIndex = next.indexOf(target);
  next.splice(targetIndex < 0 ? next.length : targetIndex, 0, draggedBlock.value);
  draftBlocks.value = next;
}

function dropBlock(target: BlockId) {
  reorderDraggedBlock(target);
  draggedBlock.value = null;
}

function endDrag() {
  draggedBlock.value = null;
}

function blockClass(block: BlockId) {
  const cssBlock = block.startsWith("disk:") ? "disk" : block.replace(".", "-");
  return [
    "monitor-block",
    cssBlock,
    {
      editing: isEditingLayout.value,
      dragging: draggedBlock.value === block,
    },
  ];
}

function diskBlockId(disk: DiskUsage): DiskBlockId {
  return `disk:${encodeURIComponent(disk.mount)}`;
}

function diskForBlock(block: BlockId) {
  if (!block.startsWith("disk:")) {
    return null;
  }
  const mount = decodeURIComponent(block.slice(5));
  return props.monitoring.disks.find((disk) => disk.mount === mount) || null;
}

function blockLabel(block: BlockId) {
  const disk = diskForBlock(block);
  return disk ? `Диск ${disk.mount}` : blockLabels[block as StaticBlockId];
}

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

function metricTone(percent: number) {
  if (percent >= 90) {
    return "danger";
  }
  if (percent >= 75) {
    return "warning";
  }
  return "ok";
}

function hasAttention() {
  return props.monitoringStatus.tone !== "ok" || monitoringAlerts.value.length > 0;
}

function mainDisk(disks: DiskUsage[]) {
  return disks.find((disk) => disk.mount === "/") || disks[0] || null;
}

function mainDiskPoint(point: MonitoringHistoryPoint) {
  const root = point.disks?.find((disk) => disk.mount === "/") || point.disks?.[0];
  return root?.percent ?? null;
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
  if (service.state !== "running" || service.cpu >= 75) {
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
  return ips.length ? ips.slice(0, 2).join(" · ") : "IP не найден";
}

function average(values: number[]) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
}

function metricValues(valueForPoint: (point: MonitoringHistoryPoint) => number | null | undefined) {
  return historyPoints.value
    .map(valueForPoint)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
}

function metricSummary(valueForPoint: (point: MonitoringHistoryPoint) => number | null | undefined, unit: string) {
  const values = metricValues(valueForPoint);
  if (values.length < 2) {
    return "история собирается";
  }
  const min = Math.round(Math.min(...values));
  const avg = Math.round(average(values));
  const max = Math.round(Math.max(...values));
  const delta = Math.round((values.at(-1)! - values[0]) * 10) / 10;
  const trend = Math.abs(delta) < 1 ? "стабильно" : delta > 0 ? `+${delta}${unit}` : `${delta}${unit}`;
  return `min ${min}${unit} · avg ${avg}${unit} · max ${max}${unit} · ${trend}`;
}

const servicesAnalytics = computed(() => {
  const latest = historyPoints.value.at(-1)?.services;
  const unhealthy = historyPoints.value.flatMap((point) => point.services?.unhealthy || []);
  const uniqueUnhealthy = [...new Set(unhealthy)].slice(0, 3);
  return {
    label: latest ? `${latest.running} / ${latest.total}` : serviceHealthLabel(props.monitoring),
    detail: uniqueUnhealthy.length ? `Проблемы: ${uniqueUnhealthy.join(", ")}` : "За период падений не видно",
  };
});

const monitoringInsights = computed(() => {
  const monitoring = props.monitoring;
  const insights: Array<{ tone: InsightTone; title: string; detail: string }> = [];

  if (monitoring.cpu_percent >= 75) {
    insights.push({
      tone: monitoring.cpu_percent >= 90 ? "danger" : "warning",
      title: monitoring.cpu_percent >= 90 ? "CPU близко к пределу" : "CPU требует внимания",
      detail: `${monitoring.cpu_percent}% сейчас · ${metricSummary((point) => point.cpu, "%")}`,
    });
  }
  if (monitoring.memory.percent >= 75) {
    insights.push({
      tone: monitoring.memory.percent >= 90 ? "danger" : "warning",
      title: monitoring.memory.percent >= 90 ? "RAM почти исчерпана" : "RAM растёт",
      detail: `${monitoring.memory.used_label} из ${monitoring.memory.total_label}`,
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

  if (!insights.length) {
    insights.push({
      tone: "ok",
      title: "Критичных признаков нет",
      detail: `CPU, RAM, диски и сервисы штатно · ${historyPoints.value.length} точек за период`,
    });
  }

  return insights.slice(0, 5);
});

function loadContext(point: MonitoringHistoryPoint) {
  return [`load ${(point.load_average || []).join(" / ")}`].filter(Boolean);
}

function memoryContext(point: MonitoringHistoryPoint) {
  return [`RAM ${point.memory}%`];
}

function diskContext(point: MonitoringHistoryPoint) {
  const disk = point.disks?.find((item) => item.mount === "/") || point.disks?.[0];
  return disk ? [`${disk.mount}: ${(disk.used / 1024 ** 3).toFixed(1)} GB занято`] : [];
}

function diskDonutStyle(disk: DiskUsage) {
  return {
    "--disk-used": `${clampPercent(disk.percent)}%`,
  };
}

const monitoringAlerts = computed(() => monitoringInsights.value.filter((insight) => insight.tone !== "ok"));
</script>

<template>
  <section class="monitoring-page">
    <section class="monitor-toolbar" aria-label="Настройки аналитики">
      <div class="segmented-control monitor-periods" aria-label="Период истории">
        <button
          v-for="window in windows"
          :key="window.id"
          type="button"
          :class="{ active: selectedWindow === window.id }"
          @click="emit('change-window', window.id)"
        >
          {{ window.label }}
        </button>
      </div>
      <div class="monitor-toolbar-actions">
        <span>{{ historyMeta.points.length }} точек · шаг {{ historyMeta.sample_seconds }} сек</span>
        <button v-if="!isEditingLayout" class="ghost-button compact" type="button" @click="startLayoutEdit">
          <SlidersHorizontal :size="16" />
          Настроить
        </button>
        <template v-else>
          <button class="ghost-button compact" type="button" @click="resetLayout">
            <RotateCcw :size="16" />
            Сбросить
          </button>
          <button class="ghost-button compact" type="button" @click="cancelLayoutEdit">
            <X :size="16" />
            Отмена
          </button>
          <button class="primary-button compact" type="button" @click="saveLayout">
            <Save :size="16" />
            Сохранить
          </button>
        </template>
      </div>
    </section>

    <section class="monitor-layout-grid" :class="{ editing: isEditingLayout }">
      <div
        v-for="block in visibleBlocks"
        :key="block"
        :class="blockClass(block)"
        :draggable="isEditingLayout"
        @dragstart="startDrag(block, $event)"
        @dragover.prevent="reorderDraggedBlock(block)"
        @dragenter.prevent="reorderDraggedBlock(block)"
        @drop="dropBlock(block)"
        @dragend="endDrag"
      >
        <div v-if="isEditingLayout" class="monitor-block-controls">
          <span><GripVertical :size="16" /> {{ blockLabel(block) }}</span>
          <div>
            <button type="button" :disabled="draftBlocks.indexOf(block) === 0" @click="moveBlock(block, -1)" aria-label="Выше">
              <ArrowUp :size="15" />
            </button>
            <button type="button" :disabled="draftBlocks.indexOf(block) === draftBlocks.length - 1" @click="moveBlock(block, 1)" aria-label="Ниже">
              <ArrowDown :size="15" />
            </button>
          </div>
        </div>

        <section v-if="block === 'host'" class="monitor-hero-main" aria-label="Сводка мониторинга">
          <div class="monitor-host-title">
            <h2>{{ monitoring.hostname }}</h2>
            <span v-if="hasAttention()" class="monitor-alert-badge" :class="monitoringStatus.tone">
              <AlertTriangle :size="16" />
              {{ monitoringAlerts.length || '!' }}
            </span>
          </div>
          <div class="monitor-host-facts" aria-label="Информация о хосте">
            <span><strong>Uptime</strong>{{ monitoring.uptime }}</span>
            <span><strong>IP</strong>{{ compactIps(monitoring.ip_addresses) }}</span>
            <span><strong>Снимок</strong>{{ monitoring.collected_at || 'только что' }}</span>
          </div>
        </section>

        <section v-else-if="block === 'summary'" class="monitor-summary-grid" aria-label="Ключевые показатели">
          <article class="monitor-summary-card" :class="metricTone(monitoring.cpu_percent)">
            <Cpu :size="18" />
            <span>CPU</span>
            <AlertTriangle v-if="metricTone(monitoring.cpu_percent) !== 'ok'" class="summary-alert-icon" :size="16" />
            <strong>{{ monitoring.cpu_percent }}%</strong>
            <small>{{ monitoring.cpu_cores }} ядер · load {{ monitoring.load_average.join(' / ') }}</small>
          </article>
          <article class="monitor-summary-card" :class="metricTone(monitoring.memory.percent)">
            <MemoryStick :size="18" />
            <span>RAM</span>
            <AlertTriangle v-if="metricTone(monitoring.memory.percent) !== 'ok'" class="summary-alert-icon" :size="16" />
            <strong>{{ monitoring.memory.percent }}%</strong>
            <small>{{ monitoring.memory.used_label }} / {{ monitoring.memory.total_label }}</small>
          </article>
          <article class="monitor-summary-card" :class="mainDisk(monitoring.disks) ? metricTone(mainDisk(monitoring.disks)!.percent) : 'ok'">
            <HardDrive :size="18" />
            <span>Диск</span>
            <AlertTriangle v-if="mainDisk(monitoring.disks) && metricTone(mainDisk(monitoring.disks)!.percent) !== 'ok'" class="summary-alert-icon" :size="16" />
            <strong>{{ mainDisk(monitoring.disks) ? `${clampPercent(mainDisk(monitoring.disks)!.percent)}%` : 'n/a' }}</strong>
            <small>{{ mainDisk(monitoring.disks)?.mount || 'mount points не найдены' }}</small>
          </article>
          <article class="monitor-summary-card" :class="monitoring.services.length && runningServices(monitoring) === monitoring.services.length ? 'ok' : 'warning'">
            <ServerCog :size="18" />
            <span>Сервисы</span>
            <AlertTriangle v-if="monitoring.services.length && runningServices(monitoring) !== monitoring.services.length" class="summary-alert-icon" :size="16" />
            <strong>{{ serviceHealthLabel(monitoring) }}</strong>
            <small>{{ servicesAnalytics.detail }}</small>
          </article>
        </section>

        <MetricChart
          v-else-if="block === 'charts.cpu'"
          title="CPU"
          unit="%"
          :points="historyPoints"
          :value-for-point="(point) => point.cpu"
          :tone="metricTone(monitoring.cpu_percent)"
          :current="`${monitoring.cpu_percent}%`"
          :summary="metricSummary((point) => point.cpu, '%')"
          :context-for-point="loadContext"
        />

        <MetricChart
          v-else-if="block === 'charts.memory'"
          title="RAM"
          unit="%"
          :points="historyPoints"
          :value-for-point="(point) => point.memory"
          :tone="metricTone(monitoring.memory.percent)"
          :current="`${monitoring.memory.percent}%`"
          :summary="metricSummary((point) => point.memory, '%')"
          :context-for-point="memoryContext"
        />

        <MetricChart
          v-else-if="block === 'charts.disk'"
          title="Диск"
          unit="%"
          :points="historyPoints"
          :value-for-point="mainDiskPoint"
          :tone="mainDisk(monitoring.disks) ? metricTone(mainDisk(monitoring.disks)!.percent) : 'ok'"
          :current="mainDisk(monitoring.disks) ? `${clampPercent(mainDisk(monitoring.disks)!.percent)}%` : 'n/a'"
          :summary="metricSummary(mainDiskPoint, '%')"
          :context-for-point="diskContext"
        />

        <section v-else-if="block === 'charts.temperatureSwap'" class="monitor-combo-charts">
          <MetricChart
            title="Температура"
            unit="°C"
            :points="historyPoints"
            :value-for-point="(point) => point.temperature"
            :current="monitoring.temperature"
            :summary="metricSummary((point) => point.temperature, '°C')"
            :max-value="100"
          />
          <MetricChart
            title="Swap"
            unit="%"
            :points="historyPoints"
            :value-for-point="(point) => point.swap"
            :tone="metricTone(monitoring.swap.percent)"
            :current="`${monitoring.swap.percent}%`"
            :summary="metricSummary((point) => point.swap, '%')"
          />
        </section>

        <section v-else-if="diskForBlock(block)" class="monitor-section disk-storage-card" :class="metricTone(diskForBlock(block)!.percent)" aria-label="Диск">
          <div class="disk-storage-visual">
            <div class="disk-pie" :style="diskDonutStyle(diskForBlock(block)!)" aria-hidden="true"></div>
          </div>
          <div class="disk-storage-info">
            <div class="disk-storage-title">
              <HardDrive :size="18" />
              <div>
                <h3>{{ diskForBlock(block)!.mount }}</h3>
                <p>{{ diskForBlock(block)!.filesystem }}</p>
              </div>
            </div>
            <dl class="disk-storage-stats">
              <div>
                <dt>Всего</dt>
                <dd>{{ diskForBlock(block)!.total_label }}</dd>
              </div>
              <div>
                <dt>Занято</dt>
                <dd>{{ diskForBlock(block)!.used_label }}</dd>
                <small>{{ clampPercent(diskForBlock(block)!.percent) }}% used</small>
              </div>
              <div>
                <dt>Свободно</dt>
                <dd>{{ freeLabel(diskForBlock(block)!) }}</dd>
              </div>
            </dl>
          </div>
        </section>

        <section v-else-if="block === 'services'" class="monitor-section" aria-label="Сервисы">
          <div class="monitor-section-head">
            <div>
              <h3>Сервисы</h3>
              <p>{{ servicesAnalytics.label }} работают · {{ servicesAnalytics.detail }}</p>
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
                <div><dt>CPU</dt><dd>{{ service.cpu }}%</dd></div>
                <div><dt>RAM</dt><dd>{{ service.ram }}</dd></div>
              </dl>
            </article>
          </div>
        </section>

        <section v-else-if="block === 'processes'" class="monitor-section" aria-label="Топ процессов">
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
          </div>
        </section>
      </div>
    </section>
  </section>
</template>
