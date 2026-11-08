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
