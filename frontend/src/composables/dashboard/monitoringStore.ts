import { useToasts } from "../useToasts";
import { useMonitoringRequests } from "./monitoring";
import { agentStatus, isMonitoringLoading, monitoring, recordMonitoringSnapshot, settings } from "./state";

const monitoringRequests = useMonitoringRequests();

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
      recordMonitoringSnapshot(data);
      await loadAgentStatus();
    } catch (error) {
      await loadAgentStatus();
      showToast("Не удалось загрузить мониторинг: Host Agent недоступен", "error");
      console.error(error);
    } finally {
      isMonitoringLoading.value = false;
    }
  }

  return { loadAgentStatus, loadMonitoring };
}
