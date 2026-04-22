/* Drop into your Review hub list view (Client Component). Wire fetchList to your real API. */

"use client";

import { useCallback, useState } from "react";
import { useReviewListOnOpen } from "./hooks/useReviewListOnOpen";

type Review = { id: string; body: string };

export function ReviewListWithAutoLoad() {
  const [items, setItems] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/reviews", { cache: "no-store" });
      if (!res.ok) throw new Error(String(res.status));
      const data = (await res.json()) as { items: Review[] };
      setItems(data.items ?? []);
    } finally {
      setLoading(false);
    }
  }, []);

  useReviewListOnOpen(fetchList);

  if (loading && items.length === 0) return <p>Loading…</p>;
  return (
    <ul>
      {items.map((r) => (
        <li key={r.id}>{r.body}</li>
      ))}
    </ul>
  );
}
