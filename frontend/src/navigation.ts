import type { Component } from "vue";
import { Gauge, LayoutDashboard, PackagePlus, Server, Settings } from "@lucide/vue";
import type { TabId } from "./types";

export const navItems: Array<{ id: TabId; label: string; icon: Component; disabled?: boolean }> = [
  { id: "overview", label: "Обзор", icon: LayoutDashboard },
  { id: "servers", label: "Серверы", icon: Server },
  { id: "monitoring", label: "Мониторинг", icon: Gauge },
  { id: "modpacks", label: "CurseForge", icon: PackagePlus, disabled: true },
  { id: "settings", label: "Настройки", icon: Settings },
];

export const tabCopy: Record<TabId, { title: string; eyebrow: string }> = {
  overview: { title: "Панель управления серверами", eyebrow: "Minecraft orchestration" },
  servers: { title: "Серверы", eyebrow: "instances" },
  monitoring: { title: "Мониторинг", eyebrow: "host health" },
  modpacks: { title: "CurseForge", eyebrow: "integration" },
  files: { title: "Файловый менеджер", eyebrow: "server files" },
  backups: { title: "Резервные копии", eyebrow: "snapshots" },
  settings: { title: "Настройки", eyebrow: "configuration" },
};

export const routePaths: Record<TabId, string> = {
  overview: "/",
  servers: "/servers",
  monitoring: "/monitoring",
  modpacks: "/modpacks",
  files: "/files",
  backups: "/backups",
  settings: "/settings",
};
