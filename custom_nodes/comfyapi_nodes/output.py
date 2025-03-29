from PIL import Image
import numpy as np
from server import PromptServer, BinaryEventTypes
import asyncio
import logging

from .socket_io import comfy_api_server, MAX_REQUEST_ID_LEN


class ComfyApiImageOutput:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "request_id": ("STRING", {"multiline": False, "default": "output_id"}),
                "client_id": ("STRING", {"multiline": False, "default": ""}),
                "images": ("IMAGE",),
                "file_type": (["WEBP", "PNG", "JPEG"],),
                "quality": ("INT", {"default": 90, "min": 1, "max": 100, "step": 1}),
            },
            "optional": {}
        }

    OUTPUT_NODE = True

    RETURN_TYPES = ()
    RETURN_NAMES = ("text",)
    FUNCTION = "run"
    CATEGORY = "📍ComfyApi"

    @classmethod
    def VALIDATE_INPUTS(cls, request_id):
        try:
            if len(request_id.encode('ascii')) > MAX_REQUEST_ID_LEN:
                raise ValueError(f"request_id cannot be greater than {MAX_REQUEST_ID_LEN} characters")

        except UnicodeEncodeError:
            raise ValueError("request_id could not be encoded")

        return True

    def run(self, request_id, images, file_type, quality, client_id):
        prompt_server = PromptServer.instance
        loop = prompt_server.loop

        def schedule_coroutine_blocking(target, *args):
            future = asyncio.run_coroutine_threadsafe(target(*args), loop)
            return future.result()  # to make the call blocking

        for tensor in images:
            array = 255.0 * tensor.cpu().numpy()
            image = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))

            schedule_coroutine_blocking(comfy_api_server.send_image, [file_type, image, None, quality], client_id, request_id)
            logging.debug(f"Image sent to client {client_id}: type={file_type}, size={image.size}")

        return {"ui": {}}


NODE_CLASS_MAPPINGS = {"ComfyApiImageOutput": ComfyApiImageOutput}
NODE_DISPLAY_NAME_MAPPINGS = {"ComfyApiImageOutput": "Image Websocket Output (ComfyAPI)"}