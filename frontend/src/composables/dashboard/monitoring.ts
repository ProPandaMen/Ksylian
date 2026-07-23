import { requestJson } from "../../services/api";
import type { AgentStatus, HostMonitoring, MonitoringHistoryPayload, MonitoringWindow } from "../../types";

export function useMonitoringRequests() {
  return {
    agentStatus: () => requestJson<AgentStatus>("/api/agent/status"),
    monitoring: () => requestJson<HostMonitoring>("/api/monitoring"),
    monitoringHistory: (window: MonitoringWindow) =>
      requestJson<MonitoringHistoryPayload>(`/api/monitoring/history?window=${encodeURIComponent(window)}`),
  };
}
