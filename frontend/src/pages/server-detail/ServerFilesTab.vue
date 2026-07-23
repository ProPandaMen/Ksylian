<script setup lang="ts">
import { ref } from "vue";
import { FileText, Folder, RefreshCw } from "@lucide/vue";
import { useDashboardStore } from "../../composables/useDashboardStore";

const store = useDashboardStore();
const newFolderName = ref("");
const fileEditorContent = ref("");
const fileSearchQuery = ref("");
const fileUploadInput = ref<HTMLInputElement | null>(null);

function openParentFolder() {
  const current = store.selectedServerFilePath.value;
  if (!current) {
    return;
  }
  const parent = current.split("/").slice(0, -1).join("/");
  store.loadServerFiles(undefined, parent);
}

async function openFileEntry(path: string, kind: "folder" | "file") {
  if (kind === "folder") {
    await store.loadServerFiles(undefined, path);
    return;
  }
  await store.openServerFile(path);
  fileEditorContent.value = store.selectedServerFileContent.value?.encoding === "text"
    ? store.selectedServerFileContent.value.content
    : "";
}

async function createFolder() {
  const name = newFolderName.value.trim();
  if (!name) {
    return;
  }
  const base = store.selectedServerFilePath.value;
  await store.runFileAction("mkdir", [base, name].filter(Boolean).join("/"));
  newFolderName.value = "";
}

async function searchFiles() {
  await store.searchServerFiles(fileSearchQuery.value);
}

async function saveOpenedFile() {
  await store.saveServerFile(fileEditorContent.value);
}

async function uploadSelectedFiles(event: Event) {
  const input = event.target as HTMLInputElement;
  const selectedFiles = Array.from(input.files || []);
  for (const file of selectedFiles) {
    await store.uploadServerFile(file);
  }
  input.value = "";
}

async function downloadServerFile(path: string) {
  await store.openServerFile(path);
  const file = store.selectedServerFileContent.value;
  if (!file) {
    return;
  }
  const bytes = file.encoding === "base64"
    ? Uint8Array.from(atob(file.content), (char) => char.charCodeAt(0))
    : new TextEncoder().encode(file.content);
  const blob = new Blob([bytes]);
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = file.name;
  link.click();
  URL.revokeObjectURL(url);
}
</script>

<template>
  <section class="server-tab-panel">
      <section class="server-detail-section server-files-panel">
        <div class="server-detail-section-head">
          <div>
            <h3>Файлы</h3>
            <span>{{ store.selectedServerFilePath.value || '/' }}</span>
          </div>
          <div class="panel-actions">
            <input ref="fileUploadInput" type="file" multiple class="visually-hidden" @change="uploadSelectedFiles" />
            <button class="ghost-button compact" type="button" @click="fileUploadInput?.click()">
              <span>Загрузить</span>
            </button>
            <button class="ghost-button compact" type="button" :disabled="!store.selectedServerFilePath.value" @click="openParentFolder">
              <span>Назад</span>
            </button>
            <button class="ghost-button compact" type="button" :aria-busy="store.isFileLoading.value" @click="store.loadServerFiles()">
              <RefreshCw :class="{ spinning: store.isFileLoading.value }" :size="16" />
              <span>Обновить</span>
            </button>
          </div>
        </div>
        <form class="file-create-row" @submit.prevent="createFolder">
          <input v-model="newFolderName" type="text" placeholder="Новая папка" />
          <button class="primary-button compact" type="submit" :disabled="!newFolderName.trim()">Создать</button>
        </form>
        <form class="file-create-row" @submit.prevent="searchFiles">
          <input v-model="fileSearchQuery" type="search" placeholder="Поиск по файлам" />
          <button class="ghost-button compact" type="submit" :disabled="fileSearchQuery.trim().length < 2">Найти</button>
        </form>
        <div v-if="store.selectedServerFileSearchResults.value.length" class="server-search-results">
          <button
            v-for="result in store.selectedServerFileSearchResults.value"
            :key="`${result.path}:${result.line}`"
            type="button"
            @click="openFileEntry(result.path, 'file')"
          >
            <strong>{{ result.path }}:{{ result.line }}</strong>
            <span>{{ result.preview }}</span>
          </button>
        </div>
        <div class="server-file-list">
          <article v-for="entry in store.selectedServerFiles.value" :key="entry.path" class="server-file-row">
            <button type="button" @click="openFileEntry(entry.path, entry.kind)">
              <Folder v-if="entry.kind === 'folder'" :size="18" />
              <FileText v-else :size="18" />
              <span>{{ entry.name }}</span>
            </button>
            <small>{{ entry.size }} · {{ entry.modified }}</small>
            <div class="server-file-actions">
              <button
                v-if="entry.kind === 'file'"
                class="ghost-button compact"
                type="button"
                @click="downloadServerFile(entry.path)"
              >
                Скачать
              </button>
              <button
                v-if="entry.kind === 'file' && (entry.name.endsWith('.zip') || entry.name.endsWith('.tar.gz'))"
                class="ghost-button compact"
                type="button"
                @click="store.runFileAction('extract', entry.path)"
              >
                Распаковать
              </button>
              <button class="ghost-button compact danger" type="button" @click="store.runFileAction('delete', entry.path)">
                Удалить
              </button>
            </div>
          </article>
          <article v-if="!store.selectedServerFiles.value.length" class="server-empty-state">
            <div>
              <strong>Папка пуста</strong>
              <span>Файлы появятся здесь после создания или загрузки через agent API.</span>
            </div>
          </article>
        </div>
        <div v-if="store.selectedServerFileContent.value" class="file-editor-panel">
          <div class="server-detail-section-head">
            <div>
              <h3>{{ store.selectedServerFileContent.value.name }}</h3>
              <span>{{ store.selectedServerFileContent.value.syntax }}</span>
            </div>
            <button
              class="primary-button compact"
              type="button"
              :disabled="store.selectedServerFileContent.value.encoding !== 'text' || store.isFileSaving.value"
              @click="saveOpenedFile"
            >
              {{ store.isFileSaving.value ? 'Сохраняю' : 'Сохранить' }}
            </button>
          </div>
          <textarea
            v-if="store.selectedServerFileContent.value.encoding === 'text'"
            v-model="fileEditorContent"
            class="config-editor"
            :class="`syntax-${store.selectedServerFileContent.value.syntax}`"
            spellcheck="false"
          ></textarea>
          <p v-else class="server-muted-note">Бинарный файл открыт только для чтения.</p>
        </div>
      </section>
    </section>
</template>
