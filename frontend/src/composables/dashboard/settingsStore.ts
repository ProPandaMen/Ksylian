import { useToasts } from "../useToasts";
import { useSettingsRequests } from "./settings";
import {
  agentStatus,
  curseForgeApiKey,
  isApplyingUpdate,
  isSavingSettings,
  isUpdateLoading,
  settings,
  updateStatus,
} from "./state";

const settingsRequests = useSettingsRequests();

export function useSettingsDashboardActions(callbacks: { loadAgentStatus: () => Promise<void>; loadDashboard: () => Promise<void> }) {
  async function loadSettings() {
    const { showToast } = useToasts();
    try {
      settings.value = await settingsRequests.settings();
      agentStatus.value = settings.value.agent;
    } catch (error) {
      showToast("Не удалось загрузить настройки", "error");
      console.error(error);
    }
  }

  async function loadUpdateStatus() {
    const { showToast } = useToasts();
    isUpdateLoading.value = true;

    try {
      updateStatus.value = await settingsRequests.updateStatus();
    } catch (error) {
      showToast("Не удалось проверить обновления", "error");
      console.error(error);
    } finally {
      isUpdateLoading.value = false;
    }
  }

  async function saveSettings() {
    const { showToast } = useToasts();
    isSavingSettings.value = true;

    try {
      settings.value = await settingsRequests.saveSettings(curseForgeApiKey.value);
      curseForgeApiKey.value = "";
      showToast(
        settings.value.curseforge_api_key_status === "invalid"
          ? "Ключ CurseForge сохранён, но API его отклоняет"
          : settings.value.has_curseforge_api_key
            ? "Ключ CurseForge сохранён"
            : "Ключ CurseForge очищен",
        settings.value.curseforge_api_key_status === "invalid" ? "error" : "success",
      );
    } catch (error) {
      showToast("Не удалось сохранить ключ CurseForge", "error");
      console.error(error);
    } finally {
      isSavingSettings.value = false;
    }
  }

  async function clearCurseForgeKey() {
    curseForgeApiKey.value = "";
    await saveSettings();
  }

  async function restartAgent() {
    const { showToast } = useToasts();
    try {
      agentStatus.value = await settingsRequests.restartAgent();
      settings.value = {
        ...settings.value,
        agent: agentStatus.value,
      };
      showToast("Host Agent перезапускается", "success");
      window.setTimeout(() => {
        callbacks.loadAgentStatus();
        callbacks.loadDashboard();
      }, 1600);
    } catch (error) {
      showToast("Не удалось перезапустить Host Agent из панели", "error");
      console.error(error);
    }
  }

  async function applyUpdate() {
    const { showToast } = useToasts();
    if (!updateStatus.value.latest_version) {
      showToast("Нет доступного release tag для обновления", "error");
      return;
    }

    isApplyingUpdate.value = true;
    try {
      const result = await settingsRequests.applyUpdate(updateStatus.value.latest_version);
      showToast(result.message || `Обновление до ${result.target_version} запущено`, "success");
      await loadUpdateStatus();
    } catch (error) {
      showToast("Не удалось запустить обновление", "error");
      console.error(error);
    } finally {
      isApplyingUpdate.value = false;
    }
  }

  return { loadSettings, loadUpdateStatus, saveSettings, clearCurseForgeKey, restartAgent, applyUpdate };
}
