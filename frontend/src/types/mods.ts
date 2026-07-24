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
  source?: "curseforge" | "manual" | "imported" | "unknown";
  project_id?: string;
  file_id?: string;
}

export interface CurseForgeProject {
  id: number;
  name: string;
  slug: string;
  summary: string;
  type: "mods" | "modpacks";
  downloads: number;
  date_modified: string;
  icon_url: string;
  website_url: string;
  latest_file_id?: number | null;
  game_versions: string[];
  loaders: string[];
}

export interface CurseForgeSearchPayload {
  items: CurseForgeProject[];
  total_count: number;
  has_api_key: boolean;
}

export interface CurseForgeFileDependency {
  mod_id: number;
  relation_type: number;
  required: boolean;
}

export interface CurseForgeFile {
  id: number;
  mod_id: number;
  display_name: string;
  file_name: string;
  download_url: string;
  release_type: "release" | "beta" | "alpha" | "unknown";
  game_versions: string[];
  dependencies: CurseForgeFileDependency[];
  file_date: string;
  file_length: number;
  hashes: Record<string, string>;
  restricted: boolean;
}

export interface CurseForgeFilesPayload {
  items: CurseForgeFile[];
  has_api_key: boolean;
}

export interface CurseForgeModpackSummary {
  mod_count: number;
  available: boolean;
}

export interface CurseForgeInstallResult {
  ok: boolean;
  message: string;
  installed: InstalledModItem[];
  skipped: string[];
}

export interface BuildManifestMod {
  id: string;
  name: string;
  version: string;
  loader: "fabric" | "forge" | "neoforge" | "unknown";
  side: "client" | "server" | "both" | "unknown";
  filename: string;
  path: string;
  sha256: string;
  source: "curseforge" | "manual" | "imported" | "unknown";
  project_id: string;
  file_id: string;
  installed_at: string;
  dependencies: ModDependency[];
}

export interface BuildManifest {
  schema: number;
  server_id: string;
  server_name: string;
  minecraft_version: string;
  loader: "legacy" | "vanilla" | "paper" | "purpur" | "fabric" | "forge" | "neoforge";
  loader_version: string;
  java_runtime: string;
  generated_at: string;
  mods: BuildManifestMod[];
  manual_changes: string[];
}

export interface BuildManifestDiff {
  added: BuildManifestMod[];
  removed: BuildManifestMod[];
  changed: Array<{ before: BuildManifestMod; after: BuildManifestMod }>;
}

export interface ModUpdatePlan {
  server_id: string;
  created_at: string;
  items: Array<{ current: BuildManifestMod; candidate: BuildManifestMod; action: "update" | "keep"; reason: string; content: string; encoding: "base64" }>;
  diff: BuildManifestDiff;
  warnings: string[];
}

export interface SafeUpdateResult {
  ok: boolean;
  message: string;
  plan: ModUpdatePlan;
  backup_id: string;
  test_instance_path: string;
  log_findings: string[];
}
