<script setup lang="ts">
import { PackagePlus, RefreshCw, Search } from "@lucide/vue";
import { computed, onMounted, ref, watch } from "vue";
import { useDashboardStore } from "../composables/useDashboardStore";
import { requestJson } from "../services/api";
import type {
  CurseForgeFile,
  CurseForgeFilesPayload,
  CurseForgeInstallResult,
  CurseForgeProject,
  CurseForgeSearchPayload,
} from "../types";

const store = useDashboardStore();
const kind = ref<"mods" | "modpacks">("modpacks");
const query = ref("");
const minecraftVersion = ref("");
const loader = ref<"any" | "forge" | "fabric" | "quilt" | "neoforge">("any");
const sort = ref<"popularity" | "updated" | "name" | "downloads">("popularity");
const selectedProject = ref<CurseForgeProject | null>(null);
const selectedFile = ref<CurseForgeFile | null>(null);
const projects = ref<CurseForgeProject[]>([]);
const files = ref<CurseForgeFile[]>([]);
const dependencies = ref<CurseForgeFile[]>([]);
const selectedServerId = ref("");
const isSearching = ref(false);
const isFilesLoading = ref(false);
const isInstalling = ref(false);
const errorMessage = ref("");
const installMessage = ref("");

const hasApiKey = computed(() => store.settings.value.has_curseforge_api_key);

async function searchProjects() {
  isSearching.value = true;
  errorMessage.value = "";
  try {
    const params = new URLSearchParams({
      kind: kind.value,
      query: query.value,
      minecraft_version: minecraftVersion.value,
      loader: loader.value,
      sort: sort.value,
      page_size: "24",
    });
    const payload = await requestJson<CurseForgeSearchPayload>(`/api/curseforge/search?${params.toString()}`);
    projects.value = payload.items;
    selectedProject.value = payload.items[0] ?? null;
  } catch (error) {
    errorMessage.value = "Не удалось загрузить CurseForge каталог";
    projects.value = [];
    selectedProject.value = null;
    console.error(error);
  } finally {
    isSearching.value = false;
  }
}

async function loadFiles(project: CurseForgeProject | null) {
  files.value = [];
  selectedFile.value = null;
  dependencies.value = [];
  if (!project) {
    return;
  }
  isFilesLoading.value = true;
  try {
    const params = new URLSearchParams({
      minecraft_version: minecraftVersion.value,
      loader: loader.value,
      page_size: "20",
    });
    const payload = await requestJson<CurseForgeFilesPayload>(`/api/curseforge/projects/${project.id}/files?${params.toString()}`);
    files.value = payload.items;
    selectedFile.value = payload.items.find((item) => !item.restricted) ?? payload.items[0] ?? null;
  } catch (error) {
    errorMessage.value = "Не удалось загрузить файлы проекта";
    console.error(error);
  } finally {
    isFilesLoading.value = false;
  }
}

async function loadDependencies(file: CurseForgeFile | null) {
  dependencies.value = [];
  if (!selectedProject.value || !file) {
    return;
  }
  try {
    dependencies.value = await requestJson<CurseForgeFile[]>(`/api/curseforge/projects/${selectedProject.value.id}/files/${file.id}/dependencies`);
  } catch (error) {
    dependencies.value = [];
    console.error(error);
  }
}

async function installSelectedFile() {
  if (!selectedProject.value || !selectedFile.value || !selectedServerId.value) {
    return;
  }
  isInstalling.value = true;
  installMessage.value = "";
  try {
    const result = await requestJson<CurseForgeInstallResult>("/api/curseforge/install", {
      method: "POST",
      body: JSON.stringify({
        server_id: selectedServerId.value,
        project_id: selectedProject.value.id,
        file_id: selectedFile.value.id,
        include_dependencies: true,
      }),
    });
    installMessage.value = `${result.installed.length} установлено, ${result.skipped.length} пропущено`;
    await store.loadServerMods(selectedServerId.value);
  } catch (error) {
    installMessage.value = "Установка не выполнена";
    console.error(error);
  } finally {
    isInstalling.value = false;
  }
}

function selectProject(project: CurseForgeProject) {
  selectedProject.value = project;
}

watch(selectedProject, loadFiles);
watch(selectedFile, loadDependencies);

onMounted(async () => {
  if (!store.isDashboardLoaded.value) {
    await store.loadDashboard();
  }
  selectedServerId.value = store.selectedServerId.value || store.servers.value[0]?.id || "";
  await store.loadSettings();
  if (hasApiKey.value) {
    await searchProjects();
  }
});
</script>

<template>
  <section class="panel curseforge-panel">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">curseforge</p>
        <h2>Каталог сборок и модов</h2>
      </div>
      <span class="settings-status" :class="{ connected: hasApiKey }">{{ hasApiKey ? 'API key подключён' : 'API key не задан' }}</span>
    </div>

    <form class="catalog-toolbar" @submit.prevent="searchProjects">
      <div class="segmented-control" aria-label="Тип проекта">
        <button type="button" :class="{ active: kind === 'modpacks' }" @click="kind = 'modpacks'">Сборки</button>
        <button type="button" :class="{ active: kind === 'mods' }" @click="kind = 'mods'">Моды</button>
      </div>
      <label class="catalog-search">
        <Search :size="18" />
        <input v-model="query" type="search" placeholder="Поиск по названию" />
      </label>
      <label>
        Версия
        <input v-model="minecraftVersion" type="text" placeholder="1.20.1" />
      </label>
      <label>
        Loader
        <select v-model="loader">
          <option value="any">Любой</option>
          <option value="forge">Forge</option>
          <option value="fabric">Fabric</option>
          <option value="neoforge">NeoForge</option>
          <option value="quilt">Quilt</option>
        </select>
      </label>
      <label>
        Сортировка
        <select v-model="sort">
          <option value="popularity">Популярность</option>
          <option value="updated">Обновлены</option>
          <option value="downloads">Загрузки</option>
          <option value="name">Название</option>
        </select>
      </label>
      <button class="primary-button" type="submit" :disabled="isSearching || !hasApiKey">
        <RefreshCw :class="{ spinning: isSearching }" :size="18" />
        <span>Искать</span>
      </button>
    </form>

    <p v-if="!hasApiKey" class="catalog-notice">Добавь CurseForge API key в настройках, чтобы включить поиск и установку.</p>
    <p v-else-if="errorMessage" class="catalog-notice">{{ errorMessage }}</p>

    <div class="catalog-layout">
      <div class="catalog-results">
        <button
          v-for="project in projects"
          :key="project.id"
          class="project-card"
          :class="{ selected: selectedProject?.id === project.id }"
          type="button"
          @click="selectProject(project)"
        >
          <img v-if="project.icon_url" :src="project.icon_url" alt="" />
          <span v-else class="project-icon-fallback"><PackagePlus :size="24" /></span>
          <div>
            <strong>{{ project.name }}</strong>
            <p>{{ project.summary }}</p>
            <span>{{ project.downloads.toLocaleString() }} downloads · {{ project.game_versions.slice(0, 3).join(', ') || 'версии не указаны' }}</span>
          </div>
        </button>
        <div v-if="!projects.length && !isSearching" class="project-card muted">Нет результатов</div>
      </div>

      <aside class="project-details">
        <template v-if="selectedProject">
          <div class="project-details-head">
            <img v-if="selectedProject.icon_url" :src="selectedProject.icon_url" alt="" />
            <span v-else class="project-icon-fallback"><PackagePlus :size="24" /></span>
            <div>
              <h3>{{ selectedProject.name }}</h3>
              <span>{{ selectedProject.loaders.join(', ') || 'loader не указан' }}</span>
            </div>
          </div>

          <p class="project-summary">{{ selectedProject.summary }}</p>

          <label>
            Сервер
            <select v-model="selectedServerId">
              <option v-for="server in store.servers.value" :key="server.id" :value="server.id">{{ server.name }}</option>
            </select>
          </label>

          <label>
            Файл
            <select v-model="selectedFile" :disabled="isFilesLoading">
              <option v-for="file in files" :key="file.id" :value="file">
                {{ file.display_name || file.file_name }}{{ file.restricted ? ' · restricted' : '' }}
              </option>
            </select>
          </label>

          <dl class="project-facts">
            <div>
              <dt>Файлов</dt>
              <dd>{{ files.length }}</dd>
            </div>
            <div>
              <dt>Зависимости</dt>
              <dd>{{ dependencies.length ? dependencies.map((item) => item.file_name).join(', ') : 'нет' }}</dd>
            </div>
            <div>
              <dt>Источник</dt>
              <dd>{{ selectedFile?.restricted ? 'скачивание ограничено' : 'готов к установке' }}</dd>
            </div>
          </dl>

          <div class="project-actions">
            <button
              class="primary-button"
              type="button"
              :disabled="!selectedFile || selectedFile.restricted || !selectedServerId || isInstalling"
              @click="installSelectedFile"
            >
              <PackagePlus :size="18" />
              <span>{{ isInstalling ? 'Устанавливаю...' : 'Установить' }}</span>
            </button>
            <a v-if="selectedProject.website_url" class="ghost-button" :href="selectedProject.website_url" target="_blank" rel="noreferrer">Открыть CurseForge</a>
            <p v-if="installMessage" class="catalog-notice">{{ installMessage }}</p>
          </div>
        </template>
        <div v-else class="empty-details">Выбери проект из списка</div>
      </aside>
    </div>
  </section>
</template>
