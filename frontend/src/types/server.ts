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
