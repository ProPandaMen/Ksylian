<script setup lang="ts">
import { CircleStop, ListRestart, Play, Plus, RefreshCw, Server, Trash2 } from "@lucide/vue";
import { useRouter } from "vue-router";
import { stateLabels, useDashboardStore } from "../composables/useDashboardStore";

const router = useRouter();
const store = useDashboardStore();

async function openServerPanel(serverId: string) {
  store.selectedServerId.value = serverId;
  await router.push(`/servers/${serverId}`);
}

function openNewServerPage() {
  router.push("/servers/new");
}
</script>

<template>
  <section class="servers-page">
    <section
      v-if="store.isDashboardInitialLoading.value"
      class="servers-section"
      aria-label="Загрузка сводки серверов"
    >
      <div class="servers-section-head">
        <h3>Сводка</h3>
      </div>
      <div class="server-summary-list">
        <article v-for="item in 4" :key="item" class="server-summary-row skeleton-tile">
          <span class="skeleton-line short"></span>
          <strong class="skeleton-number"></strong>
        </article>
      </div>
    </section>

    <section v-else class="servers-section" aria-label="Сводка серверов">
      <div class="servers-section-head">
        <h3>Сводка</h3>
      </div>
      <div class="server-summary-list">
        <article class="server-summary-row">
          <span>Стабильно работают</span>
          <strong>{{ store.stableServersCount.value }}</strong>
        </article>
        <article class="server-summary-row">
          <span>Перезагружаются</span>
          <strong>{{ store.deployingServersCount.value }}</strong>
        </article>
        <article class="server-summary-row">
          <span>Выключены</span>
          <strong>{{ store.offlineServersCount.value }}</strong>
        </article>
        <article class="server-summary-row">
          <span>Всего серверов</span>
          <strong>{{ store.servers.value.length }}</strong>
        </article>
      </div>
    </section>

    <section class="servers-section" aria-label="Серверы">
      <div class="servers-section-head">
        <h3>Серверы</h3>
        <div class="panel-actions">
          <button class="ghost-button compact" type="button" @click="store.loadDashboard()">
            <RefreshCw :size="16" />
            <span>Обновить</span>
          </button>
          <button class="primary-button compact" type="button" @click="openNewServerPage">
            <Plus :size="16" />
            <span>Новый сервер</span>
          </button>
        </div>
      </div>

      <div v-if="store.isDashboardInitialLoading.value" class="server-list" aria-label="Загрузка серверов">
        <article v-for="item in 3" :key="item" class="server-row skeleton-row">
          <div class="server-main">
            <span class="skeleton-dot"></span>
            <div>
              <span class="skeleton-line title"></span>
              <span class="skeleton-line"></span>
            </div>
          </div>
          <div class="server-metrics">
            <span class="skeleton-pill"></span>
            <span class="skeleton-pill"></span>
            <span class="skeleton-pill"></span>
          </div>
          <div class="server-actions">
            <span v-for="button in 4" :key="button" class="skeleton-button"></span>
          </div>
          <div class="progress-line static skeleton-progress">
            <span></span>
          </div>
        </article>
      </div>

      <div v-else class="server-list">
        <article
          v-for="server in store.servers.value"
          :key="server.id"
          class="server-row"
          :class="{ selected: store.selectedServerId.value === server.id }"
          role="button"
          tabindex="0"
          @click="openServerPanel(server.id)"
          @keydown.enter.prevent="openServerPanel(server.id)"
          @keydown.space.prevent="openServerPanel(server.id)"
        >
          <div class="server-main">
            <span class="server-state" :class="server.state"></span>
            <div class="server-copy">
              <div class="server-title-line">
                <h3>{{ server.name }}</h3>
              </div>
              <p>{{ server.address }}</p>
              <div class="server-tags" aria-label="Основная информация">
                <span>{{ server.pack }}</span>
                <span>Minecraft {{ server.version }}</span>
              </div>
            </div>
          </div>

          <div class="server-metrics">
            <span>{{ server.players }}</span>
            <span>{{ server.ram }}</span>
            <span>{{ server.disk }}</span>
          </div>

          <div class="server-actions" :aria-label="`Действия для ${server.name}`">
            <button
              class="icon-button"
              type="button"
              :title="server.state === 'offline' ? 'Запустить' : 'Остановить'"
              @click.stop="store.runServerAction(server.id, server.state === 'offline' ? 'start' : 'stop')"
            >
              <Play v-if="server.state === 'offline'" :size="17" />
              <CircleStop v-else :size="17" />
            </button>
            <button
              class="icon-button"
              type="button"
              title="Перезагрузить"
              @click.stop="store.runServerAction(server.id, 'restart')"
            >
              <ListRestart :size="17" />
            </button>
            <button
              class="icon-button danger"
              type="button"
              title="Удалить"
              @click.stop="store.deleteServer(server.id)"
            >
              <Trash2 :size="17" />
            </button>
          </div>

          <div class="progress-line">
            <span :style="{ width: `${server.cpu}%` }"></span>
          </div>

          <span class="state-label" :class="server.state">{{ stateLabels[server.state] }}</span>
        </article>
        <article v-if="!store.servers.value.length" class="server-empty-state">
          <div class="empty-icon">
            <Server :size="28" />
          </div>
          <div>
            <strong>Серверов пока нет</strong>
            <span>
              Создай первый Minecraft-сервер или подключи существующий через agent.
            </span>
          </div>
          <button class="ghost-button compact" type="button" @click="openNewServerPage">
            <Plus :size="18" />
            <span>Создать сервер</span>
          </button>
        </article>
      </div>
    </section>
  </section>
</template>
