import { useToasts } from "../useToasts";
import type { NewServerDraft } from "../../types";
import { useServerRequests } from "./servers";
import {
  agentStatus,
  backups,
  files,
  isConfigLoading,
  isConfigSaving,
  isCrashReportLoading,
  isCreatingServer,
  isDashboardLoaded,
  isLoading,
  isLogLoading,
  logs,
  mods,
  selectedServerConfig,
  selectedServerCrashReports,
  selectedServerId,
  selectedServerLogs,
  servers,
} from "./state";

const serverRequests = useServerRequests();

export function useServerDashboardActions() {
  async function loadDashboard(preferredServerId = "") {
    const { showToast } = useToasts();
    isLoading.value = true;

    try {
      const data = await serverRequests.dashboard();
      servers.value = data.servers;
      logs.value = data.logs;
      backups.value = data.backups;
      mods.value = data.mods;
      files.value = data.files;
      agentStatus.value = data.agent;
      selectedServerId.value = preferredServerId || selectedServerId.value || data.servers[0]?.id || "";
    } catch (error) {
      showToast("Backend пока недоступен, данные не обновлены", "error");
      console.error(error);
    } finally {
      isLoading.value = false;
      isDashboardLoaded.value = true;
    }
  }

  async function loadServerLogs(serverId = selectedServerId.value) {
    const { showToast } = useToasts();
    if (!serverId) {
      selectedServerLogs.value = [];
      return;
    }

    selectedServerId.value = serverId;
    isLogLoading.value = true;

    try {
      selectedServerLogs.value = await serverRequests.logs(serverId);
    } catch (error) {
      showToast("Не удалось загрузить логи выбранного сервера", "error");
      selectedServerLogs.value = [];
      console.error(error);
    } finally {
      isLogLoading.value = false;
    }
  }

  async function refreshServerLogs(serverId = selectedServerId.value) {
    if (!serverId || isLogLoading.value) {
      return;
    }

    try {
      selectedServerLogs.value = await serverRequests.logs(serverId);
    } catch (error) {
      console.error(error);
    }
  }

  async function loadServerCrashReports(serverId = selectedServerId.value) {
    const { showToast } = useToasts();
    if (!serverId) {
      selectedServerCrashReports.value = [];
      return;
    }

    isCrashReportLoading.value = true;
    try {
      selectedServerCrashReports.value = await serverRequests.crashReports(serverId);
    } catch (error) {
      showToast("Не удалось загрузить crash reports", "error");
      selectedServerCrashReports.value = [];
      console.error(error);
    } finally {
      isCrashReportLoading.value = false;
    }
  }

  async function loadServerConfig(serverId = selectedServerId.value) {
    const { showToast } = useToasts();
    if (!serverId) {
      selectedServerConfig.value = "";
      return;
    }

    isConfigLoading.value = true;
    try {
      const payload = await serverRequests.config(serverId);
      selectedServerConfig.value = payload.content;
    } catch (error) {
      showToast("Не удалось загрузить server.properties", "error");
      selectedServerConfig.value = "";
      console.error(error);
    } finally {
      isConfigLoading.value = false;
    }
  }

  async function saveServerConfig() {
    const { showToast } = useToasts();
    if (!selectedServerId.value) {
      return;
    }

    isConfigSaving.value = true;
    try {
      const payload = await serverRequests.saveConfig(selectedServerId.value, selectedServerConfig.value);
      selectedServerConfig.value = payload.content;
      showToast("server.properties сохранён", "success");
    } catch (error) {
      showToast("Не удалось сохранить server.properties", "error");
      console.error(error);
    } finally {
      isConfigSaving.value = false;
    }
  }

  async function runServerAction(serverId: string, action: "start" | "restart" | "stop" | "kill" | "update" | "rollback" | "backup") {
    const { showToast } = useToasts();
    try {
      const result = await serverRequests.action(serverId, action);
      await loadDashboard(serverId);
      const updatedServer = servers.value.find((server) => server.id === serverId);
      const warning = updatedServer?.warnings?.[0] || result.server.warnings?.[0] || "";
      showToast(result.message || "Действие выполнено", warning ? "info" : "success");
      if (warning) {
        showToast(warning, "info");
      }
    } catch (error) {
      showToast("Не удалось выполнить действие", "error");
      console.error(error);
    }
  }

  async function createServer(newServer: NewServerDraft) {
    const { showToast } = useToasts();
    isCreatingServer.value = true;
    try {
      await serverRequests.create(newServer);
      await loadDashboard();
      showToast("Сервер создан и готов к запуску", "success");
      return true;
    } catch (error) {
      showToast("Не удалось подготовить сервер", "error");
      console.error(error);
      return false;
    } finally {
      isCreatingServer.value = false;
    }
  }

  async function deleteServer(serverId: string) {
    const { showToast } = useToasts();
    const server = servers.value.find((item) => item.id === serverId);
    const confirmed = window.confirm(
      `Удалить ${server?.name ?? "сервер"} из панели? Сервис будет остановлен и отключен от автозапуска, файлы мира останутся на диске.`,
    );
    if (!confirmed) {
      return;
    }

    try {
      await serverRequests.delete(serverId);
      await loadDashboard();
      showToast(`${server?.name ?? "Сервер"} удалён из панели`, "success");
    } catch (error) {
      showToast("Не удалось удалить сервер через agent", "error");
      console.error(error);
    }
  }

  return {
    loadDashboard,
    loadServerLogs,
    refreshServerLogs,
    loadServerCrashReports,
    loadServerConfig,
    saveServerConfig,
    runServerAction,
    createServer,
    deleteServer,
  };
}
