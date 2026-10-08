"""Trained Legal Machine Learning Classifier & RAG Context Scorer.

Loads the scikit-learn model trained in `train_model.py` and provides:
1. Inference classification for legal petitions, complaints, and notices.
2. Probability-based context scoring and routing for the RAG retrieval pipeline.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional
import joblib

from backend import config


MODEL_PATH = Path("data/models/legal_classifier.joblib")

_model = None


def get_trained_model():
    """Load or retrieve the serialized scikit-learn pipeline."""
    global _model
    if _model is None:
        if not MODEL_PATH.exists():
            from train_model import train_legal_model
            _model, _ = train_legal_model(str(MODEL_PATH))
        else:
            _model = joblib.load(MODEL_PATH)
    return _model


def predict_category(text: str) -> Dict[str, Any]:
    """Predicts legal document category and returns class probabilities."""
    model = get_trained_model()
    clean_text = (text or "").strip()
    if not clean_text:
        return {
            "predicted_class": "unknown",
            "confidence": 0.0,
            "probabilities": {},
        }

    probs = model.predict_proba([clean_text])[0]
    classes = model.classes_
    prob_dict = {cls: round(float(p), 4) for cls, p in zip(classes, probs)}
    top_class = model.predict([clean_text])[0]
    top_conf = round(float(max(probs)), 4)

    return {
        "text_preview": clean_text[:120],
        "predicted_class": top_class,
        "confidence": top_conf,
        "probabilities": prob_dict,
    }


def score_and_rerank_chunks(query: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Reranks retrieved candidate chunks by evaluating alignment between the query's
    predicted legal category and candidate passage categories.
    """
    if not chunks:
        return []

    query_pred = predict_category(query)
    target_class = query_pred["predicted_class"]

    scored_chunks = []
    for c in chunks:
        item = dict(c)
        c_pred = predict_category(c.get("text", ""))
        class_match_bonus = 0.15 if c_pred["predicted_class"] == target_class else 0.0
        
        # Combine existing fused/hybrid score with category alignment bonus
        base_score = float(item.get("fused_score") or item.get("score") or 0.5)
        item["trained_model_category"] = c_pred["predicted_class"]
        item["trained_model_conf"] = c_pred["confidence"]
        item["ml_boosted_score"] = round(base_score + class_match_bonus, 5)
        scored_chunks.append(item)

    scored_chunks.sort(key=lambda x: x["ml_boosted_score"], reverse=True)
    return scored_chunks


def get_model_info() -> Dict[str, Any]:
    """Returns metadata and parameters of the trained model."""
    model = get_trained_model()
    tfidf = model.named_steps.get("tfidf")
    clf = model.named_steps.get("clf")
    
    return {
        "model_type": "TF-IDF + Calibrated Logistic Regression",
        "library": "scikit-learn",
        "artifact_path": str(MODEL_PATH),
        "classes": list(model.classes_),
        "vocabulary_size": len(tfidf.vocabulary_) if tfidf else 0,
        "ngram_range": tfidf.ngram_range if tfidf else (1, 2),
        "status": "trained_and_operational",
    }
