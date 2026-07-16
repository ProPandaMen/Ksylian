<script setup lang="ts">
import { Download, RefreshCw, ShieldCheck } from "@lucide/vue";
import type { SettingsPayload, UpdateStatusPayload } from "../types";

defineProps<{
  settings: SettingsPayload;
  updateStatus: UpdateStatusPayload;
  curseForgeApiKey: string;
  isSaving: boolean;
  isUpdateLoading: boolean;
  isApplyingUpdate: boolean;
}>();

const emit = defineEmits<{
  "update:curseForgeApiKey": [value: string];
  refresh: [];
  "refresh-agent": [];
  "refresh-update": [];
  "restart-agent": [];
  "apply-update": [];
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
            <dd>Self-update через agent</dd>
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

      <section class="settings-updates panel-lite" aria-label="Обновления Ksylian">
        <div class="settings-section-head">
          <div>
            <p class="eyebrow">updates</p>
            <h3>Обновления</h3>
          </div>
          <span
            class="settings-status"
            :class="{ connected: !updateStatus.update_available, warning: updateStatus.update_available }"
          >
            {{ updateStatus.update_available ? 'Доступно обновление' : 'Актуально' }}
          </span>
        </div>

        <div class="update-version-grid">
          <div>
            <span>Текущая версия</span>
            <strong>{{ updateStatus.current_version }} · {{ updateStatus.current_sha }}</strong>
          </div>
          <div>
            <span>Последняя версия</span>
            <strong>
              {{ updateStatus.latest_version || 'не найдена' }}
              <small v-if="updateStatus.latest_sha">· {{ updateStatus.latest_sha }}</small>
            </strong>
          </div>
        </div>

        <p class="settings-hint">
          Сервер сам проверяет GitHub tags и может обновиться до выбранного release без GitHub Actions runner.
        </p>

        <p v-if="updateStatus.updater_status !== 'ready'" class="settings-hint danger">
          Updater пока не готов:
          {{
            updateStatus.updater_status === 'agent_unavailable'
              ? 'Host Agent недоступен'
              : updateStatus.updater_status === 'not_configured'
                ? 'Host Agent не настроен'
                : 'статус неизвестен'
          }}.
        </p>

        <p v-if="updateStatus.notes" class="update-notes">{{ updateStatus.notes }}</p>

        <div class="form-actions">
          <a
            v-if="updateStatus.release_url"
            class="ghost-button"
            :href="updateStatus.release_url"
            target="_blank"
            rel="noreferrer"
          >
            Release
          </a>
          <button class="ghost-button" type="button" :disabled="isUpdateLoading" @click="emit('refresh-update')">
            <RefreshCw :size="17" />
            <span>{{ isUpdateLoading ? 'Проверяю' : 'Проверить' }}</span>
          </button>
          <button
            class="primary-button"
            type="button"
            :disabled="!updateStatus.can_update || isApplyingUpdate"
            @click="emit('apply-update')"
          >
            <Download :size="17" />
            <span>{{ isApplyingUpdate ? 'Запускаю' : 'Обновить' }}</span>
          </button>
        </div>
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
