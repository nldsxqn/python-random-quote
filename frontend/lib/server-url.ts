const configuredApi = process.env.NEXT_PUBLIC_API_URL?.trim() ?? "";
const configuredWs = process.env.NEXT_PUBLIC_WS_URL?.trim() ?? "";

function pageApiOrigin(): string {
  if (typeof window === "undefined") {
    return "http://127.0.0.1:8000";
  }
  const scheme = window.location.protocol === "https:" ? "https:" : "http:";
  const host = window.location.hostname;
  const name = host.includes(":") ? `[${host}]` : host;
  return `${scheme}//${name}:8000`;
}

function apiOrigin(): string {
  return (configuredApi || pageApiOrigin()).replace(/\/$/, "");
}

export function apiUrl(path: string): string {
  return `${apiOrigin()}${path}`;
}

export function wsUrl(path: string): string {
  if (configuredWs && path === "/ws") {
    return configuredWs.replace(/\/$/, "");
  }
  return `${apiOrigin().replace(/^http/i, "ws")}${path}`;
}
