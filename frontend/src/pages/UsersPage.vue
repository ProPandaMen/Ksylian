<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Ban, Copy, Crown, MessageSquare, RefreshCw, ShieldCheck, UserPlus, UserX } from "@lucide/vue";
import { requestJson } from "../services/api";
import { useDashboardStore } from "../composables/useDashboardStore";
import type { AuthUser, GamePlayer, PlayerActionRequest, PlayerListPayload, UserInvite } from "../types";
import { useToasts } from "../composables/useToasts";

const dashboard = useDashboardStore();
const users = ref<AuthUser[]>([]);
const invites = ref<UserInvite[]>([]);
const playerPayload = ref<PlayerListPayload>({ online: [], known: [], history: [], rcon_available: false, game_time: "" });
const selectedServerId = ref("");
const selectedPlayer = ref("");
const playerValue = ref("");
const playerReason = ref("");
const ttlHours = ref(24);
const isLoading = ref(false);
const isPlayersLoading = ref(false);
const isCreating = ref(false);
const isPlayerActionRunning = ref(false);
const lastInviteUrl = ref("");
const { showToast } = useToasts();

const activeInvites = computed(() => invites.value.filter((invite) => !invite.used_at));
const selectedPlayerItem = computed(() => playerPayload.value.known.find((item) => item.name === selectedPlayer.value));

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
    if (!dashboard.isDashboardLoaded.value) {
      await dashboard.loadDashboard();
    }
    selectedServerId.value = selectedServerId.value || dashboard.servers.value[0]?.id || "";
    users.value = await requestJson<AuthUser[]>("/api/users");
    invites.value = await requestJson<UserInvite[]>("/api/users/invites");
    await loadPlayers();
  } catch (error) {
    showToast("Не удалось загрузить пользователей", "error");
    console.error(error);
  } finally {
    isLoading.value = false;
  }
}

async function loadPlayers() {
  if (!selectedServerId.value) {
    playerPayload.value = { online: [], known: [], history: [], rcon_available: false, game_time: "" };
    return;
  }
  isPlayersLoading.value = true;
  try {
    playerPayload.value = await requestJson<PlayerListPayload>(`/api/servers/${selectedServerId.value}/players`);
    selectedPlayer.value = selectedPlayer.value || playerPayload.value.online[0]?.name || playerPayload.value.known[0]?.name || "";
  } catch (error) {
    showToast("Не удалось загрузить игроков сервера", "error");
    console.error(error);
  } finally {
    isPlayersLoading.value = false;
  }
}

async function runPlayerAction(action: PlayerActionRequest["action"], player = selectedPlayer.value) {
  if (!selectedServerId.value || !player) {
    return;
  }
  isPlayerActionRunning.value = true;
  try {
    const result = await requestJson<{ players: PlayerListPayload; message: string }>(`/api/servers/${selectedServerId.value}/players/actions`, {
      method: "POST",
      body: JSON.stringify({
        action,
        player,
        value: playerValue.value,
        reason: playerReason.value,
      }),
    });
    playerPayload.value = result.players;
    showToast(result.message, "success");
  } catch (error) {
    showToast("Не удалось выполнить действие игрока", "error");
    console.error(error);
  } finally {
    isPlayerActionRunning.value = false;
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
    <section class="users-section" aria-label="Игроки Minecraft">
      <div class="users-section-head">
        <div>
          <p class="eyebrow">minecraft</p>
          <h3>Игроки сервера</h3>
        </div>
        <span class="users-status" :class="{ connected: playerPayload.rcon_available }">
          {{ playerPayload.rcon_available ? 'RCON доступен' : 'RCON недоступен' }}
        </span>
      </div>

      <div class="users-control-row">
        <label>
          <span>Сервер</span>
          <select v-model="selectedServerId" @change="loadPlayers">
            <option v-for="server in dashboard.servers.value" :key="server.id" :value="server.id">{{ server.name }}</option>
          </select>
        </label>
        <label>
          <span>Игрок</span>
          <input v-model="selectedPlayer" type="text" placeholder="Nickname" />
        </label>
        <div class="users-actions">
          <button class="ghost-button compact" type="button" :aria-busy="isPlayersLoading" @click="loadPlayers">
            <RefreshCw :class="{ spinning: isPlayersLoading }" :size="16" />
            <span>Обновить</span>
          </button>
        </div>
      </div>

      <div class="users-control-row">
        <label>
          <span>Сообщение / группа / permission / IP</span>
          <input v-model="playerValue" type="text" placeholder="Например, default или Привет!" />
        </label>
        <label>
          <span>Причина</span>
          <input v-model="playerReason" type="text" placeholder="Для kick/ban" />
        </label>
      </div>

      <div class="users-actions player-actions">
        <button class="ghost-button compact" type="button" :disabled="isPlayerActionRunning" @click="runPlayerAction(selectedPlayerItem?.whitelisted ? 'whitelist_remove' : 'whitelist_add')">
          <ShieldCheck :size="16" />
          <span>{{ selectedPlayerItem?.whitelisted ? 'Убрать whitelist' : 'Whitelist' }}</span>
        </button>
        <button class="ghost-button compact" type="button" :disabled="isPlayerActionRunning" @click="runPlayerAction(selectedPlayerItem?.operator ? 'deop' : 'op')">
          <Crown :size="16" />
          <span>{{ selectedPlayerItem?.operator ? 'Снять OP' : 'OP' }}</span>
        </button>
        <button class="ghost-button compact danger" type="button" :disabled="isPlayerActionRunning" @click="runPlayerAction(selectedPlayerItem?.banned ? 'pardon' : 'ban')">
          <Ban :size="16" />
          <span>{{ selectedPlayerItem?.banned ? 'Pardon' : 'Ban' }}</span>
        </button>
        <button class="ghost-button compact danger" type="button" :disabled="isPlayerActionRunning" @click="runPlayerAction('kick')">
          <UserX :size="16" />
          <span>Kick</span>
        </button>
        <button class="ghost-button compact" type="button" :disabled="isPlayerActionRunning || !playerValue" @click="runPlayerAction('message')">
          <MessageSquare :size="16" />
          <span>Сообщение</span>
        </button>
        <button class="ghost-button compact" type="button" :disabled="isPlayerActionRunning || !playerValue" @click="runPlayerAction('luckperms_group_add')">LP group +</button>
        <button class="ghost-button compact" type="button" :disabled="isPlayerActionRunning || !playerValue" @click="runPlayerAction('luckperms_group_remove')">LP group -</button>
      </div>

      <div class="users-subhead">
        <span>Онлайн {{ playerPayload.online.length }} · gametime {{ playerPayload.game_time || 'n/a' }}</span>
      </div>
      <div class="user-list">
        <article
          v-for="player in playerPayload.known"
          :key="player.uuid || player.name"
          class="user-row"
          :class="{ highlighted: selectedPlayer === player.name }"
          @click="selectedPlayer = player.name"
        >
          <div>
            <strong>{{ player.name }}</strong>
            <span>
              {{ player.online ? 'online' : 'offline' }} · UUID {{ player.uuid || 'unknown' }} · last {{ player.last_seen || 'n/a' }}
            </span>
            <small>
              {{ player.whitelisted ? 'whitelist' : 'no whitelist' }} · {{ player.operator ? 'op' : 'no op' }} · {{ player.banned ? 'banned' : 'not banned' }}
              <template v-if="player.luckperms_groups.length"> · LP {{ player.luckperms_groups.join(', ') }}</template>
            </small>
          </div>
          <span class="users-status" :class="{ connected: player.online }">{{ player.ping || player.game_time || (player.online ? 'online' : 'seen') }}</span>
        </article>
        <article v-if="!playerPayload.known.length" class="user-row muted">
          <div>
            <strong>Игроков пока нет</strong>
            <span>Список собирается из usercache.json, stats и RCON.</span>
          </div>
        </article>
      </div>

      <div class="users-subhead">
        <span>История действий</span>
      </div>
      <div class="user-list compact-history">
        <article v-for="item in playerPayload.history" :key="`${item.at}-${item.player}-${item.action}`" class="user-row">
          <div>
            <strong>{{ item.player }} · {{ item.action }}</strong>
            <span>{{ item.at }}{{ item.detail ? ` · ${item.detail}` : '' }}</span>
          </div>
        </article>
      </div>
    </section>

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
          <button class="ghost-button compact" type="button" :aria-busy="isLoading" @click="loadUsers">
            <RefreshCw :class="{ spinning: isLoading }" :size="16" />
            <span>Обновить</span>
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
