import { createRouter, createWebHistory } from "vue-router";
import CurseForgePage from "./pages/CurseForgePage.vue";
import MonitoringRoutePage from "./pages/MonitoringRoutePage.vue";
import NewServerRoutePage from "./pages/NewServerRoutePage.vue";
import ServerDetailPage from "./pages/ServerDetailPage.vue";
import ServersPage from "./pages/ServersPage.vue";
import SettingsRoutePage from "./pages/SettingsRoutePage.vue";

const routes = [
  { path: "/", redirect: "/servers" },
  { path: "/servers", name: "servers", component: ServersPage },
  { path: "/servers/new", name: "server-new", component: NewServerRoutePage },
  { path: "/servers/:serverId", name: "server-detail", component: ServerDetailPage, props: true },
  { path: "/monitoring", name: "monitoring", component: MonitoringRoutePage },
  { path: "/modpacks", name: "modpacks", component: CurseForgePage },
  { path: "/settings", name: "settings", component: SettingsRoutePage },
  { path: "/:pathMatch(.*)*", redirect: "/servers" },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});
