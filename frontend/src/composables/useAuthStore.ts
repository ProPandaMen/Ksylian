import { computed, ref } from "vue";
import { requestJson } from "../services/api";
import type { AuthSessionPayload, AuthStatusPayload, AuthUser, ThemeName } from "../types";
import { useToasts } from "./useToasts";

const TOKEN_KEY = "ksylian_auth_token";

const user = ref<AuthUser | null>(null);
const authStatus = ref<AuthStatusPayload>({
  has_users: true,
  bootstrap_required: false,
});
const isAuthLoading = ref(false);

export const themes: Array<{ id: ThemeName; label: string }> = [
  { id: "pink", label: "Розовая" },
  { id: "black", label: "Чёрная" },
  { id: "white", label: "Белая" },
  { id: "green", label: "Зелёная" },
];

function token() {
  return window.localStorage.getItem(TOKEN_KEY);
}

function applyTheme(theme: ThemeName = "pink") {
  document.body.dataset.theme = theme;
}

function setSession(payload: AuthSessionPayload) {
  window.localStorage.setItem(TOKEN_KEY, payload.token);
  user.value = payload.user;
  applyTheme(payload.user.theme);
}

function clearSession() {
  window.localStorage.removeItem(TOKEN_KEY);
  user.value = null;
  applyTheme("pink");
}

async function loadAuthStatus() {
  authStatus.value = await requestJson<AuthStatusPayload>("/api/auth/status");
  return authStatus.value;
}

async function loadMe() {
  if (!token()) {
    user.value = null;
    applyTheme("pink");
    return null;
  }

  try {
    user.value = await requestJson<AuthUser>("/api/auth/me");
    applyTheme(user.value.theme);
    return user.value;
  } catch {
    clearSession();
    return null;
  }
}

async function bootstrapAdmin(payload: { username: string; password: string; display_name: string; theme: ThemeName }) {
  const session = await requestJson<AuthSessionPayload>("/api/auth/bootstrap", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setSession(session);
  return session.user;
}

async function login(payload: { username: string; password: string }) {
  const session = await requestJson<AuthSessionPayload>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setSession(session);
  return session.user;
}

async function registerInvite(payload: {
  token: string;
  username: string;
  password: string;
  display_name: string;
  theme: ThemeName;
}) {
  const session = await requestJson<AuthSessionPayload>("/api/auth/register-invite", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setSession(session);
  return session.user;
}

async function updateTheme(theme: ThemeName) {
  const { showToast } = useToasts();
  try {
    user.value = await requestJson<AuthUser>("/api/auth/me/theme", {
      method: "PUT",
      body: JSON.stringify({ theme }),
    });
    applyTheme(user.value.theme);
    showToast("Цветовая схема сохранена", "success");
  } catch (error) {
    showToast("Не удалось сохранить тему", "error");
    console.error(error);
  }
}

async function initializeAuth() {
  isAuthLoading.value = true;
  try {
    await loadAuthStatus();
    await loadMe();
  } finally {
    isAuthLoading.value = false;
  }
}

export function useAuthStore() {
  return {
    user,
    authStatus,
    isAuthLoading,
    isAuthenticated: computed(() => Boolean(user.value)),
    isAdmin: computed(() => user.value?.role === "admin"),
    token,
    applyTheme,
    initializeAuth,
    loadAuthStatus,
    loadMe,
    bootstrapAdmin,
    login,
    registerInvite,
    updateTheme,
    clearSession,
  };
}
