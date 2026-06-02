/**
 * 在已绘制原图的 canvas 上叠加检测框。
 * 实例分割：半透明掩膜填充 + 多边形轮廓 + 外接水平框（对齐 Ultralytics plot）。
 * OBB：使用 obb_xyxyxyxy（8 个像素坐标）；检测：bbox 轴对齐矩形。
 */
function pickLabelTop(boxTopY, labelH, ch) {
  const outside = boxTopY - labelH
  if (outside >= 0) return outside
  return Math.max(0, Math.min(boxTopY, ch - labelH))
}

function hexToRgba(hex, alpha) {
  const h = String(hex).replace('#', '')
  if (h.length < 6) return `rgba(76, 175, 80, ${alpha})`
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function isSegmentDetection(det) {
  if (det.task === 'segment') return true
  const poly = det.polygon_points
  return !!(poly && poly.length >= 3 && !det.obb_xyxyxyxy)
}

function buildPolygonPath(ctx, poly, cw, ch) {
  ctx.beginPath()
  ctx.moveTo(poly[0][0] * cw, poly[0][1] * ch)
  for (let i = 1; i < poly.length; i++) {
    ctx.lineTo(poly[i][0] * cw, poly[i][1] * ch)
  }
  ctx.closePath()
}

export function drawDetectionOverlay(ctx, scale, detections, getColor) {
  if (!detections || detections.length === 0) return

  const cw = ctx.canvas.width
  const ch = ctx.canvas.height
  const MASK_ALPHA = 0.45

  detections.forEach((det, idx) => {
    const color = getColor(idx)
    const poly = det.polygon_points
    const obb = det.obb_xyxyxyxy
    let lx
    let ly

    if (isSegmentDetection(det) && poly && poly.length >= 3) {
      buildPolygonPath(ctx, poly, cw, ch)
      ctx.fillStyle = hexToRgba(color, MASK_ALPHA)
      ctx.fill()
      ctx.strokeStyle = color
      ctx.lineWidth = 2
      ctx.stroke()

      if (det.bbox && det.bbox.length >= 4) {
        const [x1, y1, x2, y2] = det.bbox.map((v) => v * scale)
        ctx.strokeRect(x1, y1, x2 - x1, y2 - y1)
        lx = x1
        ly = y1
      } else {
        const xs = poly.map((p) => p[0] * cw)
        const ys = poly.map((p) => p[1] * ch)
        lx = (Math.min(...xs) + Math.max(...xs)) / 2
        ly = Math.min(...ys)
      }
    } else if ((det.task === 'obb' || obb) && obb && obb.length >= 8) {
      ctx.strokeStyle = color
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(obb[0] * scale, obb[1] * scale)
      for (let i = 1; i < 4; i++) {
        ctx.lineTo(obb[i * 2] * scale, obb[i * 2 + 1] * scale)
      }
      ctx.closePath()
      ctx.stroke()
      const xs = [obb[0], obb[2], obb[4], obb[6]]
      const ys = [obb[1], obb[3], obb[5], obb[7]]
      const cx = ((xs[0] + xs[1] + xs[2] + xs[3]) / 4) * scale
      const minY = Math.min(ys[0], ys[1], ys[2], ys[3]) * scale
      lx = cx
      ly = minY
    } else if (det.bbox && det.bbox.length >= 4) {
      ctx.strokeStyle = color
      ctx.lineWidth = 2
      const [x1, y1, x2, y2] = det.bbox.map((v) => v * scale)
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1)
      lx = x1
      ly = y1
    } else {
      return
    }

    const name = det.class_name ?? ''
    const conf = det.confidence != null ? (det.confidence * 100).toFixed(0) : '0'
    const label = `${name} ${conf}%`.trim()
    ctx.font = 'bold 13px sans-serif'
    const pad = 8
    const textW = ctx.measureText(label).width
    const textH = 18
    let tx = lx
    const centerLabel =
      ((det.task === 'obb' || obb) && obb && obb.length >= 8) ||
      (isSegmentDetection(det) && poly && poly.length >= 3 && !(det.bbox && det.bbox.length >= 4))
    if (centerLabel) {
      tx = lx - (textW + pad) / 2
    }
    tx = Math.max(0, Math.min(tx, cw - textW - pad))
    const ty = Math.max(0, Math.min(pickLabelTop(ly, textH, ch), ch - textH))
    ctx.fillStyle = color
    ctx.fillRect(tx, ty, textW + pad, textH)
    ctx.fillStyle = '#fff'
    ctx.fillText(label, tx + 4, ty + 14)
  })
}
