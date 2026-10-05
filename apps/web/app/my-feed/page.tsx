"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { PageContainer } from "@/components/ui";
import { loadMyFeed } from "@/lib/myFeed";

export default function MyFeed() {
  const router = useRouter();
  useEffect(() => {
    const f = loadMyFeed();
    router.replace(f ? `/manage/${f.publicToken}?token=${encodeURIComponent(f.editToken)}` : "/calendar/create");
  }, [router]);
  return <PageContainer><p className="py-24 text-text-secondary">Looking for your feed…</p></PageContainer>;
}
