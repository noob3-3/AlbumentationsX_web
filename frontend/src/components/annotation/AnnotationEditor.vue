<template>
  <div class="annotation-editor">
    <!-- Top toolbar -->
    <div class="editor-toolbar">
      <div class="toolbar-section">
        <span class="label">工具:</span>
        <el-radio-group v-model="selectedTool" @change="toolChanged">
          <el-radio-button label="select">选择/编辑</el-radio-button>
          <el-radio-button label="rect">绘制框</el-radio-button>
          <el-radio-button label="polygon">多边形</el-radio-button>
          <el-radio-button label="view">查看</el-radio-button>
        </el-radio-group>
      </div>

      <div class="toolbar-section">
        <span class="label">类别:</span>
        <el-select v-model="selectedClass" placeholder="选择类别" style="width: 150px">
          <el-option v-for="cls in classes" :key="cls" :label="cls" :value="cls" />
        </el-select>
      </div>

      <div class="toolbar-section" style="flex: 1; display: flex; justify-content: flex-end; gap: 8px">
        <el-button @click="undoAnnotation" :disabled="annotationHistory.length === 0" icon="Delete" size="small">撤销</el-button>
        <el-button @click="clearAnnotations" :disabled="annotations.length === 0" type="danger" icon="DeleteFilled" size="small">清空</el-button>
        <el-button type="primary" @click="saveAnnotations" :loading="saving" icon="Check" size="small">保存</el-button>
      </div>
    </div>

    <!-- Canvas area -->
    <div class="canvas-container" @mousemove="onCanvasMouseMove" @mouseleave="onCanvasMouseLeave" @click="onCanvasClick">
      <canvas
        ref="canvas"
        :width="canvasWidth"
        :height="canvasHeight"
        class="annotation-canvas"
        @mousedown="onCanvasMouseDown"
        @mouseup="onCanvasMouseUp"
      />
      <div v-if="!imageLoaded" class="canvas-placeholder">
        <el-icon class="is-loading"><Loading /></el-icon>
        <p>加载中...</p>
      </div>
    </div>

    <!-- Annotations list panel -->
    <div class="annotations-panel">
      <div class="panel-header">
        <span>标注列表 ({{ annotations.length }})</span>
        <el-tag v-if="selectedAnnotationIndex >= 0" type="success" size="small" style="margin-left: 8px">
          已选中第 {{ selectedAnnotationIndex + 1 }} 个
        </el-tag>
      </div>

      <el-empty v-if="annotations.length === 0" description="未标注任何物体" :image-size="100" />

      <el-table
        v-if="annotations.length > 0"
        :data="annotations"
        size="small"
        max-height="250"
        highlight-current-row
        @row-click="selectAnnotationFromTable"
        :row-class-name="({ $index }) => $index === selectedAnnotationIndex ? 'selected-row' : ''"
      >
        <el-table-column type="index" width="40" />
        <el-table-column label="类别" width="120">
          <template #default="{ row, $index }">
            <el-select
              v-model="row.class_name"
              size="small"
              @change="onClassChange($index, row.class_name)"
            >
              <el-option
                v-for="cls in classes"
                :key="cls"
                :label="cls"
                :value="cls"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="置信度" width="80">
          <template #default="{ row }">
            <span v-if="row.confidence" style="font-size: 12px">
              {{ (row.confidence * 100).toFixed(0) }}%
            </span>
            <span v-else style="font-size: 12px; color: #909399">手动</span>
          </template>
        </el-table-column>
        <el-table-column label="位置" width="120">
          <template #default="{ row }">
            <span style="font-size: 12px; color: #909399">
              x: {{ (row.x_center * 100).toFixed(1) }}%
            </span>
            <br />
            <span style="font-size: 12px; color: #909399">
              y: {{ (row.y_center * 100).toFixed(1) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ $index }">
            <el-button
              link type="danger" size="small" icon="Delete"
              @click.stop="deleteAnnotation($index)"
            />
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'

const props = defineProps({
  imageId: String,
  imageUrl: String,
  classes: {
    type: Array,
    default: () => [],
  },
  initialAnnotations: {
    type: Array,
    default: () => [],
  },
  preloadedImage: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['save', 'update', 'imageReady'])

const canvas = ref(null)
const ctx = ref(null)
const imageLoaded = ref(false)
const img = ref(null)

const selectedTool = ref('select')
const selectedClass = ref('')
const annotations = ref([])
const annotationHistory = ref([])
const saving = ref(false)
const savedSnapshot = ref('')

function annotationsSnapshot(anns) {
  return JSON.stringify((anns || []).map(a => ({
    cn: a.class_name,
    xc: Math.round((a.x_center || 0) * 100000),
    yc: Math.round((a.y_center || 0) * 100000),
    bw: Math.round((a.bbox_width || 0) * 100000),
    bh: Math.round((a.bbox_height || 0) * 100000),
  })))
}

function isDirty() {
  return annotationsSnapshot(annotations.value) !== savedSnapshot.value
}

function markSaved() {
  savedSnapshot.value = annotationsSnapshot(annotations.value)
}

const canvasWidth = ref(800)
const canvasHeight = ref(600)

// Drawing state
const isDrawing = ref(false)
const startX = ref(0)
const startY = ref(0)
const currentAnnotation = ref(null)
const polygonPoints = ref([])

// Editing state
const selectedAnnotationIndex = ref(-1)
const isDragging = ref(false)
const isResizing = ref(false)
const resizeHandle = ref('') // 'tl', 'tr', 'bl', 'br', 'l', 'r', 't', 'b'
const dragStartX = ref(0)
const dragStartY = ref(0)
const originalBBox = ref(null)

onMounted(async () => {
  await nextTick()
  if (canvas.value) {
    ctx.value = canvas.value.getContext('2d')
    loadImage()
  }
  if (props.initialAnnotations?.length) {
    annotations.value = JSON.parse(JSON.stringify(props.initialAnnotations))
  }
  savedSnapshot.value = annotationsSnapshot(annotations.value)
})

// Watch for image changes
watch(() => props.imageId, (newImageId, oldImageId) => {
  if (newImageId && newImageId !== oldImageId) {
    isDrawing.value = false
    currentAnnotation.value = null
    polygonPoints.value = []
    annotationHistory.value = []
    imageLoaded.value = false

    annotations.value = props.initialAnnotations ? JSON.parse(JSON.stringify(props.initialAnnotations)) : []
    savedSnapshot.value = annotationsSnapshot(annotations.value)

    loadImage()
  }
})

// Watch for annotation changes (when props.initialAnnotations updates)
watch(() => props.initialAnnotations, (newAnnotations) => {
  if (newAnnotations) {
    annotations.value = JSON.parse(JSON.stringify(newAnnotations))
    savedSnapshot.value = annotationsSnapshot(annotations.value)
    if (imageLoaded.value) {
      redraw()
    }
  }
}, { deep: true })

function loadImage() {
  // Use preloaded image if available for instant rendering
  if (props.preloadedImage && props.preloadedImage.complete && props.preloadedImage.naturalWidth > 0) {
    img.value = props.preloadedImage
    resizeCanvas()
    imageLoaded.value = true
    redraw()
    emit('imageReady')
    return
  }

  img.value = new Image()
  img.value.crossOrigin = 'anonymous'
  img.value.onload = () => {
    resizeCanvas()
    imageLoaded.value = true
    redraw()
    emit('imageReady')
  }
  img.value.onerror = () => {
    ElMessage.error('图片加载失败')
  }
  img.value.src = props.imageUrl
}

function resizeCanvas() {
  if (!img.value || !canvas.value) return

  const container = canvas.value.parentElement
  const maxWidth = container.clientWidth
  const maxHeight = container.clientHeight - 40

  let width = img.value.width
  let height = img.value.height

  if (width > maxWidth) {
    height = (height * maxWidth) / width
    width = maxWidth
  }
  if (height > maxHeight) {
    width = (width * maxHeight) / height
    height = maxHeight
  }

  canvasWidth.value = width
  canvasHeight.value = height
  canvas.value.width = width
  canvas.value.height = height
}

function redraw() {
  if (!ctx.value || !img.value || !imageLoaded.value) return

  ctx.value.clearRect(0, 0, canvasWidth.value, canvasHeight.value)
  ctx.value.drawImage(img.value, 0, 0, canvasWidth.value, canvasHeight.value)

  // Draw annotations
  annotations.value.forEach((ann, index) => {
    const isSelected = index === selectedAnnotationIndex.value
    drawBBox(ann, isSelected, index)
  })

  // Draw current drawing
  if (currentAnnotation.value && selectedTool.value === 'rect') {
    const x = Math.min(startX.value, currentAnnotation.value.x)
    const y = Math.min(startY.value, currentAnnotation.value.y)
    const width = Math.abs(currentAnnotation.value.x - startX.value)
    const height = Math.abs(currentAnnotation.value.y - startY.value)
    ctx.value.strokeStyle = '#FF6B6B'
    ctx.value.lineWidth = 2
    ctx.value.strokeRect(x, y, width, height)
  }

  // Draw polygon points
  if (selectedTool.value === 'polygon' && polygonPoints.value.length > 0) {
    ctx.value.fillStyle = 'rgba(255, 107, 107, 0.2)'
    ctx.value.strokeStyle = '#FF6B6B'
    ctx.value.lineWidth = 2

    if (polygonPoints.value.length > 1) {
      ctx.value.beginPath()
      ctx.value.moveTo(polygonPoints.value[0].x, polygonPoints.value[0].y)
      for (let i = 1; i < polygonPoints.value.length; i++) {
        ctx.value.lineTo(polygonPoints.value[i].x, polygonPoints.value[i].y)
      }
      ctx.value.closePath()
      ctx.value.stroke()
      ctx.value.fill()
    }

    // Draw points
    polygonPoints.value.forEach((pt) => {
      ctx.value.fillStyle = '#FF6B6B'
      ctx.value.beginPath()
      ctx.value.arc(pt.x, pt.y, 4, 0, Math.PI * 2)
      ctx.value.fill()
    })
  }
}

function drawBBox(annotation, isSelected = false, index = -1) {
  const x = annotation.x_center * canvasWidth.value - (annotation.bbox_width * canvasWidth.value) / 2
  const y = annotation.y_center * canvasHeight.value - (annotation.bbox_height * canvasHeight.value) / 2
  const width = annotation.bbox_width * canvasWidth.value
  const height = annotation.bbox_height * canvasHeight.value

  // Fill background for selected
  if (isSelected) {
    ctx.value.fillStyle = 'rgba(76, 175, 80, 0.15)'
    ctx.value.fillRect(x, y, width, height)
  }

  // Draw border
  ctx.value.strokeStyle = isSelected ? '#4CAF50' : '#2196F3'
  ctx.value.lineWidth = isSelected ? 3 : 2
  ctx.value.strokeRect(x, y, width, height)

  // Draw class label
  ctx.value.fillStyle = isSelected ? '#4CAF50' : '#2196F3'
  ctx.value.font = 'bold 14px Arial'
  const labelText = `${annotation.class_name} ${annotation.confidence ? `(${(annotation.confidence * 100).toFixed(0)}%)` : ''}`
  const textMetrics = ctx.value.measureText(labelText)
  const labelPadding = 4
  const labelHeight = 20

  // Draw label background
  ctx.value.fillRect(x, y - labelHeight, textMetrics.width + labelPadding * 2, labelHeight)

  // Draw label text
  ctx.value.fillStyle = 'white'
  ctx.value.fillText(labelText, x + labelPadding, y - 5)

  // Draw resize handles if selected
  if (isSelected) {
    drawResizeHandles(x, y, width, height)
  }
}

function drawResizeHandles(x, y, width, height) {
  const handleSize = 8
  const handles = [
    { x: x, y: y, name: 'tl' }, // top-left
    { x: x + width, y: y, name: 'tr' }, // top-right
    { x: x, y: y + height, name: 'bl' }, // bottom-left
    { x: x + width, y: y + height, name: 'br' }, // bottom-right
    { x: x + width / 2, y: y, name: 't' }, // top
    { x: x + width / 2, y: y + height, name: 'b' }, // bottom
    { x: x, y: y + height / 2, name: 'l' }, // left
    { x: x + width, y: y + height / 2, name: 'r' }, // right
  ]

  ctx.value.fillStyle = '#4CAF50'
  ctx.value.strokeStyle = 'white'
  ctx.value.lineWidth = 2

  handles.forEach(handle => {
    ctx.value.beginPath()
    ctx.value.arc(handle.x, handle.y, handleSize / 2, 0, Math.PI * 2)
    ctx.value.fill()
    ctx.value.stroke()
  })
}

function getCanvasCoordinates(e) {
  const rect = canvas.value.getBoundingClientRect()
  return {
    x: e.clientX - rect.left,
    y: e.clientY - rect.top,
  }
}

function onCanvasMouseDown(e) {
  if (!imageLoaded.value) return

  const coords = getCanvasCoordinates(e)
  startX.value = coords.x
  startY.value = coords.y

  // Select/Edit mode
  if (selectedTool.value === 'select') {
    // Check if clicking on resize handle
    if (selectedAnnotationIndex.value >= 0) {
      const handle = getResizeHandle(coords.x, coords.y)
      if (handle) {
        isResizing.value = true
        resizeHandle.value = handle
        const ann = annotations.value[selectedAnnotationIndex.value]
        originalBBox.value = { ...ann }
        dragStartX.value = coords.x
        dragStartY.value = coords.y
        return
      }
    }

    // Check if clicking inside a bbox (start dragging)
    const clickedIndex = getAnnotationAtPoint(coords.x, coords.y)
    if (clickedIndex >= 0) {
      selectedAnnotationIndex.value = clickedIndex
      isDragging.value = true
      const ann = annotations.value[clickedIndex]
      originalBBox.value = { ...ann }
      dragStartX.value = coords.x
      dragStartY.value = coords.y
      redraw()
      return
    }

    // Clicked on empty space, deselect
    selectedAnnotationIndex.value = -1
    redraw()
    return
  }

  // Drawing mode
  if (selectedTool.value === 'view') return

  isDrawing.value = true

  if (selectedTool.value === 'polygon') {
    polygonPoints.value.push({ x: coords.x, y: coords.y })
    redraw()
  } else if (selectedTool.value === 'rect') {
    currentAnnotation.value = { x: coords.x, y: coords.y }
  }
}

function onCanvasMouseMove(e) {
  if (!imageLoaded.value) return

  const coords = getCanvasCoordinates(e)

  // Update cursor based on context
  updateCursor(coords.x, coords.y)

  // Handle resizing
  if (isResizing.value && selectedAnnotationIndex.value >= 0) {
    const dx = coords.x - dragStartX.value
    const dy = coords.y - dragStartY.value
    resizeAnnotation(selectedAnnotationIndex.value, dx, dy)
    redraw()
    return
  }

  // Handle dragging
  if (isDragging.value && selectedAnnotationIndex.value >= 0) {
    const dx = coords.x - dragStartX.value
    const dy = coords.y - dragStartY.value
    moveAnnotation(selectedAnnotationIndex.value, dx, dy)
    redraw()
    return
  }

  // Handle drawing new rect
  if (isDrawing.value && selectedTool.value === 'rect') {
    currentAnnotation.value = { x: coords.x, y: coords.y }
    redraw()
  }
}

function onCanvasMouseUp() {
  // Finish resizing or dragging
  if (isResizing.value || isDragging.value) {
    isResizing.value = false
    isDragging.value = false
    resizeHandle.value = ''
    originalBBox.value = null
    // Save to history
    if (selectedAnnotationIndex.value >= 0) {
      annotationHistory.value.push(JSON.stringify(annotations.value))
    }
    return
  }

  // Finish drawing rect
  if (!isDrawing.value || selectedTool.value !== 'rect') {
    isDrawing.value = false
    return
  }

  isDrawing.value = false

  if (!currentAnnotation.value || !selectedClass.value) {
    ElMessage.warning('请先选择类别')
    currentAnnotation.value = null
    redraw()
    return
  }

  const x = Math.min(startX.value, currentAnnotation.value.x)
  const y = Math.min(startY.value, currentAnnotation.value.y)
  const width = Math.abs(currentAnnotation.value.x - startX.value)
  const height = Math.abs(currentAnnotation.value.y - startY.value)

  if (width < 5 || height < 5) {
    ElMessage.warning('框体太小，请重新绘制')
    currentAnnotation.value = null
    redraw()
    return
  }

  const ann = {
    class_id: props.classes.indexOf(selectedClass.value),
    class_name: selectedClass.value,
    x_center: (x + width / 2) / canvasWidth.value,
    y_center: (y + height / 2) / canvasHeight.value,
    bbox_width: width / canvasWidth.value,
    bbox_height: height / canvasHeight.value,
    confidence: 1.0,
  }

  annotationHistory.value.push(JSON.stringify(annotations.value))
  annotations.value.push(ann)
  currentAnnotation.value = null
  redraw()
}

// Helper functions for editing
function getAnnotationAtPoint(x, y) {
  // Check from last to first (top to bottom)
  for (let i = annotations.value.length - 1; i >= 0; i--) {
    const ann = annotations.value[i]
    const bx = ann.x_center * canvasWidth.value - (ann.bbox_width * canvasWidth.value) / 2
    const by = ann.y_center * canvasHeight.value - (ann.bbox_height * canvasHeight.value) / 2
    const bw = ann.bbox_width * canvasWidth.value
    const bh = ann.bbox_height * canvasHeight.value

    if (x >= bx && x <= bx + bw && y >= by && y <= by + bh) {
      return i
    }
  }
  return -1
}

function getResizeHandle(x, y) {
  if (selectedAnnotationIndex.value < 0) return null

  const ann = annotations.value[selectedAnnotationIndex.value]
  const bx = ann.x_center * canvasWidth.value - (ann.bbox_width * canvasWidth.value) / 2
  const by = ann.y_center * canvasHeight.value - (ann.bbox_height * canvasHeight.value) / 2
  const bw = ann.bbox_width * canvasWidth.value
  const bh = ann.bbox_height * canvasHeight.value

  const handleSize = 8
  const threshold = handleSize

  const handles = [
    { x: bx, y: by, name: 'tl' },
    { x: bx + bw, y: by, name: 'tr' },
    { x: bx, y: by + bh, name: 'bl' },
    { x: bx + bw, y: by + bh, name: 'br' },
    { x: bx + bw / 2, y: by, name: 't' },
    { x: bx + bw / 2, y: by + bh, name: 'b' },
    { x: bx, y: by + bh / 2, name: 'l' },
    { x: bx + bw, y: by + bh / 2, name: 'r' },
  ]

  for (const handle of handles) {
    const dx = x - handle.x
    const dy = y - handle.y
    if (Math.sqrt(dx * dx + dy * dy) <= threshold) {
      return handle.name
    }
  }

  return null
}

function moveAnnotation(index, dx, dy) {
  const ann = annotations.value[index]
  const newCenterX = originalBBox.value.x_center + dx / canvasWidth.value
  const newCenterY = originalBBox.value.y_center + dy / canvasHeight.value

  // Clamp to canvas bounds
  const halfWidth = ann.bbox_width / 2
  const halfHeight = ann.bbox_height / 2
  ann.x_center = Math.max(halfWidth, Math.min(1 - halfWidth, newCenterX))
  ann.y_center = Math.max(halfHeight, Math.min(1 - halfHeight, newCenterY))
}

function resizeAnnotation(index, dx, dy) {
  const ann = annotations.value[index]
  const handle = resizeHandle.value

  const bx = originalBBox.value.x_center * canvasWidth.value - (originalBBox.value.bbox_width * canvasWidth.value) / 2
  const by = originalBBox.value.y_center * canvasHeight.value - (originalBBox.value.bbox_height * canvasHeight.value) / 2
  const bw = originalBBox.value.bbox_width * canvasWidth.value
  const bh = originalBBox.value.bbox_height * canvasHeight.value

  let newX = bx
  let newY = by
  let newWidth = bw
  let newHeight = bh

  // Resize based on handle
  if (handle.includes('l')) {
    newX = bx + dx
    newWidth = bw - dx
  } else if (handle.includes('r')) {
    newWidth = bw + dx
  }

  if (handle.includes('t')) {
    newY = by + dy
    newHeight = bh - dy
  } else if (handle.includes('b')) {
    newHeight = bh + dy
  }

  // Ensure minimum size
  if (newWidth < 10) {
    newWidth = 10
    if (handle.includes('l')) newX = bx + bw - 10
  }
  if (newHeight < 10) {
    newHeight = 10
    if (handle.includes('t')) newY = by + bh - 10
  }

  // Update annotation
  ann.x_center = (newX + newWidth / 2) / canvasWidth.value
  ann.y_center = (newY + newHeight / 2) / canvasHeight.value
  ann.bbox_width = newWidth / canvasWidth.value
  ann.bbox_height = newHeight / canvasHeight.value

  // Clamp to canvas
  ann.x_center = Math.max(ann.bbox_width / 2, Math.min(1 - ann.bbox_width / 2, ann.x_center))
  ann.y_center = Math.max(ann.bbox_height / 2, Math.min(1 - ann.bbox_height / 2, ann.y_center))
}

function updateCursor(x, y) {
  if (!canvas.value) return

  if (selectedTool.value === 'select') {
    const handle = getResizeHandle(x, y)
    if (handle) {
      const cursorMap = {
        'tl': 'nw-resize', 'tr': 'ne-resize',
        'bl': 'sw-resize', 'br': 'se-resize',
        't': 'n-resize', 'b': 's-resize',
        'l': 'w-resize', 'r': 'e-resize',
      }
      canvas.value.style.cursor = cursorMap[handle]
      return
    }

    const clickedIndex = getAnnotationAtPoint(x, y)
    canvas.value.style.cursor = clickedIndex >= 0 ? 'move' : 'default'
  } else if (selectedTool.value === 'rect' || selectedTool.value === 'polygon') {
    canvas.value.style.cursor = 'crosshair'
  } else {
    canvas.value.style.cursor = 'default'
  }
}

function onCanvasClick(e) {
  if (!imageLoaded.value) return

  // Polygon mode: double click to finish
  if (selectedTool.value === 'polygon' && e.detail === 2 && polygonPoints.value.length >= 3) {
    finishPolygon()
    return
  }

  // Select mode: double click to edit class
  if (selectedTool.value === 'select' && e.detail === 2 && selectedAnnotationIndex.value >= 0) {
    editAnnotationClass(selectedAnnotationIndex.value)
  }
}

async function editAnnotationClass(index) {
  const ann = annotations.value[index]

  // Show dialog to select new class
  const { value: newClass } = await ElMessageBox.prompt('修改类别', '选择新的类别', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputValue: ann.class_name,
    inputValidator: (value) => {
      if (!value) return '请输入类别名称'
      if (!props.classes.includes(value)) return '类别不存在'
      return true
    }
  }).catch(() => null)

  if (newClass) {
    annotationHistory.value.push(JSON.stringify(annotations.value))
    ann.class_name = newClass
    ann.class_id = props.classes.indexOf(newClass)
    redraw()
    ElMessage.success('类别已修改')
  }
}

function finishPolygon() {
  if (!selectedClass.value || polygonPoints.value.length < 3) {
    ElMessage.warning('需要至少3个点来绘制多边形')
    return
  }

  // 计算边界框
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity
  polygonPoints.value.forEach((pt) => {
    minX = Math.min(minX, pt.x)
    minY = Math.min(minY, pt.y)
    maxX = Math.max(maxX, pt.x)
    maxY = Math.max(maxY, pt.y)
  })

  const width = maxX - minX
  const height = maxY - minY

  const ann = {
    class_id: props.classes.indexOf(selectedClass.value),
    class_name: selectedClass.value,
    x_center: (minX + width / 2) / canvasWidth.value,
    y_center: (minY + height / 2) / canvasHeight.value,
    bbox_width: width / canvasWidth.value,
    bbox_height: height / canvasHeight.value,
    confidence: 1.0,
  }

  annotationHistory.value.push(JSON.stringify(annotations.value))
  annotations.value.push(ann)
  polygonPoints.value = []
  redraw()
}

function onCanvasMouseLeave() {
  if (selectedTool.value === 'rect' && isDrawing.value) {
    isDrawing.value = false
  }
  redraw()
}


function deleteAnnotation(index) {
  annotationHistory.value.push(JSON.stringify(annotations.value))
  annotations.value.splice(index, 1)
  if (selectedAnnotationIndex.value === index) {
    selectedAnnotationIndex.value = -1
  } else if (selectedAnnotationIndex.value > index) {
    selectedAnnotationIndex.value--
  }
  redraw()
}

function selectAnnotationFromTable(row, column, event) {
  const index = annotations.value.indexOf(row)
  selectedAnnotationIndex.value = index
  redraw()
}

function onClassChange(index, newClassName) {
  annotationHistory.value.push(JSON.stringify(annotations.value))
  const ann = annotations.value[index]
  ann.class_name = newClassName
  ann.class_id = props.classes.indexOf(newClassName)
  redraw()
}

function undoAnnotation() {
  if (annotationHistory.value.length === 0) return
  const previousState = annotationHistory.value.pop()
  annotations.value = JSON.parse(previousState)
  redraw()
}

function clearAnnotations() {
  if (annotations.value.length === 0) return
  annotationHistory.value.push(JSON.stringify(annotations.value))
  annotations.value = []
  redraw()
}

async function saveAnnotations() {
  if (!props.imageId) return

  saving.value = true
  try {
    emit('save', {
      imageId: props.imageId,
      annotations: annotations.value,
    })
    savedSnapshot.value = annotationsSnapshot(annotations.value)
  } finally {
    saving.value = false
  }
}

function toolChanged() {
  polygonPoints.value = []
  currentAnnotation.value = null
  selectedAnnotationIndex.value = -1
  isDragging.value = false
  isResizing.value = false
  redraw()
}

defineExpose({
  saveAnnotations,
  isDirty,
  markSaved,
  getAnnotations: () => annotations.value,
})
</script>

<style scoped>
.annotation-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f5f7fa;
  border-radius: 4px;
  overflow: hidden;
}

.editor-toolbar {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 12px 16px;
  background: white;
  border-bottom: 1px solid #e0e0e0;
  flex-wrap: wrap;
}

.toolbar-section {
  display: flex;
  align-items: center;
  gap: 8px;
}

.label {
  font-weight: 500;
  color: #606266;
  min-width: 50px;
}

.canvas-container {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fafafa;
  position: relative;
  overflow: auto;
  min-height: 400px;
}

.annotation-canvas {
  cursor: crosshair;
  background: white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.canvas-placeholder {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  color: #909399;
}

.annotations-panel {
  background: white;
  border-top: 1px solid #e0e0e0;
  padding: 12px 16px;
  max-height: 300px;
  overflow-y: auto;
}

.panel-header {
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
}

:deep(.selected-row) {
  background-color: #e8f5e9 !important;
}

:deep(.el-table__row) {
  cursor: pointer;
}

:deep(.el-table__row:hover) {
  background-color: #f5f5f5 !important;
}
</style>

