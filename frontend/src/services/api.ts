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

export async function requestForm<T>(url: string, body: FormData, options?: RequestInit): Promise<T> {
  const token = window.localStorage.getItem("ksylian_auth_token");
  const headers = new Headers(options?.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(url, {
    ...options,
    method: options?.method || "POST",
    body,
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

export function requestFormWithProgress<T>(
  url: string,
  body: FormData,
  onProgress: (percent: number) => void,
): Promise<T> {
  const token = window.localStorage.getItem("ksylian_auth_token");

  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", url);
    if (token) {
      request.setRequestHeader("Authorization", `Bearer ${token}`);
    }

    request.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    request.onload = () => {
      if (request.status === 401 && !url.startsWith("/api/auth/")) {
        window.localStorage.removeItem("ksylian_auth_token");
        window.location.assign("/login");
        return;
      }
      if (request.status < 200 || request.status >= 300) {
        reject(new Error(`API returned ${request.status}`));
        return;
      }
      try {
        resolve(JSON.parse(request.responseText) as T);
      } catch (error) {
        reject(error);
      }
    };

    request.onerror = () => reject(new Error("Network error"));
    request.send(body);
  });
}
