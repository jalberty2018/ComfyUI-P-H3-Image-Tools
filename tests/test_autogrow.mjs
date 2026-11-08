import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../web/autogrow.js", import.meta.url), "utf8")
    .replace('import { app } from "../../scripts/app.js";', "")
    .replace("export function syncImageInputs", "function syncImageInputs");

function fixture(nodeName = "PH3UpsamplerPrepare") {
    let extension;
    const jobs = [];
    const context = vm.createContext({
        app: { registerExtension(value) { extension = value; } },
        queueMicrotask: (job) => jobs.push(job),
    });
    vm.runInContext(source, context);
    class Node {
        constructor() {
            this.inputs = [{ name: "prompt", type: "STRING", link: 99 },
                ...Array.from({ length: 10 }, (_, i) => ({ name: `image_${i + 1}`, type: "IMAGE", link: null }))];
        }
        removeInput(index) {
            if (this.inputs[index].name !== "image_10") {
                assert.equal(this.inputs[index].link, null, "Never remove a supported connected slot");
            }
            this.inputs.splice(index, 1);
            this.onConnectionsChange();
        }
        addInput(name, type) { this.inputs.push({ name, type, link: null }); }
        addCustomWidget(widget) { this.widgets.push(widget); }
        removeOutput(index) {
            this.outputs.splice(index, 1);
            this.onConnectionsChange();
        }
        computeSize() { return [390, this.inputs.length * 25 + 100]; }
        setSize(size) { this.size = size; }
        setDirtyCanvas() {}
        onNodeCreated() { return "original called"; }
    }
    extension.beforeRegisterNodeDef(Node, { name: nodeName });
    const node = new Node();
    const flush = () => { while (jobs.length) jobs.shift()(); };
    const names = () => node.inputs.filter(i => i.type === "IMAGE").map(i => i.name);
    return { node, flush, names };
}

test("new node starts with one input and grows to nine", () => {
    const { node, flush, names } = fixture();
    assert.equal(node.onNodeCreated(), "original called");
    flush();
    assert.deepEqual(names(), ["image_1"]);
    for (let i = 1; i <= 9; i++) {
        node.inputs.find(input => input.name === `image_${i}`).link = i;
        node.onConnectionsChange();
        flush();
        assert.equal(names().length, Math.min(i + 1, 9));
    }
    assert.equal(node.inputs.find(i => i.name === "prompt").link, 99);
});

test("resolution selector reorders, toggles, restores old settings and displays results", () => {
    const { node } = fixture("PH3ResolutionSelector");
    node.widgets = [
        { name: "aspect_ratio", type: "combo", value: "1:1 (Square)" },
        { name: "megapixels", type: "number", value: 1 },
        { name: "multiple", type: "number", value: 8 },
        { name: "use_original_image_resolution", type: "toggle", value: false },
    ];
    node.onNodeCreated();
    const toggle = node.widgets[0];
    assert.equal(toggle.name, "use_original_image_resolution");
    node.onConfigure({ widgets_values: ["3:4 (Portrait Standard)", 4, 32, true] });
    assert.equal(toggle.value, true);
    const aspect = node.widgets.find(w => w.name === "aspect_ratio");
    assert.equal(aspect.value, "3:4 (Portrait Standard)");
    assert.equal(aspect.hidden, true);
    assert.equal(aspect.computeSize()[1], -4);
    assert.equal(node.widgets.find(w => w.name === "multiple").value, 32);
    toggle.value = false;
    toggle.callback(false);
    assert.equal(aspect.type, "combo");
    assert.equal(aspect.hidden, false);
    node.onExecuted({ width: [1248], height: [704] });
    const lines = [];
    node.widgets.at(-1).draw({ fillText: text => lines.push(text) }, node, 300, 0);
    assert.deepEqual(lines, ["width: 1248", "height: 704"]);
    assert.equal(node.widgets.at(-1).options.serialize, false);
});

test("restoring a workflow preserves connected slots and interior gaps", () => {
    const { node, flush, names } = fixture();
    node.onNodeCreated();
    node.inputs.find(i => i.name === "image_8").link = 8;
    node.onConfigure();
    flush();
    assert.equal(names().length, 9);
    assert.equal(node.inputs.find(i => i.name === "image_8").link, 8);
    node.inputs.find(i => i.name === "image_8").link = null;
    node.inputs.find(i => i.name === "image_2").link = 2;
    node.onConnectionsChange();
    flush();
    assert.deepEqual(names(), ["image_1", "image_2", "image_3"]);
});

test("legacy workflow with ten connected splitter outputs removes the unsupported tenth input", () => {
    const { node, flush, names } = fixture();
    node.inputs.forEach((input, i) => { input.link = i; });
    node.onConfigure();
    flush();
    assert.equal(names().length, 9);
});


test("separate-output node also grows to nine inputs", () => {
    const { node, flush, names } = fixture("PH3UpsamplerPrepareSeparate");
    node.onNodeCreated();
    flush();
    for (let i = 1; i <= 9; i++) {
        node.inputs.find(input => input.name === `image_${i}`).link = i;
        node.onConnectionsChange();
        flush();
        assert.equal(names().length, Math.min(i + 1, 9));
    }
});

for (const nodeName of ["PH3UpsamplerPrepare", "PH3UpsamplerPrepareSeparate"]) {
    test(`${nodeName} removes saved height output and preserves image outputs`, () => {
        const { node, flush } = fixture(nodeName);
        const imageCount = nodeName.endsWith("Separate") ? 9 : 1;
        const outputs = [
            { name: "upsampler_prompt", type: "STRING", links: [71] },
            ...Array.from({ length: imageCount }, (_, i) => ({
                name: imageCount === 1 ? "images" : `image_${i + 1}`,
                type: "IMAGE", links: [100 + i],
            })),
            { name: "original_ref_image", type: "IMAGE", links: [200] },
        ];
        node.outputs = [...outputs, { name: "orginal_ref_height", type: "INT", links: null }];
        node.onConfigure();
        flush();
        assert.deepEqual(node.outputs, outputs);
        node.onConfigure();
        flush();
        assert.deepEqual(node.outputs, outputs);
    });
}
