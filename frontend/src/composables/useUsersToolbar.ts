import { ref } from "vue";

export const usersToolbarRefresh = ref<(() => void) | null>(null);
export const usersToolbarCreateInvite = ref<(() => void) | null>(null);
export const isUsersToolbarLoading = ref(false);
export const isUsersToolbarCreating = ref(false);

export function useUsersToolbar() {
  return {
    usersToolbarRefresh,
    usersToolbarCreateInvite,
    isUsersToolbarLoading,
    isUsersToolbarCreating,
  };
}
