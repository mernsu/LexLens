"use client";

import { type FormEvent, useEffect, useState } from "react";

import {
  fetchContext,
  fetchSources,
  searchJudgments,
  searchStatutes,
  type ContextItem,
  type JudgmentSearchResponse,
  type LawSource,
  type SearchResponse,
  type StatuteHit,
} from "@/lib/api";

const PAGE_SIZE = 10;

function escapeRegExp(word: string): string {
  return word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function Highlighted({ text, terms }: { text: string; terms: string[] }) {
  const words = terms.filter((term) => term.length >= 2);
  if (words.length === 0) {
    return <>{text}</>;
  }
  const pattern = new RegExp(`(${words.map(escapeRegExp).join("|")})`, "g");
  const parts = text.split(pattern);
  return (
    <>
      {parts.map((part, index) =>
        words.includes(part) ? <mark key={index}>{part}</mark> : part,
      )}
    </>
  );
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [sources, setSources] = useState<LawSource[]>([]);
  const [offset, setOffset] = useState(0);
  const [copied, setCopied] = useState<string | null>(null);
  const [contexts, setContexts] = useState<Record<string, ContextItem[]>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"statute" | "judgment">("statute");
  const [judgmentQuery, setJudgmentQuery] = useState("");
  const [judgmentResult, setJudgmentResult] = useState<JudgmentSearchResponse | null>(null);
  const [judgmentOffset, setJudgmentOffset] = useState(0);
  const [judgmentLoading, setJudgmentLoading] = useState(false);
  const [judgmentError, setJudgmentError] = useState<string | null>(null);

  useEffect(() => {
    fetchSources()
      .then(setSources)
      .catch(() => setSources([]));
  }, []);

  async function runSearch(text: string, nextOffset: number) {
    setLoading(true);
    setError(null);
    try {
      setResult(await searchStatutes(text, PAGE_SIZE, nextOffset));
      setOffset(nextOffset);
    } catch (cause) {
      setError(String(cause));
    } finally {
      setLoading(false);
    }
  }

  async function runJudgmentSearch(text: string, nextOffset: number) {
    setJudgmentLoading(true);
    setJudgmentError(null);
    try {
      setJudgmentResult(await searchJudgments(text, PAGE_SIZE, nextOffset));
      setJudgmentOffset(nextOffset);
    } catch (cause) {
      setJudgmentError(String(cause));
    } finally {
      setJudgmentLoading(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (tab === "statute") {
      const trimmed = query.trim();
      if (trimmed && !loading) {
        void runSearch(trimmed, 0);
      }
      return;
    }
    const trimmed = judgmentQuery.trim();
    if (trimmed && !judgmentLoading) {
      void runJudgmentSearch(trimmed, 0);
    }
  }

  async function copyText(key: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      window.setTimeout(() => setCopied(null), 1500);
    } catch {
      setError("复制失败：浏览器拒绝访问剪贴板");
    }
  }

  async function toggleContext(hit: StatuteHit) {
    const key = `${hit.law_name}#${hit.article_index}`;
    if (contexts[key]) {
      setContexts((previous) => {
        const next = { ...previous };
        delete next[key];
        return next;
      });
      return;
    }
    try {
      const items = await fetchContext(hit.law_name, hit.article_index);
      setContexts((previous) => ({ ...previous, [key]: items }));
    } catch (cause) {
      setError(String(cause));
    }
  }

  const total = result?.total ?? 0;
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pages = Math.ceil(total / PAGE_SIZE);
  const judgmentTotal = judgmentResult?.total ?? 0;
  const judgmentPage = Math.floor(judgmentOffset / PAGE_SIZE) + 1;
  const judgmentPages = Math.ceil(judgmentTotal / PAGE_SIZE);

  const isStatute = tab === "statute";
  const activeQuery = isStatute ? query : judgmentQuery;
  const activeLoading = isStatute ? loading : judgmentLoading;

  return (
    <main>
      <h1>LexLens 法律检索</h1>
      <p className="subtitle">
        民法典 · 建工司法解释（一）· 建筑法 · 招标投标法 · 招标投标法实施条例 · 建设工程质量管理条例
      </p>

      <div className="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={isStatute}
          className={isStatute ? "tab tab-active" : "tab"}
          onClick={() => setTab("statute")}
        >
          法条
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={!isStatute}
          className={isStatute ? "tab" : "tab tab-active"}
          onClick={() => setTab("judgment")}
        >
          类案
        </button>
      </div>

      <form className="search-form" onSubmit={handleSubmit}>
        <input
          value={activeQuery}
          onChange={(event) =>
            isStatute
              ? setQuery(event.target.value)
              : setJudgmentQuery(event.target.value)
          }
          placeholder={
            isStatute
              ? "例如：建设工程价款优先受偿权"
              : "例如：实际施工人 工程款"
          }
          aria-label={isStatute ? "法条检索关键词" : "类案检索关键词"}
        />
        <button type="submit" disabled={activeLoading || !activeQuery.trim()}>
          {activeLoading ? "检索中…" : "检索"}
        </button>
      </form>

      {isStatute && (
        <>
      {error && <p className="error">{error}</p>}

      {!error && result && total === 0 && (
        <p className="hint">未检索到条文。换个说法，或用更短的词。</p>
      )}

      {!error && !result && (
        <p className="hint">输入争议关键词，返回条文原文与来源链接。</p>
      )}

      {result && total > 0 && (
        <p className="hint">
          命中 {total} 条，按相关度排序，命中词已标色。
        </p>
      )}

      <div className="result-list">
        {result?.items.map((hit) => {
          const key = `${hit.law_name}#${hit.article_index}`;
          const context = contexts[key];
          return (
            <article className="result" key={key}>
              <div className="result-head">
                <span className="article">{hit.article_no}</span>
                <span className="law">{hit.law_name}</span>
              </div>
              <p className="result-text">
                <Highlighted text={hit.text} terms={result.terms} />
              </p>
              <p className="result-foot">
                来源：{" "}
                <a href={hit.source_url} target="_blank" rel="noreferrer">
                  原文页面
                </a>
                <button
                  type="button"
                  className="copy"
                  onClick={() => void toggleContext(hit)}
                >
                  {context ? "收起上下文" : "查看上下文"}
                </button>
                <button
                  type="button"
                  className="copy"
                  onClick={() => void copyText(key, `《${hit.law_name}》${hit.article_no}`)}
                >
                  {copied === key ? "已复制" : "复制引用"}
                </button>
              </p>
              {context && (
                <div className="context">
                  <div className="context-head">
                    <span>前后各 2 条</span>
                    <button
                      type="button"
                      className="copy"
                      onClick={() => void copyText(`raw:${key}`, hit.text)}
                    >
                      {copied === `raw:${key}` ? "已复制" : "复制原文"}
                    </button>
                  </div>
                  {context.map((item) => (
                    <div
                      key={item.article_index}
                      className={item.is_target ? "ctx-item ctx-current" : "ctx-item"}
                    >
                      <span className="ctx-no">{item.article_no}</span>
                      <p>{item.text}</p>
                    </div>
                  ))}
                </div>
              )}
            </article>
          );
        })}
      </div>

      {result && pages > 1 && (
        <div className="pager">
          <button
            type="button"
            disabled={loading || page <= 1}
            onClick={() => void runSearch(query.trim(), offset - PAGE_SIZE)}
          >
            上一页
          </button>
          <span>
            第 {page} / {pages} 页
          </span>
          <button
            type="button"
            disabled={loading || page >= pages}
            onClick={() => void runSearch(query.trim(), offset + PAGE_SIZE)}
          >
            下一页
          </button>
        </div>
      )}
        </>
      )}

      {!isStatute && (
        <>
          {judgmentError && <p className="error">{judgmentError}</p>}

          {!judgmentError && judgmentResult && judgmentTotal === 0 && (
            <p className="hint">
              案例库中未找到匹配文书。若库为空，先用入库命令导入裁判文书。
            </p>
          )}

          {!judgmentError && !judgmentResult && (
            <p className="hint">输入争议关键词，返回类案要旨、审级与引用法条。</p>
          )}

          {judgmentResult && judgmentTotal > 0 && (
            <p className="hint">命中 {judgmentTotal} 篇，按相关度排序，命中词已标色。</p>
          )}

          <div className="result-list">
            {judgmentResult?.items.map((hit) => {
              const key = `case:${hit.case_no}`;
              return (
                <article className="result" key={key}>
                  <div className="result-head">
                    <span className="article">{hit.case_no}</span>
                    <span className="law">
                      {hit.trial_level} · {hit.court}
                    </span>
                  </div>
                  <p className="meta">
                    {hit.judgment_date ? `裁判日期 ${hit.judgment_date}` : "裁判日期未记录"}
                    {" · "}
                    {hit.cause ?? "案由未记录"}
                    {hit.project_type ? ` · ${hit.project_type}` : ""}
                  </p>
                  {hit.dispute_types.length > 0 && (
                    <div className="tags">
                      {hit.dispute_types.map((tag) => (
                        <span className="tag" key={tag}>
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                  <p className="result-text">
                    <Highlighted text={hit.holding} terms={judgmentResult.terms} />
                  </p>
                  {hit.reasoning && (
                    <p className="result-sub">
                      <Highlighted text={hit.reasoning} terms={judgmentResult.terms} />
                    </p>
                  )}
                  {hit.cited_statutes.length > 0 && (
                    <p className="meta">引用法条：{hit.cited_statutes.join("；")}</p>
                  )}
                  <p className="result-foot">
                    {hit.source_url ? (
                      <a href={hit.source_url} target="_blank" rel="noreferrer">
                        原文页面
                      </a>
                    ) : (
                      <span>无原文链接</span>
                    )}
                    <button
                      type="button"
                      className="copy"
                      onClick={() => void copyText(key, hit.case_no)}
                    >
                      {copied === key ? "已复制" : "复制案号"}
                    </button>
                  </p>
                </article>
              );
            })}
          </div>

          {judgmentResult && judgmentPages > 1 && (
            <div className="pager">
              <button
                type="button"
                disabled={judgmentLoading || judgmentPage <= 1}
                onClick={() =>
                  void runJudgmentSearch(judgmentQuery.trim(), judgmentOffset - PAGE_SIZE)
                }
              >
                上一页
              </button>
              <span>
                第 {judgmentPage} / {judgmentPages} 页
              </span>
              <button
                type="button"
                disabled={judgmentLoading || judgmentPage >= judgmentPages}
                onClick={() =>
                  void runJudgmentSearch(judgmentQuery.trim(), judgmentOffset + PAGE_SIZE)
                }
              >
                下一页
              </button>
            </div>
          )}
        </>
      )}

      <section className="sources">
        <h2>知识库版本</h2>
        <ul>
          {sources.map((source) => (
            <li key={source.law_name}>
              <a href={source.source_url} target="_blank" rel="noreferrer">
                {source.law_name}
              </a>
              <span>
                {source.version ?? "版本未记录"} · {source.article_count} 条 · 生效{" "}
                {source.effective_date ?? "未记录"}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <p className="notice">
        辅助法律研究，不构成法律意见。条文引自公开发布文本，引用前请核对现行有效版本。
      </p>
    </main>
  );
}
