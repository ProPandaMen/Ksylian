<script setup lang="ts">
import { Download, RefreshCw, ShieldCheck } from "@lucide/vue";
import { computed } from "vue";
import type { AuthUser, SettingsPayload, ThemeName, UpdateStatusPayload } from "../types";

const props = defineProps<{
  settings: SettingsPayload;
  updateStatus: UpdateStatusPayload;
  curseForgeApiKey: string;
  isSaving: boolean;
  isUpdateLoading: boolean;
  isApplyingUpdate: boolean;
  user: AuthUser | null;
  themes: Array<{ id: ThemeName; label: string }>;
}>();

const emit = defineEmits<{
  "update:curseForgeApiKey": [value: string];
  "refresh-agent": [];
  "refresh-update": [];
  "restart-agent": [];
  "apply-update": [];
  "update-theme": [theme: ThemeName];
  save: [];
  clear: [];
}>();

const curseForgeStatusLabel = computed(() => {
  if (!props.settings.has_curseforge_api_key) {
    return "Не подключено";
  }
  if (props.settings.curseforge_api_key_status === "valid") {
    return "Подключено";
  }
  if (props.settings.curseforge_api_key_status === "invalid") {
    return "Неверный ключ";
  }
  return "Проверка";
});
</script>

<template>
  <section class="settings-page">
    <div class="settings-sections">
      <section class="settings-section" aria-label="Профиль пользователя">
        <div class="settings-section-head">
          <div>
            <h3>Профиль</h3>
          </div>
        </div>

        <div class="settings-row" v-if="user">
          <span>Пользователь</span>
          <strong>{{ user.display_name }}</strong>
        </div>

        <div v-if="user" class="settings-theme-row">
          <div class="settings-row-title">
            <span>Цветовая схема</span>
          </div>
          <div class="theme-picker settings-theme-picker">
            <button
              v-for="item in themes"
              :key="item.id"
              class="theme-option"
              :class="[item.id, { selected: user.theme === item.id }]"
              type="button"
              @click="emit('update-theme', item.id)"
            >
              <span></span>
              {{ item.label }}
            </button>
          </div>
        </div>
      </section>

      <section class="settings-section" aria-label="Интеграции">
        <form class="settings-form" @submit.prevent="emit('save')">
          <div class="settings-section-head">
            <div>
              <h3>CurseForge</h3>
            </div>
            <span
              class="settings-status"
              :class="{
                connected: settings.curseforge_api_key_status === 'valid',
                warning: settings.curseforge_api_key_status === 'unchecked',
                danger: settings.curseforge_api_key_status === 'invalid',
              }"
            >
              {{ curseForgeStatusLabel }}
            </span>
          </div>

          <div class="settings-row">
            <span>Текущий ключ</span>
            <strong>
              {{ settings.has_curseforge_api_key ? settings.curseforge_api_key_mask : 'не задан' }}
            </strong>
          </div>

          <p
            v-if="settings.has_curseforge_api_key && settings.curseforge_api_key_status === 'invalid'"
            class="settings-hint danger"
          >
            Сохранённый ключ не прошёл проверку CurseForge. Укажи корректный API key и сохрани заново.
          </p>

          <label>
            <span>API key</span>
            <input
              :value="curseForgeApiKey"
              autocomplete="off"
              spellcheck="false"
              type="password"
              placeholder="Новый ключ"
              @input="emit('update:curseForgeApiKey', ($event.target as HTMLInputElement).value)"
            />
          </label>

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
      </section>

      <section class="settings-section" aria-label="Host Agent">
        <div class="settings-section-head">
          <div>
            <h3>Agent</h3>
          </div>
          <span class="settings-status" :class="{ connected: settings.agent.available }">
            {{ settings.agent.available ? 'Онлайн' : settings.agent.configured ? 'Недоступен' : 'Не настроен' }}
          </span>
        </div>

        <div class="settings-actions-row">
          <button class="ghost-button" type="button" @click="emit('refresh-agent')">
            <RefreshCw :size="17" />
            <span>Проверить</span>
          </button>
          <button class="primary-button" type="button" :disabled="!settings.agent.available" @click="emit('restart-agent')">
            <RefreshCw :size="17" />
            <span>Перезапустить</span>
          </button>
        </div>

        <p v-if="settings.agent.configured && !settings.agent.available" class="settings-hint danger">
          Agent не отвечает. Запусти на сервере: sudo systemctl start ksylian-agent.service
        </p>
      </section>

      <section class="settings-section" aria-label="Публикация серверов">
        <div class="settings-section-head">
          <div>
            <h3>Публикация</h3>
          </div>
          <span class="settings-status" :class="{ connected: settings.agent.public_domain }">
            {{ settings.agent.public_domain ? 'Настроено' : 'Не настроено' }}
          </span>
        </div>

        <dl class="settings-rows">
          <div class="settings-row">
            <dt>Домен</dt>
            <dd>{{ settings.agent.public_domain || 'не задан' }}</dd>
          </div>
          <div class="settings-row">
            <dt>Proxy</dt>
            <dd>
              {{
                settings.agent.proxy_domain
                  ? `${settings.agent.proxy_domain}:${settings.agent.proxy_port || '25565'}`
                  : 'не настроен'
              }}
            </dd>
          </div>
        </dl>
      </section>

      <section class="settings-section" aria-label="Обновления Ksylian">
        <div class="settings-section-head">
          <div>
            <h3>Обновления</h3>
          </div>
          <span
            class="settings-status"
            :class="{ connected: !updateStatus.update_available, warning: updateStatus.update_available }"
          >
            {{ updateStatus.update_available ? 'Доступно обновление' : 'Актуально' }}
          </span>
        </div>

        <div class="settings-version-list">
          <div class="settings-row">
            <span>Текущая версия</span>
            <strong>{{ updateStatus.current_version }} · {{ updateStatus.current_sha }}</strong>
          </div>
          <div class="settings-row">
            <span>Последняя версия</span>
            <strong>
              {{ updateStatus.latest_version || 'не найдена' }}
              <small v-if="updateStatus.latest_sha">· {{ updateStatus.latest_sha }}</small>
            </strong>
          </div>
        </div>

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

        <div class="settings-actions-row">
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

      <section class="settings-section" aria-label="Системная информация">
        <div class="settings-section-head">
          <div>
            <h3>Окружение</h3>
          </div>
        </div>
        <dl class="settings-rows">
          <div class="settings-row">
            <dt>Host Agent</dt>
            <dd>{{ settings.agent.available ? 'Запущен' : settings.agent.configured ? 'Недоступен' : 'Не настроен' }}</dd>
          </div>
          <div class="settings-row">
            <dt>Backend</dt>
            <dd>/api</dd>
          </div>
          <div class="settings-row">
            <dt>Frontend port</dt>
            <dd>8088</dd>
          </div>
          <div class="settings-row">
            <dt>Backend port</dt>
            <dd>8090</dd>
          </div>
        </dl>
      </section>
    </div>
  </section>
</template>
