-- 检查增强图片和标注情况

-- 1. 统计各数据集的图片和标注情况
SELECT
    d.id as dataset_id,
    d.name as dataset_name,
    COUNT(DISTINCT i.id) as total_images,
    SUM(CASE WHEN i.is_augmented = TRUE THEN 1 ELSE 0 END) as augmented_images,
    SUM(CASE WHEN i.is_augmented = FALSE THEN 1 ELSE 0 END) as original_images,
    COUNT(DISTINCT a.id) as total_annotations,
    COUNT(DISTINCT CASE WHEN i.is_augmented = TRUE THEN a.id END) as augmented_annotations,
    COUNT(DISTINCT CASE WHEN i.is_augmented = FALSE THEN a.id END) as original_annotations
FROM datasets d
LEFT JOIN images i ON d.id = i.dataset_id
LEFT JOIN annotations a ON i.id = a.image_id
GROUP BY d.id, d.name
ORDER BY d.created_at DESC;

-- 2. 查找没有标注的增强图片
SELECT
    i.id as image_id,
    i.filename,
    i.dataset_id,
    d.name as dataset_name,
    i.is_augmented,
    i.parent_id,
    COUNT(a.id) as annotation_count
FROM images i
LEFT JOIN annotations a ON i.id = a.image_id
LEFT JOIN datasets d ON i.dataset_id = d.id
WHERE i.is_augmented = TRUE
GROUP BY i.id, i.filename, i.dataset_id, d.name, i.is_augmented, i.parent_id
HAVING COUNT(a.id) = 0
ORDER BY i.created_at DESC
LIMIT 20;

-- 3. 查看原始图片和其增强版本的标注情况对比
SELECT
    orig.id as original_id,
    orig.filename as original_filename,
    COUNT(DISTINCT orig_ann.id) as original_annotations,
    aug.id as augmented_id,
    aug.filename as augmented_filename,
    COUNT(DISTINCT aug_ann.id) as augmented_annotations
FROM images orig
LEFT JOIN images aug ON aug.parent_id = orig.id AND aug.is_augmented = TRUE
LEFT JOIN annotations orig_ann ON orig.id = orig_ann.image_id
LEFT JOIN annotations aug_ann ON aug.id = aug_ann.image_id
WHERE orig.is_augmented = FALSE
GROUP BY orig.id, orig.filename, aug.id, aug.filename
HAVING COUNT(DISTINCT aug_ann.id) = 0 AND COUNT(DISTINCT orig_ann.id) > 0
LIMIT 20;

-- 4. 查看数据集的图片标注状态统计
SELECT
    d.id as dataset_id,
    d.name as dataset_name,
    i.is_augmented,
    COUNT(i.id) as image_count,
    SUM(CASE WHEN EXISTS(SELECT 1 FROM annotations WHERE image_id = i.id) THEN 1 ELSE 0 END) as images_with_annotations,
    SUM(CASE WHEN NOT EXISTS(SELECT 1 FROM annotations WHERE image_id = i.id) THEN 1 ELSE 0 END) as images_without_annotations
FROM datasets d
JOIN images i ON d.id = i.dataset_id
GROUP BY d.id, d.name, i.is_augmented
ORDER BY d.created_at DESC;

