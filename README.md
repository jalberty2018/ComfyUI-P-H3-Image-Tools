# ComfyUI P-H3 Image Tools

Custom node for ComfyUI **0.44.0**: **P-H3 Upsampler Prepare (9 Images)**,
available under `P-H3/Image Tools`.

## Installation

Place this folder in `ComfyUI/custom_nodes/ComfyUI-P-H3-Image-Tools` in your
actual ComfyUI installation and restart ComfyUI. No additional dependencies
beyond ComfyUI are required. This development workspace is not itself a running
ComfyUI installation.

## Usage

- `prompt`: your editing request, optionally supplied through a STRING connection.
- `Picture 1` through `Picture 9`: optional IMAGE inputs. All nine may be connected:
  `None` values (such as those returned by LSReferenceSpitter) and batches containing
  zero images are ignored.
  The UI starts with one image input and adds one spare input as you connect
  images, up to nine. Disconnecting trailing images removes unused trailing
  inputs. Interior gaps and existing connections keep their original slot names.
  Older workflows have their unsupported tenth input removed on load.
  Internal/API names remain `image_1` through `image_9` for workflow compatibility.
- `reference_image`: the input slot that determines the image to edit and the output
  dimensions; defaults to **1**. This becomes `Edit <Picture N>` in the prompt.
  If the selected slot is empty, the first available image is used instead,
  with a warning in the ComfyUI log. The widget retains your requested slot;
  the generated `Edit <Picture N>` text shows the effective reference.
- `megapixels`: defaults to **1.0**, using Lanczos and preserving the aspect ratio.
  Like the original Scale Image to Total Pixels node, this uses 1024 × 1024 pixels
  per MP. Smaller images are also enlarged to reach this target.
- `upsampler_prompt` → `Generate Text.prompt`.
- `images` → `Generate Text.image` (a single IMAGE batch).
- `orignal_ref_width` / `orginal_ref_height`: INT outputs containing the original
  width and height in pixels of the selected reference image, before scaling.
  If the selected slot is empty, these describe the fallback reference image.

The node replaces StringFormat, ImageScaleToTotalPixels, GetImageSize,
ResizeAndPadImage, and BatchImagesNode inside **Make one node**. Generate Text
remains separate and runs the model. The original images for PH3ImageConditioning
remain connected separately.

Other images are resized to fit, with centered white padding. The batch preserves
input order; the reference image is not moved to the front. Transparency is
composited onto white, and grayscale images are converted to RGB.

When some input slots are empty, `<Picture N>` references in your input prompt
refer to the **input slot numbers**. With only image_1 and image_5 supplied,
`<Picture 5>` automatically becomes `<Picture 2>` in the output prompt. A prompt
reference to an empty input, or no images at all, produces a clear error.
A batch supplied to an input is included in full; a reference to
that input points to the first image in its batch. Each image in the batch receives
its own vision block. The total across all inputs is limited to 9 images.

An upstream ExecutionBlocker blocks execution according to ComfyUI's own rules;
use `None` for empty images. A black image is a valid image and is retained.

## Separate image outputs

**P-H3 Upsampler Prepare (9 Separate Images)** provides the same preparation and
inputs as the batch node, but replaces `images` with nine IMAGE outputs,
`image_1` through `image_9`. The prompt output stays first and the original
reference width/height outputs follow the nine images.

Connect these outputs in order to native **Generate Text** (`TextGenerateV2`)
inputs `images.image1` through `images.image9`, and connect `upsampler_prompt`
to `prompt`. Disable `use_default_template` because this prompt already contains
the full P-H3 chat template. Generate Text skips `None` image values.

Images are compacted in input order and batches are split into individual images
with a batch dimension of one. Remaining outputs return `None`, not a black image
or an execution blocker. For example, populated inputs 2 and 8 produce outputs
1 and 2; prompt references are remapped to match. At least one image is required,
and the total remains limited to nine. Scaling, padding and reference fallback
behave exactly like the existing batch node.

## Example workflow

`examples/p-h3-image_edit_one_node.json` is the supplied workflow with the group
replaced and two example images connected. Other custom nodes
and models from the original workflow are still required.

## Validation

`python -m unittest discover -s tests -v` checks selection, empty inputs,
batch counting, prompt numbering, and calls to ComfyUI using test doubles.
A full GPU/model run must be performed in the target installation.

Run `node --test tests/test_autogrow.mjs` to check input growth, disconnection,
saved connections, and compatibility with the connected prompt input.
After updating, restart ComfyUI and refresh the browser to load the UI extension.

The integration uses the official v0.44.0 classes:
[ImageScaleToTotalPixels](https://github.com/Comfy-Org/ComfyUI/blob/v0.44.0/comfy_extras/nodes_post_processing.py)
and [ResizeAndPadImage](https://github.com/Comfy-Org/ComfyUI/blob/v0.44.0/comfy_extras/nodes_images.py).

## License

This project is licensed under the [MIT License](LICENSE).
