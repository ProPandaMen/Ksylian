<script setup lang="ts">
import { computed } from "vue";
import { CircleStop, Cpu, HardDrive, ListRestart, MemoryStick, Play, RefreshCw, Users } from "@lucide/vue";
import { stateLabels, useDashboardStore } from "../../composables/useDashboardStore";

const store = useDashboardStore();
const busyStates = new Set(["installing", "starting", "stopping", "updating", "backing_up"]);
const serverOperation = computed(() => store.selectedServer.value.operation);
const isServerBusy = computed(() => busyStates.has(store.selectedServer.value.state));
</script>

<template>
  <section class="server-tab-panel">
      <section v-if="serverOperation || isServerBusy" class="server-detail-section server-operation-panel">
        <div class="server-detail-section-head">
          <h3>{{ serverOperation?.label || 'Подготовка сервера' }}</h3>
          <strong>{{ serverOperation ? `${serverOperation.percent}%` : stateLabels[store.selectedServer.value.state] }}</strong>
        </div>
        <div class="server-operation-body">
          <div class="server-install-track" :class="{ indeterminate: !serverOperation }">
            <span :style="{ width: serverOperation ? `${serverOperation.percent}%` : '42%' }"></span>
          </div>
          <div class="server-operation-meta">
            <span>{{ serverOperation?.message || 'Готовлю базовые файлы и service unit' }}</span>
            <strong v-if="serverOperation?.current_item">{{ serverOperation.current_item }}</strong>
          </div>
        </div>
      </section>

      <section class="server-detail-section">
        <div class="server-detail-section-head">
          <h3>Управление</h3>
          <span class="state-label" :class="store.selectedServer.value.state">
            {{ stateLabels[store.selectedServer.value.state] }}
          </span>
        </div>

        <div class="server-detail-row">
          <span>Адрес</span>
          <strong>{{ store.selectedServer.value.address }}</strong>
        </div>
        <div class="server-detail-row">
          <span>Тип</span>
          <strong>{{ store.selectedServer.value.pack }}</strong>
        </div>
        <div class="server-detail-row">
          <span>Код выхода</span>
          <strong>{{ store.selectedServer.value.exit_code ?? '—' }}</strong>
        </div>
        <div v-if="store.selectedServer.value.last_event" class="server-detail-row">
          <span>Последнее событие</span>
          <strong>{{ store.selectedServer.value.last_event }}</strong>
        </div>
        <div v-if="store.selectedServer.value.warnings?.length" class="server-warning-list">
          <strong v-for="warning in store.selectedServer.value.warnings" :key="warning">{{ warning }}</strong>
        </div>
        <div class="server-detail-actions">
          <button class="icon-button" type="button" title="Запустить" @click="store.runServerAction(store.selectedServer.value.id, 'start')">
            <Play :size="17" />
          </button>
          <button class="icon-button" type="button" title="Перезагрузить" @click="store.runServerAction(store.selectedServer.value.id, 'restart')">
            <ListRestart :size="17" />
          </button>
          <button class="icon-button" type="button" title="Обновить файлы сервера" @click="store.runServerAction(store.selectedServer.value.id, 'update')">
            <RefreshCw :size="17" />
          </button>
          <button class="icon-button" type="button" title="Откатить последнее обновление" @click="store.runServerAction(store.selectedServer.value.id, 'rollback')">
            <ListRestart :size="17" />
          </button>
          <button class="icon-button danger" type="button" title="Остановить" @click="store.runServerAction(store.selectedServer.value.id, 'stop')">
            <CircleStop :size="17" />
          </button>
        </div>
      </section>

      <section class="server-detail-section">
        <div class="server-detail-section-head">
          <h3>Ресурсы</h3>
        </div>
        <article class="server-resource-row">
          <Cpu :size="20" />
          <span>Процессор</span>
          <strong>{{ store.selectedServer.value.cpu }}%</strong>
        </article>
        <article class="server-resource-row">
          <MemoryStick :size="20" />
          <span>Оперативка</span>
          <strong>{{ store.selectedServer.value.ram }}</strong>
        </article>
        <article class="server-resource-row">
          <HardDrive :size="20" />
          <span>Память</span>
          <strong>{{ store.selectedServer.value.disk }}</strong>
        </article>
        <article class="server-resource-row">
          <Users :size="20" />
          <span>Онлайн</span>
          <strong>{{ store.selectedServer.value.players }}</strong>
        </article>
      </section>

      <section class="server-detail-section">
        <div class="server-detail-section-head">
          <h3>Основная информация</h3>
        </div>
        <div class="server-detail-row">
          <span>Версия Minecraft</span>
          <strong>{{ store.selectedServer.value.version }}</strong>
        </div>
        <div class="server-detail-row">
          <span>Пакет</span>
          <strong>{{ store.selectedServer.value.pack }}</strong>
        </div>
        <div class="server-detail-row">
          <span>Статус</span>
          <strong>{{ stateLabels[store.selectedServer.value.state] }}</strong>
        </div>
      </section>
    </section>
</template>
