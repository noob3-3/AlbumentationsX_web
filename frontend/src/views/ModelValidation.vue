<template>
  <div class="validation-page">
    <!-- Project Warning -->
    <el-alert
      v-if="!hasProject"
      type="warning"
      title="请先在页面顶部选择一个项目"
      description="选择项目后，模型列表将只显示该项目的模型"
      :closable="false"
      style="margin-bottom: 16px"
      show-icon
    />

    <el-card>
      <template #header>
        <div class="card-header">
          <div>
            <span class="title">模型验证</span>
            <el-tag type="info">多模型对比测试</el-tag>
          </div>
          <el-popconfirm
            v-if="hasProject && projectId"
            title="确定清除当前项目的所有验证测试数据？此操作不可恢复"
            @confirm="cleanValidationData"
          >
            <template #reference>
              <el-button type="warning" size="small" plain>清除测试数据</el-button>
            </template>
          </el-popconfirm>
        </div>
      </template>

      <el-row :gutter="20">
        <!-- Left: Upload and Settings -->
        <el-col :span="8">
          <div class="upload-section">
            <h3>上传测试图片</h3>
            <el-upload
              ref="uploadRef"
              :auto-upload="false"
              :show-file-list="true"
              :limit="100"
              accept="image/*"
              :on-change="handleImageSelect"
              :on-exceed="handleExceed"
              :on-remove="handleRemove"
              multiple
              drag
            >
              <el-icon class="el-icon--upload"><upload-filled /></el-icon>
              <div class="el-upload__text">
                拖拽图片到此处或 <em>点击上传</em>
              </div>
              <template #tip>
                <div class="el-upload__tip">支持 jpg/png 格式，最多 100 张</div>
              </template>
            </el-upload>

            <div v-if="uploadedFiles.length > 0" class="image-preview-list">
              <div v-for="(f, idx) in uploadedFiles" :key="idx" class="preview-item">
                <el-image :src="previewUrls[idx]" fit="contain" style="width: 80px; height: 60px; border-radius: 4px" />
                <span class="preview-name">{{ f.name }}</span>
              </div>
            </div>
          </div>

          <el-divider />

          <div class="model-selection">
            <h3>选择模型 (可多选)</h3>

            <!-- 调试信息面板 -->
            <el-alert
              v-if="models.length > 0"
              type="info"
              :closable="false"
              style="margin-bottom: 12px;"
            >
              <template #title>
                <div style="font-size: 13px;">
                  可用模型: {{ models.length }} 个 | 已选择: {{ selectedModels.length }} 个
                </div>
              </template>
            </el-alert>

            <div v-if="models.length === 0" style="color: #909399; margin-bottom: 12px;">
              暂无可用模型，请先训练模型
            </div>

            <el-select
              v-model="selectedModels"
              multiple
              placeholder="选择要测试的模型"
              style="width: 100%"
              :max-collapse-tags="3"
              collapse-tags
              collapse-tags-tooltip
              @change="handleModelChange"
              clearable
            >
              <el-option
                v-for="model in models"
                :key="model.id"
                :label="model.name"
                :value="model.id"
              >
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span style="color: #303133;">{{ model.name }}</span>
                  <el-tag size="small" type="success" style="margin-left: 8px;">
                    {{ model.model_type || 'YOLO' }}
                  </el-tag>
                </div>
              </el-option>
            </el-select>

            <!-- 显示已选择的模型列表 -->
            <div v-if="selectedModels.length > 0" style="margin-top: 12px;">
              <div style="font-size: 13px; color: #606266; margin-bottom: 8px;">已选择的模型：</div>
              <el-tag
                v-for="modelId in selectedModels"
                :key="modelId"
                closable
                @close="removeModel(modelId)"
                style="margin-right: 8px; margin-bottom: 8px;"
              >
                {{ getModelName(modelId) }}
              </el-tag>
            </div>
          </div>

          <el-divider />

          <div class="settings">
            <h3>检测参数</h3>
            <el-form label-width="120px" size="small">
              <el-form-item label="置信度阈值">
                <el-slider v-model="confidence" :min="0" :max="1" :step="0.05" show-input />
              </el-form-item>
              <el-form-item label="IOU阈值">
                <el-slider v-model="iou" :min="0" :max="1" :step="0.05" show-input />
              </el-form-item>
            </el-form>
          </div>

          <el-button
            type="primary"
            size="large"
            :loading="validating"
            :disabled="uploadedFiles.length === 0 || selectedModels.length === 0"
            @click="runValidation"
            style="width: 100%; margin-top: 20px"
          >
            <el-icon><View /></el-icon>
            开始验证
          </el-button>
        </el-col>

        <!-- Right: Results -->
        <el-col :span="16">
          <div class="results-section">
            <h3>验证结果</h3>

            <div v-if="validationResults" class="results">
              <div class="results-header">
                <el-alert
                  :title="`共 ${validationResults.images?.length || 0} 张图片，总耗时: ${validationResults.total_time_ms.toFixed(2)} ms`"
                  type="success"
                  :closable="false"
                  style="flex: 1; margin-bottom: 0"
                />
                <el-button type="primary" size="small" @click="openSaveDialog">
                  <el-icon><FolderOpened /></el-icon>
                  保存到数据集
                </el-button>
              </div>

              <el-collapse v-model="activeImageIndex">
                <el-collapse-item
                  v-for="(imgResult, imgIdx) in (validationResults.images || [])"
                  :key="imgIdx"
                  :name="String(imgIdx)"
                >
                  <template #title>
                    <span>{{ imgResult.image_name }}</span>
                    <el-tag size="small" type="info" style="margin-left: 8px">
                      {{ imgResult.results?.reduce((s, r) => s + (r.detection_count || 0), 0) }} 检测 / {{ imgResult.total_time_ms?.toFixed(0) }}ms
                    </el-tag>
                  </template>

                  <el-tabs v-model="activeTabByImage[imgIdx]" type="border-card" @tab-change="(name) => handleTabChange(name, imgIdx)">
                    <el-tab-pane
                      v-for="result in (imgResult.results || [])"
                      :key="result.model_id"
                      :label="`${result.model_name} (${result.detection_count})`"
                      :name="result.model_id"
                    >
                      <div v-if="result.error" class="error-message">
                        <el-alert :title="result.error" type="error" :closable="false" />
                      </div>

                      <div v-else class="result-layout">
                        <div class="result-image-wrap">
                          <canvas :ref="(el) => setCanvasRef(imgIdx, result.model_id, el)" class="result-canvas" />
                        </div>

                        <div class="result-info-panel">
                          <div class="stat-item">
                            <span class="stat-label">模型</span>
                            <span class="stat-value" style="font-size: 14px">{{ result.model_name }}</span>
                          </div>
                          <div class="stat-item">
                            <span class="stat-label">检测数量</span>
                            <span class="stat-value">{{ result.detection_count }}</span>
                          </div>
                          <div class="stat-item">
                            <span class="stat-label">推理耗时</span>
                            <span class="stat-value">{{ result.inference_time_ms.toFixed(1) }} ms</span>
                          </div>

                          <div class="detection-list-title">检测结果</div>
                          <div v-if="result.detections.length === 0" class="no-detection">
                            未检测到任何物体
                          </div>
                          <div v-else class="detection-list">
                            <div
                              v-for="(det, idx) in result.detections"
                              :key="idx"
                              class="detection-row"
                            >
                              <span class="det-color" :style="{ background: getColor(idx) }" />
                              <span class="det-class">{{ det.class_name }}</span>
                              <span class="det-conf">{{ (det.confidence * 100).toFixed(1) }}%</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </el-tab-pane>

                    <el-tab-pane label="对比分析" :name="'comparison_' + imgIdx">
                      <el-table :data="(imgResult.results || []).map(r => ({ model_name: r.model_name, detection_count: r.detection_count, inference_time_ms: r.inference_time_ms, error: r.error }))" stripe size="small">
                        <el-table-column prop="model_name" label="模型" width="200" />
                        <el-table-column prop="detection_count" label="检测数量" width="100" align="center" />
                        <el-table-column prop="inference_time_ms" label="推理时间 (ms)" width="150" align="center">
                          <template #default="{ row }">
                            {{ row.inference_time_ms?.toFixed(2) }}
                          </template>
                        </el-table-column>
                        <el-table-column label="状态" width="100" align="center">
                          <template #default="{ row }">
                            <el-tag v-if="row.error" type="danger">失败</el-tag>
                            <el-tag v-else type="success">成功</el-tag>
                          </template>
                        </el-table-column>
                      </el-table>
                    </el-tab-pane>
                  </el-tabs>
                </el-collapse-item>
              </el-collapse>
            </div>

            <el-empty v-else description="上传图片并选择模型后开始验证" :image-size="200" />
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 保存到数据集对话框 -->
    <el-dialog
      v-model="saveDialogVisible"
      title="保存到数据集"
      width="480px"
      :close-on-click-modal="false"
      @open="onSaveDialogOpen"
    >
      <el-form label-width="100px" label-position="left">
        <el-form-item label="选择数据集">
          <el-select
            v-model="saveDatasetMode"
            placeholder="选择已有或新建"
            style="width: 100%"
            @change="onSaveDatasetModeChange"
          >
            <el-option label="新建数据集" value="new" />
            <el-option
              v-for="ds in projectDatasets"
              :key="ds.id"
              :label="ds.name"
              :value="ds.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="saveDatasetMode === 'new'" label="数据集名称">
          <el-input v-model="saveDatasetName" placeholder="输入新数据集名称" maxlength="255" show-word-limit />
        </el-form-item>
        <el-form-item label="检测结果来源">
          <el-select v-model="saveModelId" placeholder="选择模型" style="width: 100%">
            <el-option
              v-for="mid in selectedModels"
              :key="mid"
              :label="getModelName(mid)"
              :value="mid"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="saveDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingToDataset" @click="submitSaveToDataset">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, View, FolderOpened } from '@element-plus/icons-vue'
import axios from 'axios'
import { useProjectStore } from '@/stores/project'
import { storeToRefs } from 'pinia'

const COLORS = [
  '#FF6B6B', '#4ECDC4', '#45B7D1', '#96E6A1', '#DDA0DD',
  '#F7DC6F', '#BB8FCE', '#F1948A', '#85C1E9', '#82E0AA',
  '#F8C471', '#D7BDE2', '#A3E4D7', '#F0B27A', '#AED6F1',
]

function getColor(index) {
  return COLORS[index % COLORS.length]
}

function drawDetections(canvas, imageSrc, detections) {
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const img = new Image()
  img.onload = () => {
    const maxW = canvas.parentElement.clientWidth - 16
    const scale = Math.min(maxW / img.width, 1)
    canvas.width = img.width * scale
    canvas.height = img.height * scale
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)

    if (!detections || detections.length === 0) return

    detections.forEach((det, idx) => {
      const color = getColor(idx)
      const [x1, y1, x2, y2] = det.bbox.map((v) => v * scale)
      const w = x2 - x1
      const h = y2 - y1

      ctx.strokeStyle = color
      ctx.lineWidth = 2
      ctx.strokeRect(x1, y1, w, h)

      const label = `${det.class_name} ${(det.confidence * 100).toFixed(0)}%`
      ctx.font = 'bold 13px sans-serif'
      const textW = ctx.measureText(label).width
      const textH = 18
      ctx.fillStyle = color
      ctx.fillRect(x1, y1 - textH, textW + 8, textH)
      ctx.fillStyle = '#fff'
      ctx.fillText(label, x1 + 4, y1 - 4)
    })
  }
  img.src = imageSrc
}

const projectStore = useProjectStore()
const { hasProject, projectId } = storeToRefs(projectStore)

const uploadRef = ref(null)
const uploadedFiles = ref([])
const previewUrls = ref([])
const selectedModels = ref([])
const models = ref([])
const confidence = ref(0.5)
const iou = ref(0.45)
const validating = ref(false)
const validationResults = ref(null)
const activeImageIndex = ref(['0'])
const activeTabByImage = ref({})
const canvasRefs = ref({})

// 保存到数据集
const saveDialogVisible = ref(false)
const saveDatasetMode = ref('new') // 'new' | dataset_id
const saveDatasetName = ref('')
const saveModelId = ref('')
const projectDatasets = ref([])
const savingToDataset = ref(false)

onMounted(() => {
  loadModels()
})

watch(projectId, () => {
  loadModels()
  selectedModels.value = []
  validationResults.value = null
})

async function cleanValidationData() {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  try {
    const res = await axios.delete('/api/v1/validation/clean', { params: { project_id: projectId.value } })
    ElMessage.success(res.data?.message || '清除成功')
    validationResults.value = null
  } catch (e) {
    ElMessage.error('清除失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function loadModels() {
  try {
    const params = {}
    if (projectId.value) {
      params.project_id = projectId.value
    }
    const response = await axios.get('/api/v1/models', { params })
    console.log('Models API response:', response.data)

    // 确保获取正确的数据格式
    if (response.data.items && Array.isArray(response.data.items)) {
      models.value = response.data.items
    } else if (Array.isArray(response.data)) {
      models.value = response.data
    } else if (response.data.models && Array.isArray(response.data.models)) {
      models.value = response.data.models
    } else {
      console.error('Unexpected response format:', response.data)
      models.value = []
    }

    console.log('Loaded models:', models.value)

    if (models.value.length === 0) {
      ElMessage.warning('没有可用的模型，请先训练模型')
    }
  } catch (error) {
    console.error('Failed to load models:', error)
    ElMessage.error('加载模型列表失败: ' + (error.response?.data?.detail || error.message))
    models.value = []
  }
}

function handleImageSelect(file, fileList) {
  const files = fileList.map(f => f.raw).filter(Boolean)
  uploadedFiles.value = files
  previewUrls.value.forEach(url => URL.revokeObjectURL(url))
  previewUrls.value = files.map(f => URL.createObjectURL(f))
  validationResults.value = null
}

function handleExceed() {
  ElMessage.warning('最多上传 100 张图片')
}

function handleRemove(file, fileList) {
  const files = fileList.map(f => f.raw).filter(Boolean)
  uploadedFiles.value = files
  previewUrls.value.forEach(url => URL.revokeObjectURL(url))
  previewUrls.value = files.map(f => URL.createObjectURL(f))
  validationResults.value = null
}

function handleModelChange(value) {
  console.log('Selected models changed:', value)
  console.log('Selected models array:', selectedModels.value)
}

function getModelName(modelId) {
  const model = models.value.find(m => m.id === modelId)
  return model ? model.name : modelId
}

function removeModel(modelId) {
  selectedModels.value = selectedModels.value.filter(id => id !== modelId)
}

async function runValidation() {
  if (uploadedFiles.value.length === 0 || selectedModels.value.length === 0) {
    ElMessage.warning('请上传图片并选择至少一个模型')
    return
  }

  validating.value = true
  validationResults.value = null

  try {
    const formData = new FormData()
    uploadedFiles.value.forEach(f => formData.append('files', f))
    formData.append('model_ids', JSON.stringify(selectedModels.value))
    formData.append('confidence', confidence.value.toString())
    formData.append('iou', iou.value.toString())

    const response = await axios.post('/api/v1/validation/validate', formData)

    validationResults.value = response.data
    activeImageIndex.value = ['0']
    activeTabByImage.value = Object.fromEntries(
      (validationResults.value.images || []).map((img, i) => [i, img.results?.[0]?.model_id || ''])
    )
    await nextTick()
    Object.entries(activeTabByImage.value).forEach(([i, modelId]) => {
      drawResultForModel(Number(i), modelId)
    })

    ElMessage.success('验证完成')
  } catch (error) {
    console.error('Validation error:', error)
    ElMessage.error('验证失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    validating.value = false
  }
}

function setCanvasRef(imgIdx, modelId, el) {
  if (el) {
    if (!canvasRefs.value[imgIdx]) canvasRefs.value[imgIdx] = {}
    canvasRefs.value[imgIdx][modelId] = el
  }
}

function drawResultForModel(imgIdx, modelId) {
  if (!validationResults.value?.images?.[imgIdx] || !previewUrls.value[imgIdx]) return
  const imgResult = validationResults.value.images[imgIdx]
  const result = imgResult.results?.find((r) => r.model_id === modelId)
  if (!result || result.error) return
  const canvas = canvasRefs.value[imgIdx]?.[modelId]
  if (canvas) drawDetections(canvas, previewUrls.value[imgIdx], result.detections)
}

function handleTabChange(tabName, imgIdx) {
  if (String(tabName).startsWith('comparison_')) return
  nextTick(() => drawResultForModel(imgIdx, tabName))
}

// 保存到数据集
async function openSaveDialog() {
  saveDialogVisible.value = true
}

async function onSaveDialogOpen() {
  saveDatasetMode.value = 'new'
  saveDatasetName.value = ''
  saveModelId.value = selectedModels.value[0] || ''
  projectDatasets.value = []
  if (projectId.value) {
    try {
      const res = await axios.get('/api/v1/datasets', { params: { project_id: projectId.value, page_size: 100 } })
      const items = res.data?.items ?? res.data
      projectDatasets.value = Array.isArray(items) ? items : []
    } catch (e) {
      console.error('Load datasets failed:', e)
    }
  }
}

function onSaveDatasetModeChange() {
  if (saveDatasetMode.value !== 'new') {
    saveDatasetName.value = ''
  }
}

function buildDetectionsForModel(modelId) {
  if (!validationResults.value?.images) return []
  return validationResults.value.images.map((imgResult) => {
    const r = imgResult.results?.find((x) => x.model_id === modelId)
    if (!r || !r.detections) return []
    return r.detections.map((d) => ({
      class_id: d.class_id ?? 0,
      class_name: d.class_name ?? 'unknown',
      confidence: d.confidence ?? null,
      bbox_normalized: d.bbox_normalized ?? null,
      bbox: d.bbox ?? null,
    }))
  })
}

async function submitSaveToDataset() {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (saveDatasetMode.value === 'new' && !saveDatasetName.value?.trim()) {
    ElMessage.warning('请输入数据集名称')
    return
  }
  if (!saveModelId.value) {
    ElMessage.warning('请选择检测结果来源模型')
    return
  }

  savingToDataset.value = true
  try {
    const formData = new FormData()
    uploadedFiles.value.forEach((f) => formData.append('files', f))
    formData.append('project_id', projectId.value)
    if (saveDatasetMode.value === 'new') {
      formData.append('dataset_name', saveDatasetName.value.trim())
    } else {
      formData.append('dataset_id', saveDatasetMode.value)
    }
    const detections = buildDetectionsForModel(saveModelId.value)
    formData.append('detections_json', JSON.stringify(detections))

    const res = await axios.post('/api/v1/validation/save-to-dataset', formData)
    ElMessage.success(res.data?.message ?? '保存成功')
    saveDialogVisible.value = false
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    savingToDataset.value = false
  }
}
</script>

<style scoped>
.validation-page {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.title {
  font-size: 18px;
  font-weight: 600;
}

.upload-section h3,
.model-selection h3,
.settings h3,
.results-section h3 {
  margin-bottom: 16px;
  font-size: 16px;
  font-weight: 500;
  color: #303133;
}

.image-preview-list {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.preview-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.preview-name {
  font-size: 12px;
  color: #606266;
  max-width: 90px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.results-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.results {
  margin-top: 16px;
}

.error-message {
  padding: 20px;
}

.result-layout {
  display: flex;
  gap: 16px;
}

.result-image-wrap {
  flex: 1;
  min-width: 0;
  background: #1a1a2e;
  border-radius: 6px;
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.result-canvas {
  max-width: 100%;
  border-radius: 4px;
  display: block;
}

.result-info-panel {
  width: 220px;
  flex-shrink: 0;
  background: #f5f7fa;
  border-radius: 6px;
  padding: 16px;
  display: flex;
  flex-direction: column;
}

.stat-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid #e4e7ed;
}

.stat-label {
  color: #909399;
  font-size: 13px;
}

.stat-value {
  font-size: 18px;
  font-weight: bold;
  color: #303133;
}

.detection-list-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-top: 14px;
  margin-bottom: 8px;
}

.no-detection {
  color: #909399;
  font-size: 13px;
  padding: 8px 0;
}

.detection-list {
  max-height: 320px;
  overflow-y: auto;
}

.detection-row {
  display: flex;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px solid #f0f0f0;
  font-size: 13px;
}

.det-color {
  width: 12px;
  height: 12px;
  border-radius: 2px;
  margin-right: 8px;
  flex-shrink: 0;
}

.det-class {
  flex: 1;
  color: #303133;
}

.det-conf {
  color: #606266;
  font-weight: 500;
  margin-left: 8px;
}

/* 修复 el-select 多选显示问题 */
.model-selection :deep(.el-select__wrapper) {
  background-color: #ffffff !important;
}

.model-selection :deep(.el-select__selected-item) {
  background-color: #f0f2f5;
  color: #303133;
}

.model-selection :deep(.el-tag) {
  background-color: #f0f2f5;
  color: #303133;
  border-color: #e4e7ed;
}

.model-selection :deep(.el-select__placeholder) {
  color: #a8abb2;
}

/* 确保下拉选项可见 */
:deep(.el-select-dropdown__item) {
  color: #303133 !important;
}

:deep(.el-select-dropdown__item.is-selected) {
  color: #409eff !important;
  font-weight: 600;
}
</style>

