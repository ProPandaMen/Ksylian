import { createRouter, createWebHistory } from "vue-router";

const routes = [
  { path: "/", name: "overview", component: {} },
  { path: "/servers", name: "servers", component: {} },
  { path: "/servers/:serverId", name: "server-detail", component: {}, props: true },
  { path: "/monitoring", name: "monitoring", component: {} },
  { path: "/modpacks", name: "modpacks", component: {} },
  { path: "/files", name: "files", component: {} },
  { path: "/backups", name: "backups", component: {} },
  { path: "/settings", name: "settings", component: {} },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});
