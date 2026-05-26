<template>
  <div class="annotation-page">
    <!-- Project Warning -->
    <el-alert
      v-if="!hasProject"
      type="warning"
      title="请先在页面顶部选择一个项目"
      description="选择项目后，数据集列表将只显示该项目的数据集"
      :closable="false"
      style="margin-bottom: 16px"
      show-icon
    />

    <el-card>
      <template #header>
        <div class="card-header">
          <span class="title">数据标注</span>
          <el-tag type="info">批量标注管理</el-tag>
        </div>
      </template>

      <!-- Dataset selector -->
      <el-row :gutter="16" style="margin-bottom: 20px">
        <el-col :span="8">
          <el-select
            v-model="selectedDatasetId"
            placeholder="选择数据集"
            filterable
            @change="loadDataset"
            style="width: 100%"
            :disabled="!hasProject"
          >
            <el-option
              v-for="ds in datasets"
              :key="ds.id"
              :label="`${ds.name} (${ds.image_count} 张图片)`"
              :value="ds.id"
            />
          </el-select>
          <span v-if="!hasProject" style="color: #909399; font-size: 12px; margin-top: 4px; display: inline-block;">请先选择项目</span>
          <span v-else-if="datasets.length === 0" style="color: #909399; font-size: 12px; margin-top: 4px; display: inline-block;">当前项目暂无数据集</span>
        </el-col>
        <el-col :span="16">
          <el-space>
            <el-button
              type="success"
              plain
              @click="classesDialogVisible = true"
              :disabled="!selectedDatasetId"
            >
              类别管理
            </el-button>
            <el-button
              type="primary"
              icon="MagicStick"
              @click="openBatchAutoAnnotation"
              :disabled="!selectedDatasetId || !images.length || annotationMode === 'semantic'"
            >
              AI预标注
            </el-button>
            <el-button
              type="warning"
              icon="Edit"
              @click="openBatchReplaceClasses"
              :disabled="!selectedDatasetId || !currentDataset?.classes?.length"
            >
              批量替换类别
            </el-button>
            <el-button
              type="danger"
              icon="Delete"
              @click="openDeleteClass"
              :disabled="!selectedDatasetId || !currentDataset?.classes?.length"
            >
              删除类别
            </el-button>
            <el-tag v-if="currentDataset" type="success">
              原始: {{ originalImageCount }} | 增强: {{ augmentedImageCount }}
            </el-tag>
            <el-switch
              v-model="showAugmented"
              @change="loadImages"
              active-text="显示增强数据"
              inactive-text="仅原始数据"
            />
          </el-space>
        </el-col>
      </el-row>

      <!-- Annotation view -->
      <div v-if="selectedDatasetId && images.length > 0">
        <el-alert
            v-if="annotationMode === 'obb'"
            type="info"
            :closable="false"
            show-icon
            style="margin-bottom: 12px"
        >
          OBB 旋转框：请使用工具「多边形」并选择「四边形 (OBB)」，依次点击四个角点；也可用「绘制框」做轴对齐框（训练时会转为四角点）。
        </el-alert>
        <el-alert
            v-else-if="annotationMode === 'pose'"
            type="info"
            :closable="false"
            show-icon
            style="margin-bottom: 12px"
        >
          姿态估计：可用多边形勾勒目标轮廓以生成关键点采样；请先选择类别再标注。
        </el-alert>
        <el-alert
            v-else-if="annotationMode === 'semantic'"
            type="success"
            :closable="false"
            show-icon
            style="margin-bottom: 12px"
        >
          语义分割：PNG 像素值为类别 id（0 为背景）；255 表示忽略区域。画布与像素一一对应，保存后写入数据集的 semantic_masks。
        </el-alert>
        <el-alert
            v-else-if="annotationMode === 'segment'"
            type="success"
            :closable="false"
            show-icon
            style="margin-bottom: 12px"
        >
          实例分割：请用「多边形」沿目标轮廓打点（不少于 3 点）；也可用「绘制框」生成矩形范围（四角多边形）。
        </el-alert>
        <AnnotationView
          :datasetId="selectedDatasetId"
          :projectId="currentDataset?.project_id || projectId"
          :images="images"
          :classes="currentDataset?.classes || []"
          :datasets="datasets"
          :imageUrlFunc="imageUrl"
          :annotation-mode="annotationMode"
          @annotationsSaved="onAnnotationsSaved"
          @imageDeleted="onImageDeleted"
          @imageMoved="onImageMoved"
        />
      </div>

      <el-empty v-else-if="selectedDatasetId" description="该数据集没有图片" />
      <el-empty v-else description="请选择一个数据集开始标注" :image-size="150" />
    </el-card>

    <!-- Auto annotation dialog -->
    <AutoAnnotationDialog
      ref="autoAnnotationDialogRef"
      :datasetId="selectedDatasetId"
      :projectId="currentDataset?.project_id || projectId"
      :selectedImages="images"
      @success="onAutoAnnotationSuccess"
    />
    <!-- Batch replace classes dialog -->
    <DatasetClassesManagerDialog
      v-model="classesDialogVisible"
      :dataset-id="selectedDatasetId"
      @success="onClassesManagerSuccess"
    />
    <BatchReplaceClassesDialog
      ref="batchReplaceClassesDialogRef"
      :datasetId="selectedDatasetId"
      :currentClasses="currentDataset?.classes || []"
      @success="onBatchReplaceSuccess"
    />

    <!-- Delete class dialog -->
    <el-dialog v-model="deleteClassDialogVisible" title="删除类别" width="500px">
      <el-alert type="warning" :closable="false" style="margin-bottom: 16px">
        <template #title>
          删除类别将同时删除该类别的所有标注数据，此操作不可恢复！
        </template>
      </el-alert>

      <el-form label-width="100px">
        <el-form-item label="选择类别">
          <el-select v-model="classToDelete" placeholder="选择要删除的类别" style="width: 100%">
            <el-option
              v-for="(cls, index) in currentDataset?.classes || []"
              :key="cls"
              :label="`${index}. ${cls}`"
              :value="cls"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="确认删除">
          <el-input
            v-model="deleteConfirmText"
            placeholder="请输入类别名称以确认删除"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="deleteClassDialogVisible = false">取消</el-button>
        <el-button
          type="danger"
          @click="confirmDeleteClass"
          :disabled="deleteConfirmText !== classToDelete"
          :loading="deletingClass"
        >
          确认删除
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import {computed, onMounted, ref, watch} from 'vue'
import {useRoute} from 'vue-router'
import {ElMessage} from 'element-plus'
import AnnotationView from '@/components/annotation/AnnotationView.vue'
import AutoAnnotationDialog from '@/components/annotation/AutoAnnotationDialog.vue'
import BatchReplaceClassesDialog from '@/components/annotation/BatchReplaceClassesDialog.vue'
import DatasetClassesManagerDialog from '@/components/dataset/DatasetClassesManagerDialog.vue'
import {datasetApi} from '@/api'
import {useProjectStore} from '@/stores/project'
import {storeToRefs} from 'pinia'

const projectStore = useProjectStore()
const { hasProject, projectId } = storeToRefs(projectStore)
const route = useRoute()

const selectedDatasetId = ref('')
/** 路由 ?mode= 优先，否则沿用数据集的 label_task（OBB/姿态/分割时与训练、多边形工具一致） */
const annotationMode = computed(() => {
  const q = route.query.mode
  if (q) return String(q)
  const lt = currentDataset.value?.label_task
  const s = lt ? String(lt).toLowerCase() : ''
  if (s === 'obb' || s === 'pose' || s === 'segment' || s === 'semantic') return s
  return ''
})
const datasets = ref([])
const currentDataset = ref(null)
const images = ref([])
const showAugmented = ref(false)
const loading = ref(false)
const autoAnnotationDialogRef = ref(null)
const batchReplaceClassesDialogRef = ref(null)
const deleteClassDialogVisible = ref(false)
const classToDelete = ref('')
const deleteConfirmText = ref('')
const deletingClass = ref(false)
const classesDialogVisible = ref(false)

const originalImageCount = computed(() => {
  if (!currentDataset.value) return 0
  return currentDataset.value.image_count - currentDataset.value.augmented_count
})

const augmentedImageCount = computed(() => {
  return currentDataset.value?.augmented_count || 0
})

onMounted(async () => {
  await loadDatasets()
  const ds = route.query.dataset
  if (ds) {
    selectedDatasetId.value = String(ds)
    await loadDataset()
  }
})

watch(
    () => route.query.dataset,
    async (ds) => {
      if (ds && String(ds) !== selectedDatasetId.value) {
        selectedDatasetId.value = String(ds)
        await loadDataset()
      }
    }
)

// 监听项目变化，刷新数据集列表
watch(projectId, () => {
  loadDatasets()
  selectedDatasetId.value = ''
  currentDataset.value = null
  images.value = []
})

// 监听数据集变化，检查是否有活动任务
watch(selectedDatasetId, async (newDatasetId) => {
  if (newDatasetId && autoAnnotationDialogRef.value) {
    // 延迟一点，确保对话框组件已准备好
    setTimeout(() => {
      autoAnnotationDialogRef.value?.checkAndResumeActiveJob()
    }, 500)
  }
})

async function loadDatasets() {
  try {
    const params = { page: 1, page_size: 100 }
    // 如果有当前项目，过滤该项目的数据集
    if (projectId.value) {
      params.project_id = projectId.value
    }
    const res = await datasetApi.list(params)
    datasets.value = res.items
  } catch (error) {
    ElMessage.error('加载数据集失败')
  }
}


async function loadDataset() {
  if (!selectedDatasetId.value) return

  try {
    loading.value = true
    currentDataset.value = await datasetApi.get(selectedDatasetId.value)
    await loadImages()

    // 加载完成后检查是否有活动任务
    setTimeout(() => {
      autoAnnotationDialogRef.value?.checkAndResumeActiveJob()
    }, 500)
  } catch (error) {
    ElMessage.error('加载数据集失败')
  } finally {
    loading.value = false
  }
}

async function loadImages() {
  if (!selectedDatasetId.value) return

  try {
    // Backend has a max page_size of 200, so we need to paginate
    const pageSize = 200
    let allImages = []
    let page = 1
    let hasMore = true

    while (hasMore) {
      const params = {
        page: page,
        page_size: pageSize,
      }

      // 根据 showAugmented 设置过滤参数
      if (showAugmented.value) {
        // 显示所有数据（原始+增强），不传 augmented_only 参数（后端会当作 None）
        // 或者可以不设置这个字段
      } else {
        // 只显示原始数据
        params.augmented_only = false
      }

      const res = await datasetApi.listImages(selectedDatasetId.value, params)

      allImages = allImages.concat(res.items)

      // Check if there are more pages
      if (res.items.length < pageSize || allImages.length >= res.total) {
        hasMore = false
      } else {
        page++
      }
    }

    images.value = allImages
    console.log(`Loaded ${allImages.length} images, showAugmented: ${showAugmented.value}, isAugmented samples: ${allImages.filter(img => img.is_augmented).length}`)
  } catch (error) {
    console.error('加载图片失败:', error)
    ElMessage.error('加载图片失败')
  }
}

function imageUrl(imageId, thumbnail = false) {
  return `/api/v1/datasets/files/image/${imageId}${thumbnail ? '?thumbnail=true' : ''}`
}

function openBatchAutoAnnotation() {
  if (!selectedDatasetId.value) {
    ElMessage.warning('请先选择数据集')
    return
  }
  if (!images.value || images.value.length === 0) {
    ElMessage.warning('当前数据集没有图片')
    return
  }
  autoAnnotationDialogRef.value?.open()
}

function openBatchReplaceClasses() {
  if (!selectedDatasetId.value) {
    ElMessage.warning('请先选择数据集')
    return
  }
  if (!currentDataset.value?.classes || currentDataset.value.classes.length === 0) {
    ElMessage.warning('当前数据集没有类别')
    return
  }
  batchReplaceClassesDialogRef.value?.open()
}

function onAutoAnnotationSuccess(result) {
  ElMessage.success(`AI预标注完成！成功: ${result.success_count || 0} 张，失败: ${result.failed_count || 0} 张`)
  // Reload images to show auto-generated annotations
  loadImages()
  // Reload dataset to update class list
  if (selectedDatasetId.value) {
    datasetApi.get(selectedDatasetId.value).then(ds => {
      currentDataset.value = ds
    })
  }
}

function onImageMoved() {
  loadImages()
  if (selectedDatasetId.value) {
    datasetApi.get(selectedDatasetId.value).then((ds) => {
      currentDataset.value = ds
    })
  }
  loadDatasets()
}

function onImageDeleted() {
  loadImages()
  if (selectedDatasetId.value) {
    datasetApi.get(selectedDatasetId.value).then(ds => {
      currentDataset.value = ds
    })
  }
}

function onBatchReplaceSuccess(result) {
  ElMessage.success(`批量替换完成！更新了 ${result.updated_count || 0} 个标注`)
  // Reload images and dataset
  loadImages()
  if (selectedDatasetId.value) {
    datasetApi.get(selectedDatasetId.value).then(ds => {
      currentDataset.value = ds
    })
  }
}

function openDeleteClass() {
  if (!selectedDatasetId.value) {
    ElMessage.warning('请先选择数据集')
    return
  }
  if (!currentDataset.value?.classes || currentDataset.value.classes.length === 0) {
    ElMessage.warning('当前数据集没有类别')
    return
  }
  classToDelete.value = ''
  deleteConfirmText.value = ''
  deleteClassDialogVisible.value = true
}

async function confirmDeleteClass() {
  if (deleteConfirmText.value !== classToDelete.value) {
    ElMessage.warning('类别名称不匹配')
    return
  }

  deletingClass.value = true
  try {
    // 调用后端API删除类别
    const response = await datasetApi.deleteClass(selectedDatasetId.value, classToDelete.value)

    ElMessage.success(`类别 "${classToDelete.value}" 已删除，共删除 ${response.deleted_annotations_count || 0} 个标注`)

    // 关闭对话框
    deleteClassDialogVisible.value = false

    // 重新加载数据集和图片
    await loadDataset()
  } catch (error) {
    console.error('删除类别失败:', error)
    ElMessage.error('删除类别失败：' + (error.response?.data?.detail || error.message))
  } finally {
    deletingClass.value = false
  }
}

function onAnnotationsSaved() {
  loadImages()
  if (selectedDatasetId.value) {
    datasetApi.get(selectedDatasetId.value).then((ds) => {
      currentDataset.value = ds
    })
  }
}

function onClassesManagerSuccess() {
  loadDataset()
  loadDatasets()
}
</script>

<style scoped>
.annotation-page {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title {
  font-size: 18px;
  font-weight: 600;
}
</style>

