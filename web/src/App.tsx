import { useCallback, useMemo, useState } from "react";
import "./App.css";

type RunRow = {
  run: number;
  tcr_pct: number | null;
  rqd_pct: number | null;
  pieces: number;
};

type DebugImage = {
  filename: string;
  mime: string;
  data_b64: string;
};

type AnalyzeResponse = {
  ok: boolean;
  runs: RunRow[];
  debug_images: DebugImage[];
  raw?: unknown;
  warning?: string;
};

const RQD_LOW = 50;

const API_BASE = import.meta.env.VITE_API_URL ?? "";

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const onPick = useCallback((f: File | null) => {
    setError(null);
    setResult(null);
    setFile(f);
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return f ? URL.createObjectURL(f) : null;
    });
  }, []);

  const analyze = useCallback(async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`${API_BASE}/api/analyze`, {
        method: "POST",
        body,
      });
      const data = (await res.json()) as AnalyzeResponse & { detail?: string };
      if (!res.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : res.statusText || "Request failed"
        );
      }
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  }, [file]);

  const debugSrc = useMemo(() => {
    if (!result?.debug_images?.length) return [];
    return result.debug_images.map((d) => ({
      filename: d.filename,
      src: `data:${d.mime};base64,${d.data_b64}`,
    }));
  }, [result]);

  const stats = useMemo(() => {
    const runs = result?.runs;
    if (!runs?.length) return null;
    const tcrVals = runs.map((r) => r.tcr_pct).filter((x): x is number => x != null);
    const rqdVals = runs.map((r) => r.rqd_pct).filter((x): x is number => x != null);
    const avg = (a: number[]) =>
      a.length ? a.reduce((s, x) => s + x, 0) / a.length : null;
    return {
      runs: runs.length,
      avgTcr: avg(tcrVals),
      avgRqd: avg(rqdVals),
      pieces: runs.reduce((s, r) => s + r.pieces, 0),
    };
  }, [result]);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const f = e.dataTransfer.files?.[0];
      if (f?.type.startsWith("image/")) onPick(f);
    },
    [onPick]
  );

  return (
    <div className="app">
      <div className="bg-mesh" aria-hidden />
      <div className="grain" aria-hidden />

      <div className="shell">
        <header className="hero">
          <div className="hero-top">
            <span className="badge">
              <span className="badge-dot" />
              Geotechnical CV
            </span>
          </div>
          <h1 className="hero-title">
            TCR <span className="hero-amp">&amp;</span> RQD
          </h1>
          <p className="hero-lead">
            Measure Total Core Recovery and Rock Quality Designation from borehole
            core box imagery calibrated scale, run detection, and piece metrics in
            one flow.
          </p>
        </header>

        <div className="bento">
          <section className="card card-upload">
            <div className="card-head">
              <span className="card-label">Input</span>
              <h2 className="card-title">Core photograph</h2>
            </div>

            <label
              className={`dropzone ${dragOver ? "dropzone--active" : ""} ${file ? "dropzone--filled" : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
            >
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp,image/bmp,image/tiff"
                onChange={(e) => onPick(e.target.files?.[0] ?? null)}
              />
              <span className="dropzone-icon" aria-hidden>
                <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
                  <path
                    d="M12 28h16M20 10v12m0 0l4-4m-4 4l-4-4"
                    stroke="currentColor"
                    strokeWidth="1.75"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <rect
                    x="5"
                    y="5"
                    width="30"
                    height="30"
                    rx="8"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    opacity="0.35"
                  />
                </svg>
              </span>
              <span className="dropzone-text">
                {file ? (
                  <>
                    <strong className="dropzone-name">{file.name}</strong>
                    <span className="dropzone-hint">Click or drop to replace</span>
                  </>
                ) : (
                  <>
                    <strong>Drop an image here</strong>
                    <span className="dropzone-hint">or click to browse — JPG, PNG, WebP</span>
                  </>
                )}
              </span>
            </label>

            {previewUrl && (
              <div className="preview">
                <div className="preview-frame">
                  <img src={previewUrl} alt="" />
                </div>
              </div>
            )}
          </section>

          <aside className="card card-side">
            <div className="card-head">
              <span className="card-label">Action</span>
              <h2 className="card-title">Run pipeline</h2>
            </div>
            <p className="side-copy">
              Segments runs, estimates lengths from scale, and aggregates TCR/RQD per
              1.5 m interval.
            </p>
            <button
              type="button"
              className="btn-primary"
              disabled={!file || loading}
              onClick={() => void analyze()}
            >
              {loading ? (
                <span className="btn-inner">
                  <span className="btn-spinner" />
                  Analyzing…
                </span>
              ) : (
                "Analyze image"
              )}
            </button>
            {!file && (
              <p className="side-foot muted">Select a core box photo to enable analysis.</p>
            )}
          </aside>
        </div>

        {error && (
          <div className="alert alert--error" role="alert">
            <span className="alert-title">Something went wrong</span>
            {error}
          </div>
        )}

        {result && (
          <>
            {stats && (
              <div className="stats">
                <div className="stat">
                  <span className="stat-label">Runs</span>
                  <span className="stat-value mono">{stats.runs}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Avg. TCR</span>
                  <span className="stat-value mono">
                    {stats.avgTcr != null ? `${stats.avgTcr.toFixed(1)}%` : "—"}
                  </span>
                </div>
                <div className="stat">
                  <span className="stat-label">Avg. RQD</span>
                  <span className="stat-value mono">
                    {stats.avgRqd != null ? `${stats.avgRqd.toFixed(1)}%` : "—"}
                  </span>
                </div>
                <div className="stat">
                  <span className="stat-label">Pieces (total)</span>
                  <span className="stat-value mono">{stats.pieces}</span>
                </div>
              </div>
            )}

            <section className="card card-results">
              <div className="card-head card-head--row">
                <div>
                  <span className="card-label">Output</span>
                  <h2 className="card-title">Per-run metrics</h2>
                </div>
                {result.runs?.length ? (
                  <span className="pill pill--subtle">
                    RQD &lt; {RQD_LOW}% highlighted
                  </span>
                ) : null}
              </div>

              {result.warning && (
                <div className="alert alert--warn">{result.warning}</div>
              )}

              {result.runs?.length > 0 ? (
                <div className="table-shell">
                  <table>
                    <thead>
                      <tr>
                        <th>Run</th>
                        <th>TCR</th>
                        <th>RQD</th>
                        <th>Pieces</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.runs.map((r, i) => {
                        const low = r.rqd_pct != null && r.rqd_pct < RQD_LOW;
                        return (
                          <tr key={`${r.run}-${i}`} className={low ? "row--warn" : undefined}>
                            <td>
                              <span className="run-pill mono">{r.run}</span>
                            </td>
                            <td className="mono">{fmtPct(r.tcr_pct)}</td>
                            <td className="mono">
                              {low && <span className="warn-dot" title="Low RQD" />}
                              {fmtPct(r.rqd_pct)}
                            </td>
                            <td className="mono">{r.pieces}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                result.raw != null && (
                  <pre className="raw-block mono">{JSON.stringify(result.raw, null, 2)}</pre>
                )
              )}
            </section>
          </>
        )}

        {result && debugSrc.length > 0 && (
          <section className="card card-debug">
            <div className="card-head">
              <span className="card-label">Diagnostics</span>
              <h2 className="card-title">Debug visualization</h2>
              <p className="card-desc">
                Overlay views from the analysis pipeline (scale, runs, pieces).
              </p>
            </div>
            <div className="debug-grid">
              {debugSrc.map((d) => (
                <figure key={d.filename} className="debug-card">
                  <div className="debug-img-wrap">
                    <img src={d.src} alt="" loading="lazy" />
                  </div>
                  <figcaption className="mono">{d.filename}</figcaption>
                </figure>
              ))}
            </div>
          </section>
        )}
      </div>

      <footer className="site-foot">
        <span>TCR &amp; RQD Analyzer</span>
        <span className="foot-dot" />
        <span className="muted">Made by Mouad</span>
      </footer>
    </div>
  );
}

function fmtPct(v: number | null): string {
  if (v == null) return "—";
  return Number.isInteger(v) ? `${v}%` : `${v.toFixed(2)}%`;
}
