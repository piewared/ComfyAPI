import sys
from functools import lru_cache
from loguru import logger
from src.utils.introspection import get_absolute_path


def configure_logging():
    # Remove the default handler
    logger.remove()

    # Add console handler for everything except comfyui logs
    logger.add(sys.stderr, filter=lambda record: record["extra"].get("module") != "comfyui")

    # Add file handler for comfyui logs only
    logger.add(
        get_absolute_path("logs/comfyui.log"),
        rotation="10 MB",
        enqueue=True,
        filter=lambda record: record["extra"].get("module") == "comfyui"
    )

    # Set loguru logger level to DEBUG for all sinks
    logger.level("DEBUG")


@lru_cache(maxsize=1)
def get_comfyui_logger():
    # Ensure logging is configured
    configure_logging()
    return logger.bind(module="comfyui")