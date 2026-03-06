<template>
  <div>
    <el-page-header @back="$router.push('/training')">
      <template #content>
        <span style="font-weight:600">{{ job?.name }}</span>
        <el-tag :type="statusType(job?.status)" size="small" style="margin-left:10px">
          {{ statusText(job?.status) }}
        </el-tag>
      </template>
      <template #extra>
        <el-button
          v-if="job?.status === 'running' || job?.status === 'pending'"
          type="danger"
          @click="cancelJob"
        >
          取消训练
        </el-button>
        <el-dropdown v-if="job?.model_path" @command="handleDownload" style="margin-left: 10px">
          <el-button type="primary">
            下载模型 <el-icon class="el-icon--right"><arrow-down /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="weights">
                <el-icon><Download /></el-icon>
                仅权重文件 (best.pt)
              </el-dropdown-item>
              <el-dropdown-item command="package" divided>
                <el-icon><FolderOpened /></el-icon>
                完整包 (权重+标签+说明)
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </template>
    </el-page-header>

    <el-row :gutter="16" style="margin-top:20px">
      <!-- Job Info -->
      <el-col :span="8">
        <el-card shadow="never">
          <template #header><span>训练信息</span></template>
          <el-descriptions :column="1" size="small">
            <el-descriptions-item label="基础模型">{{ job?.model_name }}</el-descriptions-item>
            <el-descriptions-item label="数据集">{{ job?.dataset_id?.slice(0,8) }}...</el-descriptions-item>
            <el-descriptions-item label="训练轮数">{{ job?.current_epoch }} / {{ job?.epochs }}</el-descriptions-item>
            <el-descriptions-item label="批大小">{{ job?.batch_size }}</el-descriptions-item>
            <el-descriptions-item label="图片尺寸">{{ job?.img_size }}</el-descriptions-item>
            <el-descriptions-item label="学习率">{{ job?.learning_rate }}</el-descriptions-item>
            <el-descriptions-item label="设备">{{ job?.device }}</el-descriptions-item>

            <!-- 数据使用情况 -->
            <el-descriptions-item v-if="dataInfo" label="训练数据">
              <el-tag v-if="dataInfo.use_augmented" type="success" size="small">
                使用增强数据
              </el-tag>
              <el-tag v-else type="info" size="small">
                仅原始数据
              </el-tag>
              <div style="font-size: 12px; color: #909399; margin-top: 4px">
                {{ dataInfo.train_images }} 训练 + {{ dataInfo.val_images }} 验证
                <span v-if="dataInfo.use_augmented">
                  (含 {{ dataInfo.augmented_count }} 张增强)
                </span>
              </div>
            </el-descriptions-item>

            <el-descriptions-item label="开始时间">{{ formatDate(job?.started_at) }}</el-descriptions-item>
            <el-descriptions-item label="完成时间">{{ formatDate(job?.completed_at) }}</el-descriptions-item>

            <!-- 时间预估（训练中显示） -->
            <el-descriptions-item
              v-if="job?.status === 'running' && estimatedInfo.remaining"
              label="预计剩余"
            >
              <el-text type="warning">{{ estimatedInfo.remaining }}</el-text>
            </el-descriptions-item>
            <el-descriptions-item
              v-if="job?.status === 'running' && estimatedInfo.completion"
              label="预计完成"
            >
              <el-text type="info">{{ estimatedInfo.completion }}</el-text>
            </el-descriptions-item>
            <el-descriptions-item
              v-if="job?.status === 'running' && estimatedInfo.avgEpochTime"
              label="平均每轮"
            >
              {{ estimatedInfo.avgEpochTime }}
            </el-descriptions-item>
          </el-descriptions>

          <div v-if="job?.best_map50 !== null && job?.best_map50 !== undefined" style="margin-top:16px">
            <el-divider>最佳指标</el-divider>
            <div class="metric-item">
              <span>mAP@0.5</span>
              <el-progress
                :percentage="+(job.best_map50 * 100).toFixed(1)"
                :format="() => `${(job.best_map50 * 100).toFixed(1)}%`"
              />
            </div>
            <div class="metric-item" v-if="job.best_map50_95">
              <span>mAP@0.5:0.95</span>
              <el-progress
                :percentage="+(job.best_map50_95 * 100).toFixed(1)"
                color="#67c23a"
                :format="() => `${(job.best_map50_95 * 100).toFixed(1)}%`"
              />
            </div>
          </div>
        </el-card>

        <!-- Error -->
        <el-card v-if="job?.error_message" shadow="never" style="margin-top:12px" class="error-card">
          <template #header><span style="color:#f56c6c">错误信息</span></template>
          <pre style="font-size:12px;color:#f56c6c;white-space:pre-wrap">{{ job.error_message }}</pre>
        </el-card>
      </el-col>

      <!-- Charts -->
      <el-col :span="16">
        <el-card shadow="never">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>训练曲线</span>
              <span style="color:#909399;font-size:13px">
                实时更新 ({{ job?.status === 'running' ? '训练中' : '已停止' }})
              </span>
            </div>
          </template>

          <div v-if="!metricsHistory.length" style="text-align:center;padding:60px 0;color:#909399">
            <p style="margin-top:12px">等待训练开始...</p>
          </div>

          <div v-else>
            <v-chart :option="lossChartOption" style="height:280px" autoresize />
            <v-chart v-if="hasMapData" :option="mapChartOption" style="height:280px;margin-top:12px" autoresize />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Download, FolderOpened, ArrowDown } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TitleComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { trainingApi } from '@/api'
import { useTrainingStore } from '@/stores/training'

use([LineChart, GridComponent, TitleComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const route = useRoute()
const router = useRouter()
const trainingStore = useTrainingStore()
const id = route.params.id
const job = ref(null)
const dataInfo = ref(null)
let pollTimer = null

// 时间预估信息
const estimatedInfo = ref({
  remaining: '',
  completion: '',
  avgEpochTime: '',
})

const metricsHistory = computed(() => job.value?.metrics_history || [])
const hasMapData = computed(() => metricsHistory.value.some((m) => m['val/map50'] !== undefined))

const statusType = (s) => ({ pending: 'info', running: 'warning', completed: 'success', failed: 'danger', cancelled: '' })[s] || ''
const statusText = (s) => ({ pending: '等待', running: '训练中', completed: '完成', failed: '失败', cancelled: '已取消' })[s] || s
const formatDate = (d) => d ? new Date(d).toLocaleString('zh-CN', { hour12: false }) : '-'

const lossChartOption = computed(() => {
  const epochs = metricsHistory.value.map((m) => m.epoch)
  const boxLoss = metricsHistory.value.map((m) => +(m['train/box_loss'] || 0).toFixed(4))
  const clsLoss = metricsHistory.value.map((m) => +(m['train/cls_loss'] || 0).toFixed(4))
  return {
    title: { text: '训练损失', textStyle: { fontSize: 13 } },
    tooltip: { trigger: 'axis' },
    legend: { data: ['Box Loss', 'Cls Loss'] },
    xAxis: { type: 'category', data: epochs, name: 'Epoch' },
    yAxis: { type: 'value', name: 'Loss' },
    series: [
      { name: 'Box Loss', type: 'line', data: boxLoss, smooth: true, color: '#409eff' },
      { name: 'Cls Loss', type: 'line', data: clsLoss, smooth: true, color: '#f56c6c' },
    ],
  }
})

const mapChartOption = computed(() => {
  const epochs = metricsHistory.value.map((m) => m.epoch)
  const map50 = metricsHistory.value.map((m) => +((m['val/map50'] || 0) * 100).toFixed(2))
  const map5095 = metricsHistory.value.map((m) => +((m['val/map50_95'] || 0) * 100).toFixed(2))
  return {
    title: { text: '验证指标 (mAP)', textStyle: { fontSize: 13 } },
    tooltip: { trigger: 'axis', formatter: (params) => params.map((p) => `${p.seriesName}: ${p.value}%`).join('<br>') },
    legend: { data: ['mAP@0.5', 'mAP@0.5:0.95'] },
    xAxis: { type: 'category', data: epochs, name: 'Epoch' },
    yAxis: { type: 'value', name: 'mAP (%)', max: 100 },
    series: [
      { name: 'mAP@0.5', type: 'line', data: map50, smooth: true, color: '#67c23a' },
      { name: 'mAP@0.5:0.95', type: 'line', data: map5095, smooth: true, color: '#e6a23c' },
    ],
  }
})

onMounted(async () => {
  await loadJob()
  if (job.value?.status === 'running' || job.value?.status === 'pending') {
    // Connect WebSocket for live updates
    trainingStore.connectWebSocket(id, handleWsMessage)
    // Also poll every 10s as backup
    pollTimer = setInterval(loadJob, 10000)
  }
})

onUnmounted(() => {
  trainingStore.disconnectWebSocket(id)
  if (pollTimer) clearInterval(pollTimer)
})

async function loadJob() {
  job.value = await trainingApi.getJob(id)

  // 从数据库加载时间预估信息（如果存在）
  if (job.value?.status === 'running' && job.value.avg_epoch_time) {
    updateEstimatedInfo(
      job.value.estimated_remaining_time,
      job.value.estimated_completion_time,
      job.value.avg_epoch_time
    )
  }

  if (job.value?.status === 'completed' || job.value?.status === 'failed') {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
    trainingStore.disconnectWebSocket(id)
  }
}

function updateEstimatedInfo(remainingTime, completionTime, avgTime) {
  if (!remainingTime) {
    estimatedInfo.value = { remaining: '', completion: '', avgEpochTime: '' }
    return
  }

  const hours = Math.floor(remainingTime / 3600)
  const minutes = Math.floor((remainingTime % 3600) / 60)
  const seconds = Math.floor(remainingTime % 60)

  let timeStr = ''
  if (hours > 0) timeStr += `${hours}小时 `
  if (minutes > 0 || hours > 0) timeStr += `${minutes}分 `
  timeStr += `${seconds}秒`

  estimatedInfo.value.remaining = timeStr

  if (completionTime) {
    const completionDate = new Date(completionTime)
    estimatedInfo.value.completion = completionDate.toLocaleString('zh-CN', { hour12: false })
  }

  if (avgTime) {
    estimatedInfo.value.avgEpochTime = `${avgTime.toFixed(1)}秒`
  }
}

function handleWsMessage(data) {
  console.log('📊 Training WS:', data.type)

  if (data.type === 'training_started') {
    // 保存数据信息
    if (data.data_info) {
      dataInfo.value = data.data_info
    }
  }

  if (data.type === 'info' || data.type === 'warning') {
    // 显示信息或警告消息
    const msgType = data.type === 'warning' ? 'warning' : 'info'
    ElMessage[msgType](data.message)
  }

  if (data.type === 'training_progress') {
    if (job.value) {
      job.value.current_epoch = data.epoch
      job.value.status = 'running'

      // 使用完整的历史数据而不是追加
      if (data.metrics_history) {
        job.value.metrics_history = data.metrics_history
      }

      // 更新时间预估信息
      if (data.estimated_remaining_time) {
        updateEstimatedInfo(
          data.estimated_remaining_time,
          data.estimated_completion_time,
          data.avg_epoch_time
        )
        console.log(`⏱️ 预计剩余: ${estimatedInfo.value.remaining}, 平均每轮: ${data.avg_epoch_time?.toFixed(1)}s`)
      }
    }
  } else if (data.type === 'validation_metrics') {
    // 验证指标实时更新
    if (job.value && data.metrics_history) {
      job.value.metrics_history = data.metrics_history
      console.log(`✅ Epoch ${data.epoch} 验证: mAP50=${(data.map50 * 100).toFixed(1)}%`)
    }
  } else if (data.type === 'training_complete') {
    // 清空时间预估
    estimatedInfo.value = { remaining: '', completion: '', avgEpochTime: '' }
    loadJob()
    ElMessage.success('训练完成！')
  } else if (data.type === 'training_error') {
    estimatedInfo.value = { remaining: '', completion: '', avgEpochTime: '' }
    loadJob()
    ElMessage.error(`训练失败: ${data.error}`)
  }
}

async function cancelJob() {
  await trainingStore.cancelJob(id)
  await loadJob()
}

async function handleDownload(command) {
  if (!job.value?.model_path) return

  // 获取模型ID - 需要通过训练任务查找对应的模型
  let modelId = null
  try {
    const res = await trainingApi.listModels()
    const allModels = res.models || res.items || []
    const model = allModels.find(m => m.training_job_id === id)
    if (model) {
      modelId = model.id
    }
  } catch (error) {
    console.error('Failed to find model:', error)
  }

  if (!modelId) {
    ElMessage.warning('未找到对应的模型，请在模型管理页面下载')
    return
  }

  if (command === 'weights') {
    // 下载权重文件 (best.pt)
    ElMessage.info('正在下载模型权重文件 (best.pt)...')
    window.open(trainingApi.downloadModel(modelId), '_blank')
  } else if (command === 'package') {
    // 下载完整包 (权重 + 标签 + 说明)
    ElMessage.success('正在下载完整模型包 (包含权重、标签文件和使用说明)...')
    window.open(trainingApi.downloadModelPackage(modelId), '_blank')
  }
}
</script>

<style scoped>
.metric-item { margin-bottom: 12px; }
.metric-item span { font-size: 12px; color: #606266; display: block; margin-bottom: 4px; }
.error-card :deep(.el-card__header) { background: #fef0f0; }
</style>
