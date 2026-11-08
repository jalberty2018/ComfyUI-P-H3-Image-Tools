import { app } from "../../scripts/app.js";

const imageNumber = (input) => {
    const match = /^image_([1-9]|10)$/.exec(input.name);
    return match ? Number(match[1]) : 0;
};

// Only trim unused trailing slots. Never rename or remove an interior slot:
// saved links, reference_image and <Picture N> refer to those slot names.
export function syncImageInputs(node) {
    const inputs = node.inputs ?? [];
    const highestConnected = inputs.reduce((highest, input) =>
        input.link != null ? Math.max(highest, imageNumber(input)) : highest, 0);
    const lastVisible = Math.min(9, highestConnected + 1);
    let changed = false;
    // Saved workflows may retain the removed height output after a node update.
    for (let i = (node.outputs?.length ?? 0) - 1; i >= 0; i--) {
        if (["orginal_ref_height", "original_ref_height"].includes(node.outputs[i].name)) {
            node.removeOutput(i);
            changed = true;
        }
    }
    for (let i = inputs.length - 1; i >= 0; i--) {
        if (imageNumber(inputs[i]) > 9 || (imageNumber(inputs[i]) > lastVisible && inputs[i].link == null)) {
            node.removeInput(i);
            changed = true;
        }
    }
    for (let number = 1; number <= lastVisible; number++) {
        if (!node.inputs?.some((input) => input.name === `image_${number}`)) {
            node.addInput(`image_${number}`, "IMAGE");
            changed = true;
        }
    }
    // Keep serialized/API names stable for existing workflows.
    for (const input of node.inputs ?? []) {
        const number = imageNumber(input);
        if (number && input.label !== `Picture ${number}`) {
            input.label = `Picture ${number}`;
            changed = true;
        }
    }
    if (changed) {
        node.setSize(node.computeSize());
        node.setDirtyCanvas(true, true);
    }
}

// Delay until connection/configuration callbacks finish, including workflow
// restoration. Coalesce callbacks and avoid editing slots inside removeInput.
const pending = new WeakSet();
function schedule(node) {
    if (pending.has(node)) return;
    pending.add(node);
    queueMicrotask(() => {
        try {
            syncImageInputs(node);
        } finally {
            pending.delete(node);
        }
    });
}

app.registerExtension({
    name: "PH3.ImageTools.Autogrow",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === "PH3ResolutionSelector") {
            const original = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function (...args) {
                const result = original?.apply(this, args);
                const toggle = this.widgets?.find(w => w.name === "use_original_image_resolution");
                if (!toggle) return result;
                toggle.label = "Use original image resolution";
                this.widgets.splice(this.widgets.indexOf(toggle), 1);
                this.widgets.unshift(toggle);
                const controls = this.widgets.filter(w => ["aspect_ratio", "megapixels"].includes(w.name))
                    .map(widget => ({ widget, type: widget.type, computeSize: widget.computeSize }));
                this.ph3SyncResolution = () => {
                    for (const { widget, type, computeSize } of controls) {
                        widget.type = toggle.value ? "ph3_hidden" : type;
                        widget.computeSize = toggle.value ? () => [0, -4] : computeSize;
                        widget.hidden = !!toggle.value;
                    }
                    this.setSize(this.computeSize());
                    this.setDirtyCanvas(true, true);
                };
                const callback = toggle.callback;
                toggle.callback = (...values) => {
                    callback?.apply(toggle, values);
                    this.ph3SyncResolution();
                };
                this.addCustomWidget({
                    name: "resolution_info", type: "ph3_resolution_info",
                    options: { serialize: false },
                    computeSize: () => [0, 44],
                    draw: (ctx, node, width, y) => {
                        ctx.fillStyle = "#bbb";
                        ctx.font = "12px sans-serif";
                        ctx.textAlign = "left";
                        ctx.fillText(`width: ${this.ph3Resolution?.width ?? "—"}`, 12, y + 16);
                        ctx.fillText(`height: ${this.ph3Resolution?.height ?? "—"}`, 12, y + 34);
                    },
                });
                this.ph3SyncResolution();
                return result;
            };
            const configure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function (info) {
                const result = configure?.apply(this, arguments);
                // Older workflows serialized the toggle after the three settings.
                if (typeof info?.widgets_values?.[0] === "string") {
                    ["aspect_ratio", "megapixels", "multiple", "use_original_image_resolution"].forEach((name, i) => {
                        const widget = this.widgets?.find(w => w.name === name);
                        if (widget) widget.value = info.widgets_values[i];
                    });
                }
                this.ph3SyncResolution?.();
                return result;
            };
            const executed = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
                const result = executed?.apply(this, arguments);
                this.ph3Resolution = { width: message.width?.[0], height: message.height?.[0] };
                this.setDirtyCanvas(true, true);
                return result;
            };
            return;
        }
        if (!["PH3UpsamplerPrepare", "PH3UpsamplerPrepareSeparate"].includes(nodeData.name)) return;
        for (const hook of ["onNodeCreated", "onConfigure", "onConnectionsChange"]) {
            const original = nodeType.prototype[hook];
            nodeType.prototype[hook] = function (...args) {
                const result = original?.apply(this, args);
                schedule(this);
                return result;
            };
        }
    },
});
