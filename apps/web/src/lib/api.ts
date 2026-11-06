export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8010";

export type StatuteHit = {
  law_name: string;
  article_no: string;
  article_index: number;
  text: string;
  source_url: string;
  score: number;
};

export type SearchResponse = {
  items: StatuteHit[];
  total: number;
  terms: string[];
};

export type LawSource = {
  law_name: string;
  level: string;
  version: string | null;
  effective_date: string | null;
  source_url: string;
  fetched_at: string;
  article_count: number;
};

export async function fetchSources(): Promise<LawSource[]> {
  const response = await fetch(`${API_BASE}/api/statutes/sources`);
  if (!response.ok) {
    throw new Error(`读取清单失败：HTTP ${response.status}`);
  }
  return (await response.json()) as LawSource[];
}

export async function searchStatutes(
  query: string,
  limit = 10,
  offset = 0,
): Promise<SearchResponse> {
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
    offset: String(offset),
  });
  const response = await fetch(`${API_BASE}/api/statutes/search?${params}`);
  if (!response.ok) {
    throw new Error(`检索失败：HTTP ${response.status}`);
  }
  return (await response.json()) as SearchResponse;
}
