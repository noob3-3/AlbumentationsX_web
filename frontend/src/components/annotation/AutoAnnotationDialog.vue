<template>
  <el-dialog v-model="visible" title="自动标注" width="600px" @close="onClose">
    <el-form :model="form" :rules="rules" ref="formRef" label-width="120px">
      <el-form-item label="模型类型">
        <el-radio-group v-model="form.modelType" @change="onModelTypeChange">
          <el-radio value="pretrained">
            <el-icon><MagicStick /></el-icon>
            预训练模型
          </el-radio>
          <el-radio value="custom">
            <el-icon><Trophy /></el-icon>
            自定义模型
          </el-radio>
        </el-radio-group>
      </el-form-item>

      <!-- Pretrained Model Selection -->
      <el-form-item
        v-if="form.modelType === 'pretrained'"
        label="选择预训练模型"
        prop="pretrained_model_name"
      >
        <el-select
          v-model="form.pretrained_model_name"
          placeholder="选择Ultralytics官方模型"
          :loading="loadingPretrainedModels"
          style="width: 100%"
        >
          <el-option
            v-for="model in pretrainedModels"
            :key="model.filename"
            :label="`${model.name} (${model.size})`"
            :value="model.filename"
          >
            <div style="display: flex; flex-direction: column">
              <span style="font-weight: 500">{{ model.name }}</span>
              <span style="font-size: 12px; color: #909399">
                {{ model.description }}
              </span>
            </div>
          </el-option>
        </el-select>
        <el-alert
          style="margin-top: 8px"
          type="info"
          :closable="false"
          show-icon
        >
          <template #title>
            <span style="font-size: 12px">
              预训练模型可识别80种常见物体（人、汽车、猫、狗等）
            </span>
          </template>
        </el-alert>
      </el-form-item>

      <!-- Custom Model Selection -->
      <el-form-item
        v-if="form.modelType === 'custom'"
        label="选择自定义模型"
        prop="model_id"
      >
        <el-select
          v-model="form.model_id"
          placeholder="选择已训练的模型"
          :loading="loadingModels"
          style="width: 100%"
        >
          <el-option
            v-for="model in models"
            :key="model.id"
            :label="`${model.name} (mAP50: ${(model.map50 * 100).toFixed(1)}%)`"
            :value="model.id"
          />
        </el-select>
        <el-alert
          v-if="models.length === 0"
          style="margin-top: 8px"
          type="warning"
          :closable="false"
          show-icon
        >
          <template #title>
            <span style="font-size: 12px">
              暂无自定义模型，请先训练模型或使用预训练模型
            </span>
          </template>
        </el-alert>
      </el-form-item>

      <el-form-item label="置信度阈值" prop="confidence_threshold">
        <div style="display: flex; gap: 12px; align-items: center">
          <el-slider
            v-model="form.confidence_threshold"
            :min="0"
            :max="1"
            :step="0.01"
            :marks="{ 0: '0', 0.5: '0.5', 1: '1' }"
            style="flex: 1"
          />
          <span style="min-width: 40px">{{ form.confidence_threshold.toFixed(2) }}</span>
        </div>
      </el-form-item>

      <el-form-item label="标注范围">
        <el-radio-group v-model="form.scope">
          <el-radio value="all">全部图片</el-radio>
          <el-radio value="unlabeled">未标注的图片</el-radio>
          <el-radio value="selected">已选择的图片</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="数据类型">
        <el-radio-group v-model="form.dataType">
          <el-radio value="original">仅原始数据</el-radio>
          <el-radio value="all">包含增强数据</el-radio>
        </el-radio-group>
        <div style="margin-top: 8px; font-size: 12px; color: #909399">
          <template v-if="form.dataType === 'original'">
            只对原始上传的图片进行标注，跳过数据增强生成的图片
          </template>
          <template v-else>
            对所有图片（包括增强数据）进行标注
          </template>
        </div>
      </el-form-item>

      <el-form-item v-if="form.scope === 'selected'" label="已选图片">
        <el-alert
          :title="`已选择 ${selectedImages.length} 张图片`"
          type="info"
          :closable="false"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submitForm">
        开始自动标注
      </el-button>
    </template>
  </el-dialog>

  <!-- 进度对话框 -->
  <el-dialog
    v-model="progressVisible"
    title="自动标注进度"
    width="600px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="progressStatus === 'completed' || progressStatus === 'error'"
  >
    <div class="progress-content">
      <!-- 状态消息 -->
      <el-alert
        :type="progressStatus === 'completed' ? 'success' : progressStatus === 'error' ? 'error' : 'info'"
        :title="progressMessage"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      />

      <!-- 进度条 -->
      <el-progress
        :percentage="progressPercent"
        :status="progressStatus === 'completed' ? 'success' : progressStatus === 'error' ? 'exception' : undefined"
        :striped="progressStatus === 'processing'"
        :striped-flow="progressStatus === 'processing'"
      />

      <!-- 统计信息 -->
      <div class="stats" style="margin-top: 16px">
        <el-row :gutter="16">
          <el-col :span="8">
            <el-statistic title="已处理" :value="processedCount" />
          </el-col>
          <el-col :span="8">
            <el-statistic title="成功" :value="successCount">
              <template #suffix>
                <span style="color: #67c23a">✓</span>
              </template>
            </el-statistic>
          </el-col>
          <el-col :span="8">
            <el-statistic title="失败" :value="failedCount">
              <template #suffix>
                <span style="color: #f56c6c">✗</span>
              </template>
            </el-statistic>
          </el-col>
        </el-row>
      </div>

      <!-- 当前处理的图片 -->
      <div v-if="currentImage && progressStatus === 'processing'" style="margin-top: 16px">
        <el-text type="info">正在处理: {{ currentImage }}</el-text>
      </div>

      <!-- 检测日志（最近5条） -->
      <div v-if="detectionLogs.length > 0" style="margin-top: 16px">
        <el-divider content-position="left">检测日志</el-divider>
        <div class="log-container">
          <div
            v-for="(log, index) in detectionLogs.slice(-5)"
            :key="index"
            class="log-item"
          >
            <el-icon v-if="log.status === 'success'" color="#67c23a"><CircleCheck /></el-icon>
            <el-icon v-else color="#f56c6c"><CircleClose /></el-icon>
            <span class="log-text">{{ log.message }}</span>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button
        v-if="progressStatus === 'completed' || progressStatus === 'error'"
        type="primary"
        @click="closeProgress"
      >
        关闭
      </el-button>
      <el-text v-else type="info">
        <el-icon class="is-loading"><Loading /></el-icon>
        处理中，请稍候...
      </el-text>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, Trophy, CircleCheck, CircleClose, Loading } from '@element-plus/icons-vue'
import { trainingApi, annotationApi } from '@/api'

const props = defineProps({
  datasetId: String,
  projectId: String,  // 用于过滤自定义模型，只显示当前项目的模型
  selectedImages: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['success'])

const visible = ref(false)
const formRef = ref(null)
const loadingModels = ref(false)
const loadingPretrainedModels = ref(false)
const submitting = ref(false)
const models = ref([])
const pretrainedModels = ref([])

// 进度相关状态
const progressVisible = ref(false)
const progressStatus = ref('processing')
const progressMessage = ref('')
const currentImage = ref('')
const processedCount = ref(0)
const totalCount = ref(0)
const successCount = ref(0)
const failedCount = ref(0)
const progressPercent = ref(0)
const detectionLogs = ref([])

// WebSocket和轮询相关
let ws = null
let pollingTimer = null
let jobId = null
let lastUpdateTime = Date.now() // 记录最后更新时间

const form = ref({
  modelType: 'pretrained', // 'pretrained' or 'custom'
  model_id: '',
  pretrained_model_name: 'yolov8s.pt',
  confidence_threshold: 0.5,
  scope: 'unlabeled',
  dataType: 'original', // 'original' or 'all'
})

const rules = {
  model_id: [{
    required: false,
    validator: (rule, value, callback) => {
      if (form.value.modelType === 'custom' && !value) {
        callback(new Error('请选择自定义模型'))
      } else {
        callback()
      }
    }
  }],
  pretrained_model_name: [{
    required: false,
    validator: (rule, value, callback) => {
      if (form.value.modelType === 'pretrained' && !value) {
        callback(new Error('请选择预训练模型'))
      } else {
        callback()
      }
    }
  }],
}

const open = async () => {
  visible.value = true
  await Promise.all([
    fetchModels(),
    fetchPretrainedModels()
  ])
}

async function checkAndResumeActiveJob() {
  if (!props.datasetId) return

  try {
    console.log('🔍 Checking for active annotation job...')
    const res = await annotationApi.getActiveJob(props.datasetId)

    if (res.has_active_job && res.job) {
      console.log('✅ Found active job, resuming...', res.job)

      // 恢复任务状态
      jobId = res.job.job_id
      totalCount.value = res.job.total
      processedCount.value = res.job.current
      successCount.value = res.job.success_count
      failedCount.value = res.job.failed_count
      progressPercent.value = res.job.percent

      // 显示进度对话框
      progressVisible.value = true
      progressStatus.value = res.job.status === 'completed' ? 'completed' : 'processing'
      progressMessage.value = res.job.status === 'completed'
        ? `自动标注完成！成功: ${res.job.success_count}, 失败: ${res.job.failed_count}`
        : `恢复进度: ${res.job.current} / ${res.job.total}`

      // 如果任务还在运行，同时启动 WebSocket 和轮询
      if (res.job.status === 'running') {
        ElMessage.info('检测到进行中的标注任务，正在重新连接...')
        setTimeout(() => {
          connectWebSocket(jobId)
          startPolling(jobId)
        }, 500)
      }
    }
  } catch (error) {
    console.error('Failed to check active job:', error)
  }
}

const fetchModels = async () => {
  loadingModels.value = true
  try {
    const params = props.projectId ? { project_id: props.projectId } : {}
    const res = await trainingApi.listModels(params)
    models.value = res.models || []
    if (models.value.length > 0) {
      form.value.model_id = models.value[0].id
    } else {
      // No custom models, switch to pretrained
      form.value.modelType = 'pretrained'
    }
  } catch (error) {
    ElMessage.error('加载模型列表失败')
  } finally {
    loadingModels.value = false
  }
}

const fetchPretrainedModels = async () => {
  loadingPretrainedModels.value = true
  try {
    const res = await annotationApi.listPretrainedModels()
    pretrainedModels.value = res.models || []
    if (!form.value.pretrained_model_name && pretrainedModels.value.length > 0) {
      form.value.pretrained_model_name = pretrainedModels.value[0].filename
    }
  } catch (error) {
    console.error('Failed to load pretrained models:', error)
    // Use default list if API fails
    pretrainedModels.value = [
      {
        filename: 'yolov8n.pt',
        name: 'YOLOv8 Nano',
        size: '~6 MB',
        description: '最小最快，适合快速测试'
      },
      {
        filename: 'yolov8s.pt',
        name: 'YOLOv8 Small',
        size: '~22 MB',
        description: '推荐使用，速度与精度平衡'
      },
      {
        filename: 'yolov8m.pt',
        name: 'YOLOv8 Medium',
        size: '~52 MB',
        description: '较高精度'
      },
      {
        filename: 'yolo11n.pt',
        name: 'YOLO11 Nano',
        size: '~6 MB',
        description: '最新YOLO11，最快'
      },
      {
        filename: 'yolo11s.pt',
        name: 'YOLO11 Small',
        size: '~20 MB',
        description: '最新YOLO11，推荐'
      },
    ]
  } finally {
    loadingPretrainedModels.value = false
  }
}

const onModelTypeChange = () => {
  // Clear validation when switching model type
  formRef.value?.clearValidate()
}

const submitForm = async () => {
  if (!formRef.value) return
  await formRef.value.validate()

  submitting.value = true
  try {
    const imageIds =
      form.value.scope === 'selected'
        ? props.selectedImages.map((img) => img.id)
        : undefined // 由 annotate_all 参数控制

    const requestData = {
      dataset_id: props.datasetId,
      confidence_threshold: form.value.confidence_threshold,
      image_ids: imageIds,
      annotate_all: form.value.scope === 'all', // true = 标注所有图片，false = 只标注未标注的
      include_augmented: form.value.dataType === 'all', // true = 包含增强数据，false = 仅原始数据
    }

    // Add model-specific parameters
    if (form.value.modelType === 'pretrained') {
      requestData.use_pretrained = true
      requestData.pretrained_model_name = form.value.pretrained_model_name
      requestData.model_id = null // Optional when using pretrained
    } else {
      requestData.use_pretrained = false
      requestData.model_id = form.value.model_id
      requestData.pretrained_model_name = null
    }

    const response = await annotationApi.autoAnnotate(requestData)

    // 获取job_id
    jobId = response.job_id
    console.log('✅ Auto-annotation job created:', jobId)

    // 关闭配置对话框
    visible.value = false

    // 显示进度对话框
    showProgress()

    // 同时启动 WebSocket 和轮询（双保险）
    setTimeout(() => {
      console.log('🔌 Starting WebSocket and polling...')
      connectWebSocket(jobId)
      startPolling(jobId)
    }, 200)

  } catch (error) {
    console.error('Auto-annotation failed:', error)
    ElMessage.error(error.response?.data?.detail || '创建自动标注任务失败')
  } finally {
    submitting.value = false
  }
}

function showProgress() {
  progressVisible.value = true
  progressStatus.value = 'processing'
  progressMessage.value = '正在初始化任务...'
  currentImage.value = ''
  processedCount.value = 0
  totalCount.value = 0
  successCount.value = 0
  failedCount.value = 0
  progressPercent.value = 0
  detectionLogs.value = []
  lastUpdateTime = Date.now()

  console.log('📊 Progress dialog opened')
}

async function checkJobStatus(jobId) {
  // 检查任务状态，处理任务已完成的情况
  try {
    const response = await annotationApi.getActiveJob(props.datasetId)
    if (response.job) {
      const job = response.job
      console.log('📊 Job status check:', job.status)

      if (job.status === 'completed') {
        console.log('✅ Job already completed, updating UI')
        // 任务已完成，立即更新UI
        handleJobUpdate({
          type: 'annotation_completed',
          success_count: job.success_count || 0,
          failed_count: job.failed_count || 0,
          total: job.total || 0,
          message: '自动标注完成'
        })
      } else if (job.status === 'failed' || job.status === 'error') {
        console.log('❌ Job failed, updating UI')
        handleJobUpdate({
          type: 'annotation_error',
          message: job.error_message || '标注任务失败'
        })
      }
    }
  } catch (error) {
    console.error('Failed to check job status:', error)
    // 不影响正常流程，继续等待
  }
}

// WebSocket 连接
function connectWebSocket(jobId) {
  const isDev = import.meta.env.DEV
  let wsUrl

  if (isDev) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    wsUrl = `${protocol}//${host}/ws/annotation/${jobId}`
  } else {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    wsUrl = `${protocol}//${host}/ws/annotation/${jobId}`
  }

  console.log('🔌 Connecting to WebSocket:', wsUrl)

  ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    console.log('✅ WebSocket connected for annotation job:', jobId)
    progressMessage.value = '已连接实时进度...'

    // 检查任务是否已经完成
    checkJobStatus(jobId)

    // 发送ping保持连接
    const pingInterval = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send('ping')
      } else {
        clearInterval(pingInterval)
      }
    }, 25000)

    ws._pingInterval = pingInterval
  }

  ws.onmessage = (event) => {
    try {
      if (event.data === 'pong') return

      const data = JSON.parse(event.data)
      console.log('📨 WS message received:', data.type, data)

      // 更新最后接收时间
      lastUpdateTime = Date.now()

      handleJobUpdate(data)
    } catch (error) {
      console.error('Failed to parse WS message:', error)
    }
  }

  ws.onerror = (error) => {
    console.error('❌ WebSocket error:', error)
    progressMessage.value = '实时连接失败，使用轮询模式'
  }

  ws.onclose = (event) => {
    console.log('🔌 WebSocket closed:', event.code, event.reason)

    // 使用 event.target 而非 ws，避免竞态：ws 可能已被置为 null
    const closedWs = event.target
    if (closedWs?._pingInterval) {
      clearInterval(closedWs._pingInterval)
    }

    // 不重连，依靠轮询获取进度
    console.log('ℹ️ WebSocket closed, polling will continue')
  }
}

// 开始轮询任务进度
function startPolling(jobId) {
  console.log('🔄 Starting progress polling for job:', jobId)

  // 清除之前的轮询
  if (pollingTimer) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }

  // 立即执行一次
  pollJobProgress(jobId)

  // 每秒轮询一次
  pollingTimer = setInterval(() => {
    pollJobProgress(jobId)
  }, 1000)
}

// 轮询任务进度
async function pollJobProgress(jobId) {
  if (!jobId) return

  try {
    const response = await annotationApi.getActiveJob(props.datasetId)

    if (!response.job) {
      console.warn('⚠️ Job not found, stopping polling')
      stopPolling()

      // 检查是否长时间无更新
      const timeSinceLastUpdate = Date.now() - lastUpdateTime
      if (timeSinceLastUpdate > 30000 && progressStatus.value === 'processing') {
        // 超过30秒无更新，关闭进度对话框
        console.warn('⚠️ No updates for 30s, closing progress dialog')
        progressStatus.value = 'error'
        progressMessage.value = '任务超时无响应，已自动关闭'
        ElMessage.warning('标注任务长时间无响应，请检查任务状态')

        setTimeout(() => {
          closeProgress()
        }, 3000)
      }
      return
    }

    const job = response.job

    // 记录更新时间
    lastUpdateTime = Date.now()

    // 更新进度信息
    totalCount.value = job.total || 0
    processedCount.value = job.current || 0
    successCount.value = job.success_count || 0
    failedCount.value = job.failed_count || 0
    progressPercent.value = job.percent || 0

    if (job.current > 0 && job.total > 0) {
      progressMessage.value = `正在标注: ${job.current} / ${job.total}`
    }

    // 检查任务状态
    if (job.status === 'completed') {
      console.log('✅ Job completed (polling)')
      stopPolling()

      progressStatus.value = 'completed'
      progressMessage.value = `自动标注完成！成功: ${job.success_count}, 失败: ${job.failed_count}`
      progressPercent.value = 100
      currentImage.value = ''

      ElMessage.success(`标注完成！成功 ${job.success_count} 张，失败 ${job.failed_count} 张`)

      emit('success', {
        success_count: job.success_count,
        failed_count: job.failed_count,
        total: job.total
      })

      // 关闭 WebSocket
      if (ws) {
        ws.close()
        ws = null
      }
    } else if (job.status === 'failed' || job.status === 'error') {
      console.error('❌ Job failed (polling)')
      stopPolling()

      progressStatus.value = 'error'
      progressMessage.value = job.error_message || '标注过程发生错误'

      ElMessage.error(job.error_message || '自动标注失败')

      // 关闭 WebSocket
      if (ws) {
        ws.close()
        ws = null
      }
    }
  } catch (error) {
    console.error('Failed to poll job progress:', error)
    // 网络错误不停止轮询，继续重试
  }
}

// 停止轮询
function stopPolling() {
  if (pollingTimer) {
    console.log('🛑 Stopping progress polling')
    clearInterval(pollingTimer)
    pollingTimer = null
  }
}

function handleJobUpdate(data) {
  console.log('🔄 Processing job update:', data.type)

  switch (data.type) {
    case 'job_created':
      progressMessage.value = data.message
      console.log('📝 Job created')
      break

    case 'task_started':
      progressMessage.value = data.message
      console.log('🚀 Task started')
      break

    case 'device_info':
      progressMessage.value = data.message
      if (data.device === 'cuda') {
        ElMessage.success(`🚀 使用 GPU 加速: ${data.gpu_name}`)
        console.log('🎮 GPU enabled:', data.gpu_name)
      } else {
        ElMessage.info('使用 CPU 进行推理')
        console.log('💻 Using CPU')
      }
      break

    case 'model_loading':
      progressMessage.value = data.message
      console.log('📦 Model loading:', data.message)
      break

    case 'annotation_started':
      progressMessage.value = data.message
      totalCount.value = data.total
      console.log('🚀 Annotation started, total images:', data.total)
      break

    case 'annotation_progress':
      processedCount.value = data.current
      totalCount.value = data.total
      successCount.value = data.success_count
      failedCount.value = data.failed_count
      progressPercent.value = data.percent
      currentImage.value = data.image_name
      progressMessage.value = `正在标注: ${data.current} / ${data.total}`
      console.log(`⏳ Progress: ${data.current}/${data.total} (${data.percent}%)`)
      break

    case 'image_completed':
      detectionLogs.value.push({
        status: 'success',
        message: `${data.image_name} - 检测到 ${data.detections} 个物体`,
      })
      console.log(`✅ Image completed: ${data.image_name}, detections: ${data.detections}`)
      break

    case 'image_failed':
      detectionLogs.value.push({
        status: 'error',
        message: `${data.image_name} - 失败`,
      })
      console.error(`❌ Image failed: ${data.image_name}`)
      break

    case 'annotation_completed':
      progressStatus.value = 'completed'
      progressMessage.value = `自动标注完成！成功: ${data.success_count}, 失败: ${data.failed_count}`
      progressPercent.value = 100
      currentImage.value = ''

      console.log('🎉 Annotation completed:', data)
      ElMessage.success(`标注完成！成功 ${data.success_count} 张，失败 ${data.failed_count} 张`)

      emit('success', data)

      if (ws) {
        ws.close()
        ws = null
      }
      break

    case 'annotation_error':
      progressStatus.value = 'error'
      progressMessage.value = data.message || '标注过程发生错误'

      console.error('💥 Annotation error:', data.message)
      ElMessage.error(data.message || '自动标注失败')

      if (ws) {
        ws.close()
        ws = null
      }
      break

    default:
      console.warn('⚠️ Unknown message type:', data.type)
  }
}

function closeProgress() {
  progressVisible.value = false

  // 停止轮询
  stopPolling()

  // 关闭 WebSocket
  if (ws) {
    ws.close()
    ws = null
  }
}

const onClose = () => {
  formRef.value?.clearValidate()

  // 停止轮询
  stopPolling()

  // 关闭 WebSocket
  if (ws) {
    ws.close()
    ws = null
  }
}

defineExpose({
  open,
  checkAndResumeActiveJob,
})
</script>

<style scoped>
.el-form {
  padding: 20px 0;
}

.progress-content {
  min-height: 200px;
}

.stats {
  background: #f5f7fa;
  padding: 16px;
  border-radius: 4px;
}

.log-container {
  max-height: 150px;
  overflow-y: auto;
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
}

.log-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
}

.log-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>

