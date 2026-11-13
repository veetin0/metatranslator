"""Sign recognition (M1.1): REST-based segmenter, PopSign + own-clip prototype kNN, calibrated confidence + top-2.

    from signer_core.model import build_classifier, Recognizer
    rec = Recognizer(build_classifier())            # fits on data/landmarks + data/popsign/landmarks
    pred = rec.push(frame75, ts_ms)                 # Prediction | None, one per signed segment (REST dropped)
    pred.gloss, pred.confidence, pred.tier, pred.alternatives

Eval API (eval/run.py): KNNClassifier().fit(list_of_xyz, glosses); .predict(xyz, top=3) -> [(gloss, conf)];
.predict_proba(xyz) -> {gloss: conf}; .calibrate(held_out_xyz, glosses). numpy only (no mediapipe needed).
"""
from .data import Dataset, clip_paths, load_dataset, read_vocab
from .knn import KNNClassifier, hands_present, mirror, trim_active
from .recognizer import Prediction, Recognizer, build_classifier, classify
from .segmenter import Segment, Segmenter, is_up

__all__ = [
    "Dataset", "clip_paths", "load_dataset", "read_vocab",
    "KNNClassifier", "hands_present", "mirror", "trim_active",
    "Prediction", "Recognizer", "build_classifier", "classify",
    "Segment", "Segmenter", "is_up",
]
