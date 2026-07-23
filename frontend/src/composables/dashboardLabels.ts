import type { NewServerDraft, ServerState } from "../types";

export const stateLabels: Record<ServerState, string> = {
  installing: "Устанавливается",
  stopped: "Выключен",
  starting: "Запускается",
  running: "Работает",
  stopping: "Останавливается",
  crashed: "Упал",
  updating: "Обновляется",
  backing_up: "Бэкап",
};

export const serverTypeLabels: Record<NewServerDraft["type"], string> = {
  vanilla: "Vanilla",
  paper: "Paper",
  purpur: "Purpur",
  fabric: "Fabric",
  forge: "Forge",
  neoforge: "NeoForge",
};
