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
  "refresh-agent": [];
  "restart-agent": [];
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
            <dt>Host Agent</dt>
            <dd>{{ settings.agent.available ? 'Запущен' : settings.agent.configured ? 'Недоступен' : 'Не настроен' }}</dd>
          </div>
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

      <section class="settings-agent panel-lite" aria-label="Host Agent">
        <div class="settings-section-head">
          <div>
            <p class="eyebrow">host agent</p>
            <h3>Сбор метрик и управление серверами</h3>
          </div>
          <span class="settings-status" :class="{ connected: settings.agent.available }">
            {{ settings.agent.available ? 'Онлайн' : settings.agent.configured ? 'Недоступен' : 'Не настроен' }}
          </span>
        </div>
        <p class="settings-hint">
          Agent работает на хосте и отдаёт реальные серверы, логи, systemd-статусы и нагрузку.
          Если он недоступен, панель больше не показывает демо-серверы.
        </p>
        <div class="form-actions">
          <button class="ghost-button" type="button" @click="emit('refresh-agent')">
            <RefreshCw :size="17" />
            <span>Проверить</span>
          </button>
          <button class="primary-button" type="button" :disabled="!settings.agent.available" @click="emit('restart-agent')">
            <RefreshCw :size="17" />
            <span>Перезапустить agent</span>
          </button>
        </div>
        <p v-if="settings.agent.configured && !settings.agent.available" class="settings-hint danger">
          Agent не отвечает. Если кнопка перезапуска недоступна, запусти на сервере:
          sudo systemctl start ksylian-agent.service
        </p>
      </section>
    </div>
  </section>
</template>
