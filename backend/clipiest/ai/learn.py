"""Self-learning personalization loop for Clipiest: Ridge regression on user star ratings."""
import json
import time
from pathlib import Path
import numpy as np

FEATURES = ['loud', 'shout', 'words', 'motion', 'flash', 'strobe', 'cuts', 'llm', 'chat']
DEFAULT_WEIGHTS = {
    'loud': 0.17, 'shout': 0.13, 'words': 0.20,
    'motion': 0.17, 'flash': 0.08, 'strobe': 0.04, 'cuts': 0.03,
    'llm': 0.18, 'chat': 0.14
}
MIN_RATINGS = 8

def _paths(data_dir: Path):
    return data_dir / "feedback.jsonl", data_dir / "weights.json"

def load_weights(data_dir: Path) -> dict:
    _, wp = _paths(data_dir)
    try:
        w = json.loads(wp.read_text(encoding="utf-8"))
        return {k: float(w.get(k, DEFAULT_WEIGHTS[k])) for k in FEATURES}
    except Exception:
        return dict(DEFAULT_WEIGHTS)

def compute_rank_score(features: dict, weights: dict) -> float:
    """Calculates weighted mean score across available features."""
    num = 0.0
    den = 0.0
    for k in FEATURES:
        val = features.get(k)
        if val is not None:
            w = weights.get(k, DEFAULT_WEIGHTS[k])
            num += w * float(val)
            den += w
    return num / den if den > 0 else 0.5

def record_feedback(data_dir: Path, clip_id: str, rating: int, features: dict, extra: dict = None) -> dict:
    """Records a 1-5 star user rating and triggers weight refitting."""
    fp, _ = _paths(data_dir)
    row = {
        "t": int(time.time()),
        "file": clip_id,
        "rating": int(rating),
        "features": features,
        **(extra or {})
    }
    with fp.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return refit_weights(data_dir)

def refit_weights(data_dir: Path) -> dict:
    """Fits ridge regression model on user ratings shrunk toward defaults."""
    fp, wp = _paths(data_dir)
    rows = []
    if fp.exists():
        for line in fp.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                if r.get("features"):
                    rows.append(r)
            except Exception:
                pass
                
    n = len(rows)
    summary = {"ratings": n, "weights": dict(DEFAULT_WEIGHTS), "fitted": False}
    if n >= MIN_RATINGS:
        X = np.array([[float(r["features"].get(k) or 0.0) for k in FEATURES] for r in rows])
        y = np.array([(r["rating"] - 3) / 2.0 for r in rows])  # Normalized -1.0 to 1.0
        
        w0 = np.array([DEFAULT_WEIGHTS[k] for k in FEATURES])
        lam = 2.0
        Xc = X - X.mean(axis=0)
        A = Xc.T @ Xc + lam * np.eye(len(FEATURES))
        b = Xc.T @ y + lam * w0
        
        wf = np.clip(np.linalg.solve(A, b), 0.01, None)
        wf = wf / wf.sum()
        alpha = min(0.85, n / 60.0)
        w = (1 - alpha) * w0 + alpha * wf
        w = w / w.sum()
        
        summary.update({
            "weights": {k: round(float(v), 4) for k, v in zip(FEATURES, w)},
            "fitted": True,
            "alpha": round(alpha, 2)
        })
    wp.write_text(json.dumps(summary["weights"]), encoding="utf-8")
    return summary
