import { requestJson } from "../../services/api";
import type { AgentStatus, SettingsPayload, UpdateStatusPayload } from "../../types";

export function useSettingsRequests() {
  return {
    settings: () => requestJson<SettingsPayload>("/api/settings"),
    saveSettings: (curseforgeApiKey: string) => requestJson<SettingsPayload>("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ curseforge_api_key: curseforgeApiKey }),
    }),
    updateStatus: () => requestJson<UpdateStatusPayload>("/api/update/status"),
    restartAgent: () => requestJson<AgentStatus>("/api/agent/restart", { method: "POST" }),
    applyUpdate: (targetVersion: string) => requestJson<{ message: string; target_version: string }>("/api/update/apply", {
      method: "POST",
      body: JSON.stringify({ target_version: targetVersion }),
    }),
  };
}
