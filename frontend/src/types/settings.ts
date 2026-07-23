import type { ThemeName } from "./app";
import type { AgentStatus } from "./server";

export interface SettingsPayload {
  has_curseforge_api_key: boolean;
  curseforge_api_key_mask: string;
  curseforge_api_key_status: "missing" | "valid" | "invalid" | "unchecked";
  curseforge_api_key_message: string;
  agent: AgentStatus;
}

export interface AuthStatusPayload {
  has_users: boolean;
  bootstrap_required: boolean;
}

export interface AuthUser {
  id: string;
  username: string;
  display_name: string;
  role: "admin" | "member";
  theme: ThemeName;
  created_at: string;
}

export interface AuthSessionPayload {
  token: string;
  user: AuthUser;
}

export interface UserInvite {
  id: string;
  token: string;
  role: "admin" | "member";
  created_at: string;
  expires_at: string;
  used_at: string;
  invited_by: string;
}

export interface UpdateStatusPayload {
  current_version: string;
  current_sha: string;
  latest_version: string;
  latest_sha: string;
  update_available: boolean;
  checked_at: string;
  release_url: string;
  notes: string;
  can_update: boolean;
  updater_status: "ready" | "agent_unavailable" | "not_configured" | "unknown";
}

export interface ApplyUpdateResult {
  ok: boolean;
  message: string;
  target_version: string;
}
