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

export type ContextItem = {
  article_no: string;
  article_index: number;
  text: string;
  is_target: boolean;
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

export async function fetchContext(
  lawName: string,
  articleIndex: number,
  span = 2,
): Promise<ContextItem[]> {
  const params = new URLSearchParams({
    law_name: lawName,
    article_index: String(articleIndex),
    span: String(span),
  });
  const response = await fetch(`${API_BASE}/api/statutes/context?${params}`);
  if (!response.ok) {
    throw new Error(`读取上下文失败：HTTP ${response.status}`);
  }
  return (await response.json()) as ContextItem[];
}

export type JudgmentHit = {
  case_no: string;
  court: string;
  trial_level: string;
  judgment_date: string | null;
  cause: string | null;
  project_type: string | null;
  dispute_types: string[];
  cited_statutes: string[];
  holding: string;
  reasoning: string | null;
  source_url: string | null;
};

export type JudgmentSearchResponse = {
  items: JudgmentHit[];
  total: number;
  terms: string[];
};

export async function searchJudgments(
  query: string,
  limit = 10,
  offset = 0,
): Promise<JudgmentSearchResponse> {
  const params = new URLSearchParams({
    q: query,
    limit: String(limit),
    offset: String(offset),
  });
  const response = await fetch(`${API_BASE}/api/judgments/search?${params}`);
  if (!response.ok) {
    throw new Error(`类案检索失败：HTTP ${response.status}`);
  }
  return (await response.json()) as JudgmentSearchResponse;
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
