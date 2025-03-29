import logging

from PIL import Image, ImageOps
import numpy as np
import torch

from .utils import download_image


class ComfyApiImageInput:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "url": ("STRING", {"multiline": False, "image_preview": True, "default": ""}),
            },
            "optional": {
                "backup_url": ("STRING", {"multiline": False, "image_preview": True, "default": ""}),
                "display_name": ("STRING",{"multiline": False, "default": ""}),
                "description": ("STRING",  {"multiline": False, "default": ""}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "run"
    CATEGORY = "📍ComfyAPI"

    def run(self, url, backup_url=None, default_value=None, display_name=None, description=None):

        image = default_value

        try:
            image = download_image(url)
        except IOError:
            if backup_url:
                image = download_image(backup_url)

        if image is not None:
            try:
                image = ImageOps.exif_transpose(image)
                image = image.convert("RGB")
                image = np.array(image).astype(np.float32) / 255.0
                image = torch.from_numpy(image)[None,]
            except Exception as e:
                logging.error(e)

        return [image]


NODE_CLASS_MAPPINGS = {"ComfyApiImageInput": ComfyApiImageInput}
NODE_DISPLAY_NAME_MAPPINGS = {"ComfyApiImageInput": "External Image Input (ComfyAPI)"}
