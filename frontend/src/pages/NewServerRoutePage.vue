<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useDashboardStore } from "../composables/useDashboardStore";
import { requestFormWithProgress, requestJson } from "../services/api";
import type { ImportServerPreview, ImportServerRequest, MinecraftServerType, NewServerDraft } from "../types";
import NewServerPage from "./NewServerPage.vue";

const route = useRoute();
const router = useRouter();
const store = useDashboardStore();
const serverTypes: MinecraftServerType[] = ["vanilla", "paper", "purpur", "fabric", "forge", "neoforge"];
const routeSource = String(route.query.source || "");
const routeType = String(route.query.type || "");
const routeVersion = String(route.query.version || "");
const routeName = String(route.query.name || "");

const newServer = ref<NewServerDraft>({
  name: routeSource === "curseforge" && routeName ? routeName : "",
  type: serverTypes.includes(routeType as MinecraftServerType) ? (routeType as MinecraftServerType) : "vanilla",
  version: routeSource === "curseforge" ? routeVersion : "",
  min_ram: "1G",
  max_ram: "2G",
  java_runtime: "auto",
  jvm_args: "",
  cpu_limit: 100,
  loader_version: "",
  installer_version: "",
  install_fabric_api: false,
});
const importDraft = ref<ImportServerRequest>({
  name: "",
  path: "",
  keep_current_path: true,
  min_ram: "1G",
  max_ram: "2G",
  java_runtime: "auto",
  jvm_args: "",
  cpu_limit: 100,
  loader_version: "",
});
const importPreview = ref<ImportServerPreview | null>(null);
const isImportPreviewLoading = ref(false);
const isImporting = ref(false);
const importMessage = ref("");
const archiveFile = ref<File | null>(null);
const isArchiveImporting = ref(false);
const archiveImportMessage = ref("");
const archiveUploadProgress = ref(0);

async function createServer() {
  const created = await store.createServer(newServer.value);
  if (!created) {
    return;
  }

  newServer.value = {
    name: "",
    type: "vanilla",
    version: "",
    min_ram: "1G",
    max_ram: "2G",
    java_runtime: "auto",
    jvm_args: "",
    cpu_limit: 100,
    loader_version: "",
    installer_version: "",
    install_fabric_api: false,
  };
  await router.push("/servers");
}

async function previewImport() {
  importMessage.value = "";
  importPreview.value = null;
  isImportPreviewLoading.value = true;
  try {
    importPreview.value = await requestJson<ImportServerPreview>("/api/servers/import/preview", {
      method: "POST",
      body: JSON.stringify(importDraft.value),
    });
    if (!importDraft.value.name) {
      importDraft.value.name = importPreview.value.name;
    }
  } catch (error) {
    importMessage.value = "Не удалось проверить директорию";
    console.error(error);
  } finally {
    isImportPreviewLoading.value = false;
  }
}

async function importExistingServer() {
  importMessage.value = "";
  isImporting.value = true;
  try {
    await requestJson("/api/servers/import", {
      method: "POST",
      body: JSON.stringify(importDraft.value),
    });
    await store.loadDashboard();
    await router.push("/servers");
  } catch (error) {
    importMessage.value = "Не удалось импортировать сервер";
    console.error(error);
  } finally {
    isImporting.value = false;
  }
}

function selectArchive(event: Event) {
  const input = event.target as HTMLInputElement;
  archiveFile.value = input.files?.[0] || null;
  archiveImportMessage.value = "";
  archiveUploadProgress.value = 0;
  if (archiveFile.value && !importDraft.value.name) {
    importDraft.value.name = archiveFile.value.name.replace(/\.(tar\.gz|tgz|tar|zip)$/i, "");
  }
}

async function importArchiveServer() {
  if (!archiveFile.value) {
    return;
  }
  archiveImportMessage.value = "";
  archiveUploadProgress.value = 0;
  isArchiveImporting.value = true;
  try {
    const form = new FormData();
    form.set("archive", archiveFile.value);
    form.set("name", importDraft.value.name);
    form.set("min_ram", importDraft.value.min_ram);
    form.set("max_ram", importDraft.value.max_ram);
    form.set("java_runtime", importDraft.value.java_runtime);
    form.set("jvm_args", importDraft.value.jvm_args);
    form.set("cpu_limit", String(importDraft.value.cpu_limit));
    form.set("loader_version", importDraft.value.loader_version);
    await requestFormWithProgress("/api/servers/import/archive", form, (percent) => {
      archiveUploadProgress.value = percent;
    });
    await store.loadDashboard();
    await router.push("/servers");
  } catch (error) {
    archiveImportMessage.value = "Не удалось загрузить и импортировать архив";
    console.error(error);
  } finally {
    isArchiveImporting.value = false;
  }
}
</script>

<template>
  <div class="new-server-page">
    <NewServerPage
      v-model="newServer"
      :is-submitting="store.isCreatingServer.value"
      @submit="createServer"
    />

    <form class="new-server-form" @submit.prevent="previewImport">
      <div class="new-server-section-head">
        <div>
          <p class="eyebrow">import</p>
          <h3>Импорт существующего сервера</h3>
        </div>
        <button class="ghost-button" type="submit" :disabled="isImportPreviewLoading || !importDraft.path.trim()">
          {{ isImportPreviewLoading ? 'Проверяю...' : 'Проверить' }}
        </button>
      </div>

      <div class="new-server-fields">
        <label class="new-server-file-field">
          <span>Архив с локального ПК</span>
          <input type="file" accept=".tar,.tar.gz,.tgz,.zip,application/x-tar,application/gzip,application/zip" :disabled="isArchiveImporting || isImporting" @change="selectArchive" />
          <small v-if="archiveFile">{{ archiveFile.name }} · {{ (archiveFile.size / 1024 / 1024 / 1024).toFixed(2) }} GB</small>
        </label>
        <label>
          <span>Директория</span>
          <input v-model="importDraft.path" type="text" placeholder="/opt/minecraft/server" :disabled="isImporting" />
        </label>
        <label>
          <span>Название</span>
          <input v-model="importDraft.name" type="text" placeholder="Survival Forge" :disabled="isImporting" />
        </label>
        <label>
          <span>Min RAM</span>
          <input v-model="importDraft.min_ram" type="text" placeholder="1G" :disabled="isImporting" />
        </label>
        <label>
          <span>Max RAM</span>
          <input v-model="importDraft.max_ram" type="text" placeholder="4G" :disabled="isImporting" />
        </label>
        <label>
          <span>Java</span>
          <select v-model="importDraft.java_runtime" :disabled="isImporting">
            <option value="auto">Авто</option>
            <option value="8">Java 8</option>
            <option value="17">Java 17</option>
            <option value="21">Java 21</option>
          </select>
        </label>
        <label>
          <span>CPU limit</span>
          <input v-model.number="importDraft.cpu_limit" min="10" max="400" step="10" type="number" :disabled="isImporting" />
        </label>
        <label class="new-server-checkbox-field">
          <input v-model="importDraft.keep_current_path" type="checkbox" :disabled="isImporting" />
          <span>Оставить директорию на текущем месте</span>
        </label>
      </div>

      <div v-if="importPreview" class="provisioning-card">
        <div>
          <strong>{{ importPreview.name }} · {{ importPreview.type }} · {{ importPreview.version || 'version unknown' }}</strong>
          <span>Порт {{ importPreview.port }} · модов {{ importPreview.mod_count }} · server.properties {{ importPreview.has_server_properties ? 'найден' : 'не найден' }}</span>
          <small v-if="importPreview.warnings.length">{{ importPreview.warnings.join(' · ') }}</small>
        </div>
      </div>

      <p v-if="importMessage" class="version-error">{{ importMessage }}</p>
      <p v-if="archiveImportMessage" class="version-error">{{ archiveImportMessage }}</p>
      <div v-if="archiveFile && isArchiveImporting" class="archive-upload-progress">
        <div>
          <strong>Загрузка архива</strong>
          <span>{{ archiveUploadProgress }}%</span>
        </div>
        <span><i :style="{ width: `${archiveUploadProgress}%` }"></i></span>
      </div>

      <div class="new-server-summary">
        <div>
          <span>Systemd unit будет создан Ksylian</span>
          <strong v-if="archiveFile">Архив будет загружен, распакован и запущен как managed server</strong>
          <strong v-else>{{ importDraft.keep_current_path ? 'Файлы останутся на месте' : 'Файлы будут скопированы в managed root' }}</strong>
        </div>
        <button
          v-if="archiveFile"
          class="primary-button"
          type="button"
          :disabled="isArchiveImporting"
          @click="importArchiveServer"
        >
          {{ isArchiveImporting ? 'Загружаю архив...' : 'Загрузить и импортировать' }}
        </button>
        <button v-else class="primary-button" type="button" :disabled="!importPreview || isImporting" @click="importExistingServer">
          {{ isImporting ? 'Импортирую...' : 'Импортировать' }}
        </button>
      </div>
    </form>
  </div>
</template>
