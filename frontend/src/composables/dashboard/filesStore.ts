import { useToasts } from "../useToasts";
import type { FileOperationRequest, FileWriteRequest } from "../../types";
import { useFileRequests } from "./files";
import {
  isFileLoading,
  isFileSaving,
  selectedServerFileContent,
  selectedServerFilePath,
  selectedServerFileSearchResults,
  selectedServerFiles,
  selectedServerId,
} from "./state";

const fileRequests = useFileRequests();

export function useFileDashboardActions() {
  async function loadServerFiles(serverId = selectedServerId.value, path = selectedServerFilePath.value) {
    const { showToast } = useToasts();
    if (!serverId) {
      selectedServerFiles.value = [];
      return;
    }

    selectedServerId.value = serverId;
    isFileLoading.value = true;
    try {
      const payload = await fileRequests.list(serverId, path);
      selectedServerFilePath.value = payload.path;
      selectedServerFiles.value = payload.entries;
    } catch (error) {
      showToast("Не удалось загрузить файлы сервера", "error");
      selectedServerFiles.value = [];
      console.error(error);
    } finally {
      isFileLoading.value = false;
    }
  }

  async function openServerFile(path: string, serverId = selectedServerId.value) {
    const { showToast } = useToasts();
    if (!serverId) {
      return;
    }
    isFileLoading.value = true;
    try {
      selectedServerFileContent.value = await fileRequests.content(serverId, path);
    } catch (error) {
      showToast("Не удалось открыть файл", "error");
      console.error(error);
    } finally {
      isFileLoading.value = false;
    }
  }

  async function searchServerFiles(query: string, serverId = selectedServerId.value, path = selectedServerFilePath.value) {
    const { showToast } = useToasts();
    if (!serverId || query.trim().length < 2) {
      selectedServerFileSearchResults.value = [];
      return;
    }
    isFileLoading.value = true;
    try {
      selectedServerFileSearchResults.value = await fileRequests.search(serverId, query, path);
    } catch (error) {
      showToast("Не удалось выполнить поиск по файлам", "error");
      selectedServerFileSearchResults.value = [];
      console.error(error);
    } finally {
      isFileLoading.value = false;
    }
  }

  async function saveServerFile(content: string, serverId = selectedServerId.value) {
    const { showToast } = useToasts();
    const file = selectedServerFileContent.value;
    if (!serverId || !file || file.encoding !== "text") {
      return;
    }
    isFileSaving.value = true;
    try {
      const payload: FileWriteRequest = { path: file.path, content, encoding: "text" };
      await fileRequests.write(serverId, payload);
      selectedServerFileContent.value = { ...file, content };
      await loadServerFiles(serverId);
      showToast("Файл сохранён", "success");
    } catch (error) {
      showToast("Не удалось сохранить файл", "error");
      console.error(error);
    } finally {
      isFileSaving.value = false;
    }
  }

  async function uploadServerFile(file: File, serverId = selectedServerId.value, path = selectedServerFilePath.value) {
    const { showToast } = useToasts();
    if (!serverId) {
      return;
    }
    isFileSaving.value = true;
    try {
      const content = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          const result = String(reader.result || "");
          resolve(result.split(",", 2)[1] || "");
        };
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
      });
      const payload: FileWriteRequest = {
        path: [path, file.name].filter(Boolean).join("/"),
        content,
        encoding: "base64",
      };
      await fileRequests.write(serverId, payload);
      await loadServerFiles(serverId, path);
      showToast("Файл загружен", "success");
    } catch (error) {
      showToast("Не удалось загрузить файл", "error");
      console.error(error);
    } finally {
      isFileSaving.value = false;
    }
  }

  async function runFileAction(action: FileOperationRequest["action"], path: string, targetPath = "", serverId = selectedServerId.value) {
    const { showToast } = useToasts();
    if (!serverId) {
      return;
    }
    try {
      await fileRequests.action(serverId, { action, path, target_path: targetPath });
      await loadServerFiles(serverId);
      showToast("Файловая операция выполнена", "success");
    } catch (error) {
      showToast("Не удалось выполнить файловую операцию", "error");
      console.error(error);
    }
  }

  return { loadServerFiles, openServerFile, searchServerFiles, saveServerFile, uploadServerFile, runFileAction };
}
