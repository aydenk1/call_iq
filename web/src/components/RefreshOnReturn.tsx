"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

const REFRESH_FLAG = "calliq:refresh-calls";

export default function RefreshOnReturn() {
  const router = useRouter();

  useEffect(() => {
    const shouldRefresh = window.sessionStorage.getItem(REFRESH_FLAG);
    if (!shouldRefresh) {
      return;
    }
    window.sessionStorage.removeItem(REFRESH_FLAG);
    router.refresh();
  }, [router]);

  return null;
}

export const markCallsForRefresh = () => {
  if (typeof window === "undefined") {
    return;
  }
  window.sessionStorage.setItem(REFRESH_FLAG, "1");
};
