# Local Runtime Directory

This folder holds local llama.cpp runtime artifacts. Binaries and logs are not committed.

## Layout

- `bin/` - place a local `llama-server` binary here (or set `LLAMA_CPP_SERVER_BIN`).
- `llama.cpp/` - PID file for a locally started `llama-server` process.
- `logs/` - runtime logs for llama-server, backend, and frontend when started via workspace scripts.
- `backend.pid` / `frontend.pid` - PID files for processes started by `start.sh` / `start.ps1`.

## Zero-Ollama startup (E5)

When prerequisites exist (`runtime/bin/llama-server`, `models/demo/model.gguf`):

```bash
./start.sh --provider llama_cpp --download-model
./stop.sh
```

```powershell
.\start.ps1 -Provider llama_cpp -DownloadModel
.\stop.ps1
```

The start script:

1. Optionally downloads the demo model when `--download-model` is passed.
2. Starts `llama-server` if not already reachable.
3. Starts the backend with `LLM_PROVIDER=llama_cpp` (process env only).
4. Starts the frontend dev server.
5. Writes PID/log files under `runtime/`.

Dry-run and check-only modes:

```bash
./start.sh --dry-run --provider llama_cpp --download-model
./start.sh --provider llama_cpp --check-only
```

No automatic binary download. Place `llama-server` in `runtime/bin/` manually until a future opt-in binary download flow exists.
