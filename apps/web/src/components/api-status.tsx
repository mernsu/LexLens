"use client";

import { useEffect, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8010";

type Status =
  | { kind: "loading" }
  | { kind: "ok"; body: string }
  | { kind: "error"; message: string };

export function ApiStatus() {
  const [status, setStatus] = useState<Status>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;

    fetch(`${API_BASE}/health`)
      .then((response) => response.json())
      .then((body: unknown) => {
        if (!cancelled) {
          setStatus({ kind: "ok", body: JSON.stringify(body) });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setStatus({ kind: "error", message: String(error) });
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (status.kind === "loading") {
    return <p>API 状态：检测中…</p>;
  }

  if (status.kind === "error") {
    return <p>API 状态：连接失败（{status.message}）</p>;
  }

  return <p>API 状态：{status.body}</p>;
}
