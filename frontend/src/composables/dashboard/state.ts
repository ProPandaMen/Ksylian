import { computed, ref } from "vue";
import type {
  AgentStatus,
  BackupItem,
  CrashReportItem,
  FileContentPayload,
  FileEntry,
  FileSearchResult,
  FileItem,
  GameServer,
  HostMonitoring,
  MonitoringHistoryPayload,
  InstalledModItem,
  MonitoringHistoryPoint,
  MonitoringWindow,
  ModItem,
  SettingsPayload,
  UpdateStatusPayload,
} from "../../types";

const emptyServers: GameServer[] = [];
const emptyLogs: string[] = [];
const emptyBackups: BackupItem[] = [];
const emptyCrashReports: CrashReportItem[] = [];
const emptyMods: ModItem[] = [];
const emptyFiles: FileItem[] = [];

const defaultAgentStatus: AgentStatus = {
  configured: false,
  available: false,
  status: "not_configured",
  message: "",
  public_domain: "",
  proxy_domain: "",
  proxy_port: "",
};

export const servers = ref<GameServer[]>(emptyServers);
export const logs = ref<string[]>(emptyLogs);
export const backups = ref<BackupItem[]>(emptyBackups);
export const mods = ref<ModItem[]>(emptyMods);
export const files = ref<FileItem[]>(emptyFiles);
export const isLoading = ref(true);
export const isDashboardLoaded = ref(false);
export const isMonitoringLoading = ref(false);
export const isMonitoringHistoryLoading = ref(false);
export const isSavingSettings = ref(false);
export const isSettingsLoaded = ref(false);
export const isUpdateLoading = ref(false);
export const isApplyingUpdate = ref(false);
export const isCreatingServer = ref(false);
export const selectedServerId = ref("");
export const selectedServerLogs = ref<string[]>(emptyLogs);
export const selectedServerCrashReports = ref<CrashReportItem[]>(emptyCrashReports);
export const selectedServerConfig = ref("");
export const selectedServerFiles = ref<FileEntry[]>([]);
export const selectedServerFilePath = ref("");
export const selectedServerFileContent = ref<FileContentPayload | null>(null);
export const selectedServerFileSearchResults = ref<FileSearchResult[]>([]);
export const selectedServerMods = ref<InstalledModItem[]>([]);
export const isLogLoading = ref(false);
export const isCrashReportLoading = ref(false);
export const isConfigLoading = ref(false);
export const isConfigSaving = ref(false);
export const isFileLoading = ref(false);
export const isFileSaving = ref(false);
export const isModLoading = ref(false);
export const curseForgeApiKey = ref("");
export const agentStatus = ref<AgentStatus>(defaultAgentStatus);
export const settings = ref<SettingsPayload>({
  has_curseforge_api_key: false,
  curseforge_api_key_mask: "",
  curseforge_api_key_status: "missing",
  curseforge_api_key_message: "",
  agent: defaultAgentStatus,
});
export const updateStatus = ref<UpdateStatusPayload>({
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
export const monitoring = ref<HostMonitoring>({
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
export const monitoringHistory = ref<MonitoringHistoryPoint[]>([]);
export const monitoringHistoryMeta = ref<MonitoringHistoryPayload>({
  window: "1h",
  sample_seconds: 30,
  retention_hours: 24,
  points: [],
});
export const monitoringWindow = ref<MonitoringWindow>("1h");

export const onlineServersCount = computed(
  () => servers.value.filter((server) => server.state === "running").length,
);
export const offlineServersCount = computed(
  () => servers.value.filter((server) => ["stopped", "crashed"].includes(server.state)).length,
);
export const deployingServersCount = computed(
  () => servers.value.filter((server) => ["installing", "starting", "stopping", "updating", "backing_up"].includes(server.state)).length,
);
export const stableServersCount = computed(
  () => servers.value.filter((server) => server.state === "running").length,
);
export const selectedServer = computed(
  () => servers.value.find((server) => server.id === selectedServerId.value) ?? servers.value[0],
);
export const isDashboardInitialLoading = computed(() => isLoading.value && !isDashboardLoaded.value);
export const isAgentUnavailable = computed(() => agentStatus.value.configured && !agentStatus.value.available);
export const monitoringStatus = computed(() => {
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

export function recordMonitoringSnapshot(snapshot: HostMonitoring) {
  const point: MonitoringHistoryPoint = {
    timestamp: Date.now(),
    cpu: snapshot.cpu_percent,
    memory: snapshot.memory.percent,
    swap: snapshot.swap.percent,
    temperature: parseTemperature(snapshot.temperature),
  };
  monitoringHistory.value = [...monitoringHistory.value.slice(-47), point];
}
