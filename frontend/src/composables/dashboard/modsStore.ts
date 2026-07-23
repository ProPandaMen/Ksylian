import { useToasts } from "../useToasts";
import type { ModInstallRequest } from "../../types";
import { useModRequests } from "./mods";
import { isModLoading, selectedServerId, selectedServerMods } from "./state";

const modRequests = useModRequests();

async function readFileAsBase64(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || "").split(",", 2)[1] || "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export function useModDashboardActions() {
  async function loadServerMods(serverId = selectedServerId.value) {
    const { showToast } = useToasts();
    if (!serverId) {
      selectedServerMods.value = [];
      return;
    }
    isModLoading.value = true;
    try {
      selectedServerMods.value = await modRequests.list(serverId);
    } catch (error) {
      showToast("Не удалось просканировать моды", "error");
      selectedServerMods.value = [];
      console.error(error);
    } finally {
      isModLoading.value = false;
    }
  }

  async function runModAction(action: "delete" | "disable" | "enable" | "pin", path: string, serverId = selectedServerId.value) {
    const { showToast } = useToasts();
    if (!serverId) {
      return;
    }
    try {
      await modRequests.action(serverId, { action, path });
      await loadServerMods(serverId);
      showToast("Операция с модом выполнена", "success");
    } catch (error) {
      showToast("Не удалось выполнить операцию с модом", "error");
      console.error(error);
    }
  }

  async function installServerMods(modFiles: File[], serverId = selectedServerId.value) {
    const { showToast } = useToasts();
    if (!serverId || !modFiles.length) {
      return;
    }
    isModLoading.value = true;
    try {
      const items: ModInstallRequest[] = await Promise.all(modFiles.map(async (file) => ({
        filename: file.name,
        content: await readFileAsBase64(file),
        encoding: "base64",
        pinned: false,
        release_channel: "release",
      })));
      await modRequests.bulkInstall(serverId, items);
      await loadServerMods(serverId);
      showToast("Моды установлены", "success");
    } catch (error) {
      showToast("Не удалось установить моды", "error");
      console.error(error);
    } finally {
      isModLoading.value = false;
    }
  }

  async function updateServerMod(path: string, file: File, serverId = selectedServerId.value) {
    const { showToast } = useToasts();
    if (!serverId) {
      return;
    }
    isModLoading.value = true;
    try {
      await modRequests.action(serverId, {
        action: "update",
        path,
        filename: file.name,
        content: await readFileAsBase64(file),
        release_channel: "release",
      });
      await loadServerMods(serverId);
      showToast("Мод обновлён", "success");
    } catch (error) {
      showToast("Не удалось обновить мод", "error");
      console.error(error);
    } finally {
      isModLoading.value = false;
    }
  }

  async function bulkUpdateServerMods(modFiles: File[], serverId = selectedServerId.value) {
    const { showToast } = useToasts();
    if (!serverId || !modFiles.length) {
      return;
    }
    const installedByName = new Map(
      selectedServerMods.value.map((mod) => [mod.filename.replace(/\.disabled$/i, ""), mod.path]),
    );
    const matchedFiles = modFiles.filter((file) => installedByName.has(file.name));
    if (!matchedFiles.length) {
      showToast("Не найдено совпадений с установленными модами", "error");
      return;
    }
    isModLoading.value = true;
    try {
      await modRequests.bulkAction(serverId, "update", await Promise.all(matchedFiles.map(async (file) => ({
        action: "update",
        path: installedByName.get(file.name) || "",
        filename: file.name,
        content: await readFileAsBase64(file),
        release_channel: "release",
      }))));
      await loadServerMods(serverId);
      showToast(`Моды обновлены: ${matchedFiles.length}`, "success");
    } catch (error) {
      showToast("Не удалось массово обновить моды", "error");
      console.error(error);
    } finally {
      isModLoading.value = false;
    }
  }

  async function runBulkModAction(action: "delete" | "disable" | "enable" | "pin", serverId = selectedServerId.value) {
    const { showToast } = useToasts();
    if (!serverId || !selectedServerMods.value.length) {
      return;
    }
    try {
      await modRequests.bulkAction(serverId, action, selectedServerMods.value.map((mod) => ({ action, path: mod.path })));
      await loadServerMods(serverId);
      showToast("Массовая операция выполнена", "success");
    } catch (error) {
      showToast("Не удалось выполнить массовую операцию", "error");
      console.error(error);
    }
  }

  return { loadServerMods, runModAction, installServerMods, updateServerMod, bulkUpdateServerMods, runBulkModAction };
}
