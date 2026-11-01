const fs = require("fs");
const path = require("path");
const compiler = require("vue-template-compiler");
const Vue = require("vue");

const source = fs.readFileSync(path.join(__dirname, "../../components/annotator/Category.vue"), "utf8");
const parsed = compiler.parseComponent(source);
const compiled = compiler.compile(parsed.template.content);
const annotations = { create: jest.fn() };
const component = new Function("paper", "Annotations", "Annotation", "KeypointsDefinition", "JQuery",
  parsed.script.content.replace(/^import .*;\r?$/gm, "").replace("export default", "return"))(
  {}, annotations, { render: h => h("div") }, { render: h => h("div") }, () => {});

function render(selectable) {
  const category = { id: 1, name: "rice", selectable, color: "#ffffff", supercategory: "",
    annotations: [], keypoint_labels: [], keypoint_edges: [], keypoint_colors: [] };
  const vm = new Vue({ ...component, propsData: { category, index: 0, categorysearch: "", allCategories: [],
    current: { category: -1 }, hover: { category: -1 }, opacity: 1, activeTool: "BBox" },
    render: new Function(compiled.render), staticRenderFns: compiled.staticRenderFns.map(s => new Function(s)) });
  return { vm, vnode: vm._render() };
}

function hasPlus(vnode) {
  if (!vnode) return false;
  if (vnode.data && String(vnode.data.staticClass).includes("fa-plus")) return true;
  return (vnode.children || []).some(hasPlus);
}

describe("managed category selection", () => {
  it("compiles the actual Vue 2 category template", () => {
    expect(compiled.errors).toEqual([]);
  });
  it("hides creation for legacy annotations and shows it for new categories", () => {
    expect(hasPlus(render(false).vnode)).toBe(false);
    expect(hasPlus(render(true).vnode)).toBe(true);
    expect(hasPlus(render(undefined).vnode)).toBe(true);
  });
  it("blocks legacy creation even if called directly", async () => {
    const { vm } = render(false);
    expect(await vm.createAnnotation()).toBeNull();
    expect(annotations.create).not.toHaveBeenCalled();
  });
  it("only offers selectable categories as reassignment targets", () => {
    const rows = [{ id: 1, name: "rice", selectable: false }, { id: 257, name: "ご飯", selectable: true }];
    expect(component.computed.getCategoriesList.call({ allCategories: rows })).toEqual([{ value: 257, text: "ご飯" }]);
  });
});
