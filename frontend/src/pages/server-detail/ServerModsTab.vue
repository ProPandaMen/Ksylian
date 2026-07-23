<script setup lang="ts">
import { ref } from "vue";
import { Package, RefreshCw } from "@lucide/vue";
import { useDashboardStore } from "../../composables/useDashboardStore";
import { requestJson } from "../../services/api";
import type { BuildManifest, SafeUpdateResult } from "../../types";

const store = useDashboardStore();
const modUploadInput = ref<HTMLInputElement | null>(null);
const modBulkUpdateInput = ref<HTMLInputElement | null>(null);
const modUpdateInput = ref<HTMLInputElement | null>(null);
const pendingModUpdatePath = ref("");
const manifest = ref<BuildManifest | null>(null);
const safeUpdate = ref<SafeUpdateResult | null>(null);
const manifestMessage = ref("");
const isManifestLoading = ref(false);

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

async function refreshManifest() {
  const serverId = store.selectedServer.value?.id;
  if (!serverId) {
    return;
  }
  isManifestLoading.value = true;
  manifestMessage.value = "";
  try {
    manifest.value = await requestJson<BuildManifest>(`/api/servers/${serverId}/manifest/refresh`, { method: "POST" });
    manifestMessage.value = `Manifest обновлён: ${manifest.value.mods.length} модов`;
  } catch (error) {
    manifestMessage.value = "Не удалось обновить manifest";
    console.error(error);
  } finally {
    isManifestLoading.value = false;
  }
}

async function exportManifest() {
  const serverId = store.selectedServer.value?.id;
  if (!serverId) {
    return;
  }
  try {
    const result = await requestJson<{ name: string }>(`/api/servers/${serverId}/manifest/export`, { method: "POST" });
    manifestMessage.value = `Экспорт создан: ${result.name}`;
  } catch (error) {
    manifestMessage.value = "Не удалось экспортировать сборку";
    console.error(error);
  }
}

async function planSafeUpdate() {
  const serverId = store.selectedServer.value?.id;
  if (!serverId) {
    return;
  }
  isManifestLoading.value = true;
  try {
    safeUpdate.value = await requestJson<SafeUpdateResult>(`/api/servers/${serverId}/updates/plan`, { method: "POST" });
    manifestMessage.value = safeUpdate.value.message;
  } catch (error) {
    manifestMessage.value = "Не удалось подготовить safe update";
    console.error(error);
  } finally {
    isManifestLoading.value = false;
  }
}

async function applySafeUpdate() {
  const serverId = store.selectedServer.value?.id;
  if (!serverId || !safeUpdate.value) {
    return;
  }
  isManifestLoading.value = true;
  try {
    safeUpdate.value = await requestJson<SafeUpdateResult>(`/api/servers/${serverId}/updates/apply`, {
      method: "POST",
      body: JSON.stringify({ plan: safeUpdate.value.plan, apply: true, timeout_seconds: 180 }),
    });
    manifestMessage.value = safeUpdate.value.message;
    await store.loadDashboard(serverId);
  } catch (error) {
    manifestMessage.value = "Safe update не применён";
    console.error(error);
  } finally {
    isManifestLoading.value = false;
  }
}
</script>

<template>
  <section class="server-tab-panel">
      <section class="server-detail-section">
        <div class="server-detail-section-head">
          <h3>Манифест сборки</h3>
          <div class="panel-actions">
            <button class="ghost-button compact" type="button" :disabled="isManifestLoading" @click="refreshManifest">Обновить manifest</button>
            <button class="ghost-button compact" type="button" :disabled="isManifestLoading" @click="exportManifest">Экспорт</button>
            <button class="ghost-button compact" type="button" :disabled="isManifestLoading" @click="planSafeUpdate">Тест обновления</button>
            <button class="ghost-button compact" type="button" :disabled="isManifestLoading || !safeUpdate?.ok" @click="applySafeUpdate">Применить</button>
          </div>
        </div>
        <div class="server-mod-list">
          <article class="server-mod-row">
            <Package :size="20" />
            <div>
              <strong>{{ manifest ? `${manifest.mods.length} модов в manifest` : 'Manifest ещё не загружен' }}</strong>
              <span>{{ manifest?.minecraft_version || store.selectedServer.value?.version }} · {{ manifest?.loader || store.selectedServer.value?.pack }}</span>
              <small v-if="manifest?.manual_changes.length">Ручные изменения: {{ manifest.manual_changes.join(', ') }}</small>
              <small v-if="safeUpdate">Safe update: {{ safeUpdate.message }}</small>
              <em v-for="warning in safeUpdate?.plan.warnings || []" :key="warning">{{ warning }}</em>
              <em v-for="finding in safeUpdate?.log_findings || []" :key="finding">{{ finding }}</em>
              <small v-if="manifestMessage">{{ manifestMessage }}</small>
            </div>
          </article>
        </div>
      </section>
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
