import type { Component } from "vue";
import { Gauge, PackagePlus, Server, Settings } from "@lucide/vue";
import type { TabId } from "./types";

export const navItems: Array<{ id: TabId; label: string; icon: Component; disabled?: boolean }> = [
  { id: "servers", label: "Серверы", icon: Server },
  { id: "monitoring", label: "Мониторинг", icon: Gauge },
  { id: "modpacks", label: "CurseForge", icon: PackagePlus, disabled: true },
  { id: "settings", label: "Настройки", icon: Settings },
];

export const tabCopy: Record<TabId, { title: string; eyebrow: string }> = {
  servers: { title: "Серверы", eyebrow: "instances" },
  monitoring: { title: "Мониторинг", eyebrow: "host health" },
  modpacks: { title: "CurseForge", eyebrow: "integration" },
  settings: { title: "Настройки", eyebrow: "configuration" },
};

export const routePaths: Record<TabId, string> = {
  servers: "/servers",
  monitoring: "/monitoring",
  modpacks: "/modpacks",
  settings: "/settings",
};
