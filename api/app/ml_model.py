import os
import joblib
import logging
from typing import Dict, Any, Tuple
from app.config import settings
from app.schemas import IrisFeatures

logger = logging.getLogger(__name__)

class IrisInferenceEngine:
    def __init__(self, model_path: str = settings.MODEL_PATH):
        self.model_path = model_path
        self.model = None
        self.target_names = ["setosa", "versicolor", "virginica"]
        self.feature_names = ["sepal_length", "sepal_width", "petal_length", "petal_width"]
        self.model_version = "v1.0.0-fallback"
        self.load_model()

    def load_model(self):
        """Attempts to load the joblib serialized ML model."""
        if os.path.exists(self.model_path):
            try:
                artifact = joblib.load(self.model_path)
                if isinstance(artifact, dict) and "model" in artifact and artifact["model"] is not None:
                    self.model = artifact["model"]
                    self.target_names = artifact.get("target_names", self.target_names)
                    self.feature_names = artifact.get("feature_names", self.feature_names)
                    self.model_version = artifact.get("model_version", "v1.0.0-rf")
                    logger.info(f"[ML Model] Loaded trained model from {self.model_path} ({self.model_version})")
                else:
                    logger.info(f"[ML Model] Model artifact loaded (using fallback inference engine)")
            except Exception as e:
                logger.warning(f"[ML Model] Could not load model from {self.model_path}: {e}")
        else:
            logger.info(f"[ML Model] Model path {self.model_path} not found. Running built-in inference.")

    def predict(self, features: IrisFeatures) -> Tuple[str, float, Dict[str, float]]:
        """
        Executes model inference on input features.
        Returns:
            predicted_class (str)
            confidence (float)
            probabilities (dict)
        """
        raw_features = [
            features.sepal_length,
            features.sepal_width,
            features.petal_length,
            features.petal_width
        ]

        # Use scikit-learn model if loaded
        if self.model is not None:
            try:
                import numpy as np
                X = np.array([raw_features])
                pred_idx = int(self.model.predict(X)[0])
                predicted_class = self.target_names[pred_idx]

                if hasattr(self.model, "predict_proba"):
                    probs = self.model.predict_proba(X)[0]
                    confidence = float(np.max(probs))
                    probabilities = {
                        self.target_names[i]: float(probs[i])
                        for i in range(len(self.target_names))
                    }
                else:
                    confidence = 1.0
                    probabilities = {predicted_class: 1.0}

                return predicted_class, round(confidence, 4), probabilities
            except Exception as e:
                logger.error(f"[ML Model] scikit-learn prediction error: {e}. Falling back to rule-based.")

        # Fallback decision-tree logic based on standard Iris feature boundaries
        # Iris-setosa is linearly separable by petal_length < 2.5
        pl = features.petal_length
        pw = features.petal_width

        if pl < 2.5:
            predicted_class = "setosa"
            confidence = 0.99
            probabilities = {"setosa": 0.99, "versicolor": 0.01, "virginica": 0.00}
        elif pw < 1.75:
            predicted_class = "versicolor"
            confidence = 0.92
            probabilities = {"setosa": 0.01, "versicolor": 0.92, "virginica": 0.07}
        else:
            predicted_class = "virginica"
            confidence = 0.95
            probabilities = {"setosa": 0.00, "versicolor": 0.05, "virginica": 0.95}

        return predicted_class, confidence, probabilities

# Global singleton instance
inference_engine = IrisInferenceEngine()

