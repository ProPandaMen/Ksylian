<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { LogIn } from "@lucide/vue";
import catLogo from "../assets/cat-logo.svg";
import catMascot from "../assets/ksylian-cat.png";
import { themes, useAuthStore } from "../composables/useAuthStore";
import type { ThemeName } from "../types";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const username = ref("");
const password = ref("");
const displayName = ref("");
const theme = ref<ThemeName>("pink");
const isSubmitting = ref(false);
const error = ref("");
const mascotLoved = ref(false);
let mascotLoveTimer: number | undefined;
let lastMascotPointer: { x: number; y: number } | undefined;

const pawTrail = [
  { left: "16%", top: "-3%" },
  { left: "14%", top: "8%" },
  { left: "11%", top: "18%" },
  { left: "7%", top: "28%" },
  { left: "1%", top: "38%" },
  { left: "-7%", top: "49%" },
  { left: "-13%", top: "61%" },
  { left: "-7%", top: "70%" },
  { left: "4%", top: "73%" },
  { left: "5%", top: "82%" },
  { left: "4%", top: "92%" },
  { left: "10%", top: "99%" },
  { left: "14%", top: "108%" },
  { left: "34%", top: "116%" },
  { left: "56%", top: "115%" },
  { left: "77%", top: "108%" },
  { left: "80%", top: "99%" },
  { left: "89%", top: "94%" },
  { left: "93%", top: "86%" },
  { left: "90%", top: "76%" },
  { left: "99%", top: "69%" },
  { left: "108%", top: "64%" },
  { left: "114%", top: "57%" },
  { left: "116%", top: "43%" },
  { left: "110%", top: "31%" },
  { left: "101%", top: "24%" },
  { left: "91%", top: "22%" },
  { left: "82%", top: "22%" },
  { left: "77%", top: "16%" },
  { left: "72%", top: "10%" },
  { left: "67%", top: "3%" },
  { left: "66%", top: "-7%" },
  { left: "50%", top: "-12%" },
  { left: "32%", top: "-11%" },
];

const pawPrints = computed(() =>
  pawTrail.flatMap((footprint, index) => {
    const prevFootprint = pawTrail[index - 1] ?? pawTrail[pawTrail.length - 1];
    const nextFootprint = pawTrail[index + 1] ?? pawTrail[0];
    const currentX = Number.parseFloat(footprint.left);
    const currentY = Number.parseFloat(footprint.top);
    const dx = Number.parseFloat(nextFootprint.left) - Number.parseFloat(prevFootprint.left);
    const dy = Number.parseFloat(nextFootprint.top) - Number.parseFloat(prevFootprint.top);
    const length = Math.hypot(dx, dy) || 1;
    const tangentX = dx / length;
    const tangentY = dy / length;
    const normalX = -tangentY;
    const normalY = tangentX;
    const angle = Math.atan2(dy, dx) * (180 / Math.PI) + 90;
    const side = index % 2 === 0 ? 1 : -1;
    const frontStride = 1.55;
    const rearStride = 1.25;
    const spread = 1.2;
    const delay = -14.4 + index * 0.34;

    return [
      {
        left: `${currentX + tangentX * frontStride + normalX * spread * side}%`,
        top: `${currentY + tangentY * frontStride + normalY * spread * side}%`,
        angle,
        delay,
        kind: "front",
      },
      {
        left: `${currentX - tangentX * rearStride - normalX * spread * side}%`,
        top: `${currentY - tangentY * rearStride - normalY * spread * side}%`,
        angle,
        delay: delay + 0.1,
        kind: "rear",
      },
    ];
  }),
);

const mode = computed(() => route.name);
const title = computed(() =>
  mode.value === "setup" || mode.value === "login" ? "Ksylian" : "Регистрация пользователя",
);
const eyebrow = computed(() =>
  mode.value === "setup" ? "Настройка доступа" : mode.value === "login" ? "Вход в панель" : "Доступ Ksylian",
);
const description = computed(() =>
  mode.value === "setup" || mode.value === "login"
    ? ""
    : "Регистрация по приглашению для доступа к панели.",
);
const mascotBubbleText = computed(() =>
  mode.value === "setup"
    ? "Сначала создадим администратора, а дальше я помогу с панелью"
    : mode.value === "invite"
      ? "Заполни приглашение, и я открою тебе дверь в панель"
      : "С возвращением. Введи логин и пароль, я присмотрю за серверами",
);
const submitLabel = computed(() =>
  mode.value === "setup" ? "Создать учётную запись" : mode.value === "invite" ? "Завершить регистрацию" : "Войти",
);
const pendingLabel = computed(() =>
  mode.value === "setup" ? "Создание..." : mode.value === "invite" ? "Регистрация..." : "Вход...",
);
const errorMessage = computed(() =>
  mode.value === "setup"
    ? "Не удалось создать учётную запись. Данные не прошли проверку."
    : mode.value === "invite"
      ? "Не удалось завершить регистрацию. Недействительная ссылка или некорректные данные."
      : "Не удалось войти. Неверный логин или пароль.",
);

async function submit() {
  isSubmitting.value = true;
  error.value = "";
  try {
    if (mode.value === "setup") {
      await auth.bootstrapAdmin({
        username: username.value,
        password: password.value,
        display_name: displayName.value,
        theme: theme.value,
      });
    } else if (mode.value === "invite") {
      await auth.registerInvite({
        token: String(route.query.token || ""),
        username: username.value,
        password: password.value,
        display_name: displayName.value,
        theme: theme.value,
      });
    } else {
      await auth.login({ username: username.value, password: password.value });
    }
    await router.push("/servers");
  } catch (submitError) {
    error.value = errorMessage.value;
    console.error(submitError);
  } finally {
    isSubmitting.value = false;
  }
}

function pawStyle(footprint: (typeof pawPrints.value)[number]) {
  return {
    left: footprint.left,
    top: footprint.top,
    transform: `translate(-50%, -50%) rotate(${footprint.angle}deg)`,
    animationDelay: `${footprint.delay}s`,
  };
}

function petMascot(event: PointerEvent) {
  if (!lastMascotPointer) {
    lastMascotPointer = { x: event.clientX, y: event.clientY };
    return;
  }

  const distance = Math.hypot(event.clientX - lastMascotPointer.x, event.clientY - lastMascotPointer.y);
  lastMascotPointer = { x: event.clientX, y: event.clientY };
  if (distance < 8) return;

  mascotLoved.value = true;
  window.clearTimeout(mascotLoveTimer);
  mascotLoveTimer = window.setTimeout(() => {
    mascotLoved.value = false;
  }, 520);
}

function stopPettingMascot() {
  window.clearTimeout(mascotLoveTimer);
  lastMascotPointer = undefined;
  mascotLoved.value = false;
}
</script>

<template>
  <main class="auth-shell" :class="`theme-${theme}`">
    <div class="paw-trail" aria-hidden="true">
      <span
        v-for="(footprint, index) in pawPrints"
        :key="index"
        class="paw-print"
        :class="`paw-${footprint.kind}`"
        :style="pawStyle(footprint)"
      ></span>
    </div>

    <div class="auth-scene">
      <div
        class="auth-mascot"
        :class="{ loved: mascotLoved }"
        aria-hidden="true"
        @pointermove="petMascot"
        @pointerleave="stopPettingMascot"
      >
        <span class="mascot-bubble">
          <span class="bubble-dot small"></span>
          <span class="bubble-dot medium"></span>
          <span class="bubble-dot large"></span>
          <span>{{ mascotBubbleText }}</span>
        </span>
        <span class="mascot-hearts" aria-hidden="true">
          <span v-for="heart in 7" :key="heart"></span>
        </span>
        <img :src="catMascot" alt="" />
      </div>

      <section class="auth-card panel">
      <div>
        <div class="auth-brand-title">
          <span class="auth-logo" aria-hidden="true">
            <img :src="catLogo" alt="" />
          </span>
          <h1>{{ title }}</h1>
        </div>
        <p class="eyebrow">{{ eyebrow }}</p>
        <p v-if="description">{{ description }}</p>
      </div>

      <form class="auth-form" @submit.prevent="submit">
        <label v-if="mode !== 'login'">
          <span>Имя в панели</span>
          <input v-model="displayName" autocomplete="name" type="text" placeholder="Илья" />
        </label>
        <label>
          <span>Логин</span>
          <input v-model="username" autocomplete="username" required type="text" placeholder="admin" />
          <small v-if="mode !== 'login'">3–32 символа, a–z, 0–9, . _ -</small>
        </label>
        <label>
          <span>Пароль</span>
          <input
            v-model="password"
            autocomplete="current-password"
            required
            minlength="8"
            type="password"
            placeholder="••••••••"
          />
          <small v-if="mode !== 'login'">Не менее 8 символов</small>
        </label>

        <fieldset v-if="mode !== 'login'" class="theme-picker">
          <legend class="sr-only">Внешний вид панели</legend>
          <span class="theme-picker-title">Внешний вид панели</span>
          <button
            v-for="item in themes"
            :key="item.id"
            class="theme-option"
            :class="[item.id, { selected: theme === item.id }]"
            type="button"
            @click="theme = item.id"
          >
            <span></span>
            {{ item.label }}
          </button>
        </fieldset>

        <p v-if="error" class="auth-error">{{ error }}</p>
        <button class="primary-button auth-submit" type="submit" :disabled="isSubmitting">
          <LogIn :size="18" />
          <span>{{ isSubmitting ? pendingLabel : submitLabel }}</span>
        </button>
      </form>
      </section>
    </div>
  </main>
</template>
