const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

if (!apiBaseUrl) {
  throw new Error(
    "NEXT_PUBLIC_API_BASE_URL is required. Copy .env.example to .env.local and set the FastAPI base URL.",
  );
}

let parsedApiBaseUrl: URL;

try {
  parsedApiBaseUrl = new URL(apiBaseUrl);
} catch {
  throw new Error(
    "NEXT_PUBLIC_API_BASE_URL must be an absolute HTTP(S) URL, for example http://127.0.0.1:8000.",
  );
}

if (
  parsedApiBaseUrl.protocol !== "http:" &&
  parsedApiBaseUrl.protocol !== "https:"
) {
  throw new Error("NEXT_PUBLIC_API_BASE_URL must use the http or https protocol.");
}

export const API_BASE_URL = apiBaseUrl.replace(/\/+$/, "");
