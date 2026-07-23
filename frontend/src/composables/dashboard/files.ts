import { requestJson } from "../../services/api";
import type { FileContentPayload, FileEntry, FileOperationRequest, FileSearchResult, FileWriteRequest } from "../../types";

export function useFileRequests() {
  return {
    list: (serverId: string, path: string) => {
      const query = new URLSearchParams({ path });
      return requestJson<{ path: string; entries: FileEntry[] }>(`/api/servers/${serverId}/files?${query}`);
    },
    content: (serverId: string, path: string) => {
      const query = new URLSearchParams({ path });
      return requestJson<FileContentPayload>(`/api/servers/${serverId}/files/content?${query}`);
    },
    search: (serverId: string, queryText: string, path: string) => {
      const params = new URLSearchParams({ query: queryText.trim(), path });
      return requestJson<FileSearchResult[]>(`/api/servers/${serverId}/files/search?${params}`);
    },
    write: (serverId: string, payload: FileWriteRequest) => requestJson<FileEntry>(`/api/servers/${serverId}/files`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
    action: (serverId: string, payload: FileOperationRequest) => requestJson(`/api/servers/${serverId}/files/actions`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  };
}
