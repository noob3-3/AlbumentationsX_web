<template>
  <div>
    <div class="page-header">
      <h2>模型部署</h2>
      <p>部署训练完成的模型并进行在线推理测试</p>
    </div>

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

    <el-row :gutter="16">
      <!-- Deployments list -->
      <el-col :span="6">
        <el-card shadow="never">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span>部署列表</span>
              <el-button type="primary" size="small" :icon="Plus" @click="openDeployDialog">部署</el-button>
            </div>
          </template>

          <div class="deployments-list">
            <div
              v-for="deployment in deployments"
              :key="deployment.id"
              class="deployment-item"
              :class="{ active: selectedDeployment?.id === deployment.id }"
              @click="selectDeployment(deployment)"
            >
              <div class="deploy-name">{{ deployment.name }}</div>
              <div class="deploy-status">
                <el-tag
                  :type="deployment.status === 'running' ? 'success' : 'info'"
                  size="small"
                >
                  {{ statusText(deployment.status) }}
                </el-tag>
              </div>
            </div>

            <el-empty v-if="deployments.length === 0" description="暂无部署" />
          </div>
        </el-card>
      </el-col>

      <!-- Deployment details and inference -->
      <el-col :span="18">
        <el-card v-if="selectedDeployment" shadow="never">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span>{{ selectedDeployment.name }}</span>
              <el-space>
                <el-button
                  v-if="selectedDeployment.status === 'running'"
                  @click="stopDeployment"
                  type="danger"
                  size="small"
                  :loading="operatingDeployment"
                >
                  停止
                </el-button>
                <el-button
                  v-else
                  @click="startDeployment"
                  type="success"
                  size="small"
                  :loading="operatingDeployment"
                >
                  启动
                </el-button>
                <el-popconfirm title="确认删除此部署?" @confirm="deleteDeployment">
                  <template #reference>
                    <el-button type="danger" size="small" plain>删除</el-button>
                  </template>
                </el-popconfirm>
              </el-space>
            </div>
          </template>

          <!-- Deployment info -->
          <el-row :gutter="16" style="margin-bottom: 24px">
            <el-col :span="6">
              <div class="info-box">
                <div class="info-label">模型</div>
                <div class="info-value" style="font-size: 14px">{{ selectedDeployment.model_name }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="info-box">
                <div class="info-label">部署时间</div>
                <div class="info-value" style="font-size: 12px">
                  {{ formatDate(selectedDeployment.created_at) }}
                </div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="info-box">
                <div class="info-label">推理次数</div>
                <div class="info-value">{{ selectedDeployment.inference_count || 0 }}</div>
              </div>
            </el-col>
            <el-col :span="6">
              <div class="info-box">
                <div class="info-label">平均耗时</div>
                <div class="info-value">{{ selectedDeployment.avg_time || '-' }}</div>
              </div>
            </el-col>
          </el-row>

          <el-divider />

          <!-- Tabs: Inference Test and API Doc -->
          <el-tabs v-model="activeTab">
            <el-tab-pane label="推理测试" name="inference">
              <!-- Inference test section moved here -->
              <div class="inference-section">

            <el-row :gutter="16">
              <!-- Image upload -->
              <el-col :span="12">
                <div class="upload-section">
                  <el-upload
                    ref="uploadRef"
                    drag
                    action="#"
                    :auto-upload="false"
                    :limit="1"
                    accept="image/*"
                    :on-exceed="handleExceed"
                    :on-remove="handleRemove"
                    @change="handleImageSelect"
                  >
                    <el-icon class="el-icon--upload"><Upload /></el-icon>
                    <div class="el-upload__text">拖拽上传或<em>点击选择</em>图片</div>
                    <template #tip>
                      <div class="el-upload__tip">支持 jpg/png 格式图片</div>
                    </template>
                  </el-upload>

                  <div v-if="selectedImage" style="margin-top: 12px">
                    <el-image :src="selectedImage.url" style="max-width: 100%; border-radius: 4px" />
                  </div>
                </div>
              </el-col>

              <!-- Inference controls -->
              <el-col :span="12">
                <div class="controls-section">
                  <el-form label-width="100px">
                    <el-form-item label="置信度">
                      <el-slider
                        v-model="inferenceParams.confidence"
                        :min="0"
                        :max="1"
                        :step="0.01"
                        :marks="{ 0: '0', 0.5: '0.5', 1: '1' }"
                      />
                    </el-form-item>
                    <el-form-item label="IOU阈值">
                      <el-slider
                        v-model="inferenceParams.iou"
                        :min="0"
                        :max="1"
                        :step="0.01"
                        :marks="{ 0: '0', 0.5: '0.5', 1: '1' }"
                      />
                    </el-form-item>
                    <el-form-item>
                      <el-button
                        type="primary"
                        @click="runInference"
                        :loading="inferenceLoading"
                        :disabled="!selectedImage"
                        block
                      >
                        运行推理
                      </el-button>
                    </el-form-item>
                  </el-form>
                </div>
              </el-col>
            </el-row>

            <!-- Inference results -->
            <div v-if="inferenceResult" style="margin-top: 24px">
              <el-divider />
              <h4>推理结果</h4>

              <div class="result-layout">
                <div class="result-image-wrap">
                  <canvas ref="resultCanvasRef" class="result-canvas" />
                </div>

                <div class="result-info-panel">
                  <div class="stat-item">
                    <span class="stat-label">检测物体数</span>
                    <span class="stat-value">{{ inferenceResult.detections?.length || 0 }}</span>
                  </div>
                  <div class="stat-item">
                    <span class="stat-label">推理耗时</span>
                    <span class="stat-value">{{ inferenceResult.inference_time?.toFixed(3) }} s</span>
                  </div>

                  <div class="detection-list-title">检测结果</div>
                  <div v-if="inferenceResult.detections?.length === 0" class="no-detection">
                    未检测到任何物体
                  </div>
                  <div v-else class="detection-list">
                    <div
                      v-for="(det, idx) in inferenceResult.detections"
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
            </div>
              </div>
            </el-tab-pane>

            <!-- API Documentation Tab -->
            <el-tab-pane label="API 文档" name="api">
              <div class="api-doc">
                <h3>部署 API 使用说明</h3>

                <el-alert type="info" :closable="false" style="margin-bottom: 16px">
                  <template #title>
                    此部署已加载模型到内存，可直接调用 API 进行推理，无需额外加载时间
                  </template>
                </el-alert>

                <h4>API 端点</h4>
                <el-input
                  :value="`${getApiBaseUrl()}/api/v1/deployments/${selectedDeployment.id}/predict`"
                  readonly
                >
                  <template #append>
                    <el-button @click="copyApiUrl">复制</el-button>
                  </template>
                </el-input>

                <h4 style="margin-top: 24px">请求方式</h4>
                <el-tag>POST</el-tag>
                <el-tag type="info" style="margin-left: 8px">multipart/form-data</el-tag>

                <h4 style="margin-top: 24px">请求参数</h4>
                <el-table :data="apiParams" border size="small">
                  <el-table-column prop="name" label="参数名" width="120" />
                  <el-table-column prop="type" label="类型" width="100" />
                  <el-table-column prop="required" label="必填" width="80">
                    <template #default="{ row }">
                      <el-tag :type="row.required ? 'danger' : 'info'" size="small">
                        {{ row.required ? '是' : '否' }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="description" label="说明" />
                </el-table>

                <h4 style="margin-top: 24px">响应示例</h4>
                <el-input
                  type="textarea"
                  :rows="12"
                  readonly
                  :value="responseExample"
                  style="font-family: monospace; font-size: 12px"
                />

                <h4 style="margin-top: 24px">调用示例</h4>
                <el-tabs type="border-card">
                  <el-tab-pane label="Python">
                    <pre style="background: #f5f5f5; padding: 12px; border-radius: 4px; overflow-x: auto"><code>{{ pythonExample }}</code></pre>
                  </el-tab-pane>
                  <el-tab-pane label="cURL">
                    <pre style="background: #f5f5f5; padding: 12px; border-radius: 4px; overflow-x: auto"><code>{{ curlExample }}</code></pre>
                  </el-tab-pane>
                  <el-tab-pane label="JavaScript">
                    <pre style="background: #f5f5f5; padding: 12px; border-radius: 4px; overflow-x: auto"><code>{{ jsExample }}</code></pre>
                  </el-tab-pane>
                </el-tabs>
              </div>
            </el-tab-pane>
          </el-tabs>

        </el-card>

        <el-empty v-else description="请先选择部署或创建新的部署" :image-size="150" />
      </el-col>
    </el-row>

    <!-- Deploy dialog -->
    <el-dialog v-model="showDeployDialog" title="部署模型" width="500px">
      <el-form :model="deployForm" :rules="deployRules" ref="deployFormRef" label-width="100px">
        <el-form-item label="部署名称" prop="name">
          <el-input v-model="deployForm.name" placeholder="输入部署名称" />
        </el-form-item>

        <el-form-item label="选择模型" prop="model_id">
          <el-select v-model="deployForm.model_id" placeholder="选择已训练的模型" filterable>
            <el-option
              v-for="model in models"
              :key="model.id"
              :label="`${model.name} (mAP50: ${(model.map50 * 100).toFixed(1)}%)`"
              :value="model.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="设备">
          <el-radio-group v-model="deployForm.device">
            <el-radio value="cpu">CPU</el-radio>
            <el-radio value="cuda">GPU (CUDA)</el-radio>
            <el-radio value="auto">自动</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="描述">
          <el-input v-model="deployForm.description" type="textarea" placeholder="部署描述（可选）" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showDeployDialog = false">取消</el-button>
        <el-button type="primary" @click="submitDeploy" :loading="deploying">部署</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import {nextTick, onMounted, ref, watch} from 'vue'
import {ElMessage} from 'element-plus'
import {Plus, Upload} from '@element-plus/icons-vue'
import {deploymentApi, trainingApi} from '@/api'
import {drawDetectionOverlay} from '@/utils/drawDetectionsCanvas'
import {useProjectStore} from '@/stores/project'
import {storeToRefs} from 'pinia'

const COLORS = [
  '#FF6B6B', '#4ECDC4', '#45B7D1', '#96E6A1', '#DDA0DD',
  '#F7DC6F', '#BB8FCE', '#F1948A', '#85C1E9', '#82E0AA',
  '#F8C471', '#D7BDE2', '#A3E4D7', '#F0B27A', '#AED6F1',
]

function getColor(index) {
  return COLORS[index % COLORS.length]
}

function drawDetections(canvas, imageSrc, detections) {
  const ctx = canvas.getContext('2d')
  const img = new Image()
  img.onload = () => {
    const maxW = canvas.parentElement.clientWidth
    const scale = maxW / img.width
    canvas.width = img.width * scale
    canvas.height = img.height * scale
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)

    drawDetectionOverlay(ctx, scale, detections, getColor)
  }
  img.src = imageSrc
}

const projectStore = useProjectStore()
const { hasProject, projectId } = storeToRefs(projectStore)

// 使用真实数据
const deployments = ref([])
const models = ref([])
const loading = ref(false)

const selectedDeployment = ref(null)
const showDeployDialog = ref(false)
const uploadRef = ref(null)
const operatingDeployment = ref(false)
const deploying = ref(false)
const inferenceLoading = ref(false)

const deployForm = ref({
  name: '',
  model_id: '',
  device: 'auto',
  description: '',
})

const deployRules = {
  name: [{ required: true, message: '请输入部署名称' }],
  model_id: [{ required: true, message: '请选择模型' }],
}

const selectedImage = ref(null)
const inferenceParams = ref({
  confidence: 0.5,
  iou: 0.45,
})

const inferenceResult = ref(null)
const activeTab = ref('inference')
const resultCanvasRef = ref(null)

const deployFormRef = ref(null)

// API文档相关数据
const apiParams = ref([
  { name: 'file', type: 'File', required: true, description: '要进行推理的图片文件 (jpg/png)' },
  { name: 'confidence', type: 'float', required: false, description: '置信度阈值 (默认: 0.5)' },
  { name: 'iou', type: 'float', required: false, description: 'IOU阈值 (默认: 0.45)' },
])

const responseExample = `{
  "detections": [
    {
      "class_id": 0,
      "class_name": "person",
      "confidence": 0.89,
      "bbox": [100, 150, 300, 450]
    },
    {
      "class_id": 1,
      "class_name": "car",
      "confidence": 0.76,
      "bbox": [400, 200, 600, 400]
    }
  ],
  "inference_time": 0.234,
  "image_with_boxes": "data:image/jpeg;base64,/9j/4AAQ..."
}`

const pythonExample = `import requests

# API端点
url = "${window.location.origin}/api/v1/deployments/${selectedDeployment.value?.id || '{deployment_id}'}/predict"

# 准备文件和参数
files = {
    'file': open('test_image.jpg', 'rb')
}
params = {
    'confidence': 0.5,
    'iou': 0.45
}

# 发送请求
response = requests.post(url, files=files, params=params)
result = response.json()

# 处理结果
print(f"检测到 {len(result['detections'])} 个物体")
for det in result['detections']:
    print(f"  - {det['class_name']}: {det['confidence']:.2%}")
`

const curlExample = `curl -X POST \\
  "${window.location.origin}/api/v1/deployments/${selectedDeployment.value?.id || '{deployment_id}'}/predict?confidence=0.5&iou=0.45" \\
  -H "Content-Type: multipart/form-data" \\
  -F "file=@test_image.jpg"
`

const jsExample = `// 使用 Fetch API
const formData = new FormData();
formData.append('file', fileInput.files[0]);

const url = '${window.location.origin}/api/v1/deployments/${selectedDeployment.value?.id || '{deployment_id}'}/predict';
const params = new URLSearchParams({
  confidence: 0.5,
  iou: 0.45
});

fetch(\`\${url}?\${params}\`, {
  method: 'POST',
  body: formData
})
  .then(response => response.json())
  .then(data => {
    console.log('检测结果:', data.detections);
    // 显示带标注的图片
    document.getElementById('result').src = data.image_with_boxes;
  })
  .catch(error => console.error('Error:', error));
`

function getApiBaseUrl() {
  return window.location.origin
}

function copyApiUrl() {
  const url = `${getApiBaseUrl()}/api/v1/deployments/${selectedDeployment.value.id}/predict`
  navigator.clipboard.writeText(url).then(() => {
    ElMessage.success('API地址已复制到剪贴板')
  })
}

onMounted(async () => {
  await loadData()
  if (deployments.value.length > 0) {
    selectedDeployment.value = deployments.value[0]
  }
})

watch(projectId, () => loadData())

async function loadData() {
  loading.value = true
  try {
    // 加载模型
    await loadModels()

    // 从后端加载部署数据
    const deploymentsResponse = await deploymentApi.listDeployments()
    deployments.value = deploymentsResponse.items || []
  } catch (error) {
    console.error('Failed to load data:', error)
    ElMessage.error('加载数据失败')
  } finally {
    loading.value = false
  }
}

// 不再需要手动保存到 localStorage，由后端管理

async function openDeployDialog() {
  showDeployDialog.value = true
  // 刷新模型列表，确保显示最新的模型
  await loadModels()
}

async function loadModels() {
  try {
    const params = {}
    if (projectId.value) {
      params.project_id = projectId.value
    }
    const modelsResponse = await trainingApi.listModels(params)
    console.log('Refreshing models:', modelsResponse)
    models.value = modelsResponse.models || modelsResponse.items || []
  } catch (error) {
    console.error('Failed to load models:', error)
    ElMessage.error('加载模型列表失败')
  }
}

function selectDeployment(deployment) {
  selectedDeployment.value = deployment
  inferenceResult.value = null
}

function statusText(status) {
  return {
    running: '运行中',
    stopped: '已停止',
    error: '错误',
  }[status] || status
}

function formatDate(date) {
  return new Date(date).toLocaleString('zh-CN', { hour12: false })
}

function handleImageSelect(file) {
  const reader = new FileReader()
  reader.onload = (e) => {
    selectedImage.value = {
      file: file.raw,
      url: e.target.result,
    }
    // 清除之前的推理结果
    inferenceResult.value = null
  }
  reader.readAsDataURL(file.raw)
}

function handleExceed(files) {
  // 当超过限制时，清除旧文件，使用新文件
  uploadRef.value.clearFiles()
  const file = files[0]
  uploadRef.value.handleStart(file)
  handleImageSelect({ raw: file })
}

function handleRemove() {
  // 移除图片时清除选择
  selectedImage.value = null
  inferenceResult.value = null
}

async function runInference() {
  if (!selectedImage.value || !selectedDeployment.value) return

  inferenceLoading.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedImage.value.file)

    inferenceResult.value = await deploymentApi.predict(
      selectedDeployment.value.id,
      formData,
      {
        confidence: inferenceParams.value.confidence,
        iou: inferenceParams.value.iou,
      }
    )
    ElMessage.success('推理完成')
    await nextTick()
    if (resultCanvasRef.value && selectedImage.value) {
      drawDetections(resultCanvasRef.value, selectedImage.value.url, inferenceResult.value.detections)
    }
  } catch (error) {
    console.error('Inference failed:', error)
    ElMessage.error('推理失败：' + (error.response?.data?.detail || error.message))
  } finally {
    inferenceLoading.value = false
  }
}

async function startDeployment() {
  if (!selectedDeployment.value) return

  operatingDeployment.value = true
  try {
    await deploymentApi.restartDeployment(selectedDeployment.value.id)
    selectedDeployment.value.status = 'running'
    ElMessage.success('部署已启动')
  } catch (error) {
    console.error('Failed to start deployment:', error)
    ElMessage.error('启动部署失败：' + (error.response?.data?.detail || error.message))
  } finally {
    operatingDeployment.value = false
  }
}

async function stopDeployment() {
  if (!selectedDeployment.value) return

  operatingDeployment.value = true
  try {
    await deploymentApi.stopDeployment(selectedDeployment.value.id)
    selectedDeployment.value.status = 'stopped'
    ElMessage.success('部署已停止')
  } catch (error) {
    console.error('Failed to stop deployment:', error)
    ElMessage.error('停止部署失败：' + (error.response?.data?.detail || error.message))
  } finally {
    operatingDeployment.value = false
  }
}

async function deleteDeployment() {
  if (!selectedDeployment.value) return

  try {
    await deploymentApi.deleteDeployment(selectedDeployment.value.id)
    const index = deployments.value.findIndex((d) => d.id === selectedDeployment.value.id)
    if (index > -1) {
      deployments.value.splice(index, 1)
      selectedDeployment.value = deployments.value[0] || null
    }
    ElMessage.success('部署已删除')
  } catch (error) {
    console.error('Failed to delete deployment:', error)
    ElMessage.error('删除部署失败：' + (error.response?.data?.detail || error.message))
  }
}

async function submitDeploy() {
  if (!deployFormRef.value) return

  deployFormRef.value.validate(async (valid) => {
    if (!valid) return

    deploying.value = true

    try {
      const deployData = {
        name: deployForm.value.name,
        model_id: deployForm.value.model_id,
        device: deployForm.value.device,
        confidence_threshold: 0.5,
        iou_threshold: 0.45,
        max_detections: 100,
      }

      const newDeployment = await deploymentApi.createDeployment(deployData)
      deployments.value.unshift(newDeployment)
      selectedDeployment.value = newDeployment
      showDeployDialog.value = false
      deployForm.value = { name: '', model_id: '', device: 'auto', description: '' }
      ElMessage.success('部署创建成功')
    } catch (error) {
      console.error('Failed to create deployment:', error)
      ElMessage.error('创建部署失败：' + (error.response?.data?.detail || error.message))
    } finally {
      deploying.value = false
    }
  })
}
</script>

<style scoped>
.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  margin: 0 0 8px 0;
  font-size: 24px;
  font-weight: 600;
}

.page-header p {
  margin: 0;
  color: #909399;
}

.deployments-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.deployment-item {
  padding: 12px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.deployment-item:hover {
  border-color: #409eff;
  background: #f0f9ff;
}

.deployment-item.active {
  border-color: #409eff;
  background: #e6f7ff;
}

.deploy-name {
  font-weight: 500;
  flex: 1;
}

.deploy-status {
  margin-left: 8px;
}

.info-box {
  background: #f5f7fa;
  padding: 16px;
  border-radius: 4px;
  text-align: center;
}

.info-label {
  color: #909399;
  font-size: 12px;
  margin-bottom: 8px;
}

.info-value {
  font-size: 20px;
  font-weight: bold;
  color: #303133;
}

.inference-section h3 {
  margin-top: 0;
  margin-bottom: 20px;
  font-size: 18px;
  font-weight: 500;
}

.inference-section h4 {
  margin-bottom: 16px;
  font-size: 16px;
}

.inference-section h5 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.upload-section {
  background: #f5f7fa;
  padding: 16px;
  border-radius: 4px;
}

.controls-section {
  background: #f5f7fa;
  padding: 16px;
  border-radius: 4px;
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
  width: 240px;
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
</style>

