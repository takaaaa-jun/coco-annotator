import { resolveCategoryReview } from "@/libs/category-review";

const categories = [{ id: 101, name: "テスト1" }, { id: 102, name: "テスト2" }];

describe("category review handoff", () => {
  it("selects exactly the category ID in the loaded dataset", () => {
    expect(resolveCategoryReview({ dataset_id: "2", category_id: "102" }, 2, categories)).toEqual({ index: 1, category: categories[1] });
  });
  it("leaves normal editor URLs unchanged", () => {
    expect(resolveCategoryReview({}, 2, categories)).toBeNull();
  });
  it.each([
    { dataset_id: "3", category_id: "101" },
    { dataset_id: "2", category_id: "999" },
    { dataset_id: "2", category_id: "101x" },
    { dataset_id: "2", category_id: "-1" },
    { dataset_id: "2", category_id: "0" },
    { dataset_id: "2", category_id: ["101", "102"] },
    { dataset_id: "2", category_id: "9007199254740993" },
    { category_id: "101" },
  ])("rejects invalid or foreign IDs: %j", query => {
    expect(() => resolveCategoryReview(query, 2, categories)).toThrow();
  });
});
