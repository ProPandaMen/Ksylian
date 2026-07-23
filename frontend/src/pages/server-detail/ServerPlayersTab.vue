<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Ban, Crown, MessageSquare, RefreshCw, ShieldCheck, UserCheck, UserX } from "@lucide/vue";
import { requestJson } from "../../services/api";
import { useDashboardStore } from "../../composables/useDashboardStore";
import { useToasts } from "../../composables/useToasts";
import type { GamePlayer, PlayerActionRequest, PlayerListPayload } from "../../types";

const store = useDashboardStore();
const playerPayload = ref<PlayerListPayload>({ online: [], known: [], history: [], rcon_available: false, game_time: "" });
const selectedPlayer = ref("");
const playerValue = ref("");
const playerReason = ref("");
const isPlayersLoading = ref(false);
const isPlayerActionRunning = ref(false);
const { showToast } = useToasts();

const selectedPlayerItem = computed(() => playerPayload.value.known.find((item) => item.name === selectedPlayer.value));
const offlinePlayers = computed(() => playerPayload.value.known.filter((item) => !item.online));

function serverId() {
  return store.selectedServer.value?.id || store.selectedServerId.value || "";
}

function playerStatus(player: GamePlayer) {
  if (player.online) {
    return player.ping || player.game_time || "online";
  }
  return player.last_seen ? "seen" : "offline";
}

async function loadPlayers() {
  const id = serverId();
  if (!id) {
    playerPayload.value = { online: [], known: [], history: [], rcon_available: false, game_time: "" };
    return;
  }
  isPlayersLoading.value = true;
  try {
    playerPayload.value = await requestJson<PlayerListPayload>(`/api/servers/${id}/players`);
    selectedPlayer.value = selectedPlayer.value || playerPayload.value.online[0]?.name || playerPayload.value.known[0]?.name || "";
  } catch (error) {
    showToast("Не удалось загрузить игроков сервера", "error");
    console.error(error);
  } finally {
    isPlayersLoading.value = false;
  }
}

async function runPlayerAction(action: PlayerActionRequest["action"], player = selectedPlayer.value) {
  const id = serverId();
  if (!id || !player) {
    return;
  }
  isPlayerActionRunning.value = true;
  try {
    const result = await requestJson<{ players: PlayerListPayload; message: string }>(`/api/servers/${id}/players/actions`, {
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

onMounted(loadPlayers);
</script>

<template>
  <section class="server-tab-panel players-tab">
    <section class="players-hero server-detail-section">
      <div class="server-detail-section-head">
        <div>
          <p class="eyebrow">minecraft players</p>
          <h3>Игроки сервера</h3>
        </div>
        <div class="panel-actions">
          <span class="users-status" :class="{ connected: playerPayload.rcon_available }">
            {{ playerPayload.rcon_available ? 'RCON доступен' : 'RCON недоступен' }}
          </span>
          <button class="ghost-button compact" type="button" :aria-busy="isPlayersLoading" @click="loadPlayers">
            <RefreshCw :class="{ spinning: isPlayersLoading }" :size="16" />
            <span>Обновить</span>
          </button>
        </div>
      </div>

      <section class="users-summary-grid players-summary-grid" aria-label="Сводка игроков">
        <article class="users-summary-card ok">
          <UserCheck :size="18" />
          <span>Онлайн</span>
          <strong>{{ playerPayload.online.length }}</strong>
          <small>{{ playerPayload.game_time || 'gametime n/a' }}</small>
        </article>
        <article class="users-summary-card">
          <ShieldCheck :size="18" />
          <span>Известные</span>
          <strong>{{ playerPayload.known.length }}</strong>
          <small>{{ offlinePlayers.length }} офлайн</small>
        </article>
        <article class="users-summary-card" :class="{ ok: playerPayload.rcon_available, warning: !playerPayload.rcon_available }">
          <Crown :size="18" />
          <span>RCON</span>
          <strong>{{ playerPayload.rcon_available ? 'OK' : 'OFF' }}</strong>
          <small>действия игроков</small>
        </article>
      </section>
    </section>

    <section class="server-detail-section player-console">
      <div class="server-detail-section-head">
        <div>
          <p class="eyebrow">actions</p>
          <h3>Управление игроком</h3>
        </div>
      </div>

      <div class="players-control-grid">
        <label>
          <span>Игрок</span>
          <input v-model="selectedPlayer" type="text" placeholder="Nickname" />
        </label>
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
        <button class="ghost-button compact" type="button" :disabled="isPlayerActionRunning || !selectedPlayer" @click="runPlayerAction(selectedPlayerItem?.whitelisted ? 'whitelist_remove' : 'whitelist_add')">
          <ShieldCheck :size="16" />
          <span>{{ selectedPlayerItem?.whitelisted ? 'Убрать whitelist' : 'Whitelist' }}</span>
        </button>
        <button class="ghost-button compact" type="button" :disabled="isPlayerActionRunning || !selectedPlayer" @click="runPlayerAction(selectedPlayerItem?.operator ? 'deop' : 'op')">
          <Crown :size="16" />
          <span>{{ selectedPlayerItem?.operator ? 'Снять OP' : 'OP' }}</span>
        </button>
        <button class="ghost-button compact danger" type="button" :disabled="isPlayerActionRunning || !selectedPlayer" @click="runPlayerAction(selectedPlayerItem?.banned ? 'pardon' : 'ban')">
          <Ban :size="16" />
          <span>{{ selectedPlayerItem?.banned ? 'Pardon' : 'Ban' }}</span>
        </button>
        <button class="ghost-button compact danger" type="button" :disabled="isPlayerActionRunning || !selectedPlayer" @click="runPlayerAction('kick')">
          <UserX :size="16" />
          <span>Kick</span>
        </button>
        <button class="ghost-button compact" type="button" :disabled="isPlayerActionRunning || !selectedPlayer || !playerValue" @click="runPlayerAction('message')">
          <MessageSquare :size="16" />
          <span>Сообщение</span>
        </button>
        <button class="ghost-button compact" type="button" :disabled="isPlayerActionRunning || !selectedPlayer || !playerValue" @click="runPlayerAction('luckperms_group_add')">LP group +</button>
        <button class="ghost-button compact" type="button" :disabled="isPlayerActionRunning || !selectedPlayer || !playerValue" @click="runPlayerAction('luckperms_group_remove')">LP group -</button>
      </div>
    </section>

    <section class="server-detail-section">
      <div class="server-detail-section-head">
        <div>
          <p class="eyebrow">directory</p>
          <h3>Известные игроки</h3>
        </div>
      </div>
      <div class="user-list players-list">
        <article
          v-for="player in playerPayload.known"
          :key="player.uuid || player.name"
          class="user-row player-row"
          :class="{ highlighted: selectedPlayer === player.name }"
          @click="selectedPlayer = player.name"
        >
          <div>
            <strong>{{ player.name }}</strong>
            <span>{{ player.online ? 'online' : 'offline' }} · UUID {{ player.uuid || 'unknown' }}</span>
            <small>
              {{ player.whitelisted ? 'whitelist' : 'no whitelist' }} · {{ player.operator ? 'op' : 'no op' }} · {{ player.banned ? 'banned' : 'not banned' }}
              <template v-if="player.luckperms_groups.length"> · LP {{ player.luckperms_groups.join(', ') }}</template>
            </small>
          </div>
          <span class="users-status" :class="{ connected: player.online }">{{ playerStatus(player) }}</span>
        </article>
        <article v-if="!playerPayload.known.length && !isPlayersLoading" class="user-row muted">
          <div>
            <strong>Игроков пока нет</strong>
            <span>Список собирается из usercache.json, stats и RCON.</span>
          </div>
        </article>
      </div>
    </section>

    <section class="server-detail-section">
      <div class="server-detail-section-head">
        <div>
          <p class="eyebrow">history</p>
          <h3>История действий</h3>
        </div>
      </div>
      <div class="user-list compact-history">
        <article v-for="item in playerPayload.history" :key="`${item.at}-${item.player}-${item.action}`" class="user-row">
          <div>
            <strong>{{ item.player }} · {{ item.action }}</strong>
            <span>{{ item.at }}{{ item.detail ? ` · ${item.detail}` : '' }}</span>
          </div>
        </article>
        <article v-if="!playerPayload.history.length" class="user-row muted">
          <div>
            <strong>История пуста</strong>
            <span>Действия появятся здесь после команд через Ksylian.</span>
          </div>
        </article>
      </div>
    </section>
  </section>
</template>
