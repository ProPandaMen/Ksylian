import { createRouter, createWebHistory } from "vue-router";
import CurseForgePage from "./pages/CurseForgePage.vue";
import MonitoringRoutePage from "./pages/MonitoringRoutePage.vue";
import NewServerRoutePage from "./pages/NewServerRoutePage.vue";
import ServerDetailPage from "./pages/ServerDetailPage.vue";
import ServersPage from "./pages/ServersPage.vue";
import SettingsRoutePage from "./pages/SettingsRoutePage.vue";
import LoginPage from "./pages/LoginPage.vue";
import UsersPage from "./pages/UsersPage.vue";
import { useAuthStore } from "./composables/useAuthStore";

const routes = [
  { path: "/", redirect: "/servers" },
  { path: "/setup", name: "setup", component: LoginPage, meta: { public: true } },
  { path: "/login", name: "login", component: LoginPage, meta: { public: true } },
  { path: "/invite", name: "invite", component: LoginPage, meta: { public: true } },
  { path: "/servers", name: "servers", component: ServersPage },
  { path: "/servers/new", name: "server-new", component: NewServerRoutePage },
  { path: "/servers/:serverId", name: "server-detail", component: ServerDetailPage, props: true },
  { path: "/monitoring", name: "monitoring", component: MonitoringRoutePage },
  { path: "/modpacks", name: "modpacks", component: CurseForgePage },
  { path: "/users", name: "users", component: UsersPage },
  { path: "/settings", name: "settings", component: SettingsRoutePage },
  { path: "/:pathMatch(.*)*", redirect: "/servers" },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  const status = await auth.loadAuthStatus();

  if (status.bootstrap_required && to.name !== "setup") {
    return "/setup";
  }
  if (!status.bootstrap_required && to.name === "setup") {
    return "/login";
  }
  if (to.meta.public) {
    return true;
  }

  const currentUser = auth.user.value ?? await auth.loadMe();
  if (!currentUser) {
    return "/login";
  }
  return true;
});
