<script setup lang="ts">
import { ArrowLeft, Box, CheckCircle2, Layers3, Pickaxe, Plus, Server, Sparkles } from "@lucide/vue";
import type { Component } from "vue";
import type { MinecraftServerType, NewServerDraft } from "../types";

const modelValue = defineModel<NewServerDraft>({ required: true });

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
            <input
              :value="modelValue.version"
              required
              type="text"
              placeholder="1.20.1"
              @input="updateField('version', ($event.target as HTMLInputElement).value)"
            />
          </label>
        </div>
      </section>

      <div class="new-server-summary">
        <div>
          <span>Будет создан черновик</span>
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
