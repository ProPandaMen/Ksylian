<script setup lang="ts">
import { ChevronDown, ChevronLeft, ChevronRight, Download, ExternalLink, PackagePlus, RefreshCw, Search, Server, X } from "@lucide/vue";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useDashboardStore } from "../composables/useDashboardStore";
import { requestJson } from "../services/api";
import type {
  CurseForgeFile,
  CurseForgeFilesPayload,
  CurseForgeInstallResult,
  CurseForgeProject,
  CurseForgeSearchPayload,
  MinecraftVersionsPayload,
} from "../types";

const store = useDashboardStore();
const router = useRouter();
const kind = ref<"mods" | "modpacks">("modpacks");
const query = ref("");
const minecraftVersion = ref("");
const isVersionPickerOpen = ref(false);
const versionPickerRef = ref<HTMLElement | null>(null);
const loader = ref<"any" | "forge" | "fabric" | "quilt" | "neoforge">("any");
const sort = ref<"popularity" | "updated" | "name" | "downloads">("popularity");
const pageSize = 24;
const page = ref(1);
const totalCount = ref(0);
const selectedProject = ref<CurseForgeProject | null>(null);
const selectedFile = ref<CurseForgeFile | null>(null);
const projects = ref<CurseForgeProject[]>([]);
const files = ref<CurseForgeFile[]>([]);
const dependencies = ref<CurseForgeFile[]>([]);
const minecraftVersions = ref<MinecraftVersionsPayload>({
  latest_release: "",
  latest_snapshot: "",
  versions: [],
});
const selectedServerId = ref("");
const isSearching = ref(false);
const isVersionsLoading = ref(false);
const isFilesLoading = ref(false);
const isInstalling = ref(false);
const errorMessage = ref("");
const installMessage = ref("");

const hasApiKey = computed(() => store.settings.value.has_curseforge_api_key);
const totalPages = computed(() => Math.max(1, Math.ceil(totalCount.value / pageSize)));
const visibleFrom = computed(() => (totalCount.value ? (page.value - 1) * pageSize + 1 : 0));
const visibleTo = computed(() => Math.min(page.value * pageSize, totalCount.value));
const modalActionLabel = computed(() => (kind.value === "modpacks" ? "Создать сервер по сборке" : "Установить мод"));
const selectedVersion = computed(() => {
  const versions = selectedFile.value?.game_versions.length ? selectedFile.value.game_versions : selectedProject.value?.game_versions ?? [];
  return versions.find((value) => /^\d+\.\d+(?:\.\d+)?$/.test(value)) ?? "";
});
const releaseVersions = computed(() => minecraftVersions.value.versions.filter((version) => version.type === "release"));
const minecraftVersionLabel = computed(() => minecraftVersion.value || "Любая версия");

async function loadMinecraftVersions() {
  isVersionsLoading.value = true;
  try {
    minecraftVersions.value = await requestJson<MinecraftVersionsPayload>("/api/minecraft/versions");
  } catch (error) {
    console.error(error);
  } finally {
    isVersionsLoading.value = false;
  }
}

async function searchProjects(resetPage = true) {
  if (resetPage) {
    page.value = 1;
  }
  isSearching.value = true;
  errorMessage.value = "";
  installMessage.value = "";
  try {
    const params = new URLSearchParams({
      kind: kind.value,
      query: query.value,
      minecraft_version: minecraftVersion.value,
      loader: loader.value,
      sort: sort.value,
      page_size: String(pageSize),
      index: String((page.value - 1) * pageSize),
    });
    const payload = await requestJson<CurseForgeSearchPayload>(`/api/curseforge/search?${params.toString()}`);
    projects.value = payload.items;
    totalCount.value = payload.total_count;
    selectedProject.value = null;
  } catch (error) {
    errorMessage.value = "Не удалось загрузить CurseForge каталог";
    projects.value = [];
    totalCount.value = 0;
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

function selectMinecraftVersion(version: string) {
  minecraftVersion.value = version;
  isVersionPickerOpen.value = false;
}

function closeProject() {
  selectedProject.value = null;
  files.value = [];
  selectedFile.value = null;
  dependencies.value = [];
  installMessage.value = "";
}

async function changePage(nextPage: number) {
  const normalized = Math.min(Math.max(nextPage, 1), totalPages.value);
  if (normalized === page.value || isSearching.value) {
    return;
  }
  page.value = normalized;
  await searchProjects(false);
}

function inferServerType() {
  const projectLoaders = selectedProject.value?.loaders.map((item) => item.toLowerCase()) ?? [];
  if (projectLoaders.includes("neoforge") || loader.value === "neoforge") {
    return "neoforge";
  }
  if (projectLoaders.includes("forge") || loader.value === "forge") {
    return "forge";
  }
  if (projectLoaders.includes("fabric") || projectLoaders.includes("quilt") || loader.value === "fabric" || loader.value === "quilt") {
    return "fabric";
  }
  return "vanilla";
}

async function createServerFromModpack() {
  if (!selectedProject.value || !selectedFile.value) {
    return;
  }

  await router.push({
    path: "/servers/new",
    query: {
      source: "curseforge",
      project_id: String(selectedProject.value.id),
      file_id: String(selectedFile.value.id),
      name: selectedProject.value.name,
      version: selectedVersion.value,
      type: inferServerType(),
    },
  });
}

function closeVersionPickerOnOutsideClick(event: PointerEvent) {
  if (!versionPickerRef.value?.contains(event.target as Node)) {
    isVersionPickerOpen.value = false;
  }
}

watch(selectedProject, loadFiles);
watch(selectedFile, loadDependencies);
watch(kind, () => {
  closeProject();
  if (hasApiKey.value) {
    searchProjects(true);
  }
});

onMounted(async () => {
  document.addEventListener("pointerdown", closeVersionPickerOnOutsideClick);
  if (!store.isDashboardLoaded.value) {
    await store.loadDashboard();
  }
  selectedServerId.value = store.selectedServerId.value || store.servers.value[0]?.id || "";
  await Promise.all([store.loadSettings(), loadMinecraftVersions()]);
  if (hasApiKey.value) {
    await searchProjects();
  }
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", closeVersionPickerOnOutsideClick);
});
</script>

<template>
  <section class="curseforge-page">
    <form class="catalog-toolbar" @submit.prevent="searchProjects(true)">
      <div class="segmented-control" aria-label="Тип проекта">
        <button type="button" :class="{ active: kind === 'modpacks' }" @click="kind = 'modpacks'">Сборки</button>
        <button type="button" :class="{ active: kind === 'mods' }" @click="kind = 'mods'">Моды</button>
      </div>
      <label class="catalog-search">
        <Search :size="18" />
        <input v-model="query" type="search" placeholder="Поиск по названию" />
      </label>
      <div ref="versionPickerRef" class="catalog-filter catalog-version-picker" @keydown.escape="isVersionPickerOpen = false">
        <span>Версия</span>
        <button
          class="version-picker-button"
          type="button"
          :aria-expanded="isVersionPickerOpen"
          aria-haspopup="listbox"
          :disabled="isVersionsLoading"
          @click="isVersionPickerOpen = !isVersionPickerOpen"
        >
          <span>{{ isVersionsLoading ? 'Загружаю...' : minecraftVersionLabel }}</span>
          <ChevronDown :size="17" />
        </button>
        <div v-if="isVersionPickerOpen" class="version-picker-menu" role="listbox">
          <button
            class="version-picker-option"
            type="button"
            role="option"
            :aria-selected="minecraftVersion === ''"
            :class="{ active: minecraftVersion === '' }"
            @click="selectMinecraftVersion('')"
          >
            Любая версия
          </button>
          <button
            v-for="version in releaseVersions"
            :key="version.id"
            class="version-picker-option"
            type="button"
            role="option"
            :aria-selected="minecraftVersion === version.id"
            :class="{ active: minecraftVersion === version.id }"
            @click="selectMinecraftVersion(version.id)"
          >
            {{ version.id }}
          </button>
        </div>
      </div>
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

    <section class="catalog-section">
      <div class="catalog-section-head">
        <div>
          <h3>{{ kind === 'modpacks' ? 'Сборки' : 'Моды' }}</h3>
          <span v-if="totalCount">{{ visibleFrom }}–{{ visibleTo }} из {{ totalCount.toLocaleString() }}</span>
          <span v-else>{{ isSearching ? 'Загружаю каталог' : 'Нет результатов' }}</span>
        </div>
      </div>

      <div class="catalog-results">
        <button
          v-for="project in projects"
          :key="project.id"
          class="project-card"
          type="button"
          @click="selectProject(project)"
        >
          <img v-if="project.icon_url" :src="project.icon_url" alt="" />
          <span v-else class="project-icon-fallback"><PackagePlus :size="24" /></span>
          <div>
            <strong>{{ project.name }}</strong>
            <p>{{ project.summary }}</p>
            <span>{{ project.downloads.toLocaleString() }} загрузок · {{ project.game_versions.slice(0, 3).join(', ') || 'версии не указаны' }}</span>
          </div>
        </button>
        <div v-if="!projects.length && !isSearching" class="project-card muted">Нет результатов</div>
      </div>

      <div v-if="totalCount" class="catalog-pagination">
        <button class="ghost-button compact" type="button" :disabled="page <= 1 || isSearching" @click="changePage(page - 1)">
          <ChevronLeft :size="18" />
          <span>Назад</span>
        </button>
        <span>Страница {{ page }} / {{ totalPages }}</span>
        <button class="ghost-button compact" type="button" :disabled="page >= totalPages || isSearching" @click="changePage(page + 1)">
          <span>Вперёд</span>
          <ChevronRight :size="18" />
        </button>
      </div>
    </section>

    <Teleport to="body">
      <div v-if="selectedProject" class="project-modal-backdrop" role="presentation" @click.self="closeProject">
        <section class="project-modal" role="dialog" aria-modal="true" :aria-label="selectedProject.name">
          <button class="modal-close-button" type="button" aria-label="Закрыть" @click="closeProject">
            <X :size="20" />
          </button>
          <div class="project-modal-hero">
            <div class="project-details-head">
              <img v-if="selectedProject.icon_url" :src="selectedProject.icon_url" alt="" />
              <span v-else class="project-icon-fallback"><PackagePlus :size="24" /></span>
              <div>
                <h3>{{ selectedProject.name }}</h3>
                <div class="project-badges">
                  <span>{{ selectedProject.downloads.toLocaleString() }} загрузок</span>
                  <span>{{ selectedProject.loaders.join(', ') || 'loader не указан' }}</span>
                  <span>{{ selectedVersion || selectedProject.game_versions.slice(0, 2).join(', ') || 'версия не указана' }}</span>
                </div>
              </div>
            </div>
            <p class="project-summary">{{ selectedProject.summary }}</p>
          </div>

          <div class="project-controls">
            <label v-if="kind === 'mods'">
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
          </div>

          <dl class="project-facts">
            <div>
              <dt>Версия</dt>
              <dd>{{ selectedVersion || selectedProject.game_versions.slice(0, 3).join(', ') || 'не указана' }}</dd>
            </div>
            <div>
              <dt>Зависимости</dt>
              <dd>{{ dependencies.length ? dependencies.map((item) => item.file_name).join(', ') : 'нет' }}</dd>
            </div>
            <div>
              <dt>Источник</dt>
              <dd>{{ selectedFile?.restricted ? 'скачивание ограничено CurseForge' : 'доступен' }}</dd>
            </div>
          </dl>

          <div class="project-actions">
            <button
              v-if="kind === 'mods'"
              class="primary-button"
              type="button"
              :disabled="!selectedFile || selectedFile.restricted || !selectedServerId || isInstalling"
              @click="installSelectedFile"
            >
              <Download :size="18" />
              <span>{{ isInstalling ? 'Устанавливаю...' : modalActionLabel }}</span>
            </button>
            <button
              v-else
              class="primary-button"
              type="button"
              :disabled="!selectedFile"
              @click="createServerFromModpack"
            >
              <Server :size="18" />
              <span>{{ modalActionLabel }}</span>
            </button>
            <a v-if="selectedProject.website_url" class="ghost-button" :href="selectedProject.website_url" target="_blank" rel="noreferrer">
              <ExternalLink :size="18" />
              <span>Открыть CurseForge</span>
            </a>
            <p v-if="installMessage" class="catalog-notice">{{ installMessage }}</p>
          </div>
        </section>
      </div>
    </Teleport>
  </section>
</template>
