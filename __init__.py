from .nodes import PH3UpsamplerPrepare, PH3UpsamplerPrepareSeparate

NODE_CLASS_MAPPINGS = {
    "PH3UpsamplerPrepare": PH3UpsamplerPrepare,
    "PH3UpsamplerPrepareSeparate": PH3UpsamplerPrepareSeparate,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "PH3UpsamplerPrepare": "P-H3 Upsampler Prepare (9 Images)",
    "PH3UpsamplerPrepareSeparate": "P-H3 Upsampler Prepare (9 Separate Images)",
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
