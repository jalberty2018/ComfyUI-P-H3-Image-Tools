from .nodes import PH3UpsamplerPrepare

NODE_CLASS_MAPPINGS = {"PH3UpsamplerPrepare": PH3UpsamplerPrepare}
NODE_DISPLAY_NAME_MAPPINGS = {"PH3UpsamplerPrepare": "P-H3 Upsampler Prepare (10 Images)"}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
