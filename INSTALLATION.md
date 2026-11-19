# Installed local inference

CPU Python 3.12 environment: `.venv`. Official libraries are pinned in requirements-lock.txt. TabICL 2.2.0, chronos-forecasting 2.3.2, PyTorch 2.15.0+cpu and transformers 4.57.6. Base Python 3.12 was already installed on C:; the environment, dependencies, model files, raw data and caches are on D:. Shared uv cache: D:\DevCache\uv-cache.

| Original publisher file | Bytes | SHA-256 |
| --- | --- | --- |
| models/tabicl/tabicl-classifier-v2-20260212.ckpt | 110368038 | bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0 |
| models/tabicl/tabicl-regressor-v2-20260212.ckpt | 114324594 | 0db9cb538f114e79026bf08f45f41ad8dd7ad2de2aaca9a5ca8cd3bd9748ae7a |
| models/chronos-bolt-small/model.safetensors | 190888824 | 06a6a19bbe74bc10a9cd193bd4bf2bf638ae07f7e0d51653ae7ab8ea968a21dd |
| models/chronos-bolt-small/config.json | 1121 | 9ca0ebbe049ccebacb0546361e8aa728f0cf104cd18d1838d78d296aa317bd21 |

All three large weights match the publishers' LFS SHA-256. Models and config are pinned to repository revisions in models/manifest.json. The manifest retains download URLs and metadata.

| Directory | Logical bytes | MiB |
| --- | --- | --- |
| models | 415599826 | 396.35 |
| .venv | 900717775 | 858.99 |
| data/raw | 17726358 | 16.91 |
| data/real | 3196972 | 3.05 |
| artifacts | 969104 | 0.92 |
| .cache | 0 | 0.00 |
| project_total_logical_bytes | 1339347777 | 1277.30 |

Directory sizes are logical file lengths. The environment can share hardlinked package content with the pre-existing uv cache, so these numbers are not a claim of unique newly allocated disk blocks. The shared cache's pre-existing unrelated contents are excluded.

Restart: `Set-Location 'D:\Sports Prediction'; .\.venv\Scripts\python.exe app.py --port 8766 --open` (or start.cmd). Local URL: http://127.0.0.1:8766. The earlier demo server on 8765 is left alone.

For the managed background server, run `.\restart.ps1` from the project directory. It verifies the recorded process identity, stops only this dashboard's process tree, checks the port, restarts hidden, and opens the browser. Use `-NoOpen` to skip another browser tab. This restart path was tested successfully.
