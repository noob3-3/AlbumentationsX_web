/**
 * 在已绘制原图的 canvas 上叠加检测框。
 * OBB：使用 obb_xyxyxyxy（8 个像素坐标）；否则使用 bbox 轴对齐矩形。
 * 标签优先画在框外（上方），若超出画布上缘则画在框内顶部。
 */
function pickLabelTop(boxTopY, labelH, ch) {
  const outside = boxTopY - labelH
  if (outside >= 0) return outside
  return Math.max(0, Math.min(boxTopY, ch - labelH))
}

export function drawDetectionOverlay(ctx, scale, detections, getColor) {
  if (!detections || detections.length === 0) return

  detections.forEach((det, idx) => {
    const color = getColor(idx)
    ctx.strokeStyle = color
    ctx.lineWidth = 2

    const obb = det.obb_xyxyxyxy
    let lx
    let ly

    if ((det.task === 'obb' || obb) && obb && obb.length >= 8) {
      ctx.beginPath()
      ctx.moveTo(obb[0] * scale, obb[1] * scale)
      for (let i = 1; i < 4; i++) {
        ctx.lineTo(obb[i * 2] * scale, obb[i * 2 + 1] * scale)
      }
      ctx.closePath()
      ctx.stroke()
      // 标签放在旋转框「顶边」附近：水平居中对齐四角重心，竖直取最上角点上方（避免贴在外接矩形角上）
      const xs = [obb[0], obb[2], obb[4], obb[6]]
      const ys = [obb[1], obb[3], obb[5], obb[7]]
      const cx =
        ((xs[0] + xs[1] + xs[2] + xs[3]) / 4) * scale
      const minY = Math.min(ys[0], ys[1], ys[2], ys[3]) * scale
      lx = cx
      ly = minY
    } else if (det.bbox && det.bbox.length >= 4) {
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
    const cw = ctx.canvas.width
    const ch = ctx.canvas.height
    let tx = lx
    if ((det.task === 'obb' || obb) && obb && obb.length >= 8) {
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
