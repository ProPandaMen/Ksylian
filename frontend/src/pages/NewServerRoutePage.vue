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
  min_ram: "1G",
  max_ram: "2G",
  java_runtime: "auto",
  jvm_args: "",
  cpu_limit: 100,
  loader_version: "",
  installer_version: "",
  install_fabric_api: false,
});

async function createServer() {
  const created = await store.createServer(newServer.value);
  if (!created) {
    return;
  }

  newServer.value = {
    name: "",
    type: "vanilla",
    version: "",
    min_ram: "1G",
    max_ram: "2G",
    java_runtime: "auto",
    jvm_args: "",
    cpu_limit: 100,
    loader_version: "",
    installer_version: "",
    install_fabric_api: false,
  };
  await router.push("/servers");
}
</script>

<template>
  <NewServerPage
    v-model="newServer"
    :is-submitting="store.isCreatingServer.value"
    @submit="createServer"
  />
</template>
