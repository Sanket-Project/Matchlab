# Local model discovery — 10 November 2026

**Superseded setup status:** The initial audit below is retained as a historical record. Official TabICLv2 classifier/regressor and Amazon Chronos-Bolt Small weights have now been downloaded, publisher-hash verified, installed on D: and tested with actual offline CPU inference. Real historical data for all six sports is installed. See [INSTALLATION.md](INSTALLATION.md), [DATA_SOURCES.md](DATA_SOURCES.md) and [EVALUATION.md](EVALUATION.md) for current paths, coverage, measured results and remaining player-data gaps.

The initial project folder `D:\Sports Prediction` contained no code, datasets or model artifacts.

A recursive filename search with ripgrep was run across `D:\` and `C:\Users\admin` for ONNX, joblib, pickle, PyTorch, Keras/HDF5, safetensors, GGUF, CatBoost artifacts and model-named JSON files. Git folders, node_modules and Codex session archives were excluded. The search did not identify sports-specific artifacts. Some unreadable folders may have been skipped; models in other drives, extensionless stores, or unknown formats are not ruled out.

A supplementary search for CKPT, UBJ, XGB, and TFLite artifacts found browser optimization/OCR models, with no sports-specific artifacts identifiable by location or filename. These files were not loaded.

Notable existing candidates (not loaded):

- `D:\DevCache\huggingface\hub\models--openbmb--VoxCPM2\...`: speech generation weights and audio VAE.
- `D:\DevCache\huggingface\hub\models--k2-fsa--OmniVoice\...`: voice/audio models and tokenizer.
- `C:\Users\admin\AppData\Roaming\Code\chatDictationModels\Microsoft\nemotron-3.5-asr-streaming-0.6b-generic-cpu-3\v3\...`: NVIDIA-based speech recognition ONNX encoder/decoder/joint and VAD.
- `C:\Users\admin\.rembg\models\...`: background-removal/segmentation ONNX models.
- Editor-assistance models, NumPy/joblib/ONNX/statistics package test fixtures, Python `.pth` environment configuration files and model-list metadata.

These filenames/locations identify unrelated tasks; no evidence establishes a compatible sports winner, score, or player-threat model. No arbitrary pickle or model code was executed to investigate them. No file was changed, uploaded or downloaded. No external service was consulted.

Default Python is 3.14.5. numpy and pandas are available; joblib/scikit-learn, torch, TensorFlow and onnxruntime are not installed in that interpreter. The dashboard uses Python's standard library; optional adapters require an appropriate prepared environment and compatible local artifacts.

The application therefore starts in clearly marked synthetic demo/reference mode, with genuine ML inference available after compatible local artifacts and their schema are connected.
