"""Read-only inference adapters. Nothing in this module fits or saves a model."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from .data import local_path

FORMATS = {"linear_json": None, "joblib": "joblib", "onnx": "onnxruntime", "torchscript": "torch", "keras": "tensorflow"}
TASKS = {"winner", "team_score", "player_score", "player_threat"}


def finite(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Model returned a non-finite output")
    return result


class ModelRegistry:
    def __init__(self, configs, root):
        if not isinstance(configs, dict) or not set(configs).issubset(TASKS):
            raise ValueError(f"Model tasks must be: {', '.join(sorted(TASKS))}")
        self.configs, self.root, self.cache = configs, root, {}

    def inspect(self, task):
        spec = self.configs.get(task)
        result = {"task": task, "state": "not_configured", "message": "Connect a local model", "path": None}
        if not spec:
            return result
        try:
            if not isinstance(spec, dict):
                raise ValueError("Model configuration must be an object")
            fmt = spec.get("format")
            if fmt in ("tabicl_classifier", "tabicl_regressor"):
                from .pretrained import inspect_tabicl
                return inspect_tabicl(task, spec, self.root)
            if fmt in ("trained_logistic", "trained_elo", "trained_ensemble", "trained_ridge"):
                from .trained import inspect_trained
                return inspect_trained(task, spec)
            if fmt not in FORMATS:
                raise ValueError(f"Supported formats: {', '.join(FORMATS)}")
            path = local_path(spec.get("path"), self.root)
            result["path"] = str(path)
            if not path.is_file():
                raise ValueError("Model file not found")
            if not isinstance(spec.get("features"), list) or not spec["features"] or len(set(spec["features"])) != len(spec["features"]):
                raise ValueError("Provide a unique ordered feature list matching the model's training schema")
            if fmt in ("joblib", "torchscript", "keras") and spec.get("trusted") is not True:
                raise ValueError("Only load trusted serialized models; set trusted: true after verifying their provenance")
            dependency = FORMATS[fmt]
            if dependency and importlib.util.find_spec(dependency) is None:
                raise ValueError(f"Runtime '{dependency}' is not installed in this Python environment; use a prepared offline environment")
            if task == "winner" and spec.get("labels") not in (["team", "opponent"], ["opponent", "team"], ["team", "draw", "opponent"], ["opponent", "draw", "team"], ["draw", "team", "opponent"], ["draw", "opponent", "team"], ["team", "opponent", "draw"], ["opponent", "team", "draw"]):
                raise ValueError("Winner labels must map output columns to team/opponent, optionally draw")
            result.update(state="available", message="File and runtime found; inference validates schema", format=fmt)
        except (ValueError, TypeError, ImportError) as exc:
            result.update(state="unavailable", message=str(exc))
        return result

    def _load(self, task):
        status = self.inspect(task)
        if status["state"] != "available":
            raise ValueError(status["message"])
        spec = self.configs[task]
        path = Path(status["path"])
        stat = path.stat()
        identity = (str(path), stat.st_mtime_ns, stat.st_size)
        if task in self.cache and self.cache[task][0] == identity:
            return self.cache[task][1:]
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        if spec.get("sha256") and digest.lower() != spec["sha256"].lower():
            raise ValueError("Model SHA-256 does not match configured checksum")
        fmt = spec["format"]
        if fmt == "linear_json":
            with path.open(encoding="utf-8") as handle:
                model = json.load(handle)
            if model.get("features") != spec["features"]:
                raise ValueError("Model feature order does not match configuration")
        elif fmt == "joblib":
            import joblib
            model = joblib.load(path)
        elif fmt == "onnx":
            import onnxruntime as ort
            model = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        elif fmt == "torchscript":
            import torch
            model = torch.jit.load(str(path), map_location="cpu").eval()
        else:
            import tensorflow as tf
            model = tf.keras.models.load_model(path, compile=False, safe_mode=True)
        self.cache[task] = (identity, model, digest)
        return model, digest

    def predict(self, task, features):
        model, digest = self._load(task)
        spec = self.configs[task]
        missing = [name for name in spec["features"] if name not in features or features[name] is None]
        if missing:
            raise ValueError("Missing feature values: " + ", ".join(missing))
        values = [finite(features[name]) for name in spec["features"]]
        fmt = spec["format"]
        if fmt == "linear_json":
            weights, biases = model.get("weights"), model.get("bias")
            if not isinstance(weights, list) or not isinstance(biases, list) or len(weights) != len(biases) or not weights:
                raise ValueError("linear_json requires weights [outputs, features] and bias [outputs]")
            if any(len(row) != len(values) for row in weights):
                raise ValueError("Model input dimension does not match feature count")
            outputs = [sum(finite(w) * x for w, x in zip(row, values)) + finite(b) for row, b in zip(weights, biases)]
            activation = model.get("activation", "identity")
            if activation == "softmax":
                exps = [math.exp(v - max(outputs)) for v in outputs]
                outputs = [v / sum(exps) for v in exps]
            elif activation == "sigmoid":
                outputs = [1 / (1 + math.exp(-max(-700, min(700, v)))) for v in outputs]
            elif activation != "identity":
                raise ValueError("Unsupported linear_json activation")
        else:
            import numpy as np
            array = np.asarray([values], dtype=spec.get("dtype", "float32"))
            if fmt == "joblib":
                if spec.get("input", "array") == "dataframe":
                    import pandas as pd
                    array = pd.DataFrame([values], columns=spec["features"])
                if hasattr(model, "feature_names_in_") and list(model.feature_names_in_) != spec["features"]:
                    raise ValueError("Serialized model feature names differ from the configured order")
                if task == "winner":
                    if not hasattr(model, "predict_proba"):
                        raise ValueError("Winner joblib models must implement predict_proba")
                    if "classes" not in spec or list(model.classes_) != spec["classes"]:
                        raise ValueError("Configure classes in the exact serialized model.classes_ order")
                    outputs = model.predict_proba(array)[0]
                else:
                    outputs = np.asarray(model.predict(array)).reshape(-1)
            elif fmt == "onnx":
                inputs = model.get_inputs()
                if len(inputs) != 1:
                    raise ValueError("ONNX adapter requires one numeric feature tensor; export preprocessing with the model")
                outputs = model.run(None, {inputs[0].name: array})[int(spec.get("output_index", 0))]
                if not hasattr(outputs, "shape"):
                    raise ValueError("ONNX ZipMap outputs are unsupported; export a dense numeric output")
                outputs = np.asarray(outputs).reshape(-1)
            elif fmt == "torchscript":
                import torch
                with torch.inference_mode():
                    outputs = model(torch.from_numpy(array)).cpu().numpy().reshape(-1)
            else:
                outputs = np.asarray(model(array, training=False)).reshape(-1)
            outputs = [finite(v) for v in outputs]
        outputs = [finite(v) for v in outputs]
        if task == "winner":
            labels = spec["labels"]
            if len(outputs) != len(labels) or any(v < 0 or v > 1 for v in outputs) or abs(sum(outputs) - 1) > 0.001:
                raise ValueError("Winner model must return probabilities summing to 1 in configured label order")
            result = dict(zip(labels, outputs))
        else:
            if len(outputs) != 1 or outputs[0] < 0:
                raise ValueError("Score/threat models must return one nonnegative scalar")
            if task == "player_threat" and outputs[0] > 1:
                raise ValueError("Threat model must return a probability between 0 and 1")
            result = outputs[0]
        return {"value": result, "source": "model", "model": Path(spec["path"]).name, "sha256": digest}
