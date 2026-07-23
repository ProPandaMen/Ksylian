export type ServerDetailTab = "overview" | "players" | "logs" | "files" | "mods" | "backups" | "diagnostics" | "settings";

export const serverDetailTabs: Array<{ id: ServerDetailTab; label: string }> = [
  { id: "overview", label: "Информация" },
  { id: "players", label: "Игроки" },
  { id: "logs", label: "Логи" },
  { id: "files", label: "Файлы" },
  { id: "mods", label: "Моды" },
  { id: "backups", label: "Бэкапы" },
  { id: "diagnostics", label: "Диагностика" },
  { id: "settings", label: "Настройки" },
];
