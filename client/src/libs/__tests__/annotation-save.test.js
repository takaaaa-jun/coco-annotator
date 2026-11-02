const fs = require("fs");
const path = require("path");
const compiler = require("vue-template-compiler");
const axios = require("axios");

const source = fs.readFileSync(path.join(__dirname, "../../views/Annotator.vue"), "utf8");
const parsed = compiler.parseComponent(source);

function component(http) {
  const names = [];
  const script = parsed.script.content.replace(/^import (.+) from "[^"]+";\r?$/gm, (_, binding) => {
    binding.replace(/[{}]/g, "").split(",").forEach(name => names.push(name.trim()));
    return "";
  });
  const values = names.map(name => name === "axios" ? http : name === "mapMutations" ? () => ({}) : {});
  return new Function(...names, script.replace("export default", "return"))(...values);
}

function editor() {
  const refs = {};
  ["bbox", "polygon", "eraser", "brush", "magicwand", "select", "settings"].forEach(name => {
    refs[name] = { export: () => ({}) };
  });
  refs.settings.exportMetadata = () => ({ note: "keep" });
  refs.category = [{ export: () => ({ id: 257, annotations: [{ id: 90001 }] }) }];
  return { annotationDataReady: true, $refs: refs, mode: "segment", image: { id: 4001, categoryIds: [] },
    dataset: { id: 2, category_review_taxonomy_revision: "current-taxonomy" }, categoryReviewRevision: 3,
    current: {}, activeTool: "BBox", zoom: 1, addProcess: jest.fn(), removeProcess: jest.fn() };
}

describe("editor save request format", () => {
  it("sends the actual save payload as application/json with dataset revision", async () => {
    let sent;
    const http = axios.create({ adapter: config => {
      sent = config;
      return Promise.resolve({ status: 200, data: {}, config, headers: {} });
    } });
    const state = editor();
    component(http).methods.save.call(state);
    await new Promise(resolve => setImmediate(resolve));
    expect(sent.headers["Content-Type"]).toMatch(/^application\/json/);
    const payload = JSON.parse(sent.data);
    expect(payload.image.id).toBe(4001);
    expect(payload.image.category_review_revision).toBe(3);
    expect(payload.dataset.category_review_taxonomy_revision).toBe("current-taxonomy");
    expect(payload.categories[0].annotations[0].id).toBe(90001);
    expect(state.removeProcess).toHaveBeenCalledWith("Saving");
  });
  it("reproduces the old string-body form Content-Type rejected by the lock", async () => {
    let sent;
    const http = axios.create({ adapter: config => {
      sent = config;
      return Promise.resolve({ status: 200, data: {}, config, headers: {} });
    } });
    await http.post("/api/annotator/data", JSON.stringify({ image: { id: 4001 } }));
    expect(sent.headers["Content-Type"]).toMatch(/^application\/x-www-form-urlencoded/);
  });
  it("does not save incomplete image data", () => {
    const http = { post: jest.fn() };
    const state = editor();
    state.annotationDataReady = false;
    component(http).methods.save.call(state);
    expect(http.post).not.toHaveBeenCalled();
  });
});
