<script setup lang="ts">
import {
  Archive,
  Box,
  CheckCircle2,
  ChevronRight,
  CircleStop,
  Clock3,
  Download,
  FileArchive,
  FileText,
  Folder,
  Gauge,
  HardDrive,
  Heart,
  History,
  Home,
  LayoutDashboard,
  ListRestart,
  PackagePlus,
  Play,
  Plus,
  RefreshCw,
  Search,
  Server,
  Settings,
  ShieldCheck,
  Sparkles,
  TerminalSquare,
  UploadCloud,
} from "@lucide/vue";
import catLogo from "./assets/cat-logo.svg";
import catPaw from "./assets/cat-paw.svg";
import catMascot from "./assets/ksylian-cat.png";

type ServerState = "online" | "deploying" | "offline";

interface GameServer {
  name: string;
  pack: string;
  version: string;
  state: ServerState;
  players: string;
  ram: string;
  cpu: number;
  disk: string;
  address: string;
}

interface BackupItem {
  name: string;
  size: string;
  created: string;
}

const navItems = [
  { label: "Обзор", icon: LayoutDashboard, active: true },
  { label: "Серверы", icon: Server, active: false },
  { label: "Модпаки", icon: PackagePlus, active: false },
  { label: "Файлы", icon: Folder, active: false },
  { label: "Бэкапы", icon: Archive, active: false },
  { label: "Настройки", icon: Settings, active: false },
];

const servers: GameServer[] = [
  {
    name: "Ksy Vanilla+",
    pack: "Better MC Fabric",
    version: "1.20.1",
    state: "online",
    players: "12 / 48",
    ram: "8.2 / 16 GB",
    cpu: 34,
    disk: "42 GB",
    address: "play.ksylian.local:25565",
  },
  {
    name: "Pink Nether",
    pack: "Prominence II",
    version: "1.20.1",
    state: "deploying",
    players: "0 / 32",
    ram: "2.1 / 12 GB",
    cpu: 18,
    disk: "18 GB",
    address: "pink.ksylian.local:25566",
  },
  {
    name: "Archive Realm",
    pack: "Create: Perfect World",
    version: "1.19.2",
    state: "offline",
    players: "0 / 24",
    ram: "0 / 10 GB",
    cpu: 0,
    disk: "31 GB",
    address: "archive.ksylian.local:25567",
  },
];

const logs = [
  "[23:04:11] Server thread/INFO Starting Minecraft server version 1.20.1",
  "[23:04:19] Loader/INFO Loaded 143 mods from CurseForge manifest",
  "[23:04:28] Backup/INFO Snapshot world-2026-07-15 completed",
  "[23:05:02] Proxy/INFO Velocity route registered: pink.ksylian.local",
  "[23:05:35] Mods/INFO 4 updates available for review",
];

const backups: BackupItem[] = [
  { name: "world-before-update", size: "6.8 GB", created: "Сегодня, 22:40" },
  { name: "pink-nether-auto", size: "3.1 GB", created: "Сегодня, 20:15" },
  { name: "archive-realm-monthly", size: "12.4 GB", created: "13 июля" },
];

const mods = [
  { name: "Fabric API", status: "Обновлён", tag: "required" },
  { name: "Simple Voice Chat", status: "Есть апдейт", tag: "update" },
  { name: "WorldEdit", status: "Обновлён", tag: "required" },
  { name: "Dynmap", status: "Проверить", tag: "review" },
];

const files = [
  { name: "world", meta: "Папка мира", icon: Folder },
  { name: "mods", meta: "143 файла", icon: Folder },
  { name: "server.properties", meta: "1.2 KB", icon: FileText },
  { name: "latest.log", meta: "284 KB", icon: FileText },
];

const stateLabels: Record<ServerState, string> = {
  online: "Онлайн",
  deploying: "Разворачивается",
  offline: "Выключен",
};
</script>

<template>
  <main class="app-shell">
    <div class="scene-orb orb-one"></div>
    <div class="scene-orb orb-two"></div>
    <div class="scene-orb orb-three"></div>
    <div class="scene-ribbon ribbon-one"></div>
    <div class="scene-ribbon ribbon-two"></div>

    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">
          <img :src="catLogo" alt="" />
        </div>
        <div>
          <strong>Ksylian</strong>
          <span>server panel</span>
        </div>
      </div>

      <nav class="nav-list" aria-label="Основная навигация">
        <button
          v-for="item in navItems"
          :key="item.label"
          class="nav-item"
          :class="{ active: item.active }"
          type="button"
        >
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <section class="mascot-card">
        <img :src="catMascot" alt="Розовый кот-талисман Ksylian" />
        <div>
          <strong>Ксю-контроль</strong>
          <span>3 мира под присмотром</span>
        </div>
      </section>
    </aside>

    <section class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">Minecraft orchestration</p>
          <h1>Панель управления серверами</h1>
        </div>

        <div class="topbar-actions">
          <label class="search-box">
            <Search :size="18" />
            <input type="search" placeholder="Найти сервер, мод или файл" />
          </label>
          <button class="icon-button" type="button" title="История задач">
            <History :size="20" />
          </button>
          <button class="primary-button" type="button">
            <Plus :size="18" />
            <span>Новый сервер</span>
          </button>
        </div>
      </header>

      <section class="hero-panel">
        <div class="hero-copy">
          <div class="status-pill">
            <CheckCircle2 :size="16" />
            <span>Агент сервера активен</span>
          </div>
          <h2>Выбираешь сборку, Ksylian разворачивает мир</h2>
          <p>
            Черновой интерфейс для установки CurseForge-сборок, управления процессами,
            бэкапов, логов, файлов и обновлений модов.
          </p>
          <div class="hero-actions">
            <button class="primary-button" type="button">
              <PackagePlus :size="18" />
              <span>Импорт CurseForge</span>
            </button>
            <button class="ghost-button" type="button">
              <UploadCloud :size="18" />
              <span>Загрузить manifest.json</span>
            </button>
          </div>
        </div>
        <div class="hero-mascot">
          <img :src="catMascot" alt="" />
        </div>
      </section>

      <section class="stats-grid" aria-label="Сводка">
        <article class="stat-tile">
          <Server :size="20" />
          <span>Серверы</span>
          <strong>3</strong>
        </article>
        <article class="stat-tile mint">
          <Gauge :size="20" />
          <span>Средняя нагрузка</span>
          <strong>17%</strong>
        </article>
        <article class="stat-tile amber">
          <HardDrive :size="20" />
          <span>Хранилище</span>
          <strong>72 GB</strong>
        </article>
        <article class="stat-tile graphite">
          <ShieldCheck :size="20" />
          <span>Последний бэкап</span>
          <strong>22:40</strong>
        </article>
      </section>

      <section class="content-grid">
        <div class="main-column">
          <section class="panel">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">instances</p>
                <h2>Серверы</h2>
              </div>
              <button class="ghost-button compact" type="button">
                <RefreshCw :size="16" />
                <span>Обновить</span>
              </button>
            </div>

            <div class="server-list">
              <article v-for="server in servers" :key="server.name" class="server-row">
                <div class="server-main">
                  <span class="server-state" :class="server.state"></span>
                  <div>
                    <h3>{{ server.name }}</h3>
                    <p>{{ server.pack }} · {{ server.version }} · {{ server.address }}</p>
                  </div>
                </div>

                <div class="server-metrics">
                  <span>{{ server.players }}</span>
                  <span>{{ server.ram }}</span>
                  <span>{{ server.disk }}</span>
                </div>

                <div class="server-actions" :aria-label="`Действия для ${server.name}`">
                  <button class="icon-button" type="button" title="Запустить">
                    <Play :size="17" />
                  </button>
                  <button class="icon-button" type="button" title="Перезагрузить">
                    <ListRestart :size="17" />
                  </button>
                  <button class="icon-button danger" type="button" title="Остановить">
                    <CircleStop :size="17" />
                  </button>
                  <button class="icon-button" type="button" title="Открыть">
                    <ChevronRight :size="17" />
                  </button>
                </div>

                <div class="progress-line">
                  <span :style="{ width: `${server.cpu}%` }"></span>
                </div>

                <span class="state-label" :class="server.state">{{ stateLabels[server.state] }}</span>
              </article>
            </div>
          </section>

          <section class="panel terminal-panel">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">live output</p>
                <h2>Логи</h2>
              </div>
              <button class="ghost-button compact" type="button">
                <Download :size="16" />
                <span>Скачать</span>
              </button>
            </div>
            <pre><code v-for="line in logs" :key="line">{{ line }}
</code></pre>
          </section>
        </div>

        <aside class="side-column">
          <section class="panel">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">backups</p>
                <h2>Резервные копии</h2>
              </div>
              <button class="icon-button" type="button" title="Создать бэкап">
                <FileArchive :size="18" />
              </button>
            </div>
            <div class="stack-list">
              <article v-for="backup in backups" :key="backup.name" class="stack-item">
                <Archive :size="18" />
                <div>
                  <strong>{{ backup.name }}</strong>
                  <span>{{ backup.size }} · {{ backup.created }}</span>
                </div>
              </article>
            </div>
          </section>

          <section class="panel">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">curseforge</p>
                <h2>Моды</h2>
              </div>
              <button class="icon-button" type="button" title="Проверить обновления">
                <RefreshCw :size="18" />
              </button>
            </div>
            <div class="stack-list">
              <article v-for="mod in mods" :key="mod.name" class="stack-item">
                <Box :size="18" />
                <div>
                  <strong>{{ mod.name }}</strong>
                  <span>{{ mod.status }}</span>
                </div>
                <i :class="mod.tag"></i>
              </article>
            </div>
          </section>

          <section class="panel">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">files</p>
                <h2>Файлы</h2>
              </div>
              <button class="icon-button" type="button" title="Домой">
                <Home :size="18" />
              </button>
            </div>
            <div class="file-list">
              <button v-for="file in files" :key="file.name" type="button" class="file-row">
                <component :is="file.icon" :size="18" />
                <span>{{ file.name }}</span>
                <small>{{ file.meta }}</small>
              </button>
            </div>
          </section>

          <section class="love-note">
            <img :src="catPaw" alt="" />
            <span>Pink mode включён для Ксюши</span>
            <Clock3 :size="16" />
          </section>
        </aside>
      </section>
    </section>
  </main>
</template>
