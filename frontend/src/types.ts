export type ServerState = "online" | "deploying" | "offline";
export type TabId = "overview" | "servers" | "monitoring" | "modpacks" | "files" | "backups" | "settings";

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
}

export interface BackupItem {
  id: string;
  name: string;
  size: string;
  created: string;
  server_id: string;
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

export interface DashboardPayload {
  servers: GameServer[];
  logs: string[];
  backups: BackupItem[];
  mods: ModItem[];
  files: FileItem[];
}

export interface SettingsPayload {
  has_curseforge_api_key: boolean;
  curseforge_api_key_mask: string;
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
