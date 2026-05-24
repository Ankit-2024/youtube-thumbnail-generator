import { useState } from "react";
import "./App.css";

const API_URL = "https://uznzieth25.execute-api.us-west-2.amazonaws.com/prod/generate";

export default function App() {
  const [idea, setIdea] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const generate = async () => {
    if (!idea.trim()) return;
    setLoading(true);
    setResult(null);
    setError(null);

    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_idea: idea }),
      });
      const data = await res.json();
      if (data.url) {
        setResult(data);
      } else {
        setError(data.error || "Something went wrong.");
      }
    } catch (err) {
      setError("Failed to connect to the API.");
    } finally {
      setLoading(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !loading) generate();
  };

  return (
    <div className="app">
      {/* Background grid */}
      <div className="bg-grid" />

      {/* Header */}
      <header className="header">
        <div className="header-badge">AI POWERED</div>
        <h1 className="title">
          <span className="title-yt">YT</span>
          <span className="title-thumb">Thumbnail</span>
          <span className="title-gen">Generator</span>
        </h1>
        <p className="subtitle">
          Type a video idea. Get a scroll-stopping thumbnail in seconds.
        </p>
      </header>

      {/* Input section */}
      <main className="main">
        <div className="input-wrapper">
          <div className="input-label">YOUR VIDEO IDEA</div>
          <div className="input-row">
            <input
              className="idea-input"
              type="text"
              placeholder="e.g. 10 tips to learn Python faster"
              value={idea}
              onChange={(e) => setIdea(e.target.value)}
              onKeyDown={handleKey}
              disabled={loading}
            />
            <button
              className={`generate-btn ${loading ? "loading" : ""}`}
              onClick={generate}
              disabled={loading || !idea.trim()}
            >
              {loading ? (
                <span className="spinner-wrap">
                  <span className="spinner" />
                  Generating
                </span>
              ) : (
                "Generate →"
              )}
            </button>
          </div>
          {loading && (
            <div className="progress-bar">
              <div className="progress-fill" />
            </div>
          )}
          {loading && (
            <p className="loading-note">
              ⚡ Calling Claude + Stable Diffusion 3.5 — usually 30–50s
            </p>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="error-card">
            <span className="error-icon">⚠</span> {error}
          </div>
        )}

        {/* Result */}
        {result && (
          <div className="result-section">
            <div className="result-header">
              <div className="result-label">GENERATED THUMBNAIL</div>
              <div className="result-title-badge">{result.title}</div>
            </div>
            <div className="thumbnail-frame">
              <img
                src={result.url}
                alt={result.title}
                className="thumbnail-img"
              />
              <div className="thumbnail-overlay">
                <a
                  href={result.url}
                  download="thumbnail.jpg"
                  target="_blank"
                  rel="noreferrer"
                  className="download-btn"
                >
                  ↓ Download Thumbnail
                </a>
              </div>
            </div>
            <div className="result-meta">
              1280 × 720 · JPEG · AI Generated · Powered by AWS Bedrock
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="footer">
        Built with AWS Lambda · API Gateway · S3 · Bedrock
      </footer>
    </div>
  );
}
