import { requestJson } from "../../services/api";
import { serverTypeLabels } from "../dashboardLabels";
import type {
  CrashReportItem,
  DashboardPayload,
  GameServer,
  NewServerDraft,
  RconCommandResult,
  ServerConfigPayload,
} from "../../types";

export function useServerRequests() {
  return {
    dashboard: () => requestJson<DashboardPayload>("/api/dashboard"),
    logs: (serverId: string) => requestJson<string[]>(`/api/servers/${serverId}/logs`),
    crashReports: (serverId: string) => requestJson<CrashReportItem[]>(`/api/servers/${serverId}/crash-reports`),
    config: (serverId: string) => requestJson<ServerConfigPayload>(`/api/servers/${serverId}/config`),
    saveConfig: (serverId: string, content: string) => requestJson<ServerConfigPayload>(`/api/servers/${serverId}/config`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),
    action: (serverId: string, action: "start" | "restart" | "stop" | "kill" | "update" | "rollback" | "backup") =>
      requestJson(`/api/servers/${serverId}/actions/${action}`, { method: "POST" }),
    rconCommand: (serverId: string, command: string) => requestJson<RconCommandResult>(`/api/servers/${serverId}/rcon/command`, {
      method: "POST",
      body: JSON.stringify({ command }),
    }),
    create: (newServer: NewServerDraft) => requestJson<GameServer>("/api/servers", {
      method: "POST",
      body: JSON.stringify({
        name: newServer.name,
        type: newServer.type,
        pack: serverTypeLabels[newServer.type],
        version: newServer.version,
        min_ram: newServer.min_ram,
        max_ram: newServer.max_ram,
        java_runtime: newServer.java_runtime,
        jvm_args: newServer.jvm_args,
        cpu_limit: newServer.cpu_limit,
        loader_version: newServer.loader_version,
        installer_version: newServer.installer_version,
        install_fabric_api: newServer.install_fabric_api,
        address: "",
      }),
    }),
    delete: (serverId: string) => requestJson(`/api/servers/${serverId}`, { method: "DELETE" }),
  };
}
