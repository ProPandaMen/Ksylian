<script setup lang="ts">
import { RefreshCw } from "@lucide/vue";
import { useDashboardStore } from "../../composables/useDashboardStore";

const store = useDashboardStore();
</script>

<template>
  <section class="server-tab-panel">
      <section class="server-detail-section server-config-panel">
        <div class="server-detail-section-head">
          <h3>server.properties</h3>
          <div class="panel-actions">
            <button class="ghost-button compact" type="button" :aria-busy="store.isConfigLoading.value" @click="store.loadServerConfig()">
              <RefreshCw :class="{ spinning: store.isConfigLoading.value }" :size="16" />
              <span>Обновить</span>
            </button>
            <button class="primary-button compact" type="button" :disabled="store.isConfigSaving.value" @click="store.saveServerConfig">
              <span>{{ store.isConfigSaving.value ? 'Сохраняю' : 'Сохранить' }}</span>
            </button>
          </div>
        </div>
        <textarea
          v-model="store.selectedServerConfig.value"
          class="config-editor"
          spellcheck="false"
          :disabled="store.isConfigLoading.value || store.isConfigSaving.value"
          placeholder="server.properties пока не загружен"
        ></textarea>
      </section>
    </section>
</template>
