"""Prepare the prompt and image batch for P-H3's TextGenerate node."""

import logging
import math
import re


class PH3UpsamplerPrepare:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "reference_image": ("INT", {"default": 1, "min": 1, "max": 9,
                    "tooltip": "Input slot used for Edit <Picture N> and output dimensions. If empty, uses the first available image."}),
                "megapixels": ("FLOAT", {"default": 1.0, "min": 0.01, "max": 16.0, "step": 0.01}),
            },
            "optional": {f"image_{i}": ("IMAGE",) for i in range(1, 10)},
        }

    RETURN_TYPES = ("STRING", "IMAGE", "IMAGE")
    RETURN_NAMES = ("upsampler_prompt", "images", "original_ref_image")
    FUNCTION = "prepare"
    CATEGORY = "P-H3/Image Tools"
    DESCRIPTION = "Prepare an adaptive P-H3 prompt and a white-padded image batch. Empty inputs are skipped."

    def prepare(self, prompt, reference_image=1, megapixels=1.0, **kwargs):
        import torch
        from comfy_extras.nodes_post_processing import ImageScaleToTotalPixels
        from comfy_extras.nodes_images import ResizeAndPadImage

        if not isinstance(reference_image, int) or not 1 <= reference_image <= 9:
            raise ValueError("reference_image must be an input slot between 1 and 9.")
        if not math.isfinite(megapixels) or not 0.01 <= megapixels <= 16.0:
            raise ValueError("megapixels must be between 0.01 and 16.0.")

        if kwargs.get("image_10") is not None:
            raise ValueError("P-H3 supports at most 9 image inputs; disconnect image_10.")

        active = []
        picture_numbers = {}
        count = 0
        for slot in range(1, 10):
            value = kwargs.get(f"image_{slot}")
            if value is None:
                continue
            if not isinstance(value, torch.Tensor) or value.ndim != 4:
                raise ValueError(f"image_{slot} must be an IMAGE tensor [batch, height, width, channels].")
            if value.shape[0] == 0:
                continue
            if min(value.shape[1:3]) < 1 or value.shape[-1] not in (1, 3, 4):
                raise ValueError(f"image_{slot} has invalid dimensions or channels.")
            picture_numbers[slot] = count + 1
            count += value.shape[0]
            active.append((slot, value))

        if count > 9:
            raise ValueError("P-H3 supports at most 9 images in total, including batch frames.")

        if not active:
            raise ValueError("No images supplied. Connect at least one non-empty IMAGE.")
        if reference_image not in picture_numbers:
            fallback = active[0][0]
            logging.warning(
                "P-H3 Upsampler Prepare: reference image_%s is empty; using image_%s instead.",
                reference_image, fallback,
            )
            reference_image = fallback

        # Prompt references name input slots; compact them together with the batch.
        def replace_picture(match):
            slot = int(match.group(1))
            if slot not in picture_numbers:
                raise ValueError(f"Prompt refers to <Picture {slot}>, but that input is empty.")
            return f"<Picture {picture_numbers[slot]}>"

        request = re.sub(r"<Picture\s+(\d+)>", replace_picture, prompt)
        reference = next(value for slot, value in active if slot == reference_image)

        def rgb(value):
            value = value.to(device=reference.device, dtype=reference.dtype)
            if value.shape[-1] == 1:
                return value.repeat(1, 1, 1, 3)
            if value.shape[-1] == 4:
                alpha = value[..., 3:4]
                return value[..., :3] * alpha + (1 - alpha)
            return value

        # Match the original group's Scale Image to Total Pixels, including
        # ComfyUI's 1024**2 pixels/MP and upscaling of smaller source images.
        scaled = ImageScaleToTotalPixels.execute(rgb(reference), "lanczos", megapixels, 1)[0]
        height, width = scaled.shape[1:3]
        images = []
        for slot, value in active:
            if slot == reference_image:
                images.append(scaled)
            else:
                images.append(ResizeAndPadImage.execute(rgb(value), width, height, "white", "lanczos")[0])

        blocks = "".join(
            f"<Picture {i}>: <|vision_start|><|image_pad|><|vision_end|>\n"
            for i in range(1, count + 1)
        )
        text = (
            "<|im_start|>user\n" + blocks
            + f"Edit <Picture {picture_numbers[reference_image]}>. {request}<|im_end|>\n"
            + "<|im_start|>assistant\n<think>\n"
        )
        return text, torch.cat(images, dim=0), reference


class PH3UpsamplerPrepareSeparate(PH3UpsamplerPrepare):
    RETURN_TYPES = ("STRING",) + ("IMAGE",) * 10
    RETURN_NAMES = ("upsampler_prompt",) + tuple(f"image_{i}" for i in range(1, 10)) + (
        "original_ref_image",
    )
    DESCRIPTION = "Prepare a P-H3 prompt and up to nine separate images. Unused outputs return None."

    def prepare(self, prompt, reference_image=1, megapixels=1.0, **kwargs):
        text, batch, reference = super().prepare(prompt, reference_image, megapixels, **kwargs)
        images = tuple(batch[i:i + 1] if i < batch.shape[0] else None for i in range(9))
        return (text, *images, reference)


class PH3ResolutionSelector:
    @classmethod
    def INPUT_TYPES(cls):
        from comfy_extras.nodes_resolution import AspectRatio

        return {
            "required": {
                "aspect_ratio": ([ratio.value for ratio in AspectRatio], {"default": AspectRatio.SQUARE.value}),
                "megapixels": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 16.0, "step": 0.1}),
                "multiple": ("INT", {"default": 8, "min": 8, "max": 128, "step": 4}),
                "use_original_image_resolution": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Round the input image's width and height to the nearest multiple, ignoring aspect_ratio and megapixels.",
                }),
            },
            "optional": {"image": ("IMAGE",)},
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "select"
    CATEGORY = "P-H3/Image Tools"
    DESCRIPTION = "Native resolution selection with an option to use the original input image dimensions."

    def select(self, aspect_ratio, megapixels, multiple, use_original_image_resolution=False, image=None):
        if use_original_image_resolution:
            import torch

            if not isinstance(image, torch.Tensor) or image.ndim != 4 or min(image.shape) < 1:
                raise ValueError("Use original image resolution requires a non-empty IMAGE input.")
            width = max(multiple, round(image.shape[2] / multiple) * multiple)
            height = max(multiple, round(image.shape[1] / multiple) * multiple)
            return {"result": (width, height), "ui": {"width": [width], "height": [height]}}

        from comfy_extras.nodes_resolution import ResolutionSelector

        result = ResolutionSelector.execute(aspect_ratio, megapixels, multiple)
        return {"result": (result[0], result[1]), "ui": {"width": [result[0]], "height": [result[1]]}}
