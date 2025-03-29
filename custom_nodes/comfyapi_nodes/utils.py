import requests
import logging
from PIL import Image


def download_image(url: str, max_retries: int = 3, retry_delay: int = 1) -> Image.Image:
    image = None

    # Try to download the image from url
    if url.startswith('http'):
        from io import BytesIO
        import time

        for attempt in range(max_retries):
            try:
                logging.info(f"Fetching image from url: {url} (attempt {attempt + 1}/{max_retries})")
                response = requests.get(url, timeout=10)
                response.raise_for_status()  # Raise exception for HTTP errors
                image = Image.open(BytesIO(response.content))
                break
            except (requests.RequestException, IOError, Exception) as e:
                logging.warning(f"Error fetching image from {url}")
                if attempt < max_retries - 1:
                    logging.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff

    if not image:
        raise IOError(f"Failed to fetch image from {url}")

    return image