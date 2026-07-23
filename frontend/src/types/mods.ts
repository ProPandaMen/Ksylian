export interface ModItem {
  id: string;
  name: string;
  status: string;
  tag: "required" | "update" | "review";
}

export interface ModDependency {
  id: string;
  version: string;
  required: boolean;
}

export interface InstalledModItem {
  id: string;
  name: string;
  version: string;
  loader: "fabric" | "forge" | "neoforge" | "unknown";
  side: "client" | "server" | "both" | "unknown";
  filename: string;
  path: string;
  size: string;
  enabled: boolean;
  sha1: string;
  sha256: string;
  sha512: string;
  dependencies: ModDependency[];
  duplicate: boolean;
  multiple_versions: boolean;
  warnings: string[];
}

export interface ModInstallRequest {
  filename: string;
  content: string;
  encoding: "base64";
  pinned: boolean;
  release_channel: "release" | "beta" | "alpha";
}
