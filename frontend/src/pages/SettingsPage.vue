<script setup lang="ts">
import { RefreshCw, ShieldCheck } from "@lucide/vue";
import type { SettingsPayload } from "../types";

defineProps<{
  settings: SettingsPayload;
  curseForgeApiKey: string;
  isSaving: boolean;
}>();

const emit = defineEmits<{
  "update:curseForgeApiKey": [value: string];
  refresh: [];
  save: [];
  clear: [];
}>();
</script>

<template>
  <section class="panel settings-panel">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">configuration</p>
        <h2>Настройки проекта</h2>
      </div>
      <button class="icon-button" type="button" title="Обновить" @click="emit('refresh')">
        <RefreshCw :size="18" />
      </button>
    </div>
    <div class="settings-layout">
      <form class="settings-form" @submit.prevent="emit('save')">
        <div class="settings-section-head">
          <div>
            <p class="eyebrow">curseforge</p>
            <h3>Интеграция с каталогом</h3>
          </div>
          <span class="settings-status" :class="{ connected: settings.has_curseforge_api_key }">
            {{ settings.has_curseforge_api_key ? 'Подключено' : 'Не подключено' }}
          </span>
        </div>

        <div class="settings-current">
          <span>Текущий ключ</span>
          <strong>
            {{ settings.has_curseforge_api_key ? settings.curseforge_api_key_mask : 'не задан' }}
          </strong>
        </div>

        <label>
          <span>CurseForge API key</span>
          <input
            :value="curseForgeApiKey"
            autocomplete="off"
            spellcheck="false"
            type="password"
            placeholder="Вставь новый ключ"
            @input="emit('update:curseForgeApiKey', ($event.target as HTMLInputElement).value)"
          />
        </label>

        <p class="settings-hint">
          Ключ хранится только на backend. В браузер возвращается только статус и маска.
        </p>

        <div class="form-actions">
          <button class="ghost-button" type="button" @click="emit('clear')">
            Очистить
          </button>
          <button class="primary-button" type="submit" :disabled="isSaving">
            <ShieldCheck :size="18" />
            <span>{{ isSaving ? 'Сохраняю' : 'Сохранить' }}</span>
          </button>
        </div>
      </form>

      <section class="settings-summary" aria-label="Системная информация">
        <div class="settings-section-head">
          <div>
            <p class="eyebrow">system</p>
            <h3>Окружение</h3>
          </div>
        </div>
        <dl>
          <div>
            <dt>Backend</dt>
            <dd>Подключён через /api</dd>
          </div>
          <div>
            <dt>Deploy</dt>
            <dd>GitHub tag → self-hosted runner</dd>
          </div>
          <div>
            <dt>Frontend port</dt>
            <dd>8088</dd>
          </div>
          <div>
            <dt>Backend port</dt>
            <dd>8090</dd>
          </div>
        </dl>
      </section>
    </div>
  </section>
</template>
