import os

import config
from app.apscheduler_compat import apply_apscheduler_utc_patch
from utils.logger import get_logger

logger = get_logger("main")

apply_apscheduler_utc_patch()
from app.bootstrap import build_application


def main():
    """Главная точка входа (не асинхронная)."""
    from utils.logger import log_event

    os.makedirs(config.DATA_DIR, exist_ok=True)

    application = build_application()

    log_event(logger, "system_initialized", status="ready")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    from utils.logger import log_error

    try:
        main()
    except KeyboardInterrupt:
        from utils.logger import log_event

        log_event(logger, "bot_stopped", status="interrupted", reason="user_action")
    except Exception as e:
        log_error(logger, e, "critical_error", status="failed")
