import { requestJson } from "../../services/api";
import type { AgentStatus, HostMonitoring } from "../../types";

export function useMonitoringRequests() {
  return {
    agentStatus: () => requestJson<AgentStatus>("/api/agent/status"),
    monitoring: () => requestJson<HostMonitoring>("/api/monitoring"),
  };
}
