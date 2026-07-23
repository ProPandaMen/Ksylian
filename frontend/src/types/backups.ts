export interface BackupItem {
  id: string;
  name: string;
  size: string;
  created: string;
  server_id: string;
  checksum?: string;
  description?: string;
  manifest?: string;
}

export interface BackupRequest {
  mode: "live" | "stopped";
  parts: Array<"world" | "mods" | "config" | "root">;
  description: string;
}

export interface RestoreRequest {
  backup_id: string;
  target: "all" | "world" | "mods" | "config";
  insurance_backup: boolean;
}
