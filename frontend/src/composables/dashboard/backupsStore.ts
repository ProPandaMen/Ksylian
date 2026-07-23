import { useToasts } from "../useToasts";
import type { BackupRequest } from "../../types";
import { useBackupRequests } from "./backups";
import { backups, selectedServerId } from "./state";

const backupRequests = useBackupRequests();

export function useBackupDashboardActions() {
  async function createServerBackup(serverId = selectedServerId.value, payload?: BackupRequest) {
    const { showToast } = useToasts();
    if (!serverId) {
      return;
    }
    try {
      const backup = await backupRequests.create(serverId, payload ?? {
        mode: "live",
        parts: ["world", "mods", "config", "root"],
        description: "Manual backup",
      });
      backups.value = [backup, ...backups.value.filter((item) => item.id !== backup.id)];
      showToast("Бэкап создан", "success");
    } catch (error) {
      showToast("Не удалось создать бэкап", "error");
      console.error(error);
    }
  }

  return { createServerBackup };
}
