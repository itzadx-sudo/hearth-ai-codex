import os
import sys

from .config import validate_environment


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"validate", "prepare", "ai", "adapter", "dashboard", "simulator"}:
        print("Usage: python -m hearth.launch {validate|prepare|ai|adapter|dashboard|simulator}", file=sys.stderr)
        return 2
    mode = sys.argv[1]
    config = validate_environment()
    if mode == "validate":
        return 0
    if mode == "prepare":
        from .database import initialize
        from .web import bootstrap_from_environment
        initialize()
        try:
            bootstrap_from_environment(config)
        except ValueError as exc:
            print(f"Startup error: {exc}", file=sys.stderr)
            return 2
        return 0
    if mode == "ai":
        from .database import initialize
        from .tcp_services import run_ai
        initialize()
        run_ai()
    elif mode == "adapter":
        from .tcp_services import run_adapter
        run_adapter()
    elif mode == "dashboard":
        from .database import initialize
        from .web import create_app
        initialize()
        # Model readiness is measured by a successful load, not checkpoint existence.
        app = create_app(config)
        app.run(host="127.0.0.1", port=config["port"], threaded=True, use_reloader=False)
    elif mode == "simulator":
        from .tcp_services import simulator
        simulator()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
