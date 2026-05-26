/**
 * 语义分割验证：将 PNG 掩膜（像素=类别 id）半透明叠在原图上。
 * 必须用离屏 canvas + drawImage 合成，不可对主 canvas putImageData（透明像素会擦掉底图）。
 */

/** 叠色不透明度（0~1） */
const OVERLAY_ALPHA = 0.62

function rgbaForClassId(classId) {
  if (classId === 255) return [0, 0, 0, 0]
  // 背景 0 不着色；前景类（含 id=1）均着色，便于看出掩膜
  if (classId === 0) return [0, 0, 0, 0]

  const hue = ((classId * 47) % 360 + 360) % 360 / 360
  const sat = 0.78
  const lig = 0.5
  const alphaByte = Math.round(OVERLAY_ALPHA * 255)

  function hueToRgb(pp, qq, tt) {
    let t = tt
    if (t < 0) t += 1
    if (t > 1) t -= 1
    if (t < 1 / 6) return pp + (qq - pp) * 6 * t
    if (t < 1 / 2) return qq
    if (t < 2 / 3) return pp + (qq - pp) * (2 / 3 - t) * 6
    return pp
  }

  let r
  let g
  let b
  if (sat === 0) {
    r = g = b = lig
  } else {
    const q = lig < 0.5 ? lig * (1 + sat) : lig + sat - lig * sat
    const p = 2 * lig - q
    r = hueToRgb(p, q, hue + 1 / 3)
    g = hueToRgb(p, q, hue)
    b = hueToRgb(p, q, hue - 1 / 3)
  }
  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255), alphaByte]
}

function pixelClassIdFromRgba(data, i) {
  const r = data[i]
  const g = data[i + 1]
  const b = data[i + 2]
  if (r === g && g === b) return r
  return Math.round((r + g + b) / 3)
}

function loadMaskGrayFromBase64(b64, targetW, targetH) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      const oc = document.createElement('canvas')
      oc.width = targetW
      oc.height = targetH
      const octx = oc.getContext('2d')
      octx.imageSmoothingEnabled = false
      octx.drawImage(img, 0, 0, targetW, targetH)
      const data = octx.getImageData(0, 0, targetW, targetH).data
      const gray = new Uint8Array(targetW * targetH)
      for (let i = 0, p = 0; p < gray.length; p++, i += 4) {
        gray[p] = pixelClassIdFromRgba(data, i)
      }
      resolve(gray)
    }
    img.onerror = () => reject(new Error('掩膜 PNG 解码失败'))
    img.src = `data:image/png;base64,${b64}`
  })
}

/**
 * 在离屏 canvas 生成叠色层，再 drawImage 到主 canvas（保留底图）。
 */
export function paintSemanticMaskOverlay(mainCtx, displayW, displayH, maskGray) {
  const oc = document.createElement('canvas')
  oc.width = displayW
  oc.height = displayH
  const octx = oc.getContext('2d')
  const overlay = octx.createImageData(displayW, displayH)
  const d = overlay.data
  const n = displayW * displayH
  let painted = 0

  for (let p = 0, i = 0; p < n; p++, i += 4) {
    const v = maskGray[p]
    const [r, g, b, a] = rgbaForClassId(v)
    if (a === 0) continue
    d[i] = r
    d[i + 1] = g
    d[i + 2] = b
    d[i + 3] = a
    painted++
  }

  octx.putImageData(overlay, 0, 0)
  mainCtx.drawImage(oc, 0, 0)
  return painted
}

/**
 * 在 canvas 上绘制原图 + 语义掩膜叠色。
 * @returns {Promise<number>} 着色的前景像素数（0 表示掩膜可能全背景）
 */
export async function drawSemanticValidationCanvas(canvas, imageSrc, semantic) {
  if (!canvas || !semantic?.mask_png_base64) return 0

  const ctx = canvas.getContext('2d')
  const img = await loadImage(imageSrc)
  const parentW = canvas.parentElement?.clientWidth ?? 0
  const availW =
    parentW > 32 ? parentW - 16 : Math.min(1200, Math.max(320, img.width))
  const scale = Math.min(availW / img.width, 1)
  const dw = Math.max(1, Math.round(img.width * scale))
  const dh = Math.max(1, Math.round(img.height * scale))

  canvas.width = dw
  canvas.height = dh
  ctx.imageSmoothingEnabled = true
  ctx.drawImage(img, 0, 0, dw, dh)

  const gray = await loadMaskGrayFromBase64(semantic.mask_png_base64, dw, dh)
  return paintSemanticMaskOverlay(ctx, dw, dh, gray)
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('原图加载失败'))
    img.src = src
  })
}

/** 仅掩膜预览：深色底 + 高不透明度伪彩色，便于确认 mask_png_base64 是否有效 */
export async function drawSemanticMaskOnlyCanvas(canvas, semantic) {
  if (!canvas || !semantic?.mask_png_base64) return 0
  const mw = semantic.width || 640
  const mh = semantic.height || 480
  const parentW = canvas.parentElement?.clientWidth ?? 0
  const availW = parentW > 32 ? parentW - 16 : mw
  const scale = Math.min(availW / mw, 1)
  const dw = Math.max(1, Math.round(mw * scale))
  const dh = Math.max(1, Math.round(mh * scale))
  canvas.width = dw
  canvas.height = dh
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#2b2b2b'
  ctx.fillRect(0, 0, dw, dh)
  const gray = await loadMaskGrayFromBase64(semantic.mask_png_base64, dw, dh)
  return paintSemanticMaskOverlay(ctx, dw, dh, gray)
}
