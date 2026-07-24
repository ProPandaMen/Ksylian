import type { BackupItem } from "./backups";
import type { FileItem } from "./files";
import type { ModItem } from "./mods";

export type ServerState =
  | "installing"
  | "stopped"
  | "starting"
  | "running"
  | "stopping"
  | "crashed"
  | "updating"
  | "backing_up";
export type MinecraftServerType = "vanilla" | "paper" | "purpur" | "fabric" | "forge" | "neoforge";

export interface NewServerDraft {
  name: string;
  type: MinecraftServerType;
  version: string;
  min_ram: string;
  max_ram: string;
  java_runtime: "auto" | "8" | "17" | "21";
  jvm_args: string;
  cpu_limit: number;
  loader_version: string;
  installer_version: string;
  install_fabric_api: boolean;
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
  operation?: ServerOperationProgress | null;
}

export interface ServerOperationProgress {
  kind: "curseforge_install";
  label: string;
  current: number;
  total: number;
  percent: number;
  current_item: string;
  message: string;
}

export interface ServerActionResult {
  ok: boolean;
  message: string;
  server: GameServer;
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

export interface ServerConfigPayload {
  content: string;
}

export interface RconCommandResult {
  ok: boolean;
  output: string;
}

export interface GamePlayer {
  name: string;
  uuid: string;
  online: boolean;
  ping: string;
  game_time: string;
  last_seen: string;
  whitelisted: boolean;
  operator: boolean;
  banned: boolean;
  ip_banned: boolean;
  luckperms_groups: string[];
}

export interface PlayerHistoryItem {
  at: string;
  player: string;
  action: string;
  detail: string;
  actor: string;
}

export interface PlayerListPayload {
  online: GamePlayer[];
  known: GamePlayer[];
  history: PlayerHistoryItem[];
  rcon_available: boolean;
  game_time: string;
}

export interface PlayerActionRequest {
  action:
    | "whitelist_add"
    | "whitelist_remove"
    | "op"
    | "deop"
    | "ban"
    | "pardon"
    | "ban_ip"
    | "pardon_ip"
    | "kick"
    | "message"
    | "luckperms_group_add"
    | "luckperms_group_remove"
    | "luckperms_permission_set"
    | "luckperms_permission_unset";
  player: string;
  value: string;
  reason: string;
}

export interface ImportServerRequest {
  name: string;
  path: string;
  keep_current_path: boolean;
  min_ram: string;
  max_ram: string;
  java_runtime: "auto" | "8" | "17" | "21";
  jvm_args: string;
  cpu_limit: number;
  loader_version: string;
}

export interface ImportServerPreview {
  ok: boolean;
  name: string;
  path: string;
  type: "legacy" | MinecraftServerType;
  version: string;
  loader_version: string;
  java_runtime: string;
  port: number;
  has_server_properties: boolean;
  mod_count: number;
  warnings: string[];
}
