export type ServerState =
  | "installing"
  | "stopped"
  | "starting"
  | "running"
  | "stopping"
  | "crashed"
  | "updating"
  | "backing_up";
export type TabId = "servers" | "monitoring" | "modpacks" | "users" | "settings";
export type MinecraftServerType = "vanilla" | "paper" | "purpur" | "fabric" | "forge";
export type ThemeName = "pink" | "black" | "white" | "green";

export interface NewServerDraft {
  name: string;
  type: MinecraftServerType;
  version: string;
  min_ram: string;
  max_ram: string;
  java_runtime: "auto" | "8" | "17" | "21";
  jvm_args: string;
  cpu_limit: number;
}

export type MinecraftVersionType = "release" | "snapshot" | "old_beta" | "old_alpha";

export interface MinecraftVersion {
  id: string;
  type: MinecraftVersionType;
  label: string;
  released_at: string;
}

export interface MinecraftVersionsPayload {
  latest_release: string;
  latest_snapshot: string;
  versions: MinecraftVersion[];
}

export interface GameServer {
  id: string;
  name: string;
  pack: string;
  version: string;
  state: ServerState;
  players: string;
  ram: string;
  cpu: number;
  disk: string;
  address: string;
  exit_code?: number | null;
  last_event?: string;
  warnings?: string[];
}

export interface BackupItem {
  id: string;
  name: string;
  size: string;
  created: string;
  server_id: string;
}

export interface CrashReportItem {
  name: string;
  size: string;
  created: string;
  summary: string;
  probable_cause?: string;
  conflicting_mod?: string;
  missing_dependency?: string;
  client_only_mod?: string;
  stack_trace?: string[];
  recent_changes?: string[];
}

export interface ModItem {
  id: string;
  name: string;
  status: string;
  tag: "required" | "update" | "review";
}

export interface FileItem {
  name: string;
  meta: string;
  kind: "folder" | "file";
}

export interface AgentStatus {
  configured: boolean;
  available: boolean;
  status: "online" | "offline" | "not_configured";
  message: string;
  public_domain: string;
  proxy_domain: string;
  proxy_port: string;
}

export interface DashboardPayload {
  servers: GameServer[];
  logs: string[];
  backups: BackupItem[];
  mods: ModItem[];
  files: FileItem[];
  agent: AgentStatus;
}

export interface SettingsPayload {
  has_curseforge_api_key: boolean;
  curseforge_api_key_mask: string;
  agent: AgentStatus;
}

export interface AuthStatusPayload {
  has_users: boolean;
  bootstrap_required: boolean;
}

export interface AuthUser {
  id: string;
  username: string;
  display_name: string;
  role: "admin" | "member";
  theme: ThemeName;
  created_at: string;
}

export interface AuthSessionPayload {
  token: string;
  user: AuthUser;
}

export interface UserInvite {
  id: string;
  token: string;
  role: "admin" | "member";
  created_at: string;
  expires_at: string;
  used_at: string;
  invited_by: string;
}

export interface UpdateStatusPayload {
  current_version: string;
  current_sha: string;
  latest_version: string;
  latest_sha: string;
  update_available: boolean;
  checked_at: string;
  release_url: string;
  notes: string;
  can_update: boolean;
  updater_status: "ready" | "agent_unavailable" | "not_configured" | "unknown";
}

export interface ApplyUpdateResult {
  ok: boolean;
  message: string;
  target_version: string;
}

export interface ServerConfigPayload {
  content: string;
}

export interface RconCommandResult {
  ok: boolean;
  output: string;
}

export interface MetricUsage {
  used: number;
  total: number;
  percent: number;
  used_label: string;
  total_label: string;
}

export interface DiskUsage {
  mount: string;
  filesystem: string;
  used: number;
  total: number;
  percent: number;
  used_label: string;
  total_label: string;
}

export interface ProcessUsage {
  pid: number;
  name: string;
  cpu: number;
  memory: number;
  command: string;
}

export interface ServiceUsage {
  id: string;
  name: string;
  state: ServerState;
  cpu: number;
  ram: string;
}

export interface HostMonitoring {
  hostname: string;
  ip_addresses: string[];
  uptime: string;
  load_average: number[];
  cpu_percent: number;
  cpu_cores: number;
  memory: MetricUsage;
  swap: MetricUsage;
  disks: DiskUsage[];
  top_processes: ProcessUsage[];
  services: ServiceUsage[];
  temperature: string;
  collected_at: string;
}

export interface MonitoringHistoryPoint {
  timestamp: number;
  cpu: number;
  memory: number;
  swap: number;
  temperature: number | null;
}
