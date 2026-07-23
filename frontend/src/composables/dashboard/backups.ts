import { requestJson } from "../../services/api";
import type { BackupItem, BackupRequest } from "../../types";

export function useBackupRequests() {
  return {
    create: (serverId: string, payload: BackupRequest) => requestJson<BackupItem>(`/api/backups?server_id=${encodeURIComponent(serverId)}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  };
}
