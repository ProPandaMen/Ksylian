<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Copy, RefreshCw, RotateCcw, ShieldCheck, UserCheck, UserPlus, UserX } from "@lucide/vue";
import { requestJson } from "../services/api";
import { useAuthStore } from "../composables/useAuthStore";
import type { AuthUser, UserInvite } from "../types";
import { useToasts } from "../composables/useToasts";

const auth = useAuthStore();
const users = ref<AuthUser[]>([]);
const invites = ref<UserInvite[]>([]);
const ttlHours = ref(24);
const inviteRole = ref<"member" | "admin">("member");
const isLoading = ref(false);
const isCreating = ref(false);
const busyUserId = ref("");
const busyInviteId = ref("");
const lastInviteUrl = ref("");
const { showToast } = useToasts();

const ttlOptions = [
  { value: 6, label: "6ч" },
  { value: 24, label: "24ч" },
  { value: 72, label: "3д" },
  { value: 168, label: "7д" },
  { value: 336, label: "14д" },
];

const roleOptions: Array<{ value: "member" | "admin"; label: string }> = [
  { value: "member", label: "Участник" },
  { value: "admin", label: "Админ" },
];

const activeUsers = computed(() => users.value.filter((item) => !item.disabled_at));
const adminUsers = computed(() => activeUsers.value.filter((item) => item.role === "admin"));
const inactiveUsers = computed(() => users.value.filter((item) => item.disabled_at));
const activeInvites = computed(() => invites.value.filter((invite) => inviteState(invite) === "active"));
const archivedInvites = computed(() => invites.value.filter((invite) => inviteState(invite) !== "active"));

function inviteUrl(token: string) {
  return `${window.location.origin}/invite?token=${encodeURIComponent(token)}`;
}

function isExpired(invite: UserInvite) {
  return Boolean(invite.expires_at && new Date(invite.expires_at).getTime() < Date.now());
}

function inviteState(invite: UserInvite) {
  if (invite.revoked_at) {
    return "revoked";
  }
  if (invite.used_at) {
    return "used";
  }
  if (isExpired(invite)) {
    return "expired";
  }
  return "active";
}

function inviteStateLabel(invite: UserInvite) {
  const state = inviteState(invite);
  if (state === "active") {
    return "Активно";
  }
  if (state === "used") {
    return "Использовано";
  }
  if (state === "revoked") {
    return "Отозвано";
  }
  return "Истекло";
}

function roleLabel(role: AuthUser["role"] | UserInvite["role"]) {
  return role === "admin" ? "Админ" : "Участник";
}

function themeLabel(theme: AuthUser["theme"]) {
  const labels: Record<AuthUser["theme"], string> = {
    pink: "Pink",
    black: "Black",
    white: "White",
    green: "Green",
  };
  return labels[theme] || theme;
}

function userInitials(user: AuthUser) {
  const source = user.display_name || user.username;
  return source
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || user.username.slice(0, 2).toUpperCase();
}

function canDemote(user: AuthUser) {
  return !(user.role === "admin" && !user.disabled_at && adminUsers.value.length <= 1);
}

function canDeactivate(user: AuthUser) {
  if (user.id === auth.user.value?.id) {
    return false;
  }
  return !(user.role === "admin" && !user.disabled_at && adminUsers.value.length <= 1);
}

async function copyInvite(url: string) {
  await navigator.clipboard.writeText(url);
  showToast("Ссылка приглашения скопирована", "success");
}

async function loadUsers() {
  isLoading.value = true;
  try {
    const [userItems, inviteItems] = await Promise.all([
      requestJson<AuthUser[]>("/api/users"),
      requestJson<UserInvite[]>("/api/users/invites"),
    ]);
    users.value = userItems;
    invites.value = inviteItems;
  } catch (error) {
    showToast("Не удалось загрузить пользователей Ksylian", "error");
    console.error(error);
  } finally {
    isLoading.value = false;
  }
}

async function createInvite() {
  isCreating.value = true;
  try {
    const invite = await requestJson<UserInvite>("/api/users/invites", {
      method: "POST",
      body: JSON.stringify({ role: inviteRole.value, ttl_hours: ttlHours.value }),
    });
    invites.value = [invite, ...invites.value];
    lastInviteUrl.value = inviteUrl(invite.token);
    await copyInvite(lastInviteUrl.value);
  } catch (error) {
    showToast("Не удалось создать приглашение", "error");
    console.error(error);
  } finally {
    isCreating.value = false;
  }
}

async function changeRole(user: AuthUser, role: AuthUser["role"]) {
  if (user.role === role || busyUserId.value) {
    return;
  }
  busyUserId.value = user.id;
  try {
    const updated = await requestJson<AuthUser>(`/api/users/${user.id}`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    });
    users.value = users.value.map((item) => (item.id === updated.id ? updated : item));
    showToast("Роль пользователя обновлена", "success");
  } catch (error) {
    showToast("Не удалось обновить роль", "error");
    console.error(error);
  } finally {
    busyUserId.value = "";
  }
}

async function deactivateUser(user: AuthUser) {
  if (!canDeactivate(user) || busyUserId.value) {
    return;
  }
  busyUserId.value = user.id;
  try {
    const updated = await requestJson<AuthUser>(`/api/users/${user.id}/deactivate`, { method: "POST" });
    users.value = users.value.map((item) => (item.id === updated.id ? updated : item));
    showToast("Пользователь отключён", "success");
  } catch (error) {
    showToast("Не удалось отключить пользователя", "error");
    console.error(error);
  } finally {
    busyUserId.value = "";
  }
}

async function restoreUser(user: AuthUser) {
  if (busyUserId.value) {
    return;
  }
  busyUserId.value = user.id;
  try {
    const updated = await requestJson<AuthUser>(`/api/users/${user.id}/restore`, { method: "POST" });
    users.value = users.value.map((item) => (item.id === updated.id ? updated : item));
    showToast("Пользователь восстановлен", "success");
  } catch (error) {
    showToast("Не удалось восстановить пользователя", "error");
    console.error(error);
  } finally {
    busyUserId.value = "";
  }
}

async function revokeInvite(invite: UserInvite) {
  if (busyInviteId.value || inviteState(invite) !== "active") {
    return;
  }
  busyInviteId.value = invite.id;
  try {
    const updated = await requestJson<UserInvite>(`/api/users/invites/${invite.id}/revoke`, { method: "POST" });
    invites.value = invites.value.map((item) => (item.id === updated.id ? updated : item));
    showToast("Приглашение отозвано", "success");
  } catch (error) {
    showToast("Не удалось отозвать приглашение", "error");
    console.error(error);
  } finally {
    busyInviteId.value = "";
  }
}

onMounted(loadUsers);
</script>

<template>
  <section class="users-page">
    <section class="users-hero panel">
      <div>
        <p class="eyebrow">ksylian accounts</p>
        <h2>Пользователи панели</h2>
      </div>
      <div class="users-hero-actions">
        <button class="ghost-button compact" type="button" :aria-busy="isLoading" @click="loadUsers">
          <RefreshCw :class="{ spinning: isLoading }" :size="16" />
          <span>Обновить</span>
        </button>
        <button class="primary-button compact" type="button" :disabled="isCreating" @click="createInvite">
          <UserPlus :size="16" />
          <span>{{ isCreating ? 'Создаю' : 'Создать приглашение' }}</span>
        </button>
      </div>
    </section>

    <section class="users-summary-grid" aria-label="Сводка пользователей">
      <article class="users-summary-card">
        <UserCheck :size="18" />
        <span>Всего</span>
        <strong>{{ users.length }}</strong>
        <small>аккаунтов Ksylian</small>
      </article>
      <article class="users-summary-card ok">
        <ShieldCheck :size="18" />
        <span>Активные</span>
        <strong>{{ activeUsers.length }}</strong>
        <small>{{ inactiveUsers.length }} отключено</small>
      </article>
      <article class="users-summary-card">
        <ShieldCheck :size="18" />
        <span>Админы</span>
        <strong>{{ adminUsers.length }}</strong>
        <small>с активным доступом</small>
      </article>
      <article class="users-summary-card">
        <UserPlus :size="18" />
        <span>Инвайты</span>
        <strong>{{ activeInvites.length }}</strong>
        <small>активных ссылок</small>
      </article>
    </section>

    <section class="users-section users-directory" aria-label="Пользователи Ksylian">
      <div class="users-section-head">
        <div>
          <p class="eyebrow">directory</p>
          <h3>Аккаунты</h3>
        </div>
        <span class="users-status">{{ activeUsers.length }} активных</span>
      </div>

      <div class="user-list">
        <article v-for="item in users" :key="item.id" class="user-row user-account-card" :class="{ disabled: item.disabled_at }">
          <div class="user-avatar" aria-hidden="true">{{ userInitials(item) }}</div>
          <div class="user-main">
            <strong>{{ item.display_name }}</strong>
            <span>@{{ item.username }} · создан {{ item.created_at || 'n/a' }}</span>
            <small>{{ roleLabel(item.role) }} · тема {{ themeLabel(item.theme) }}</small>
          </div>
          <div class="user-meta">
            <span class="users-status" :class="{ connected: !item.disabled_at, danger: item.disabled_at }">
              {{ item.disabled_at ? 'Отключён' : 'Активен' }}
            </span>
            <span v-if="item.id === auth.user.value?.id" class="users-status">Вы</span>
          </div>
          <div class="users-actions account-actions">
            <select
              :value="item.role"
              :disabled="busyUserId === item.id || (item.role === 'admin' && !canDemote(item))"
              @change="changeRole(item, ($event.target as HTMLSelectElement).value as AuthUser['role'])"
            >
              <option value="member">Участник</option>
              <option value="admin">Админ</option>
            </select>
            <button
              v-if="item.disabled_at"
              class="ghost-button compact"
              type="button"
              :disabled="busyUserId === item.id"
              @click="restoreUser(item)"
            >
              <RotateCcw :size="16" />
              <span>Восстановить</span>
            </button>
            <button
              v-else
              class="ghost-button compact danger"
              type="button"
              :disabled="busyUserId === item.id || !canDeactivate(item)"
              @click="deactivateUser(item)"
            >
              <UserX :size="16" />
              <span>Отключить</span>
            </button>
          </div>
        </article>
        <article v-if="!users.length && !isLoading" class="user-row muted">
          <div>
            <strong>Пользователей пока нет</strong>
            <span>После bootstrap здесь появится первый администратор.</span>
          </div>
        </article>
      </div>
    </section>

    <section class="users-section users-invites" aria-label="Приглашения пользователей">
      <div class="users-section-head">
        <div>
          <p class="eyebrow">invites</p>
          <h3>Приглашения</h3>
        </div>
      </div>

      <div class="invite-builder">
        <div>
          <span>Срок ссылки</span>
          <div class="segmented-control users-segmented" aria-label="Срок приглашения">
            <button v-for="option in ttlOptions" :key="option.value" type="button" :class="{ active: ttlHours === option.value }" @click="ttlHours = option.value">
              {{ option.label }}
            </button>
          </div>
        </div>
        <div>
          <span>Роль</span>
          <div class="segmented-control users-segmented" aria-label="Роль приглашения">
            <button v-for="option in roleOptions" :key="option.value" type="button" :class="{ active: inviteRole === option.value }" @click="inviteRole = option.value">
              {{ option.label }}
            </button>
          </div>
        </div>
      </div>

      <div class="users-subhead">
        <span>Активные приглашения</span>
      </div>
      <div class="user-list">
        <article
          v-for="invite in activeInvites"
          :key="invite.id"
          class="user-row invite-row"
          :class="{ highlighted: lastInviteUrl === inviteUrl(invite.token) }"
        >
          <div>
            <strong>{{ roleLabel(invite.role) }}</strong>
            <span>Действует до {{ invite.expires_at }}</span>
          </div>
          <div class="users-actions">
            <button class="ghost-button compact" type="button" @click="copyInvite(inviteUrl(invite.token))">
              <Copy :size="16" />
              <span>Скопировать</span>
            </button>
            <button class="ghost-button compact danger" type="button" :disabled="busyInviteId === invite.id" @click="revokeInvite(invite)">
              <UserX :size="16" />
              <span>Отозвать</span>
            </button>
          </div>
        </article>
        <article v-if="!activeInvites.length" class="user-row muted">
          <div>
            <strong>Активных ссылок нет</strong>
            <span>Создай приглашение, когда понадобится добавить пользователя.</span>
          </div>
        </article>
      </div>

      <details v-if="archivedInvites.length" class="users-archive">
        <summary>Архив приглашений · {{ archivedInvites.length }}</summary>
        <div class="user-list">
          <article v-for="invite in archivedInvites" :key="invite.id" class="user-row muted invite-row">
            <div>
              <strong>{{ roleLabel(invite.role) }}</strong>
              <span>{{ inviteStateLabel(invite) }} · до {{ invite.expires_at }}</span>
            </div>
            <span class="users-status">{{ inviteStateLabel(invite) }}</span>
          </article>
        </div>
      </details>
    </section>
  </section>
</template>
