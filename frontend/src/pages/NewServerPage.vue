<script setup lang="ts">
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Hammer,
  Loader2,
  Pickaxe,
  Plus,
  Sparkles,
} from "@lucide/vue";
import { computed, onMounted, ref, watch } from "vue";
import type { Component } from "vue";
import { requestJson } from "../services/api";
import type { MinecraftServerType, MinecraftVersionType, MinecraftVersionsPayload, NewServerDraft } from "../types";

const modelValue = defineModel<NewServerDraft>({ required: true });

defineProps<{
  isSubmitting?: boolean;
}>();

const emit = defineEmits<{
  submit: [];
}>();

const step = ref<1 | 2>(1);
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

const serverTypes: Array<{
  id: MinecraftServerType;
  label: string;
  note: string;
  description: string;
  icon: Component;
  available: boolean;
}> = [
  {
    id: "vanilla",
    label: "Vanilla",
    note: "готово",
    description: "Чистый Minecraft сервер без модов и плагинов. Лучший вариант для первого запуска.",
    icon: Pickaxe,
    available: true,
  },
  {
    id: "fabric",
    label: "Fabric",
    note: "готово",
    description: "Легкая база для модовых сборок и современных клиентских/серверных модов.",
    icon: Sparkles,
    available: true,
  },
  {
    id: "forge",
    label: "Forge",
    note: "готово",
    description: "Классическая экосистема для крупных модпаков и тяжелых сборок.",
    icon: Hammer,
    available: true,
  },
];

const selectedType = computed(() => serverTypes.find((item) => item.id === modelValue.value.type) ?? serverTypes[0]);

const filteredVersions = computed(() =>
  versions.value.versions.filter((version) => versionFilters.value[version.type]),
);

const selectedVersion = computed(() =>
  versions.value.versions.find((version) => version.id === modelValue.value.version),
);

const canContinue = computed(() => Boolean(selectedType.value.available));
const canSubmit = computed(() =>
  Boolean(modelValue.value.name.trim() && modelValue.value.version && selectedType.value.available),
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

function formatVersionOption(type: MinecraftVersionType) {
  if (type === "release") {
    return "Стабильный релиз";
  }
  if (type === "snapshot") {
    return "Snapshot";
  }
  if (type === "old_beta") {
    return "Beta";
  }
  return "Alpha";
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
    versions.value = await requestJson<MinecraftVersionsPayload>("/api/minecraft/versions");
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

function goNext() {
  if (!canContinue.value) {
    return;
  }
  step.value = 2;
}

function submit() {
  if (!canSubmit.value) {
    return;
  }
  emit("submit");
}

watch(filteredVersions, selectInitialVersion);
onMounted(loadMinecraftVersions);
</script>

<template>
  <section class="new-server-page">
    <div class="new-server-steps" aria-label="Шаги создания сервера">
      <span :class="{ active: step === 1, done: step > 1 }">
        <Check v-if="step > 1" :size="15" />
        <span v-else>1</span>
        Тип сервера
      </span>
      <span :class="{ active: step === 2 }">
        <span>2</span>
        Основные данные
      </span>
    </div>

    <form class="new-server-form" @submit.prevent="submit">
      <section v-if="step === 1" class="server-wizard-step">
        <div class="new-server-section-head">
          <h3>Тип сервера</h3>
        </div>

        <div class="server-type-list" role="radiogroup" aria-label="Тип сервера">
          <button
            v-for="serverType in serverTypes"
            :key="serverType.id"
            class="server-type-row"
            :class="{ selected: modelValue.type === serverType.id, disabled: !serverType.available }"
            type="button"
            role="radio"
            :disabled="!serverType.available || isSubmitting"
            :aria-checked="modelValue.type === serverType.id"
            :aria-disabled="!serverType.available"
            @click="selectType(serverType.id, serverType.available)"
          >
            <span class="server-type-icon"><component :is="serverType.icon" :size="24" /></span>
            <div class="server-type-title">
              <strong>{{ serverType.label }}</strong>
              <span>{{ serverType.available ? 'Готов к созданию' : 'Появится позже' }}</span>
            </div>
            <small>{{ serverType.note }}</small>
          </button>
        </div>

        <div class="new-server-summary">
          <div>
            <span>Выбрано</span>
            <strong>{{ selectedType.label }}</strong>
          </div>
          <button class="primary-button" type="button" :disabled="!canContinue || isSubmitting" @click="goNext">
            <span>Далее</span>
            <ChevronRight :size="18" />
          </button>
        </div>
      </section>

      <section v-else class="server-wizard-step">
        <div class="new-server-section-head">
          <h3>Основные данные</h3>
        </div>

        <div class="new-server-fields">
          <label>
            <span>Название сервера</span>
            <input
              :value="modelValue.name"
              required
              type="text"
              placeholder="Например, Ksy Survival"
              :disabled="isSubmitting"
              @input="updateField('name', ($event.target as HTMLInputElement).value)"
            />
          </label>

          <label>
            <span>Версия Minecraft</span>
            <select
              :value="modelValue.version"
              required
              :disabled="isVersionLoading || !filteredVersions.length || isSubmitting"
              @change="updateField('version', ($event.target as HTMLSelectElement).value)"
            >
              <option v-if="isVersionLoading" value="">Загружаю версии...</option>
              <option v-else-if="!filteredVersions.length" value="">Нет версий под выбранные фильтры</option>
              <option v-for="version in filteredVersions" :key="version.id" :value="version.id">
                Minecraft {{ version.id }} — {{ formatVersionOption(version.type) }}
              </option>
            </select>
          </label>
        </div>

        <div class="version-filter-row" aria-label="Фильтр версий Minecraft">
          <label>
            <input
              type="checkbox"
              :checked="versionFilters.release"
              :disabled="isSubmitting"
              @change="toggleVersionFilter('release', ($event.target as HTMLInputElement).checked)"
            />
            <span>Релизы</span>
          </label>
          <label>
            <input
              type="checkbox"
              :checked="versionFilters.snapshot"
              :disabled="isSubmitting"
              @change="toggleVersionFilter('snapshot', ($event.target as HTMLInputElement).checked)"
            />
            <span>Снапшоты</span>
          </label>
          <label>
            <input
              type="checkbox"
              :checked="versionFilters.old_beta"
              :disabled="isSubmitting"
              @change="toggleVersionFilter('old_beta', ($event.target as HTMLInputElement).checked)"
            />
            <span>Beta</span>
          </label>
          <label>
            <input
              type="checkbox"
              :checked="versionFilters.old_alpha"
              :disabled="isSubmitting"
              @change="toggleVersionFilter('old_alpha', ($event.target as HTMLInputElement).checked)"
            />
            <span>Alpha</span>
          </label>
        </div>

        <p v-if="versionError" class="version-error">{{ versionError }}</p>

        <div v-if="isSubmitting" class="provisioning-card">
          <Loader2 :size="22" />
          <div>
            <strong>Подготавливаю сервер</strong>
            <span>Создаю файлы, скачиваю server.jar и настраиваю systemd-сервис. Это может занять немного времени.</span>
          </div>
        </div>

        <div class="new-server-summary">
          <button class="ghost-button" type="button" :disabled="isSubmitting" @click="step = 1">
            <ChevronLeft :size="18" />
            <span>Назад</span>
          </button>

          <div>
            <span>Будет создан сервер</span>
            <strong>
              {{ modelValue.name || 'Без названия' }}
              <template v-if="modelValue.version"> · Minecraft {{ modelValue.version }}</template>
            </strong>
            <small>{{ selectedType.label }}{{ selectedVersion ? ` · ${formatVersionOption(selectedVersion.type)}` : '' }}</small>
          </div>

          <button class="primary-button" type="submit" :disabled="!canSubmit || isSubmitting">
            <Loader2 v-if="isSubmitting" class="spinning" :size="18" />
            <Plus v-else :size="18" />
            <span>{{ isSubmitting ? 'Создаю...' : 'Создать сервер' }}</span>
          </button>
        </div>
      </section>
    </form>
  </section>
</template>
