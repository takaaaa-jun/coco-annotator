// Validate IDs against the loaded dataset; query parameters are never trusted as category objects.
export function resolveCategoryReview(query, datasetId, categories) {
  if (query.category_id == null) return null;
  const categoryId = String(query.category_id);
  const requestedDataset = String(query.dataset_id);
  if (!/^[1-9][0-9]*$/.test(categoryId) || !/^[1-9][0-9]*$/.test(requestedDataset) || !Number.isSafeInteger(Number(categoryId)) || Number(requestedDataset) !== datasetId) {
    throw new Error("引き継いだカテゴリまたはデータセットが不正です。カテゴリ確認画面から開き直してください。");
  }
  const index = categories.findIndex(category => category.id === Number(categoryId));
  if (index < 0) throw new Error("選択したカテゴリはこのデータセットで有効ではありません。");
  return { index, category: categories[index] };
}
