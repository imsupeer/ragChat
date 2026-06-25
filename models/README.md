# Local Model Files

GGUF model weights are not bundled with this repository.

## Demo model (E4)

The default demo slot uses **Qwen2.5 1.5B Instruct GGUF** (`Q4_K_M`) from `Qwen/Qwen2.5-1.5B-Instruct-GGUF`. This is a small instruct model suitable for local demo/testing, not high-end reasoning. See the Qwen license and model card on Hugging Face before use.

### Explicit download (recommended)

```bash
python scripts/download_demo_model.py
python scripts/check_llama_cpp_runtime.py --strict
```

Or during start (E5 full workspace startup):

```bash
./start.sh --provider llama_cpp --download-model
```

```powershell
.\start.ps1 -Provider llama_cpp -DownloadModel
```

Downloads are **opt-in only**. The backend and frontend never download models automatically.

### Manual setup

1. Browse [llama.cpp-compatible models on Hugging Face](https://huggingface.co/models?apps=llama.cpp&sort=trending).
2. Choose a **GGUF** instruct/chat model.
3. Prefer `Q4_K_M` or `Q5_K_M` for constrained CPU/VRAM.
4. Save as `models/demo/model.gguf` or update `models/demo/model-manifest.json`.
5. Place `llama-server` in `runtime/bin/`.
6. Run `python scripts/check_llama_cpp_runtime.py --strict`.

Manifest fields:

- `models/demo/model-manifest.json` - download URL, recommended repo/file, optional `sha256`
- Local filename remains `model.gguf` even when the upstream file has a longer name

Checksum behavior:

- If `sha256` is set in the manifest, download/check scripts verify it.
- If `sha256` is empty, scripts verify basic file properties only and report `checksum_missing`.

Automatic download during normal app startup is not implemented.
