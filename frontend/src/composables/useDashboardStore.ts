import { computed, ref } from "vue";
import { requestJson } from "../services/api";
import type {
  AgentStatus,
  BackupItem,
  DashboardPayload,
  FileItem,
  GameServer,
  HostMonitoring,
  ModItem,
  NewServerDraft,
  ServerConfigPayload,
  ServerState,
  SettingsPayload,
} from "../types";
import { useToasts } from "./useToasts";

const emptyServers: GameServer[] = [];
const emptyLogs: string[] = [];
const emptyBackups: BackupItem[] = [];
const emptyMods: ModItem[] = [];
const emptyFiles: FileItem[] = [];

export const stateLabels: Record<ServerState, string> = {
  online: "Онлайн",
  deploying: "Разворачивается",
  offline: "Выключен",
};

export const serverTypeLabels: Record<NewServerDraft["type"], string> = {
  vanilla: "Vanilla",
  fabric: "Fabric",
  forge: "Forge",
  neoforge: "NeoForge",
  quilt: "Quilt",
  paper: "Paper / Purpur",
  purpur: "Paper / Purpur",
};

const defaultAgentStatus: AgentStatus = {
  configured: false,
  available: false,
  status: "not_configured",
  message: "",
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
const selectedServerId = ref("");
const selectedServerLogs = ref<string[]>(emptyLogs);
const selectedServerConfig = ref("");
const isLogLoading = ref(false);
const isConfigLoading = ref(false);
const isConfigSaving = ref(false);
const curseForgeApiKey = ref("");
const agentStatus = ref<AgentStatus>(defaultAgentStatus);
const settings = ref<SettingsPayload>({
  has_curseforge_api_key: false,
  curseforge_api_key_mask: "",
  agent: defaultAgentStatus,
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

const onlineServersCount = computed(
  () => servers.value.filter((server) => server.state !== "offline").length,
);
const offlineServersCount = computed(
  () => servers.value.filter((server) => server.state === "offline").length,
);
const deployingServersCount = computed(
  () => servers.value.filter((server) => server.state === "deploying").length,
);
const stableServersCount = computed(
  () => servers.value.filter((server) => server.state === "online").length,
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
    monitoring.value = await requestJson<HostMonitoring>("/api/monitoring");
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

async function runServerAction(serverId: string, action: "start" | "restart" | "stop" | "backup") {
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
  try {
    await requestJson("/api/servers", {
      method: "POST",
      body: JSON.stringify({
        name: newServer.name,
        type: newServer.type === "purpur" ? "paper" : newServer.type,
        pack: serverTypeLabels[newServer.type],
        version: newServer.version,
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
    selectedServerId,
    selectedServer,
    selectedServerLogs,
    selectedServerConfig,
    isLogLoading,
    isConfigLoading,
    isConfigSaving,
    curseForgeApiKey,
    agentStatus,
    settings,
    monitoring,
    onlineServersCount,
    offlineServersCount,
    deployingServersCount,
    stableServersCount,
    isAgentUnavailable,
    monitoringStatus,
    loadDashboard,
    loadSettings,
    loadAgentStatus,
    loadMonitoring,
    loadServerLogs,
    refreshServerLogs,
    loadServerConfig,
    saveServerConfig,
    runServerAction,
    createServer,
    deleteServer,
    saveSettings,
    clearCurseForgeKey,
    restartAgent,
  };
}
