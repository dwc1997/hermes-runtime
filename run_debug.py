"""Local debug entry point — hot-reload, verbose logs, host 127.0.0.1:8080."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8080,
        reload=True,
        log_level="info",
        reload_dirs=["app", "core", "infra", "runtime", "models"],
    )
