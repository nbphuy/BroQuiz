import { apiClient } from "./client";

export async function getHealth() {
  const { data, response } = await apiClient.GET("/health");

  // The current FastAPI contract declares no non-2xx response for this route,
  // so openapi-fetch types `error` as `never`. Check the raw response rather
  // than silently accepting an unexpected HTTP failure.
  if (!response.ok) {
    throw new Error(`FastAPI health check failed with HTTP ${response.status}.`, {
      cause: response.statusText,
    });
  }

  if (!data) {
    throw new Error("FastAPI health check returned no response data.");
  }

  return data;
}
