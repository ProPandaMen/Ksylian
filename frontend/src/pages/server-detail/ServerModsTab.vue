<script setup lang="ts">
import { ref } from "vue";
import { Package, RefreshCw } from "@lucide/vue";
import { useDashboardStore } from "../../composables/useDashboardStore";

const store = useDashboardStore();
const modUploadInput = ref<HTMLInputElement | null>(null);
const modBulkUpdateInput = ref<HTMLInputElement | null>(null);
const modUpdateInput = ref<HTMLInputElement | null>(null);
const pendingModUpdatePath = ref("");

async function installSelectedMods(event: Event) {
  const input = event.target as HTMLInputElement;
  const selectedFiles = Array.from(input.files || []).filter((file) => file.name.endsWith(".jar"));
  await store.installServerMods(selectedFiles);
  input.value = "";
}

async function bulkUpdateSelectedMods(event: Event) {
  const input = event.target as HTMLInputElement;
  const selectedFiles = Array.from(input.files || []).filter((file) => file.name.endsWith(".jar"));
  await store.bulkUpdateServerMods(selectedFiles);
  input.value = "";
}

function chooseModUpdate(path: string) {
  pendingModUpdatePath.value = path;
  modUpdateInput.value?.click();
}

async function updateSelectedMod(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file && pendingModUpdatePath.value) {
    await store.updateServerMod(pendingModUpdatePath.value, file);
  }
  pendingModUpdatePath.value = "";
  input.value = "";
}
</script>

<template>
  <section class="server-tab-panel">
      <section class="server-detail-section">
        <div class="server-detail-section-head">
          <h3>Установленные моды</h3>
          <div class="panel-actions">
            <input ref="modUploadInput" type="file" multiple accept=".jar" class="visually-hidden" @change="installSelectedMods" />
            <input ref="modBulkUpdateInput" type="file" multiple accept=".jar" class="visually-hidden" @change="bulkUpdateSelectedMods" />
            <input ref="modUpdateInput" type="file" accept=".jar" class="visually-hidden" @change="updateSelectedMod" />
            <button class="ghost-button compact" type="button" @click="modUploadInput?.click()">Установить JAR</button>
            <button class="ghost-button compact" type="button" @click="modBulkUpdateInput?.click()">Обновить JAR</button>
            <button class="ghost-button compact" type="button" @click="store.runBulkModAction('disable')">Отключить все</button>
            <button class="ghost-button compact" type="button" @click="store.runBulkModAction('enable')">Включить все</button>
            <button class="ghost-button compact" type="button" @click="store.loadServerMods()">
              <RefreshCw :size="16" />
              <span>{{ store.isModLoading.value ? 'Сканирую' : 'Сканировать' }}</span>
            </button>
          </div>
        </div>
        <div class="server-mod-list">
          <article v-for="mod in store.selectedServerMods.value" :key="mod.path" class="server-mod-row" :class="{ disabled: !mod.enabled }">
            <Package :size="20" />
            <div>
              <strong>{{ mod.name }}</strong>
              <span>{{ mod.id }} · {{ mod.version || 'без версии' }} · {{ mod.loader }}</span>
              <small>{{ mod.filename }} · {{ mod.size }}</small>
              <em v-for="warning in mod.warnings" :key="warning">{{ warning }}</em>
            </div>
            <div class="server-mod-actions">
              <button class="ghost-button compact" type="button" @click="store.runModAction(mod.enabled ? 'disable' : 'enable', mod.path)">
                {{ mod.enabled ? 'Отключить' : 'Включить' }}
              </button>
              <button class="ghost-button compact" type="button" @click="chooseModUpdate(mod.path)">Обновить</button>
              <button class="ghost-button compact" type="button" @click="store.runModAction('pin', mod.path)">Зафиксировать</button>
              <button class="ghost-button compact danger" type="button" @click="store.runModAction('delete', mod.path)">Удалить</button>
            </div>
          </article>
          <article v-if="!store.selectedServerMods.value.length" class="server-empty-state">
            <div>
              <strong>Моды не найдены</strong>
              <span>Сканер читает JAR-файлы из папки mods.</span>
            </div>
          </article>
        </div>
      </section>
    </section>
</template>
