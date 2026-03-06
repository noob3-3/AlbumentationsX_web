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
          <span class="title">模型验证</span>
          <el-tag type="info">多模型对比测试</el-tag>
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
              :limit="1"
              accept="image/*"
              :on-change="handleImageSelect"
              :on-exceed="handleExceed"
              :on-remove="handleRemove"
              drag
            >
              <el-icon class="el-icon--upload"><upload-filled /></el-icon>
              <div class="el-upload__text">
                拖拽图片到此处或 <em>点击上传</em>
              </div>
              <template #tip>
                <div class="el-upload__tip">支持 jpg/png 格式图片，拖入新图片将替换旧图片</div>
              </template>
            </el-upload>

            <div v-if="previewImage" class="image-preview">
              <el-image :src="previewImage" fit="contain" style="width: 100%; max-height: 300px" />
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
            :disabled="!uploadedFile || selectedModels.length === 0"
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
              <el-alert
                :title="`总耗时: ${validationResults.total_time_ms.toFixed(2)} ms`"
                type="success"
                :closable="false"
                style="margin-bottom: 16px"
              />

              <el-tabs v-model="activeTab" type="border-card" @tab-change="handleTabChange">
                <el-tab-pane
                  v-for="result in validationResults.results"
                  :key="result.model_id"
                  :label="`${result.model_name} (${result.detection_count})`"
                  :name="result.model_id"
                >
                  <div v-if="result.error" class="error-message">
                    <el-alert :title="result.error" type="error" :closable="false" />
                  </div>

                  <div v-else class="result-layout">
                    <div class="result-image-wrap">
                      <canvas :ref="(el) => setCanvasRef(result.model_id, el)" class="result-canvas" />
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

                <!-- Comparison tab -->
                <el-tab-pane label="对比分析" name="comparison">
                  <el-table :data="comparisonData" stripe size="small">
                    <el-table-column prop="model_name" label="模型" width="200" />
                    <el-table-column prop="detection_count" label="检测数量" width="100" align="center" />
                    <el-table-column prop="inference_time_ms" label="推理时间 (ms)" width="150" align="center">
                      <template #default="{ row }">
                        {{ row.inference_time_ms.toFixed(2) }}
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
            </div>

            <el-empty v-else description="上传图片并选择模型后开始验证" :image-size="200" />
          </div>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, View } from '@element-plus/icons-vue'
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
const uploadedFile = ref(null)
const previewImage = ref('')
const selectedModels = ref([])
const models = ref([])
const confidence = ref(0.5)
const iou = ref(0.45)
const validating = ref(false)
const validationResults = ref(null)
const activeTab = ref('')
const canvasRefs = ref({})

const comparisonData = computed(() => {
  if (!validationResults.value) return []
  return validationResults.value.results.map(r => ({
    model_name: r.model_name,
    detection_count: r.detection_count,
    inference_time_ms: r.inference_time_ms,
    error: r.error,
  }))
})

onMounted(() => {
  loadModels()
})

watch(projectId, () => {
  loadModels()
  selectedModels.value = []
  validationResults.value = null
})

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

function handleImageSelect(file) {
  uploadedFile.value = file.raw
  previewImage.value = URL.createObjectURL(file.raw)
  // 清除之前的验证结果
  validationResults.value = []
}

function handleExceed(files) {
  // 当超过限制时，清除旧文件，使用新文件
  uploadRef.value.clearFiles()
  const file = files[0]
  uploadRef.value.handleStart(file)
  handleImageSelect({ raw: file })
}

function handleRemove() {
  // 移除图片时清除选择和预览
  uploadedFile.value = null
  previewImage.value = null
  validationResults.value = []
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
  if (!uploadedFile.value || selectedModels.value.length === 0) {
    ElMessage.warning('请上传图片并选择至少一个模型')
    return
  }

  console.log('Starting validation with models:', selectedModels.value)

  validating.value = true
  validationResults.value = null

  try {
    const formData = new FormData()
    formData.append('file', uploadedFile.value)

    // 将模型ID数组转换为JSON字符串
    const modelIdsJson = JSON.stringify(selectedModels.value)
    console.log('Model IDs JSON:', modelIdsJson)
    formData.append('model_ids', modelIdsJson)

    formData.append('confidence', confidence.value.toString())
    formData.append('iou', iou.value.toString())

    console.log('FormData contents:')
    for (let pair of formData.entries()) {
      console.log(pair[0] + ':', pair[1])
    }

    const response = await axios.post('/api/v1/validation/validate', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })

    console.log('Validation response:', response.data)

    validationResults.value = response.data
    if (validationResults.value.results.length > 0) {
      activeTab.value = validationResults.value.results[0].model_id
      await nextTick()
      drawResultForModel(activeTab.value)
    }

    ElMessage.success('验证完成')
  } catch (error) {
    console.error('Validation error:', error)
    ElMessage.error('验证失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    validating.value = false
  }
}

function setCanvasRef(modelId, el) {
  if (el) canvasRefs.value[modelId] = el
}

function drawResultForModel(modelId) {
  if (!previewImage.value || !validationResults.value) return
  const result = validationResults.value.results.find((r) => r.model_id === modelId)
  if (!result || result.error) return
  const canvas = canvasRefs.value[modelId]
  if (canvas) drawDetections(canvas, previewImage.value, result.detections)
}

function handleTabChange(tabName) {
  if (tabName === 'comparison') return
  nextTick(() => drawResultForModel(tabName))
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

.image-preview {
  margin-top: 16px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
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

