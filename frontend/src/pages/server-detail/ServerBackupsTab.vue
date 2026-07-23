<script setup lang="ts">
import { useDashboardStore } from "../../composables/useDashboardStore";

const store = useDashboardStore();
</script>

<template>
  <section class="server-tab-panel">
      <section class="server-detail-section">
        <div class="server-detail-section-head">
          <h3>Бэкапы</h3>
          <button class="primary-button compact" type="button" @click="store.createServerBackup()">
            Создать безопасный бэкап
          </button>
        </div>
        <div class="server-backup-list">
          <article
            v-for="backup in store.backups.value.filter((item) => item.server_id === store.selectedServer.value?.id)"
            :key="backup.id"
            class="server-backup-row"
          >
            <div>
              <strong>{{ backup.name }}</strong>
              <span>{{ backup.created }} · {{ backup.size }}</span>
              <small v-if="backup.checksum">SHA-256 {{ backup.checksum.slice(0, 18) }}…</small>
            </div>
          </article>
          <article v-if="!store.backups.value.some((item) => item.server_id === store.selectedServer.value?.id)" class="server-empty-state">
            <div>
              <strong>Бэкапов пока нет</strong>
              <span>Создай первый backup перед изменениями мира или модов.</span>
            </div>
          </article>
        </div>
      </section>
    </section>
</template>
