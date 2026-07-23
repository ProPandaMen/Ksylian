import type { ServerState } from "./server";

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
  collected_at?: string;
  cpu: number;
  memory: number;
  swap: number;
  temperature: number | null;
  load_average?: number[];
  disks?: MonitoringDiskPoint[];
  services?: MonitoringServicesPoint;
  top_process?: MonitoringTopProcessPoint | null;
}

export interface MonitoringDiskPoint {
  mount: string;
  percent: number;
  used: number;
  total: number;
}

export interface MonitoringServicesPoint {
  running: number;
  total: number;
  unhealthy: string[];
}

export interface MonitoringTopProcessPoint {
  pid: number;
  name: string;
  cpu: number;
  memory: number;
}

export type MonitoringWindow = "1h" | "6h" | "24h";

export interface MonitoringHistoryPayload {
  window: MonitoringWindow;
  sample_seconds: number;
  retention_hours: number;
  points: MonitoringHistoryPoint[];
}
