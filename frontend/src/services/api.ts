export async function requestJson<T>(url: string, options?: RequestInit): Promise<T> {
  const token = window.localStorage.getItem("ksylian_auth_token");
  const headers = new Headers(options?.headers);
  headers.set("Content-Type", "application/json");
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    if (response.status === 401 && !url.startsWith("/api/auth/")) {
      window.localStorage.removeItem("ksylian_auth_token");
      window.location.assign("/login");
    }
    throw new Error(`API returned ${response.status}`);
  }

  return response.json() as Promise<T>;
}
