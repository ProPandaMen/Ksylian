<script setup lang="ts">
import { computed, ref } from "vue";
import type { MonitoringHistoryPoint, MonitoringWindow } from "../types";

const props = defineProps<{
  title: string;
  unit: string;
  points: MonitoringHistoryPoint[];
  window: MonitoringWindow;
  sampleSeconds: number;
  valueForPoint: (point: MonitoringHistoryPoint) => number | null | undefined;
  tone?: "ok" | "warning" | "danger";
  current: string;
  summary: string;
  contextForPoint?: (point: MonitoringHistoryPoint, previous?: MonitoringHistoryPoint) => string[];
  maxValue?: number;
}>();

const width = 260;
const height = 82;
const activeIndex = ref<number | null>(null);
const windowSeconds: Record<MonitoringWindow, number> = {
  "1h": 60 * 60,
  "6h": 6 * 60 * 60,
  "24h": 24 * 60 * 60,
};
const maxVisiblePoints = computed(() => Math.floor((windowSeconds[props.window] || windowSeconds["1h"]) / Math.max(1, props.sampleSeconds)) + 1);
const visiblePoints = computed(() => props.points.slice(-maxVisiblePoints.value));

const chartPoints = computed(() =>
  visiblePoints.value
    .map((point, index) => ({ point, index, value: props.valueForPoint(point) }))
    .filter((item): item is { point: MonitoringHistoryPoint; index: number; value: number } =>
      typeof item.value === "number" && Number.isFinite(item.value),
    ),
);

const hasHistory = computed(() => chartPoints.value.length >= 2);
const safeMax = computed(() => Math.max(props.maxValue || 100, ...chartPoints.value.map((item) => item.value), 1));
const timeRange = computed(() => {
  const selectedWindow = windowSeconds[props.window] || windowSeconds["1h"];
  const latestTimestamp = chartPoints.value.at(-1)?.point.timestamp ?? Math.floor(Date.now() / 1000);
  return {
    start: latestTimestamp - selectedWindow,
    end: latestTimestamp,
    span: selectedWindow,
  };
});

const plotted = computed(() =>
  chartPoints.value.map((item) => {
    const progress = (item.point.timestamp - timeRange.value.start) / Math.max(1, timeRange.value.span);
    const x = Math.min(width, Math.max(0, progress * width));
    const y = height - (Math.min(safeMax.value, Math.max(0, item.value)) / safeMax.value) * height;
    return { ...item, x, y };
  }),
);

const activePoint = computed(() => {
  if (!plotted.value.length || activeIndex.value === null) {
    return null;
  }
  return plotted.value[Math.min(Math.max(0, activeIndex.value), plotted.value.length - 1)];
});

const linePath = computed(() =>
  plotted.value
    .map((item, index) => `${index === 0 ? "M" : "L"} ${item.x.toFixed(1)} ${item.y.toFixed(1)}`)
    .join(" "),
);

const areaPath = computed(() => `${linePath.value} L ${width} ${height} L 0 ${height} Z`);

const tooltipStyle = computed(() => {
  const point = activePoint.value;
  if (!point) {
    return {};
  }
  const left = point.x > width * 0.66 ? point.x - 132 : point.x + 12;
  return {
    left: `${Math.max(8, Math.min(width - 132, left))}px`,
    top: `${Math.max(8, point.y - 12)}px`,
  };
});

const tooltipLines = computed(() => {
  const item = activePoint.value;
  if (!item) {
    return [];
  }
  const previous = plotted.value[Math.max(0, plotted.value.indexOf(item) - 1)]?.point;
  const lines = [
    item.point.collected_at || new Date(item.point.timestamp * 1000).toLocaleTimeString("ru-RU"),
    `${item.value}${props.unit}`,
  ];
  if (previous) {
    const previousValue = props.valueForPoint(previous);
    if (typeof previousValue === "number" && Number.isFinite(previousValue)) {
      const delta = Math.round((item.value - previousValue) * 10) / 10;
      lines.push(`${delta >= 0 ? "+" : ""}${delta}${props.unit} к прошлой точке`);
    }
  }
  return [...lines, ...(props.contextForPoint?.(item.point, previous) || [])];
});

function setActiveFromClientX(clientX: number, element: SVGElement) {
  if (!plotted.value.length) {
    return;
  }
  const rect = element.getBoundingClientRect();
  const x = ((clientX - rect.left) / Math.max(1, rect.width)) * width;
  const nearest = plotted.value.reduce((selected, item) => (Math.abs(item.x - x) < Math.abs(selected.x - x) ? item : selected));
  activeIndex.value = plotted.value.indexOf(nearest);
}

function setActiveFromEvent(event: MouseEvent | PointerEvent) {
  if (event.currentTarget instanceof SVGElement) {
    setActiveFromClientX(event.clientX, event.currentTarget);
  }
}

function moveActive(delta: number) {
  if (!plotted.value.length) {
    return;
  }
  const current = activeIndex.value ?? plotted.value.length - 1;
  activeIndex.value = Math.min(Math.max(0, current + delta), plotted.value.length - 1);
}

function activateLatest() {
  if (plotted.value.length && activeIndex.value === null) {
    activeIndex.value = plotted.value.length - 1;
  }
}
</script>

<template>
  <article class="metric-chart-card" :class="[tone || 'ok', { empty: !hasHistory }]">
    <div class="metric-chart-head">
      <div>
        <span>{{ title }}</span>
        <strong>{{ current }}</strong>
      </div>
      <small>{{ summary }}</small>
    </div>

    <div class="metric-chart-shell">
      <svg
        class="metric-chart"
        :viewBox="`0 0 ${width} ${height}`"
        preserveAspectRatio="none"
        tabindex="0"
        role="img"
        :aria-label="`${title}: ${current}`"
        @mousemove="setActiveFromEvent"
        @pointerdown="setActiveFromEvent"
        @mouseleave="activeIndex = null"
        @focus="activateLatest"
        @blur="activeIndex = null"
        @keydown.left.prevent="moveActive(-1)"
        @keydown.right.prevent="moveActive(1)"
      >
        <path v-if="hasHistory" class="metric-chart-area" :d="areaPath" />
        <path v-if="hasHistory" class="metric-chart-line" :d="linePath" />
        <line v-if="activePoint && hasHistory" class="metric-chart-guide" :x1="activePoint.x" y1="0" :x2="activePoint.x" :y2="height" />
        <circle v-if="activePoint && hasHistory" class="metric-chart-dot" :cx="activePoint.x" :cy="activePoint.y" r="4" />
      </svg>

      <div v-if="!hasHistory" class="metric-chart-empty">История собирается</div>
      <div v-if="activePoint && hasHistory" class="metric-chart-tooltip" :style="tooltipStyle">
        <strong>{{ title }}</strong>
        <span v-for="line in tooltipLines" :key="line">{{ line }}</span>
      </div>
    </div>
  </article>
</template>
