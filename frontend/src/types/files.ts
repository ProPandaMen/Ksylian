export interface FileItem {
  name: string;
  meta: string;
  kind: "folder" | "file";
}

export interface FileEntry {
  name: string;
  path: string;
  kind: "folder" | "file";
  size: string;
  modified: string;
  quick: string;
}

export interface FileListPayload {
  path: string;
  entries: FileEntry[];
}

export interface FileContentPayload {
  path: string;
  name: string;
  content: string;
  encoding: "text" | "base64";
  syntax: "json" | "yaml" | "toml" | "properties" | "text" | "binary";
}

export interface FileSearchResult {
  path: string;
  line: number;
  preview: string;
  syntax: "json" | "yaml" | "toml" | "properties" | "text" | "binary";
}

export interface FileWriteRequest {
  path: string;
  content: string;
  encoding: "text" | "base64";
}

export interface FileOperationRequest {
  action: "mkdir" | "delete" | "move" | "rename" | "extract";
  path: string;
  target_path?: string;
}
