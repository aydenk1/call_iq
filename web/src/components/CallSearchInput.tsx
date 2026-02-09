"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";

type CallSearchInputProps = {
  initialQuery: string;
  debounceMs?: number;
};

export default function CallSearchInput({ initialQuery, debounceMs = 250 }: CallSearchInputProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [value, setValue] = useState(initialQuery);

  const normalized = useMemo(() => value.trim(), [value]);

  useEffect(() => {
    setValue(initialQuery);
  }, [initialQuery]);

  useEffect(() => {
    const handle = setTimeout(() => {
      const params = new URLSearchParams(searchParams.toString());
      if (normalized) {
        params.set("q", normalized);
      } else {
        params.delete("q");
      }
      // New query should always start from first page.
      params.delete("page");
      const next = params.toString();
      router.replace(next ? `${pathname}?${next}` : pathname);
    }, debounceMs);

    return () => clearTimeout(handle);
  }, [debounceMs, normalized, pathname, router, searchParams]);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        className="h-9 w-full max-w-lg rounded-md border border-input bg-background px-3 text-sm"
        onChange={(event) => setValue(event.target.value)}
        placeholder="Search transcript, external number, or implied name"
        type="search"
        value={value}
      />
      {normalized ? (
        <Button asChild type="button" size="sm" variant="outline">
          <Link href="/">Clear</Link>
        </Button>
      ) : null}
    </div>
  );
}
