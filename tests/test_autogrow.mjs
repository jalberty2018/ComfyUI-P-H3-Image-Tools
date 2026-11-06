import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../web/autogrow.js", import.meta.url), "utf8")
    .replace('import { app } from "../../scripts/app.js";', "")
    .replace("export function syncImageInputs", "function syncImageInputs");

function fixture() {
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
            assert.equal(this.inputs[index].link, null, "Never remove a connected slot");
            this.inputs.splice(index, 1);
            this.onConnectionsChange();
        }
        addInput(name, type) { this.inputs.push({ name, type, link: null }); }
        computeSize() { return [390, this.inputs.length * 25 + 100]; }
        setSize(size) { this.size = size; }
        setDirtyCanvas() {}
        onNodeCreated() { return "original called"; }
    }
    extension.beforeRegisterNodeDef(Node, { name: "PH3UpsamplerPrepare" });
    const node = new Node();
    const flush = () => { while (jobs.length) jobs.shift()(); };
    const names = () => node.inputs.filter(i => i.type === "IMAGE").map(i => i.name);
    return { node, flush, names };
}

test("new node starts with one input and grows to ten", () => {
    const { node, flush, names } = fixture();
    assert.equal(node.onNodeCreated(), "original called");
    flush();
    assert.deepEqual(names(), ["image_1"]);
    for (let i = 1; i <= 10; i++) {
        node.inputs.find(input => input.name === `image_${i}`).link = i;
        node.onConnectionsChange();
        flush();
        assert.equal(names().length, Math.min(i + 1, 10));
    }
    assert.equal(node.inputs.find(i => i.name === "prompt").link, 99);
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

test("legacy workflow with ten connected splitter outputs keeps all inputs", () => {
    const { node, flush, names } = fixture();
    node.inputs.forEach((input, i) => { input.link = i; });
    node.onConfigure();
    flush();
    assert.equal(names().length, 10);
});
