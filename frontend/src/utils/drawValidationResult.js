import { drawDetectionOverlay } from '@/utils/drawDetectionsCanvas'
import { drawSemanticValidationCanvas } from '@/utils/drawSemanticMaskOverlay'
import { isSemanticValidationResult } from '@/utils/parseValidationResult'

function getColorFactory(colors) {
  return (index) => colors[index % colors.length]
}

/**
 * 根据验证结果 task 绘制检测框或语义掩膜叠色。
 */
export function drawValidationResult(canvas, imageSrc, result, colors, getColor) {
  if (!canvas || !result || result.error) return Promise.resolve()

  const colorFn = getColor || getColorFactory(colors || [])

  if (isSemanticValidationResult(result)) {
    return drawSemanticValidationCanvas(canvas, imageSrc, result.semantic).catch((e) => {
      console.warn('semantic validation draw failed', e)
    })
  }

  return new Promise((resolve) => {
    const ctx = canvas.getContext('2d')
    const img = new Image()
    img.onload = () => {
      const parentW = canvas.parentElement?.clientWidth ?? 0
      const availW =
        parentW > 32 ? parentW - 16 : Math.min(1200, Math.max(320, img.width))
      const scale = Math.min(availW / img.width, 1)
      canvas.width = img.width * scale
      canvas.height = img.height * scale
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
      drawDetectionOverlay(ctx, scale, result.detections || [], colorFn)
      resolve()
    }
    img.onerror = () => resolve()
    img.src = imageSrc
  })
}
