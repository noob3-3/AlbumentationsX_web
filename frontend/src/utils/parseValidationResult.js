/** 模型验证单条结果是否为语义分割 */
export function isSemanticValidationResult(result) {
  if (!result) return false
  if (result.task === 'semantic') return true
  return !!(result.semantic && result.semantic.mask_png_base64)
}

/** 模型验证单条结果是否为实例分割（多边形） */
export function isSegmentValidationResult(result) {
  if (!result) return false
  if (result.task === 'segment') return true
  return (result.detections || []).some(
    (d) => d.task === 'segment' || (d.polygon_points && d.polygon_points.length >= 3),
  )
}

/** 结果摘要数量：检测框数 / 语义前景类数 / 实例数 */
export function validationResultCount(result) {
  if (!result) return 0
  if (isSemanticValidationResult(result)) {
    return (
      result.semantic?.foreground_class_count ??
      (result.semantic?.class_stats || []).filter(
        (s) => s.class_id !== 0 && s.class_id !== 255 && s.pixel_count > 0,
      ).length
    )
  }
  return result.detection_count ?? result.detections?.length ?? 0
}

/** 结果摘要标签 */
export function validationResultCountLabel(result) {
  if (isSemanticValidationResult(result)) return '前景类别'
  if (isSegmentValidationResult(result)) return '实例数量'
  return '检测数量'
}

/** 用于右侧列表：检测框 或 语义类别统计（不含背景/ignore） */
export function validationResultItems(result) {
  if (!result) return []
  if (isSemanticValidationResult(result)) {
    return (result.semantic?.class_stats || []).filter(
      (s) => s.class_id !== 0 && s.class_id !== 255 && s.pixel_count > 0,
    )
  }
  return result.detections || []
}

export function formatValidationItemSecondary(item, result) {
  if (isSemanticValidationResult(result)) {
    const pct = ((item.coverage ?? 0) * 100).toFixed(1)
    return `${pct}% · ${item.pixel_count ?? 0}px`
  }
  const conf = item.confidence != null ? (item.confidence * 100).toFixed(1) : '0'
  const verts = item.polygon_points?.length
  if (isSegmentValidationResult(result) && verts >= 3) {
    return `${conf}% · ${verts}点`
  }
  return `${conf}%`
}

/** 对比表任务列展示名 */
export function validationTaskLabel(task) {
  if (task === 'semantic') return '语义'
  if (task === 'segment') return '分割'
  if (task === 'obb') return 'OBB'
  return '检测'
}
