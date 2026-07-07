from app.logging_config import configure_logging, get_logger


def test_configure_logging_and_get_logger_smoke():
    configure_logging()
    logger = get_logger("test-module")
    logger.info("smoke_event", foo="bar")


def test_configure_logging_accepts_custom_level():
    configure_logging(level="DEBUG")
    logger = get_logger("test-module-debug")
    logger.debug("debug_event")
