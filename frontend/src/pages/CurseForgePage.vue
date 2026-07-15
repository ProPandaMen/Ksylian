<script setup lang="ts">
import { PackagePlus } from "@lucide/vue";
</script>

<template>
  <section class="panel curseforge-panel inactive-integration">
    <div class="panel-heading">
      <div>
        <p class="eyebrow">integration paused</p>
        <h2>CurseForge пока не активен</h2>
      </div>
      <span class="settings-status">Ждем API key</span>
    </div>

    <div class="empty-details integration-waiting">
      <PackagePlus :size="32" />
      <strong>Вернемся после одобрения заявки</strong>
      <span>
        Каталог модов и сборок выключен, чтобы не показывать ошибку доступа.
        После получения 3rd Party API key снова активируем поиск, фильтры и установку.
      </span>
    </div>
  </section>
</template>
