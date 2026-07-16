<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { LogIn } from "@lucide/vue";
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

const mode = computed(() => route.name);
const title = computed(() =>
  mode.value === "setup" ? "Создать администратора" : mode.value === "invite" ? "Принять приглашение" : "Войти",
);
const submitLabel = computed(() =>
  mode.value === "setup" ? "Создать аккаунт" : mode.value === "invite" ? "Зарегистрироваться" : "Войти",
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
    error.value = "Не удалось выполнить вход. Проверь данные и попробуй ещё раз.";
    console.error(submitError);
  } finally {
    isSubmitting.value = false;
  }
}
</script>

<template>
  <main class="auth-shell">
    <section class="auth-card panel">
      <div>
        <p class="eyebrow">ksylian access</p>
        <h1>{{ title }}</h1>
        <p>
          {{
            mode === 'setup'
              ? 'Первый пользователь станет администратором панели.'
              : mode === 'invite'
                ? 'Заполни данные, чтобы создать учётку по приглашению.'
                : 'Введи логин и пароль, чтобы открыть панель.'
          }}
        </p>
      </div>

      <form class="auth-form" @submit.prevent="submit">
        <label v-if="mode !== 'login'">
          <span>Имя на экране</span>
          <input v-model="displayName" autocomplete="name" type="text" placeholder="Например, Илья" />
        </label>
        <label>
          <span>Логин</span>
          <input v-model="username" autocomplete="username" required type="text" placeholder="propandamen" />
        </label>
        <label>
          <span>Пароль</span>
          <input
            v-model="password"
            autocomplete="current-password"
            required
            minlength="8"
            type="password"
            placeholder="Минимум 8 символов"
          />
        </label>

        <fieldset v-if="mode !== 'login'" class="theme-picker">
          <legend>Цветовая схема</legend>
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
        <button class="primary-button" type="submit" :disabled="isSubmitting">
          <LogIn :size="18" />
          <span>{{ isSubmitting ? 'Подожди' : submitLabel }}</span>
        </button>
      </form>
    </section>
  </main>
</template>
