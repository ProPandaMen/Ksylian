<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Copy, RefreshCw, UserPlus } from "@lucide/vue";
import { requestJson } from "../services/api";
import type { AuthUser, UserInvite } from "../types";
import { useToasts } from "../composables/useToasts";

const users = ref<AuthUser[]>([]);
const invites = ref<UserInvite[]>([]);
const ttlHours = ref(24);
const isLoading = ref(false);
const isCreating = ref(false);
const lastInviteUrl = ref("");
const { showToast } = useToasts();

const activeInvites = computed(() => invites.value.filter((invite) => !invite.used_at));

function inviteUrl(token: string) {
  return `${window.location.origin}/invite?token=${encodeURIComponent(token)}`;
}

async function copyInvite(url: string) {
  await navigator.clipboard.writeText(url);
  showToast("Ссылка приглашения скопирована", "success");
}

async function loadUsers() {
  isLoading.value = true;
  try {
    users.value = await requestJson<AuthUser[]>("/api/users");
    invites.value = await requestJson<UserInvite[]>("/api/users/invites");
  } catch (error) {
    showToast("Не удалось загрузить пользователей", "error");
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
      body: JSON.stringify({ role: "member", ttl_hours: ttlHours.value }),
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

onMounted(loadUsers);
</script>

<template>
  <section class="users-page">
    <section class="users-section" aria-label="Приглашения пользователей">
      <div class="users-section-head">
        <h3>Приглашения</h3>
      </div>

      <div class="users-control-row">
        <label>
          <span>Срок ссылки</span>
          <select v-model.number="ttlHours">
            <option :value="6">6 часов</option>
            <option :value="24">24 часа</option>
            <option :value="72">3 дня</option>
            <option :value="168">7 дней</option>
          </select>
        </label>
        <div class="users-actions">
          <button class="ghost-button compact" type="button" @click="loadUsers">
            <RefreshCw :size="16" />
            <span>{{ isLoading ? 'Обновляю' : 'Обновить' }}</span>
          </button>
          <button class="primary-button compact" type="button" :disabled="isCreating" @click="createInvite">
            <UserPlus :size="16" />
            <span>{{ isCreating ? 'Создаю' : 'Создать ссылку' }}</span>
          </button>
        </div>
      </div>

      <div class="users-subhead">
        <span>Активные приглашения</span>
      </div>

      <div class="user-list">
        <article
          v-for="invite in activeInvites"
          :key="invite.id"
          class="user-row"
          :class="{ highlighted: lastInviteUrl === inviteUrl(invite.token) }"
        >
          <div>
            <strong>{{ invite.role === 'admin' ? 'Админ' : 'Участник' }}</strong>
            <span>Действует до {{ invite.expires_at }}</span>
          </div>
          <button class="ghost-button compact" type="button" @click="copyInvite(inviteUrl(invite.token))">
            <Copy :size="16" />
            <span>Скопировать</span>
          </button>
        </article>
        <article v-if="!activeInvites.length" class="user-row muted">
          <div>
            <strong>Активных ссылок нет</strong>
            <span>Создай приглашение, когда понадобится добавить пользователя.</span>
          </div>
        </article>
      </div>
    </section>

    <section class="users-section" aria-label="Пользователи">
      <div class="users-section-head">
        <h3>Пользователи</h3>
      </div>
      <div class="user-list">
        <article v-for="item in users" :key="item.id" class="user-row">
          <div>
            <strong>{{ item.display_name }}</strong>
            <span>@{{ item.username }} · {{ item.role === 'admin' ? 'Админ' : 'Участник' }}</span>
          </div>
          <span class="users-status">{{ item.theme }}</span>
        </article>
      </div>
    </section>
  </section>
</template>
