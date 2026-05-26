<template>

  <div class="semantic-mask-editor" v-loading="loading">

    <el-row :gutter="12" class="toolbar" align="middle">

      <el-col :xs="24" :sm="12">

        <el-space wrap>

          <span class="muted">画笔类别</span>

          <el-select v-model="selectedClassId" style="width: 220px" :disabled="!ready">

            <el-option label="忽略 (255)" :value="-1" />

            <el-option

              v-for="(name, idx) in classes"

              :key="idx"

              :label="`#${idx} ${name}`"

              :value="idx"

            />

          </el-select>

          <span class="muted">笔尖(像素)</span>

          <el-slider v-model="brushRadius" :min="1" :max="80" :step="1" style="width: 140px" :disabled="!ready" />

        </el-space>

      </el-col>

      <el-col :xs="24" :sm="12">

        <el-space wrap>

          <span class="muted">视图缩放 {{ zoomPercent }}%</span>

          <el-slider

            :model-value="zoomPercent"

            :min="25"

            :max="400"

            :step="5"

            style="width: 160px"

            :disabled="!ready"

            @update:model-value="onZoomSlider"

          />

          <el-button :disabled="!ready || undoStack.length === 0" @click="undo">撤销</el-button>

          <el-button :disabled="!ready" @click="fillIgnore">整块标为忽略(255)</el-button>

          <el-button type="primary" :disabled="!ready || saving" :loading="saving" @click="onSaveClick">

            保存掩膜 PNG

          </el-button>

        </el-space>

      </el-col>

    </el-row>



    <el-alert type="info" show-icon :closable="false" style="margin: 12px 0">

      背景像素 0 不着色；忽略区 255 默认不着色（与检测标注画布一致）；前景类半透明叠色。

      <strong>滚轮</strong>缩放（以指针为中心，与矩形/多边形标注相同）；也可用上方缩放条。

      切换上一张/下一张时会尝试自动保存未保存的修改。

    </el-alert>



    <div v-if="loadError" class="warn">{{ loadError }}</div>



    <div ref="viewportRef" class="viewport" @wheel.prevent="onViewportWheel">

      <div ref="stageScalerRef" v-show="ready" class="stage-scaler" :style="scalerStyle">

        <div class="stage" :style="stageStyle">

          <img

            ref="imgRef"

            class="base-img"

            :src="imageUrl"

            alt=""

            crossorigin="anonymous"

            draggable="false"

            @load="onImgLoad"

          />

          <canvas

            ref="overlayRef"

            class="overlay"

            @pointerdown="onPointerDown"

            @pointermove="onPointerMove"

            @pointerup="onPointerUp"

            @pointerleave="(e)=>onPointerUp(e)"

          />

        </div>

      </div>

    </div>

  </div>

</template>



<script setup>

import {computed, nextTick, onBeforeUnmount, onMounted, ref, watch} from 'vue'

import {ElMessage} from 'element-plus'

import {datasetApi} from '@/api'



const props = defineProps({

  datasetId: {type: String, required: true},

  imageId: {type: String, required: true},

  /** 与原图同源，需与 img 同源或带 Cookie */

  imageUrl: {type: String, required: true},

  classes: {

    type: Array,

    default: () => [],

  },

})



const emit = defineEmits(['saved'])



const loading = ref(false)

const saving = ref(false)

const ready = ref(false)

const loadError = ref('')

const imgRef = ref(null)

const overlayRef = ref(null)

const viewportRef = ref(null)

/** 递增以驱动 stageStyle 随视口 Resize 重算（clientWidth 非响应式） */

const viewportLayoutTick = ref(0)

const stageScalerRef = ref(null)



const naturalW = ref(0)

const naturalH = ref(0)

const brushRadius = ref(12)

/** CSS transform scale（1 = 100%）；与 AnnotationEditor 滚轮缩放一致 */

const MIN_ZOOM = 0.25

const MAX_ZOOM = 4

const zoomScale = ref(1)

const zoomOriginX = ref(0)

const zoomOriginY = ref(0)



const zoomPercent = computed(() => Math.round(zoomScale.value * 100))

/** -1 → 画笔画 255(忽略)，0..→ 该类 id */

const selectedClassId = ref(1)



/** 相对上次保存或加载后有未提交的编辑 */

const dirty = ref(false)



/** Uint8 mask length = W*H */

let maskPixels = null

let painting = false

const undoStack = ref([])

let strokeSnapshot = null



/** CSS 画布宽度：与原图一致，但总不超过下方滚动容器宽度（≈「100% 装进控件」）；需要更大可用滚轮/滑条缩放 */

const stageStyle = computed(() => {

  /* 依赖 tick，resize 时能重算 */

  void viewportLayoutTick.value

  if (!naturalW.value || !naturalH.value) return {}

  let vw = 1200

  const el = viewportRef.value

  if (el && el.clientWidth > 0) {

    vw = el.clientWidth

  } else if (typeof window !== 'undefined') {

    vw = Math.max(320, Math.min(1920, Math.floor(window.innerWidth - 120)))

  }

  const w = Math.min(naturalW.value, Math.max(1, Math.floor(vw)))

  const h = Math.round((naturalH.value / naturalW.value) * w)

  return {width: `${w}px`, height: `${h}px`}

})



const scalerStyle = computed(() => ({

  transform: `scale(${zoomScale.value})`,

  transformOrigin: `${zoomOriginX.value}px ${zoomOriginY.value}px`,

}))



function markDirty() {

  dirty.value = true

}



function clampZoom(z) {

  return Math.round(Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, z)) * 100) / 100

}



function onZoomSlider(pct) {

  zoomScale.value = clampZoom(Number(pct) / 100 || 1)

}



function onViewportWheel(ev) {

  if (!ready.value) return

  const scaler = stageScalerRef.value

  if (!scaler) return

  const rect = scaler.getBoundingClientRect()

  zoomOriginX.value = (ev.clientX - rect.left) / zoomScale.value

  zoomOriginY.value = (ev.clientY - rect.top) / zoomScale.value

  const delta = ev.deltaY > 0 ? -0.1 : 0.1

  zoomScale.value = clampZoom(zoomScale.value + delta)

}



/**

 * 显示用颜色：0 透明；255 忽略区不着色（避免整页误看成红雾）；其余类半透明便于对照原图。

 */

/** @returns {[number,number,number,number]} RGBA bytes + alpha byte（与画布一致） */

function rgbaForMaskPaint(v) {

  if (v === 0 || v === 255) return [0, 0, 0, 0]

  const hue = ((v * 47) % 360 + 360) % 360 / 360

  const sat = 0.72

  const lig = 0.52

  const alphaByte = Math.round(0.42 * 255)

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



function redrawOverlayFull() {

  const canvas = overlayRef.value

  if (!canvas || !maskPixels) return

  const w = canvas.width

  const h = canvas.height

  const ctx = canvas.getContext('2d')

  ctx.clearRect(0, 0, w, h)

  ctx.imageSmoothingEnabled = false

  const imgData = ctx.createImageData(w, h)

  const d = imgData.data

  let p = 0

  let i = 0

  const n = w * h

  while (p < n) {

    const v = maskPixels[p]

    if (v !== 0 && v !== 255) {

      const [r, g, b, a] = rgbaForMaskPaint(v)

      d[i] = r

      d[i + 1] = g

      d[i + 2] = b

      d[i + 3] = a

    }

    p++

    i += 4

  }

  ctx.putImageData(imgData, 0, 0)

}



function clamp(v, lo, hi) {

  return Math.max(lo, Math.min(hi, v))

}



function paintAt(canvasX, canvasY) {

  if (!maskPixels || !naturalW.value) return

  const r = brushRadius.value

  const cx = clamp(Math.floor(canvasX), 0, naturalW.value - 1)

  const cy = clamp(Math.floor(canvasY), 0, naturalH.value - 1)

  const pixVal = selectedClassId.value === -1 ? 255 : clamp(selectedClassId.value, 0, props.classes.length - 1)



  const w = naturalW.value

  const h = naturalH.value

  const r2 = r * r

  for (let yy = Math.max(0, cy - r); yy <= Math.min(h - 1, cy + r); yy++) {

    for (let xx = Math.max(0, cx - r); xx <= Math.min(w - 1, cx + r); xx++) {

      const dx = xx - cx

      const dy = yy - cy

      if (dx * dx + dy * dy <= r2) maskPixels[yy * w + xx] = pixVal

    }

  }

  redrawOverlayFull()

}



/** 画布坐标 ← 指针（相对 overlay）× 像素比例 */

function toCanvas(ev) {

  const canvas = overlayRef.value

  if (!canvas) return null

  const rect = canvas.getBoundingClientRect()

  const fx = rect.width > 0 ? canvas.width / rect.width : 1

  const fy = rect.height > 0 ? canvas.height / rect.height : 1

  return {

    x: (ev.clientX - rect.left) * fx,

    y: (ev.clientY - rect.top) * fy,

  }

}



function snapshotMask() {

  if (!maskPixels) return null

  return Uint8Array.from(maskPixels)

}



function onPointerDown(ev) {

  if (!ready.value) return

  ev.preventDefault()

  overlayRef.value?.setPointerCapture?.(ev.pointerId)

  painting = true

  strokeSnapshot = snapshotMask()

  const p = toCanvas(ev)

  if (p) paintAt(p.x, p.y)

}



function onPointerMove(ev) {

  if (!painting || !ready.value) return

  const p = toCanvas(ev)

  if (p) paintAt(p.x, p.y)

}



function onPointerUp(ev) {

  if (!painting && !strokeSnapshot) return

  painting = false

  const beforeStroke = strokeSnapshot

  strokeSnapshot = null

  if (ev?.pointerId != null) {

    try {

      overlayRef.value?.releasePointerCapture?.(ev.pointerId)

    } catch {

      /* ignore */

    }

  }

  const after = snapshotMask()

  if (!beforeStroke || !after) return

  let diff = beforeStroke.length !== after.length

  if (!diff) {

    for (let i = 0; i < beforeStroke.length; i++) {

      if (beforeStroke[i] !== after[i]) {

        diff = true

        break

      }

    }

  }

  if (diff) {

    undoStack.value.push(beforeStroke)

    if (undoStack.value.length > 20) undoStack.value.shift()

    markDirty()

  }

}



function undo() {

  const prev = undoStack.value.pop()

  if (!prev || !maskPixels) return

  maskPixels.set(prev)

  redrawOverlayFull()

  markDirty()

}



function fillIgnore() {

  if (!maskPixels) return

  undoStack.value.push(snapshotMask())

  if (undoStack.value.length > 20) undoStack.value.shift()

  maskPixels.fill(255)

  redrawOverlayFull()

  markDirty()

}



async function decodeMaskBlob(blob) {

  const bmp = await createImageBitmap(blob)

  const oc = document.createElement('canvas')

  oc.width = bmp.width

  oc.height = bmp.height

  const octx = oc.getContext('2d')

  octx.drawImage(bmp, 0, 0)

  bmp.close?.()

  const data = octx.getImageData(0, 0, oc.width, oc.height).data

  if (!maskPixels || oc.width !== naturalW.value || oc.height !== naturalH.value) {

    throw new Error(`掩膜尺寸 ${oc.width}x${oc.height} 与原图不一致`)

  }

  for (let i = 0; i < maskPixels.length; i++) {

    maskPixels[i] = data[i * 4]

  }

}



function resetState() {

  ready.value = false

  loadError.value = ''

  maskPixels = null

  undoStack.value = []

  dirty.value = false

  zoomScale.value = 1

  zoomOriginX.value = 0

  zoomOriginY.value = 0

}



async function maybeLoadExistingMask() {

  // 必须与保存后的掩膜保持一致：同一 URL + 陈旧 ETag/浏览器磁盘缓存会拿到旧图，故禁用 HTTP 磁盘缓存（后端 etag 也已随 mtime 变化）
  const url = `${datasetApi.semanticMaskUrl(props.imageId)}?_=${Date.now()}`

  try {

    const res = await fetch(url, {

      credentials: 'include',

      cache: 'no-store',

    })

    if (res.status === 404 || res.status === 403) return

    if (!res.ok) throw new Error(await res.text())

    const blob = await res.blob()

    await decodeMaskBlob(blob)

    redrawOverlayFull()

  } catch {

    /* 无掩膜或尚未保存 */

  }

}



async function onImgLoad() {

  const img = imgRef.value

  if (!img) return

  const w = img.naturalWidth

  const h = img.naturalHeight

  naturalW.value = w

  naturalH.value = h

  maskPixels = new Uint8Array(w * h)



  await nextPaint()

  const canvas = overlayRef.value

  if (canvas) {

    canvas.width = w

    canvas.height = h

  }



  if (!props.classes.length) {

    loadError.value = '数据集尚无类别列表，无法在掩膜中使用类别 id'

    maskPixels.fill(255)

    ready.value = true

    redrawOverlayFull()

    dirty.value = false

    viewportLayoutTick.value++

    return

  }



  maskPixels.fill(0)

  await maybeLoadExistingMask()

  redrawOverlayFull()

  ready.value = true

  dirty.value = false

  viewportLayoutTick.value++

}



function nextPaint() {

  return new Promise((r) => requestAnimationFrame(() => r()))

}



async function exportPngBlob() {

  const w = naturalW.value

  const h = naturalH.value

  const c = document.createElement('canvas')

  c.width = w

  c.height = h

  const ctx = c.getContext('2d')

  const imgd = ctx.createImageData(w, h)

  for (let i = 0; i < w * h; i++) {

    const v = maskPixels[i]

    const o = i * 4

    imgd.data[o] = v

    imgd.data[o + 1] = v

    imgd.data[o + 2] = v

    imgd.data[o + 3] = 255

  }

  ctx.putImageData(imgd, 0, 0)

  return new Promise((resolve) => c.toBlob((b) => resolve(b), 'image/png'))

}



/**

 * @param {{ silent?: boolean }} options silent=true 时不弹成功 toast（切换图片自动保存时使用）

 */

async function commitToServer(options = {}) {

  const silent = !!options.silent

  if (!ready.value || !maskPixels) return

  if (!props.classes.length) {

    ElMessage.warning('请先配置数据集类别')

    throw new Error('no classes')

  }

  saving.value = true

  try {

    const blob = await exportPngBlob()

    if (!blob) throw new Error('导出 PNG 失败')

    await datasetApi.uploadSemanticMask(props.datasetId, props.imageId, blob)

    if (!silent) {

      ElMessage.success('语义掩膜已保存')

    }

    dirty.value = false

    emit('saved')

  } finally {

    saving.value = false

  }

}



async function onSaveClick() {

  try {

    await commitToServer({silent: false})

  } catch (e) {

    const msg =

      typeof e.response?.data?.detail === 'string'

        ? e.response.data.detail

        : e.message || '保存失败'

    ElMessage.error(msg)

  }

}



/** 有待保存修改则上传；返回是否成功或无修改 */

async function saveIfDirty({silent = true} = {}) {

  if (!dirty.value) return true

  try {

    await commitToServer({silent})

    return true

  } catch (e) {

    const msg =

      typeof e.response?.data?.detail === 'string'

        ? e.response.data.detail

        : e.message || '保存失败'

    ElMessage.error(msg)

    return false

  }

}



function isDirty() {

  return dirty.value

}



defineExpose({

  isDirty,

  saveIfDirty,

  save() {

    return onSaveClick()

  },

})



let resizeObserver = null



let windowResizeListener = null



onMounted(() => {

  windowResizeListener = () => {

    viewportLayoutTick.value++

  }

  window.addEventListener('resize', windowResizeListener)

  nextTick(() => {

    viewportLayoutTick.value++

    const el = viewportRef.value

    if (el && typeof ResizeObserver !== 'undefined') {

      resizeObserver = new ResizeObserver(() => {

        viewportLayoutTick.value++

      })

      resizeObserver.observe(el)

    }

  })

})



watch(

    () => [props.imageUrl, props.imageId],

    () => {

      resetState()

      const img = imgRef.value

      if (img) img.src = props.imageUrl

    },

)



onBeforeUnmount(() => {

  maskPixels = null

  if (windowResizeListener) {

    window.removeEventListener('resize', windowResizeListener)

    windowResizeListener = null

  }

  if (resizeObserver) {

    resizeObserver.disconnect()

    resizeObserver = null

  }

})

</script>



<style scoped>

.semantic-mask-editor {

  flex: 1;

  display: flex;

  flex-direction: column;

  min-height: 0;

  width: 100%;

  padding: 4px;

  box-sizing: border-box;

}

.toolbar {

  margin-bottom: 8px;

}

.muted {

  color: var(--el-text-color-secondary);

  font-size: 13px;

}

.viewport {

  flex: 1;

  width: 100%;

  min-width: 0;

  max-height: 85vh;

  min-height: 36vh;

  overflow: auto;

  border: 1px solid var(--el-border-color);

  border-radius: 8px;

  background: #f5f7fa;

}

.stage-scaler {

  display: inline-block;

  line-height: 0;

}

.stage {

  position: relative;

  display: inline-block;

  line-height: 0;

  vertical-align: top;

}

.base-img {

  display: block;

  width: 100%;

  height: 100%;

  object-fit: fill;

}

.overlay {

  position: absolute;

  left: 0;

  top: 0;

  width: 100%;

  height: 100%;

  touch-action: none;

  cursor: crosshair;

  image-rendering: pixelated;

}

.warn {

  color: var(--el-color-danger);

  margin-bottom: 8px;

}

</style>

