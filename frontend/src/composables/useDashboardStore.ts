import { computed, ref } from "vue";
import { requestJson } from "../services/api";
import type {
  AgentStatus,
  BackupItem,
  BackupRequest,
  CrashReportItem,
  DashboardPayload,
  FileContentPayload,
  FileEntry,
  FileSearchResult,
  FileItem,
  FileOperationRequest,
  FileWriteRequest,
  GameServer,
  HostMonitoring,
  InstalledModItem,
  MonitoringHistoryPoint,
  ModItem,
  ModInstallRequest,
  NewServerDraft,
  ServerConfigPayload,
  ServerState,
  SettingsPayload,
  UpdateStatusPayload,
} from "../types";
import { useToasts } from "./useToasts";

const emptyServers: GameServer[] = [];
const emptyLogs: string[] = [];
const emptyBackups: BackupItem[] = [];
const emptyCrashReports: CrashReportItem[] = [];
const emptyMods: ModItem[] = [];
const emptyFiles: FileItem[] = [];

export const stateLabels: Record<ServerState, string> = {
  installing: "Устанавливается",
  stopped: "Выключен",
  starting: "Запускается",
  running: "Работает",
  stopping: "Останавливается",
  crashed: "Упал",
  updating: "Обновляется",
  backing_up: "Бэкап",
};

export const serverTypeLabels: Record<NewServerDraft["type"], string> = {
  vanilla: "Vanilla",
  paper: "Paper",
  purpur: "Purpur",
  fabric: "Fabric",
  forge: "Forge",
  neoforge: "NeoForge",
};

const defaultAgentStatus: AgentStatus = {
  configured: false,
  available: false,
  status: "not_configured",
  message: "",
  public_domain: "",
  proxy_domain: "",
  proxy_port: "",
};

const servers = ref<GameServer[]>(emptyServers);
const logs = ref<string[]>(emptyLogs);
const backups = ref<BackupItem[]>(emptyBackups);
const mods = ref<ModItem[]>(emptyMods);
const files = ref<FileItem[]>(emptyFiles);
const isLoading = ref(true);
const isDashboardLoaded = ref(false);
const isMonitoringLoading = ref(false);
const isSavingSettings = ref(false);
const isUpdateLoading = ref(false);
const isApplyingUpdate = ref(false);
const isCreatingServer = ref(false);
const selectedServerId = ref("");
const selectedServerLogs = ref<string[]>(emptyLogs);
const selectedServerCrashReports = ref<CrashReportItem[]>(emptyCrashReports);
const selectedServerConfig = ref("");
const selectedServerFiles = ref<FileEntry[]>([]);
const selectedServerFilePath = ref("");
const selectedServerFileContent = ref<FileContentPayload | null>(null);
const selectedServerFileSearchResults = ref<FileSearchResult[]>([]);
const selectedServerMods = ref<InstalledModItem[]>([]);
const isLogLoading = ref(false);
const isCrashReportLoading = ref(false);
const isConfigLoading = ref(false);
const isConfigSaving = ref(false);
const isFileLoading = ref(false);
const isFileSaving = ref(false);
const isModLoading = ref(false);
const curseForgeApiKey = ref("");
const agentStatus = ref<AgentStatus>(defaultAgentStatus);
const settings = ref<SettingsPayload>({
  has_curseforge_api_key: false,
  curseforge_api_key_mask: "",
  agent: defaultAgentStatus,
});
const updateStatus = ref<UpdateStatusPayload>({
  current_version: "dev",
  current_sha: "local",
  latest_version: "",
  latest_sha: "",
  update_available: false,
  checked_at: "",
  release_url: "",
  notes: "",
  can_update: false,
  updater_status: "unknown",
});
const monitoring = ref<HostMonitoring>({
  hostname: "server",
  ip_addresses: [],
  uptime: "0m",
  load_average: [0, 0, 0],
  cpu_percent: 0,
  cpu_cores: 1,
  memory: { used: 0, total: 1, percent: 0, used_label: "0 MB", total_label: "0 MB" },
  swap: { used: 0, total: 0, percent: 0, used_label: "0 MB", total_label: "0 MB" },
  disks: [],
  top_processes: [],
  services: [],
  temperature: "n/a",
  collected_at: "",
});
const monitoringHistory = ref<MonitoringHistoryPoint[]>([]);

const onlineServersCount = computed(
  () => servers.value.filter((server) => server.state === "running").length,
);
const offlineServersCount = computed(
  () => servers.value.filter((server) => ["stopped", "crashed"].includes(server.state)).length,
);
const deployingServersCount = computed(
  () => servers.value.filter((server) => ["installing", "starting", "stopping", "updating", "backing_up"].includes(server.state)).length,
);
const stableServersCount = computed(
  () => servers.value.filter((server) => server.state === "running").length,
);
const selectedServer = computed(
  () => servers.value.find((server) => server.id === selectedServerId.value) ?? servers.value[0],
);
const isDashboardInitialLoading = computed(() => isLoading.value && !isDashboardLoaded.value);
const isAgentUnavailable = computed(() => agentStatus.value.configured && !agentStatus.value.available);
const monitoringStatus = computed(() => {
  if (isAgentUnavailable.value) {
    return { label: "Agent недоступен", tone: "danger" };
  }
  const maxDisk = Math.max(0, ...monitoring.value.disks.map((disk) => disk.percent));
  const maxUsage = Math.max(monitoring.value.cpu_percent, monitoring.value.memory.percent, maxDisk);
  if (maxUsage >= 90) {
    return { label: "Критичная нагрузка", tone: "danger" };
  }
  if (maxUsage >= 75) {
    return { label: "Нужно внимание", tone: "warning" };
  }
  return { label: "Нагрузка в норме", tone: "ok" };
});

function parseTemperature(value: string) {
  const match = value.match(/-?\d+(?:[.,]\d+)?/);
  if (!match) {
    return null;
  }
  return Number(match[0].replace(",", "."));
}

function recordMonitoringSnapshot(snapshot: HostMonitoring) {
  const point: MonitoringHistoryPoint = {
    timestamp: Date.now(),
    cpu: snapshot.cpu_percent,
    memory: snapshot.memory.percent,
    swap: snapshot.swap.percent,
    temperature: parseTemperature(snapshot.temperature),
  };
  monitoringHistory.value = [...monitoringHistory.value.slice(-47), point];
}

async function loadDashboard(preferredServerId = "") {
  const { showToast } = useToasts();
  isLoading.value = true;

  try {
    const data = await requestJson<DashboardPayload>("/api/dashboard");
    servers.value = data.servers;
    logs.value = data.logs;
    backups.value = data.backups;
    mods.value = data.mods;
    files.value = data.files;
    agentStatus.value = data.agent;
    selectedServerId.value = preferredServerId || selectedServerId.value || data.servers[0]?.id || "";
  } catch (error) {
    showToast("Backend пока недоступен, данные не обновлены", "error");
    console.error(error);
  } finally {
    isLoading.value = false;
    isDashboardLoaded.value = true;
  }
}

async function loadSettings() {
  const { showToast } = useToasts();
  try {
    settings.value = await requestJson<SettingsPayload>("/api/settings");
    agentStatus.value = settings.value.agent;
  } catch (error) {
    showToast("Не удалось загрузить настройки", "error");
    console.error(error);
  }
}

async function loadUpdateStatus() {
  const { showToast } = useToasts();
  isUpdateLoading.value = true;

  try {
    updateStatus.value = await requestJson<UpdateStatusPayload>("/api/update/status");
  } catch (error) {
    showToast("Не удалось проверить обновления", "error");
    console.error(error);
  } finally {
    isUpdateLoading.value = false;
  }
}

async function loadAgentStatus() {
  const { showToast } = useToasts();
  try {
    agentStatus.value = await requestJson<AgentStatus>("/api/agent/status");
    settings.value = {
      ...settings.value,
      agent: agentStatus.value,
    };
  } catch (error) {
    showToast("Не удалось проверить Host Agent", "error");
    console.error(error);
  }
}

async function loadMonitoring() {
  const { showToast } = useToasts();
  isMonitoringLoading.value = true;

  try {
    const data = await requestJson<HostMonitoring>("/api/monitoring");
    monitoring.value = data;
    recordMonitoringSnapshot(data);
    await loadAgentStatus();
  } catch (error) {
    await loadAgentStatus();
    showToast("Не удалось загрузить мониторинг: Host Agent недоступен", "error");
    console.error(error);
  } finally {
    isMonitoringLoading.value = false;
  }
}

async function loadServerLogs(serverId = selectedServerId.value) {
  const { showToast } = useToasts();
  if (!serverId) {
    selectedServerLogs.value = [];
    return;
  }

  selectedServerId.value = serverId;
  isLogLoading.value = true;

  try {
    selectedServerLogs.value = await requestJson<string[]>(`/api/servers/${serverId}/logs`);
  } catch (error) {
    showToast("Не удалось загрузить логи выбранного сервера", "error");
    selectedServerLogs.value = [];
    console.error(error);
  } finally {
    isLogLoading.value = false;
  }
}

async function refreshServerLogs(serverId = selectedServerId.value) {
  if (!serverId || isLogLoading.value) {
    return;
  }

  try {
    selectedServerLogs.value = await requestJson<string[]>(`/api/servers/${serverId}/logs`);
  } catch (error) {
    console.error(error);
  }
}

async function loadServerCrashReports(serverId = selectedServerId.value) {
  const { showToast } = useToasts();
  if (!serverId) {
    selectedServerCrashReports.value = [];
    return;
  }

  isCrashReportLoading.value = true;
  try {
    selectedServerCrashReports.value = await requestJson<CrashReportItem[]>(`/api/servers/${serverId}/crash-reports`);
  } catch (error) {
    showToast("Не удалось загрузить crash reports", "error");
    selectedServerCrashReports.value = [];
    console.error(error);
  } finally {
    isCrashReportLoading.value = false;
  }
}

async function loadServerConfig(serverId = selectedServerId.value) {
  const { showToast } = useToasts();
  if (!serverId) {
    selectedServerConfig.value = "";
    return;
  }

  isConfigLoading.value = true;
  try {
    const payload = await requestJson<ServerConfigPayload>(`/api/servers/${serverId}/config`);
    selectedServerConfig.value = payload.content;
  } catch (error) {
    showToast("Не удалось загрузить server.properties", "error");
    selectedServerConfig.value = "";
    console.error(error);
  } finally {
    isConfigLoading.value = false;
  }
}

async function loadServerFiles(serverId = selectedServerId.value, path = selectedServerFilePath.value) {
  const { showToast } = useToasts();
  if (!serverId) {
    selectedServerFiles.value = [];
    return;
  }

  selectedServerId.value = serverId;
  isFileLoading.value = true;
  try {
    const query = new URLSearchParams({ path });
    const payload = await requestJson<{ path: string; entries: FileEntry[] }>(`/api/servers/${serverId}/files?${query}`);
    selectedServerFilePath.value = payload.path;
    selectedServerFiles.value = payload.entries;
  } catch (error) {
    showToast("Не удалось загрузить файлы сервера", "error");
    selectedServerFiles.value = [];
    console.error(error);
  } finally {
    isFileLoading.value = false;
  }
}

async function openServerFile(path: string, serverId = selectedServerId.value) {
  const { showToast } = useToasts();
  if (!serverId) {
    return;
  }
  isFileLoading.value = true;
  try {
    const query = new URLSearchParams({ path });
    selectedServerFileContent.value = await requestJson<FileContentPayload>(`/api/servers/${serverId}/files/content?${query}`);
  } catch (error) {
    showToast("Не удалось открыть файл", "error");
    console.error(error);
  } finally {
    isFileLoading.value = false;
  }
}

async function searchServerFiles(query: string, serverId = selectedServerId.value, path = selectedServerFilePath.value) {
  const { showToast } = useToasts();
  if (!serverId || query.trim().length < 2) {
    selectedServerFileSearchResults.value = [];
    return;
  }
  isFileLoading.value = true;
  try {
    const params = new URLSearchParams({ query: query.trim(), path });
    selectedServerFileSearchResults.value = await requestJson<FileSearchResult[]>(`/api/servers/${serverId}/files/search?${params}`);
  } catch (error) {
    showToast("Не удалось выполнить поиск по файлам", "error");
    selectedServerFileSearchResults.value = [];
    console.error(error);
  } finally {
    isFileLoading.value = false;
  }
}

async function saveServerFile(content: string, serverId = selectedServerId.value) {
  const { showToast } = useToasts();
  const file = selectedServerFileContent.value;
  if (!serverId || !file || file.encoding !== "text") {
    return;
  }
  isFileSaving.value = true;
  try {
    const payload: FileWriteRequest = { path: file.path, content, encoding: "text" };
    await requestJson<FileEntry>(`/api/servers/${serverId}/files`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    selectedServerFileContent.value = { ...file, content };
    await loadServerFiles(serverId);
    showToast("Файл сохранён", "success");
  } catch (error) {
    showToast("Не удалось сохранить файл", "error");
    console.error(error);
  } finally {
    isFileSaving.value = false;
  }
}

async function uploadServerFile(file: File, serverId = selectedServerId.value, path = selectedServerFilePath.value) {
  const { showToast } = useToasts();
  if (!serverId) {
    return;
  }
  isFileSaving.value = true;
  try {
    const content = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || "");
        resolve(result.split(",", 2)[1] || "");
      };
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
    const payload: FileWriteRequest = {
      path: [path, file.name].filter(Boolean).join("/"),
      content,
      encoding: "base64",
    };
    await requestJson<FileEntry>(`/api/servers/${serverId}/files`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    await loadServerFiles(serverId, path);
    showToast("Файл загружен", "success");
  } catch (error) {
    showToast("Не удалось загрузить файл", "error");
    console.error(error);
  } finally {
    isFileSaving.value = false;
  }
}

async function runFileAction(action: FileOperationRequest["action"], path: string, targetPath = "", serverId = selectedServerId.value) {
  const { showToast } = useToasts();
  if (!serverId) {
    return;
  }
  try {
    await requestJson(`/api/servers/${serverId}/files/actions`, {
      method: "POST",
      body: JSON.stringify({ action, path, target_path: targetPath }),
    });
    await loadServerFiles(serverId);
    showToast("Файловая операция выполнена", "success");
  } catch (error) {
    showToast("Не удалось выполнить файловую операцию", "error");
    console.error(error);
  }
}

async function loadServerMods(serverId = selectedServerId.value) {
  const { showToast } = useToasts();
  if (!serverId) {
    selectedServerMods.value = [];
    return;
  }
  isModLoading.value = true;
  try {
    selectedServerMods.value = await requestJson<InstalledModItem[]>(`/api/servers/${serverId}/mods`);
  } catch (error) {
    showToast("Не удалось просканировать моды", "error");
    selectedServerMods.value = [];
    console.error(error);
  } finally {
    isModLoading.value = false;
  }
}

async function runModAction(action: "delete" | "disable" | "enable" | "pin", path: string, serverId = selectedServerId.value) {
  const { showToast } = useToasts();
  if (!serverId) {
    return;
  }
  try {
    await requestJson(`/api/servers/${serverId}/mods/actions`, {
      method: "POST",
      body: JSON.stringify({ action, path }),
    });
    await loadServerMods(serverId);
    showToast("Операция с модом выполнена", "success");
  } catch (error) {
    showToast("Не удалось выполнить операцию с модом", "error");
    console.error(error);
  }
}

async function readFileAsBase64(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || "").split(",", 2)[1] || "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function installServerMods(modFiles: File[], serverId = selectedServerId.value) {
  const { showToast } = useToasts();
  if (!serverId || !modFiles.length) {
    return;
  }
  isModLoading.value = true;
  try {
    const items: ModInstallRequest[] = await Promise.all(modFiles.map(async (file) => ({
      filename: file.name,
      content: await readFileAsBase64(file),
      encoding: "base64",
      pinned: false,
      release_channel: "release",
    })));
    await requestJson(`/api/servers/${serverId}/mods/bulk`, {
      method: "POST",
      body: JSON.stringify({ items }),
    });
    await loadServerMods(serverId);
    showToast("Моды установлены", "success");
  } catch (error) {
    showToast("Не удалось установить моды", "error");
    console.error(error);
  } finally {
    isModLoading.value = false;
  }
}

async function updateServerMod(path: string, file: File, serverId = selectedServerId.value) {
  const { showToast } = useToasts();
  if (!serverId) {
    return;
  }
  isModLoading.value = true;
  try {
    await requestJson(`/api/servers/${serverId}/mods/actions`, {
      method: "POST",
      body: JSON.stringify({
        action: "update",
        path,
        filename: file.name,
        content: await readFileAsBase64(file),
        release_channel: "release",
      }),
    });
    await loadServerMods(serverId);
    showToast("Мод обновлён", "success");
  } catch (error) {
    showToast("Не удалось обновить мод", "error");
    console.error(error);
  } finally {
    isModLoading.value = false;
  }
}

async function bulkUpdateServerMods(modFiles: File[], serverId = selectedServerId.value) {
  const { showToast } = useToasts();
  if (!serverId || !modFiles.length) {
    return;
  }
  const installedByName = new Map(
    selectedServerMods.value.map((mod) => [mod.filename.replace(/\.disabled$/i, ""), mod.path]),
  );
  const matchedFiles = modFiles.filter((file) => installedByName.has(file.name));
  if (!matchedFiles.length) {
    showToast("Не найдено совпадений с установленными модами", "error");
    return;
  }
  isModLoading.value = true;
  try {
    await requestJson(`/api/servers/${serverId}/mods/bulk-actions`, {
      method: "POST",
      body: JSON.stringify({
        action: "update",
        items: await Promise.all(matchedFiles.map(async (file) => ({
          action: "update",
          path: installedByName.get(file.name) || "",
          filename: file.name,
          content: await readFileAsBase64(file),
          release_channel: "release",
        }))),
      }),
    });
    await loadServerMods(serverId);
    showToast(`Моды обновлены: ${matchedFiles.length}`, "success");
  } catch (error) {
    showToast("Не удалось массово обновить моды", "error");
    console.error(error);
  } finally {
    isModLoading.value = false;
  }
}

async function runBulkModAction(action: "delete" | "disable" | "enable" | "pin", serverId = selectedServerId.value) {
  const { showToast } = useToasts();
  if (!serverId || !selectedServerMods.value.length) {
    return;
  }
  try {
    await requestJson(`/api/servers/${serverId}/mods/bulk-actions`, {
      method: "POST",
      body: JSON.stringify({
        action,
        items: selectedServerMods.value.map((mod) => ({ action, path: mod.path })),
      }),
    });
    await loadServerMods(serverId);
    showToast("Массовая операция выполнена", "success");
  } catch (error) {
    showToast("Не удалось выполнить массовую операцию", "error");
    console.error(error);
  }
}

async function createServerBackup(serverId = selectedServerId.value, payload?: BackupRequest) {
  const { showToast } = useToasts();
  if (!serverId) {
    return;
  }
  try {
    const backup = await requestJson<BackupItem>(`/api/backups?server_id=${encodeURIComponent(serverId)}`, {
      method: "POST",
      body: JSON.stringify(payload ?? {
        mode: "live",
        parts: ["world", "mods", "config", "root"],
        description: "Manual backup",
      }),
    });
    backups.value = [backup, ...backups.value.filter((item) => item.id !== backup.id)];
    showToast("Бэкап создан", "success");
  } catch (error) {
    showToast("Не удалось создать бэкап", "error");
    console.error(error);
  }
}

async function saveServerConfig() {
  const { showToast } = useToasts();
  if (!selectedServerId.value) {
    return;
  }

  isConfigSaving.value = true;
  try {
    const payload = await requestJson<ServerConfigPayload>(`/api/servers/${selectedServerId.value}/config`, {
      method: "PUT",
      body: JSON.stringify({ content: selectedServerConfig.value }),
    });
    selectedServerConfig.value = payload.content;
    showToast("server.properties сохранён", "success");
  } catch (error) {
    showToast("Не удалось сохранить server.properties", "error");
    console.error(error);
  } finally {
    isConfigSaving.value = false;
  }
}

async function runServerAction(serverId: string, action: "start" | "restart" | "stop" | "kill" | "update" | "rollback" | "backup") {
  const { showToast } = useToasts();
  try {
    await requestJson(`/api/servers/${serverId}/actions/${action}`, { method: "POST" });
    await loadDashboard(serverId);
  } catch (error) {
    showToast("Не удалось выполнить действие", "error");
    console.error(error);
  }
}

async function createServer(newServer: NewServerDraft) {
  const { showToast } = useToasts();
  isCreatingServer.value = true;
  try {
    await requestJson("/api/servers", {
      method: "POST",
      body: JSON.stringify({
        name: newServer.name,
        type: newServer.type,
        pack: serverTypeLabels[newServer.type],
        version: newServer.version,
        min_ram: newServer.min_ram,
        max_ram: newServer.max_ram,
        java_runtime: newServer.java_runtime,
        jvm_args: newServer.jvm_args,
        cpu_limit: newServer.cpu_limit,
        loader_version: newServer.loader_version,
        installer_version: newServer.installer_version,
        install_fabric_api: newServer.install_fabric_api,
        address: "",
      }),
    });
    await loadDashboard();
    showToast("Сервер создан и готов к запуску", "success");
    return true;
  } catch (error) {
    showToast("Не удалось подготовить сервер", "error");
    console.error(error);
    return false;
  } finally {
    isCreatingServer.value = false;
  }
}

async function deleteServer(serverId: string) {
  const { showToast } = useToasts();
  const server = servers.value.find((item) => item.id === serverId);
  const confirmed = window.confirm(
    `Удалить ${server?.name ?? "сервер"} из панели? Сервис будет остановлен и отключен от автозапуска, файлы мира останутся на диске.`,
  );
  if (!confirmed) {
    return;
  }

  try {
    await requestJson(`/api/servers/${serverId}`, { method: "DELETE" });
    await loadDashboard();
    showToast(`${server?.name ?? "Сервер"} удалён из панели`, "success");
  } catch (error) {
    showToast("Не удалось удалить сервер через agent", "error");
    console.error(error);
  }
}

async function saveSettings() {
  const { showToast } = useToasts();
  isSavingSettings.value = true;

  try {
    settings.value = await requestJson<SettingsPayload>("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ curseforge_api_key: curseForgeApiKey.value }),
    });
    curseForgeApiKey.value = "";
    showToast(
      settings.value.has_curseforge_api_key ? "Ключ CurseForge сохранён" : "Ключ CurseForge очищен",
      "success",
    );
  } catch (error) {
    showToast("Не удалось сохранить ключ CurseForge", "error");
    console.error(error);
  } finally {
    isSavingSettings.value = false;
  }
}

async function clearCurseForgeKey() {
  curseForgeApiKey.value = "";
  await saveSettings();
}

async function restartAgent() {
  const { showToast } = useToasts();
  try {
    agentStatus.value = await requestJson<AgentStatus>("/api/agent/restart", { method: "POST" });
    settings.value = {
      ...settings.value,
      agent: agentStatus.value,
    };
    showToast("Host Agent перезапускается", "success");
    window.setTimeout(() => {
      loadAgentStatus();
      loadDashboard();
    }, 1600);
  } catch (error) {
    showToast("Не удалось перезапустить Host Agent из панели", "error");
    console.error(error);
  }
}

async function applyUpdate() {
  const { showToast } = useToasts();
  if (!updateStatus.value.latest_version) {
    showToast("Нет доступного release tag для обновления", "error");
    return;
  }

  isApplyingUpdate.value = true;
  try {
    const result = await requestJson<{ message: string; target_version: string }>("/api/update/apply", {
      method: "POST",
      body: JSON.stringify({ target_version: updateStatus.value.latest_version }),
    });
    showToast(result.message || `Обновление до ${result.target_version} запущено`, "success");
    await loadUpdateStatus();
  } catch (error) {
    showToast("Не удалось запустить обновление", "error");
    console.error(error);
  } finally {
    isApplyingUpdate.value = false;
  }
}

export function useDashboardStore() {
  return {
    servers,
    logs,
    backups,
    mods,
    files,
    isLoading,
    isDashboardLoaded,
    isDashboardInitialLoading,
    isMonitoringLoading,
    isSavingSettings,
    isUpdateLoading,
    isApplyingUpdate,
    isCreatingServer,
    selectedServerId,
    selectedServer,
    selectedServerLogs,
    selectedServerCrashReports,
    selectedServerConfig,
    selectedServerFiles,
    selectedServerFilePath,
    selectedServerFileContent,
    selectedServerFileSearchResults,
    selectedServerMods,
    isLogLoading,
    isCrashReportLoading,
    isConfigLoading,
    isConfigSaving,
    isFileLoading,
    isFileSaving,
    isModLoading,
    curseForgeApiKey,
    agentStatus,
    settings,
    updateStatus,
    monitoring,
    monitoringHistory,
    onlineServersCount,
    offlineServersCount,
    deployingServersCount,
    stableServersCount,
    isAgentUnavailable,
    monitoringStatus,
    loadDashboard,
    loadSettings,
    loadUpdateStatus,
    loadAgentStatus,
    loadMonitoring,
    loadServerLogs,
    refreshServerLogs,
    loadServerCrashReports,
    loadServerConfig,
    loadServerFiles,
    openServerFile,
    searchServerFiles,
    saveServerFile,
    uploadServerFile,
    runFileAction,
    loadServerMods,
    runModAction,
    installServerMods,
    updateServerMod,
    bulkUpdateServerMods,
    runBulkModAction,
    createServerBackup,
    saveServerConfig,
    runServerAction,
    createServer,
    deleteServer,
    saveSettings,
    clearCurseForgeKey,
    restartAgent,
    applyUpdate,
  };
}
