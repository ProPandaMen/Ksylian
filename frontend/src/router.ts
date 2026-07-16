import { createRouter, createWebHistory } from "vue-router";

const routes = [
  { path: "/", redirect: "/servers" },
  { path: "/servers", name: "servers", component: {} },
  { path: "/servers/new", name: "server-new", component: {} },
  { path: "/servers/:serverId", name: "server-detail", component: {}, props: true },
  { path: "/monitoring", name: "monitoring", component: {} },
  { path: "/modpacks", name: "modpacks", component: {} },
  { path: "/settings", name: "settings", component: {} },
  { path: "/:pathMatch(.*)*", redirect: "/servers" },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});
