import { useToasts } from "../useToasts";
import { useMonitoringRequests } from "./monitoring";
import type { MonitoringWindow } from "../../types";
import {
  agentStatus,
  isMonitoringHistoryLoading,
  isMonitoringLoading,
  monitoring,
  monitoringHistory,
  monitoringHistoryMeta,
  monitoringWindow,
  settings,
} from "./state";

const monitoringRequests = useMonitoringRequests();
let lastHistoryErrorToast = "";

export function useMonitoringDashboardActions() {
  async function loadAgentStatus() {
    const { showToast } = useToasts();
    try {
      agentStatus.value = await monitoringRequests.agentStatus();
      settings.value = {
        ...settings.value,
        agent: agentStatus.value,
      };
    } catch (error) {
      showToast("Не удалось проверить Host Agent", "error");
      console.error(error);
    }
  }

  async function loadMonitoring() {
    const { showToast } = useToasts();
    isMonitoringLoading.value = true;

    try {
      const data = await monitoringRequests.monitoring();
      monitoring.value = data;
      await loadAgentStatus();
    } catch (error) {
      await loadAgentStatus();
      showToast("Не удалось загрузить мониторинг: Host Agent недоступен", "error");
      console.error(error);
    } finally {
      isMonitoringLoading.value = false;
    }
  }

  async function loadMonitoringHistory(window: MonitoringWindow = monitoringWindow.value) {
    const { showToast } = useToasts();
    monitoringWindow.value = window;
    isMonitoringHistoryLoading.value = true;

    try {
      const data = await monitoringRequests.monitoringHistory(window);
      monitoringHistoryMeta.value = data;
      monitoringHistory.value = data.points;
      if (data.error) {
        if (data.error !== lastHistoryErrorToast) {
          showToast(data.error, "error");
          lastHistoryErrorToast = data.error;
        }
      } else {
        lastHistoryErrorToast = "";
      }
    } catch (error) {
      showToast("Не удалось загрузить историю мониторинга", "error");
      console.error(error);
    } finally {
      isMonitoringHistoryLoading.value = false;
    }
  }

  return { loadAgentStatus, loadMonitoring, loadMonitoringHistory };
}
