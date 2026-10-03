import { useCallback, useEffect, useState } from "react";
import { fetchCommonsImages } from "@/api/client.js";

// Commons suggestions indexed by taxon. ImageGallery is unmounted and
// remounted on each sub-tab switch: keeping the cache here avoids a
// request on each return to "Image". Loading starts as soon as the
// taxon is known, without waiting for the sub-tab to open.
//
// No "loading" entry: ImageGallery treats a missing entry as loading.
export function useCommonsImages(taxon) {
  const [cache, setCache] = useState({});
  const hasEntry = taxon !== null && taxon in cache;

  useEffect(() => {
    if (!taxon || hasEntry) return;
    let cancelled = false;
    fetchCommonsImages(taxon)
      .then((data) => {
        if (!cancelled) setCache((prev) => ({ ...prev, [taxon]: { status: "ok", data } }));
      })
      .catch((err) => {
        if (cancelled) return;
        setCache((prev) => ({ ...prev, [taxon]: { status: "error", error: err.message || "Erreur inconnue." } }));
      });
    return () => {
      cancelled = true;
    };
  }, [taxon, hasEntry]);

  const reset = useCallback(() => setCache({}), []);
  const okEntries = () => Object.fromEntries(Object.entries(cache).filter(([, e]) => e.status === "ok"));

  return { cache, reset, restore: setCache, okEntries };
}
