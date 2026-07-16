<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useDashboardStore } from "../composables/useDashboardStore";
import type { NewServerDraft } from "../types";
import NewServerPage from "./NewServerPage.vue";

const router = useRouter();
const store = useDashboardStore();
const newServer = ref<NewServerDraft>({
  name: "",
  type: "vanilla",
  version: "",
});

function backToServerList() {
  router.push("/servers");
}

async function createServer() {
  const created = await store.createServer(newServer.value);
  if (!created) {
    return;
  }

  newServer.value = { name: "", type: "vanilla", version: "" };
  await router.push("/servers");
}
</script>

<template>
  <NewServerPage
    v-model="newServer"
    :is-submitting="store.isCreatingServer.value"
    @cancel="backToServerList"
    @submit="createServer"
  />
</template>
