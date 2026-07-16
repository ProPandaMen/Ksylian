<script setup lang="ts">
import { ArrowLeft, Box, CheckCircle2, Layers3, Pickaxe, Plus, RefreshCw, Server, Sparkles } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import type { Component } from "vue";
import type { MinecraftServerType, MinecraftVersionType, MinecraftVersionsPayload, NewServerDraft } from "../types";

const modelValue = defineModel<NewServerDraft>({ required: true });
const versions = ref<MinecraftVersionsPayload>({
  latest_release: "",
  latest_snapshot: "",
  versions: [],
});
const versionFilters = ref<Record<MinecraftVersionType, boolean>>({
  release: true,
  snapshot: false,
  old_beta: false,
  old_alpha: false,
});
const isVersionLoading = ref(false);
const versionError = ref("");

const emit = defineEmits<{
  cancel: [];
  submit: [];
}>();

const serverTypes: Array<{
  id: MinecraftServerType;
  label: string;
  description: string;
  icon: Component;
  available: boolean;
}> = [
  {
    id: "vanilla",
    label: "Vanilla",
    description: "Чистый Minecraft без модов и плагинов.",
    icon: Pickaxe,
    available: true,
  },
  {
    id: "fabric",
    label: "Fabric",
    description: "Лёгкий mod loader для современных сборок.",
    icon: Box,
    available: false,
  },
  {
    id: "forge",
    label: "Forge",
    description: "Классическая база для больших модовых сборок.",
    icon: Layers3,
    available: false,
  },
  {
    id: "neoforge",
    label: "NeoForge",
    description: "Новая ветка Forge-экосистемы.",
    icon: Sparkles,
    available: false,
  },
  {
    id: "quilt",
    label: "Quilt",
    description: "Совместимый loader для Quilt/Fabric-модов.",
    icon: CheckCircle2,
    available: false,
  },
  {
    id: "paper",
    label: "Paper / Purpur",
    description: "Производительная база для плагин-серверов.",
    icon: Server,
    available: true,
  },
];

const versionTypeLabels: Record<MinecraftVersionType, string> = {
  release: "релиз",
  snapshot: "снапшот",
  old_beta: "beta",
  old_alpha: "alpha",
};

const filteredVersions = computed(() =>
  versions.value.versions.filter((version) => versionFilters.value[version.type]),
);

function updateField(field: keyof NewServerDraft, value: string) {
  modelValue.value = {
    ...modelValue.value,
    [field]: value,
  };
}

function selectType(type: MinecraftServerType, isAvailable: boolean) {
  if (!isAvailable) {
    return;
  }

  updateField("type", type);
}

function selectInitialVersion() {
  const visibleVersions = filteredVersions.value;
  if (modelValue.value.version && visibleVersions.some((version) => version.id === modelValue.value.version)) {
    return;
  }

  const latestRelease = visibleVersions.find((version) => version.id === versions.value.latest_release);
  const preferredVersion = latestRelease?.id || visibleVersions[0]?.id || "";
  if (preferredVersion) {
    updateField("version", preferredVersion);
  }
}

async function loadMinecraftVersions() {
  isVersionLoading.value = true;
  versionError.value = "";

  try {
    const response = await fetch("/api/minecraft/versions");
    if (!response.ok) {
      throw new Error(`API returned ${response.status}`);
    }
    versions.value = await response.json() as MinecraftVersionsPayload;
    selectInitialVersion();
  } catch (error) {
    versionError.value = "Не удалось загрузить список версий Minecraft";
    console.error(error);
  } finally {
    isVersionLoading.value = false;
  }
}

function toggleVersionFilter(type: MinecraftVersionType, value: boolean) {
  versionFilters.value = {
    ...versionFilters.value,
    [type]: value,
  };
  selectInitialVersion();
}

onMounted(loadMinecraftVersions);
</script>

<template>
  <section class="new-server-page">
    <section class="panel new-server-hero">
      <button class="ghost-button compact" type="button" @click="emit('cancel')">
        <ArrowLeft :size="16" />
        <span>К списку</span>
      </button>
      <div>
        <p class="eyebrow">new instance</p>
        <h2>Настройка нового сервера</h2>
        <p>
          Для первого запуска достаточно выбрать тип, название и версию Minecraft.
          Остальные параметры добавим следующим шагом, когда подключим provisioner.
        </p>
      </div>
    </section>

    <form class="panel new-server-form" @submit.prevent="emit('submit')">
      <section class="form-block">
        <div class="settings-section-head">
          <div>
            <p class="eyebrow">server type</p>
            <h3>Тип сервера</h3>
          </div>
        </div>

        <div class="server-type-grid" role="radiogroup" aria-label="Тип сервера">
          <button
            v-for="serverType in serverTypes"
            :key="serverType.id"
            class="server-type-card"
            :class="{ selected: modelValue.type === serverType.id, disabled: !serverType.available }"
            type="button"
            role="radio"
            :disabled="!serverType.available"
            :aria-checked="modelValue.type === serverType.id"
            :aria-disabled="!serverType.available"
            @click="selectType(serverType.id, serverType.available)"
          >
            <component :is="serverType.icon" :size="22" />
            <div class="server-type-title">
              <strong>{{ serverType.label }}</strong>
              <small v-if="!serverType.available">скоро</small>
            </div>
            <span>{{ serverType.description }}</span>
          </button>
        </div>
      </section>

      <section class="form-block">
        <div class="settings-section-head">
          <div>
            <p class="eyebrow">basic info</p>
            <h3>Основные данные</h3>
          </div>
        </div>

        <div class="new-server-fields">
          <label>
            <span>Название сервера</span>
            <input
              :value="modelValue.name"
              required
              type="text"
              placeholder="Например, Ksy Survival"
              @input="updateField('name', ($event.target as HTMLInputElement).value)"
            />
          </label>

          <label>
            <span>Версия Minecraft</span>
            <select
              :value="modelValue.version"
              required
              :disabled="isVersionLoading || !filteredVersions.length"
              @change="updateField('version', ($event.target as HTMLSelectElement).value)"
            >
              <option v-if="isVersionLoading" value="">Загружаю версии...</option>
              <option v-else-if="!filteredVersions.length" value="">Нет версий под фильтры</option>
              <option v-for="version in filteredVersions" :key="version.id" :value="version.id">
                {{ version.label }} · {{ versionTypeLabels[version.type] }}
              </option>
            </select>
          </label>
        </div>

        <div class="version-filter-row" aria-label="Фильтр версий Minecraft">
          <label>
            <input
              type="checkbox"
              :checked="versionFilters.release"
              @change="toggleVersionFilter('release', ($event.target as HTMLInputElement).checked)"
            />
            <span>Релизы</span>
          </label>
          <label>
            <input
              type="checkbox"
              :checked="versionFilters.snapshot"
              @change="toggleVersionFilter('snapshot', ($event.target as HTMLInputElement).checked)"
            />
            <span>Снапшоты</span>
          </label>
          <label>
            <input
              type="checkbox"
              :checked="versionFilters.old_beta"
              @change="toggleVersionFilter('old_beta', ($event.target as HTMLInputElement).checked)"
            />
            <span>Beta</span>
          </label>
          <label>
            <input
              type="checkbox"
              :checked="versionFilters.old_alpha"
              @change="toggleVersionFilter('old_alpha', ($event.target as HTMLInputElement).checked)"
            />
            <span>Alpha</span>
          </label>
          <button class="ghost-button compact" type="button" :disabled="isVersionLoading" @click="loadMinecraftVersions">
            <RefreshCw :size="15" />
            <span>{{ isVersionLoading ? 'Обновляю' : 'Обновить' }}</span>
          </button>
        </div>

        <p v-if="versionError" class="version-error">{{ versionError }}</p>
      </section>

      <div class="new-server-summary">
        <div>
          <span>Будет создан сервер</span>
          <strong>{{ modelValue.name || 'Без названия' }} · {{ modelValue.version }}</strong>
        </div>
        <button class="primary-button" type="submit">
          <Plus :size="18" />
          <span>Создать сервер</span>
        </button>
      </div>
    </form>
  </section>
</template>
