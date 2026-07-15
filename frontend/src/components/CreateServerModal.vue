<script setup lang="ts">
import { Plus, X } from "@lucide/vue";

const emit = defineEmits<{
  close: [];
  submit: [];
}>();

const modelValue = defineModel<{
  name: string;
  pack: string;
  version: string;
  address: string;
}>({ required: true });

function updateField(field: "name" | "pack" | "version" | "address", value: string) {
  modelValue.value = {
    ...modelValue.value,
    [field]: value,
  };
}
</script>

<template>
  <div class="modal-layer" role="dialog" aria-modal="true" aria-labelledby="create-server-title">
    <section class="modal-panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">new instance</p>
          <h2 id="create-server-title">Новый сервер</h2>
        </div>
        <button class="icon-button" type="button" title="Закрыть" @click="emit('close')">
          <X :size="18" />
        </button>
      </div>

      <form class="server-form" @submit.prevent="emit('submit')">
        <label>
          <span>Название</span>
          <input :value="modelValue.name" required type="text" placeholder="Например, Ksy Survival" @input="updateField('name', ($event.target as HTMLInputElement).value)" />
        </label>
        <label>
          <span>Сборка</span>
          <input :value="modelValue.pack" required type="text" placeholder="CurseForge pack или manifest" @input="updateField('pack', ($event.target as HTMLInputElement).value)" />
        </label>
        <label>
          <span>Версия Minecraft</span>
          <input :value="modelValue.version" required type="text" placeholder="1.20.1" @input="updateField('version', ($event.target as HTMLInputElement).value)" />
        </label>
        <label>
          <span>Адрес</span>
          <input :value="modelValue.address" type="text" placeholder="server.ksylian.ru:25566" @input="updateField('address', ($event.target as HTMLInputElement).value)" />
        </label>

        <p class="form-note">
          Сейчас форма готовит контракт интерфейса. Для реального создания ещё нужен provisioner,
          который будет скачивать сборку, выделять порт, создавать папку и systemd-службу.
        </p>

        <div class="form-actions">
          <button class="ghost-button" type="button" @click="emit('close')">Отмена</button>
          <button class="primary-button" type="submit">
            <Plus :size="18" />
            <span>Создать</span>
          </button>
        </div>
      </form>
    </section>
  </div>
</template>
