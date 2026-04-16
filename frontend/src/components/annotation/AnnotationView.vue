<template>
  <div class="annotation-view" @keydown="handleKeyDown" tabindex="0">
    <!-- Image selector -->
    <el-row :gutter="16" class="image-selector">
      <el-col :span="12">
        <div class="selector-label">
          选择要标注的图片
          <el-tag size="small" type="info" style="margin-left: 8px">
            快捷键: A 上一张 | D 下一张 | W 切换绘制/选择 | 滚轮缩放 | Ctrl+S/Ctrl+P 保存并跳转
          </el-tag>
        </div>
        <el-select
          v-model="selectedImageId"
          placeholder="选择图片"
          filterable
          @change="onImageSelected"
          style="width: 100%"
        >
          <el-option
            v-for="(img, index) in images"
            :key="img.id"
            :label="`${index + 1}. ${img.original_filename} (${img.annotations?.length || 0} 个标注)${img.is_augmented ? ' [增强]' : ''}`"
            :value="img.id"
          >
            <span style="float: left">#{{ index + 1 }}</span>
            <span style="margin-left: 8px">{{ img.original_filename }}</span>
            <span style="float: right; color: #8492a6; font-size: 12px">
              {{ img.annotations?.length || 0 }} 个标注
              <el-tag v-if="img.is_augmented" size="small" type="warning" style="margin-left: 4px">增强</el-tag>
            </span>
          </el-option>
        </el-select>
      </el-col>
      <el-col :span="12" style="display: flex; gap: 8px; align-items: flex-end">
        <el-button type="primary" icon="MagicStick" @click="openAutoAnnotation" plain>
          自动标注
        </el-button>
        <el-button @click="previousImage" :disabled="!canGoPrevious">
          上一张
        </el-button>
        <el-button @click="nextImage" :disabled="!canGoNext">
          下一张
        </el-button>
        <el-button icon="Picture" @click="showImageList = true" plain>
          图库
        </el-button>
        <el-dropdown
          v-if="currentImage && moveTargetDatasets.length > 0"
          @command="(targetId) => moveCurrentImage(targetId)"
          trigger="click"
        >
          <el-button type="info" :icon="FolderOpened" plain :disabled="!currentImage">
            移动到 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="ds in moveTargetDatasets"
                :key="ds.id"
                :command="ds.id"
              >
                {{ ds.name }} ({{ ds.image_count }} 张)
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-popconfirm
          v-if="currentImage"
          title="确认删除此图片？"
          @confirm="deleteCurrentImage"
        >
          <template #reference>
            <el-button type="danger" icon="Delete" plain :disabled="!currentImage">
              删除图片
            </el-button>
          </template>
        </el-popconfirm>
      </el-col>
    </el-row>

    <!-- Editor -->
    <div v-if="currentImage" class="editor-wrapper">
      <AnnotationEditor
        ref="editorRef"
        :imageId="currentImage.id"
        :imageUrl="imageUrl(currentImage.id)"
        :classes="classes"
        :initialAnnotations="editorInitialAnnotations"
        :preloadedImage="currentPreloadedImage"
        :polygon-style="polygonStyleProp"
        :require-class-first="true"
        @save="saveAnnotations"
        @image-ready="onImageReady"
      />
    </div>

    <el-empty v-else description="请先选择要标注的图片" :image-size="150" />

    <!-- Auto annotation dialog -->
    <AutoAnnotationDialog
      ref="autoAnnotationDialog"
      :datasetId="datasetId"
      :projectId="projectId"
      :selectedImages="[currentImage]"
      @success="onAutoAnnotationSuccess"
    />

    <!-- Image list drawer -->
    <el-drawer v-model="showImageList" title="图片库" size="40%">
      <div class="image-grid-small">
        <div
          v-for="img in images"
          :key="img.id"
          class="image-card-small"
          :class="{ active: img.id === selectedImageId }"
          @click="selectedImageId = img.id; showImageList = false; onImageSelected(img.id)"
        >
          <el-image
            :src="imageUrl(img.id, true)"
            fit="cover"
            style="width: 100%; height: 100%"
          />
          <div class="image-badge">{{ img.annotations?.length || 0 }}</div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import {computed, nextTick, onMounted, reactive, ref, watch} from 'vue'
import {ElMessage} from 'element-plus'
import {ArrowDown, FolderOpened} from '@element-plus/icons-vue'
import AnnotationEditor from './AnnotationEditor.vue'
import AutoAnnotationDialog from './AutoAnnotationDialog.vue'
import {datasetApi} from '@/api'

const props = defineProps({
  datasetId: String,
  projectId: String,  // 用于自动标注时过滤自定义模型
  images: {
    type: Array,
    default: () => [],
  },
  classes: {
    type: Array,
    default: () => [],
  },
  datasets: {
    type: Array,
    default: () => [],
  },
  imageUrlFunc: Function,
  /** 标注场景：obb 时默认四边形工具；其它为自由多边形 */
  annotationMode: {
    type: String,
    default: '',
  },
})

const polygonStyleProp = computed(() => (props.annotationMode === 'obb' ? 'quad' : 'free'))

const emit = defineEmits(['annotationsSaved', 'imageDeleted', 'imageMoved'])

const selectedImageId = ref('')
const editorRef = ref(null)
const autoAnnotationDialog = ref(null)
const showImageList = ref(false)

const preloadCache = reactive(new Map())

const currentPreloadedImage = computed(() => {
  return preloadCache.get(selectedImageId.value) || null
})

const currentImage = computed(() => {
  return props.images.find((img) => img.id === selectedImageId.value)
})

/** 避免模板里 `|| []` 每次渲染新建数组，导致子组件 watch 误触发、画布标签不刷新 */
const EMPTY_ANNOTATIONS = Object.freeze([])

const editorInitialAnnotations = computed(() => {
  const ann = currentImage.value?.annotations
  if (Array.isArray(ann)) return ann
  return EMPTY_ANNOTATIONS
})

const currentImageIndex = computed(() => {
  return props.images.findIndex((img) => img.id === selectedImageId.value)
})

const canGoPrevious = computed(() => {
  return currentImageIndex.value > 0
})

const canGoNext = computed(() => {
  return currentImageIndex.value >= 0 && currentImageIndex.value < props.images.length - 1
})

// 可移动到的数据集（排除当前数据集）
const moveTargetDatasets = computed(() => {
  if (!props.datasets || !props.datasetId) return []
  return props.datasets.filter((d) => d.id !== props.datasetId)
})

onMounted(() => {
  if (props.images.length > 0) {
    selectedImageId.value = props.images[0].id
    nextTick(() => preloadAdjacentImages())
  }
})

watch(() => props.images, (newImages) => {
  if (newImages?.length > 0) {
    nextTick(() => preloadAdjacentImages())
  }
}, { immediate: false })

watch([() => currentImage.value?.id, () => currentPreloadedImage.value], ([imgId, preloaded]) => {
  logLoad('editor props', { imageId: imgId, hasPreloaded: !!preloaded })
})

function preloadImage(imgData) {
  if (!imgData || preloadCache.has(imgData.id)) return

  const preImg = new Image()
  preImg.crossOrigin = 'anonymous'
  preImg.onload = () => {
    preloadCache.set(imgData.id, preImg)
  }
  preImg.onerror = () => {
    console.warn(`Failed to preload image: ${imgData.id}`)
  }
  preImg.src = imageUrl(imgData.id)
}

function preloadAdjacentImages() {
  const idx = currentImageIndex.value
  if (idx < 0) return
  if (idx > 0) {
    preloadImage(props.images[idx - 1])
  }
  if (idx + 1 < props.images.length) {
    preloadImage(props.images[idx + 1])
  }
  if (idx + 2 < props.images.length) {
    preloadImage(props.images[idx + 2])
  }
}

function onImageReady() {
  nextTick(() => {
    preloadAdjacentImages()
  })
}

const DEBUG_LOAD = false
function logLoad(...args) {
  if (!DEBUG_LOAD) return
  const now = performance.now()
  const ts = new Date().toLocaleTimeString('zh-CN', { hour12: false }) + '.' + String(now % 1000).padStart(3, '0').slice(0, 3)
  console.log(`[AnnotationView] [${ts}]`, ...args)
}

function imageUrl(imageId, thumbnail = false) {
  if (props.imageUrlFunc) {
    return props.imageUrlFunc(imageId, thumbnail)
  }
  return `/api/v1/datasets/files/image/${imageId}${thumbnail ? '?thumbnail=true' : ''}`
}

function onImageSelected(imageId) {
  selectedImageId.value = imageId
}

async function previousImage() {
  if (!canGoPrevious.value) return

  if (editorRef.value?.isDirty()) {
    try {
      await editorRef.value.saveAnnotations()
      await new Promise(resolve => setTimeout(resolve, 200))
    } catch (error) {
      console.error('Failed to save annotations:', error)
      ElMessage.error('保存标注失败')
      return
    }
  }

  selectedImageId.value = props.images[currentImageIndex.value - 1].id
}

async function nextImage() {
  if (!canGoNext.value) return

  if (editorRef.value?.isDirty()) {
    try {
      await editorRef.value.saveAnnotations()
      await new Promise(resolve => setTimeout(resolve, 200))
    } catch (error) {
      console.error('Failed to save annotations:', error)
      ElMessage.error('保存标注失败')
      return
    }
  }

  selectedImageId.value = props.images[currentImageIndex.value + 1].id
}

// Quick navigation without saving - used by Alt+Arrow shortcuts
function quickPreviousImage() {
  if (canGoPrevious.value) {
    selectedImageId.value = props.images[currentImageIndex.value - 1].id
  }
}

function quickNextImage() {
  if (canGoNext.value) {
    selectedImageId.value = props.images[currentImageIndex.value + 1].id
  }
}

// Save current annotations and go to next image
async function saveAndNext() {
  // Now this is the same as nextImage, kept for backward compatibility
  await nextImage()
}

// Save current annotations and go to previous image
async function saveAndPrevious() {
  // Now this is the same as previousImage, kept for backward compatibility
  await previousImage()
}

function handleKeyDown(event) {
  // 输入框或下拉选择展开时不响应快捷键
  const target = event.target
  const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable
  const isInDropdown = target.closest?.('.el-select__popper') || target.closest?.('.el-popper')
  if (isInput || isInDropdown) return

  // Check if Ctrl/Cmd is pressed
  const isCtrl = event.ctrlKey || event.metaKey

  // A: 上一张
  if (event.key === 'a' || event.key === 'A') {
    event.preventDefault()
    previousImage()
    return
  }
  // D: 下一张
  if (event.key === 'd' || event.key === 'D') {
    event.preventDefault()
    nextImage()
    return
  }
  // W: 切换绘制/选择状态
  if (event.key === 'w' || event.key === 'W') {
    event.preventDefault()
    editorRef.value?.toggleDrawSelect?.()
    return
  }

  if (isCtrl && event.key === 's') {
    event.preventDefault()
    // Ctrl+S: 保存并跳转到下一张（最常用）
    saveAndNext()
  } else if (isCtrl && event.key === 'Enter') {
    event.preventDefault()
    // Ctrl+Enter: 仅保存不跳转
    if (editorRef.value) {
      editorRef.value.saveAnnotations()
    }
  } else if (isCtrl && event.key === 'p') {
    event.preventDefault()
    // Ctrl+P: 保存并跳转到上一张
    saveAndPrevious()
  } else if (event.key === 'ArrowRight' && event.altKey) {
    event.preventDefault()
    // Alt + Right arrow: 快速下一张（不保存，用于快速浏览）
    quickNextImage()
  } else if (event.key === 'ArrowLeft' && event.altKey) {
    event.preventDefault()
    // Alt + Left arrow: 快速上一张（不保存，用于快速浏览）
    quickPreviousImage()
  }
}

async function moveCurrentImage(targetDatasetId) {
  if (!props.datasetId || !selectedImageId.value || !targetDatasetId) return
  try {
    await datasetApi.moveImage(props.datasetId, selectedImageId.value, targetDatasetId)
    const movedId = selectedImageId.value
    const idx = currentImageIndex.value
    if (idx > 0) {
      selectedImageId.value = props.images[idx - 1].id
    } else if (idx < props.images.length - 1) {
      selectedImageId.value = props.images[idx + 1].id
    } else {
      selectedImageId.value = ''
    }
    emit('imageMoved', { movedId, targetDatasetId })
    ElMessage.success('图片已移动到目标数据集')
  } catch (error) {
    ElMessage.error('移动失败: ' + (error.response?.data?.detail || error.message))
  }
}

async function deleteCurrentImage() {
  if (!props.datasetId || !selectedImageId.value) return
  try {
    await datasetApi.deleteImage(props.datasetId, selectedImageId.value)
    const deletedId = selectedImageId.value
    const idx = currentImageIndex.value
    // 切换到上一张或下一张
    if (idx > 0) {
      selectedImageId.value = props.images[idx - 1].id
    } else if (idx < props.images.length - 1) {
      selectedImageId.value = props.images[idx + 1].id
    } else {
      selectedImageId.value = ''
    }
    emit('imageDeleted', deletedId)
    ElMessage.success('图片已删除')
  } catch (error) {
    ElMessage.error('删除失败: ' + (error.response?.data?.detail || error.message))
  }
}

async function saveAnnotations({ imageId, annotations }) {
  try {
    // Call API to save annotations
    const response = await fetch(`/api/v1/annotation/images/${imageId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        annotations: annotations,
      }),
    })

    if (!response.ok) {
      throw new Error('保存失败')
    }

    // Update local image annotations
    const image = props.images.find((img) => img.id === imageId)
    if (image) {
      image.annotations = annotations
    }

    ElMessage.success('标注已保存')
    emit('annotationsSaved', { imageId, annotations })
  } catch (error) {
    ElMessage.error('保存标注失败：' + error.message)
  }
}

function openAutoAnnotation() {
  autoAnnotationDialog.value?.open()
}

function onAutoAnnotationSuccess(result) {
  ElMessage.success('自动标注任务已创建，请稍候...')
  // 重新加载图片数据
  emit('annotationsSaved', result)
}

defineExpose({
  saveAnnotations,
})
</script>

<style scoped>
.annotation-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
}

.image-selector {
  background: white;
  padding: 16px;
  border-radius: 4px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

.selector-label {
  margin-bottom: 8px;
  font-weight: 500;
  color: #606266;
  font-size: 14px;
}

.editor-wrapper {
  flex: 1;
  background: white;
  border-radius: 4px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  overflow: hidden;
}

.image-grid-small {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
  gap: 8px;
  padding: 8px;
}

.image-card-small {
  position: relative;
  aspect-ratio: 1;
  cursor: pointer;
  border-radius: 4px;
  overflow: hidden;
  border: 2px solid #e0e0e0;
  transition: all 0.2s;
}

.image-card-small:hover {
  border-color: #409eff;
}

.image-card-small.active {
  border-color: #409eff;
  box-shadow: 0 0 8px rgba(64, 158, 255, 0.3);
}

.image-badge {
  position: absolute;
  bottom: 4px;
  right: 4px;
  background: rgba(0, 0, 0, 0.6);
  color: white;
  border-radius: 50%;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: bold;
}
</style>

