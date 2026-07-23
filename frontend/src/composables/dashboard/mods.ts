import { requestJson } from "../../services/api";
import type { InstalledModItem, ModInstallRequest } from "../../types";

export type ModAction = "delete" | "disable" | "enable" | "pin" | "update";

export function useModRequests() {
  return {
    list: (serverId: string) => requestJson<InstalledModItem[]>(`/api/servers/${serverId}/mods`),
    action: (serverId: string, payload: Record<string, unknown>) => requestJson(`/api/servers/${serverId}/mods/actions`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
    bulkInstall: (serverId: string, items: ModInstallRequest[]) => requestJson(`/api/servers/${serverId}/mods/bulk`, {
      method: "POST",
      body: JSON.stringify({ items }),
    }),
    bulkAction: (serverId: string, action: ModAction, items: Record<string, unknown>[]) => requestJson(`/api/servers/${serverId}/mods/bulk-actions`, {
      method: "POST",
      body: JSON.stringify({ action, items }),
    }),
  };
}
