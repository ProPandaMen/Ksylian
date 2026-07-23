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
  cpu: number;
  memory: number;
  swap: number;
  temperature: number | null;
}
