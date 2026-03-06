<template>
  <div>
    <div class="page-header">
      <h2>系统概览</h2>
      <p>VST 目标检测训练平台</p>
    </div>

    <!-- Stats Cards -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="6" v-for="stat in stats" :key="stat.label">
        <el-card class="stat-card" shadow="never">
          <div class="stat-content">
            <div class="stat-icon" :style="{ background: stat.color + '20' }">
              <el-icon :size="28" :color="stat.color">
                <component :is="stat.icon" />
              </el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stat.value }}</div>
              <div class="stat-label">{{ stat.label }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- System Hardware Info -->
    <el-row :gutter="16" style="margin-top: 20px">
      <!-- GPU Info -->
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div style="display: flex; align-items: center; gap: 8px">
              <el-icon><VideoCamera /></el-icon>
              <span>GPU 信息</span>
              <el-tag v-if="systemInfo.gpu?.available" type="success" size="small">已启用</el-tag>
              <el-tag v-else type="info" size="small">不可用</el-tag>
            </div>
          </template>

          <div v-if="systemInfoLoading" v-loading="true" style="min-height: 150px"></div>

          <div v-else-if="systemInfo.gpu?.available">
            <div style="margin-bottom: 12px">
              <el-tag type="primary" size="small">{{ systemInfo.gpu.count }} 个 GPU</el-tag>
              <el-tag type="info" size="small" style="margin-left: 8px">CUDA {{ systemInfo.gpu.cuda_version }}</el-tag>
            </div>

            <div v-for="(device, idx) in systemInfo.gpu.devices" :key="idx" class="gpu-device">
              <div class="device-header">
                <span class="device-name">
                  <el-icon><Monitor /></el-icon>
                  GPU {{ device.id }}: {{ device.name }}
                </span>
                <el-tag :type="getMemoryType(device.memory_usage_percent)" size="small">
                  {{ device.memory_usage_percent }}%
                </el-tag>
              </div>

              <div class="device-memory">
                <div class="memory-bar">
                  <el-progress
                    :percentage="device.memory_usage_percent"
                    :color="getMemoryColor(device.memory_usage_percent)"
                    :show-text="false"
                  />
                </div>
                <div class="memory-text">
                  {{ device.reserved_memory_gb }} GB / {{ device.total_memory_gb }} GB
                  <span style="color: #909399">(可用: {{ device.free_memory_gb }} GB)</span>
                </div>
              </div>
            </div>
          </div>

          <el-empty v-else description="未检测到 GPU 设备，使用 CPU 模式" :image-size="80" />
        </el-card>
      </el-col>

      <!-- Disk Info -->
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div style="display: flex; align-items: center; gap: 8px">
              <el-icon><Files /></el-icon>
              <span>磁盘容量</span>
            </div>
          </template>

          <div v-if="systemInfoLoading" v-loading="true" style="min-height: 150px"></div>

          <div v-else-if="systemInfo.disk?.available && systemInfo.disk.partitions?.length > 0">
            <div v-for="(partition, idx) in systemInfo.disk.partitions.slice(0, 3)" :key="idx" class="disk-partition">
              <div class="partition-header">
                <span class="partition-name">
                  <el-icon><Folder /></el-icon>
                  {{ partition.mountpoint || partition.device }}
                </span>
                <el-tag :type="getDiskType(partition.usage_percent)" size="small">
                  {{ partition.usage_percent }}%
                </el-tag>
              </div>

              <div class="partition-space">
                <div class="space-bar">
                  <el-progress
                    :percentage="partition.usage_percent"
                    :color="getDiskColor(partition.usage_percent)"
                    :show-text="false"
                  />
                </div>
                <div class="space-text">
                  {{ partition.used_gb }} GB / {{ partition.total_gb }} GB
                  <span style="color: #909399">(可用: {{ partition.free_gb }} GB)</span>
                </div>
              </div>
            </div>
          </div>

          <el-empty v-else description="磁盘信息不可用" :image-size="80" />
        </el-card>
      </el-col>
    </el-row>

    <!-- Quick Actions & Recent Jobs -->
    <el-row :gutter="16" style="margin-top: 20px">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <span>快速操作</span>
          </template>
          <div class="quick-actions">
            <el-button type="primary" :icon="Download" @click="$router.push('/collect')">采集数据</el-button>
            <el-button type="success" :icon="MagicStick" @click="$router.push('/augmentation')">数据增强</el-button>
            <el-button type="warning" :icon="Cpu" @click="$router.push('/training')">开始训练</el-button>
            <el-button :icon="FolderOpened" @click="$router.push('/projects')">管理项目</el-button>
          </div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <span>最近训练任务</span>
          </template>
          <el-empty v-if="!recentJobs.length" description="暂无训练任务" :image-size="60" />
          <div v-else>
            <div
              v-for="job in recentJobs"
              :key="job.id"
              class="job-item"
              @click="$router.push(`/training/${job.id}`)"
            >
              <div class="job-name">{{ job.name }}</div>
              <el-tag :type="statusType(job.status)" size="small">{{ statusText(job.status) }}</el-tag>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Download, MagicStick, Cpu, FolderOpened, VideoCamera, Monitor, Files, Folder } from '@element-plus/icons-vue'
import { datasetApi, trainingApi, augmentationApi, systemApi } from '@/api'
import { ElMessage } from 'element-plus'

const stats = ref([
  { label: '数据集总数', value: 0, icon: 'FolderOpened', color: '#409eff' },
  { label: '图片总数', value: 0, icon: 'Picture', color: '#67c23a' },
  { label: '增强任务', value: 0, icon: 'MagicStick', color: '#e6a23c' },
  { label: '训练任务', value: 0, icon: 'Cpu', color: '#f56c6c' },
])

const recentJobs = ref([])
const systemInfo = ref({
  gpu: { available: false, devices: [] },
  disk: { available: false, partitions: [] },
  memory: { available: false }
})
const systemInfoLoading = ref(false)

const statusType = (s) => ({
  pending: 'info', running: 'warning', completed: 'success',
  failed: 'danger', cancelled: ''
})[s] || 'info'

const statusText = (s) => ({
  pending: '等待中', running: '训练中', completed: '已完成',
  failed: '失败', cancelled: '已取消'
})[s] || s

// GPU/Disk usage color helpers
const getMemoryType = (percent) => {
  if (percent > 85) return 'danger'
  if (percent > 70) return 'warning'
  return 'success'
}

const getMemoryColor = (percent) => {
  if (percent > 85) return '#f56c6c'
  if (percent > 70) return '#e6a23c'
  return '#67c23a'
}

const getDiskType = (percent) => {
  if (percent > 90) return 'danger'
  if (percent > 75) return 'warning'
  return 'success'
}

const getDiskColor = (percent) => {
  if (percent > 90) return '#f56c6c'
  if (percent > 75) return '#e6a23c'
  return '#67c23a'
}

const loadSystemInfo = async () => {
  systemInfoLoading.value = true
  try {
    const res = await systemApi.getInfo()
    systemInfo.value = res
  } catch (error) {
    console.error('Failed to load system info:', error)
    ElMessage.warning('无法加载系统信息')
  } finally {
    systemInfoLoading.value = false
  }
}

onMounted(async () => {
  try {
    const [dsRes, augRes, trainRes] = await Promise.all([
      datasetApi.list({ page_size: 100 }),
      augmentationApi.listJobs(),
      trainingApi.listJobs(),
      loadSystemInfo(), // Load system info in parallel
    ])
    stats.value[0].value = dsRes.total
    stats.value[1].value = dsRes.items.reduce((s, d) => s + d.image_count, 0)
    stats.value[2].value = augRes.total
    stats.value[3].value = trainRes.total

    recentJobs.value = trainRes.items.slice(0, 5)
  } catch {}
})
</script>

<style scoped>
.stats-row { margin-bottom: 4px; }

.stat-card :deep(.el-card__body) { padding: 20px; }

.stat-content {
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #303133;
  line-height: 1;
}

.stat-label {
  font-size: 13px;
  color: #909399;
  margin-top: 6px;
}

.quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.job-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid #f5f5f5;
  cursor: pointer;
  transition: background 0.2s;
}
.job-item:hover { background: #f5f7fa; }
.job-item:last-child { border-bottom: none; }
.job-name { font-size: 14px; color: #303133; }

/* GPU Device Styles */
.gpu-device {
  padding: 12px;
  background: #f5f7fa;
  border-radius: 8px;
  margin-bottom: 12px;
}

.gpu-device:last-child {
  margin-bottom: 0;
}

.device-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.device-name {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 6px;
}

.device-memory {
  margin-top: 8px;
}

.memory-bar {
  margin-bottom: 4px;
}

.memory-text {
  font-size: 13px;
  color: #606266;
}

/* Disk Partition Styles */
.disk-partition {
  padding: 12px;
  background: #f5f7fa;
  border-radius: 8px;
  margin-bottom: 12px;
}

.disk-partition:last-child {
  margin-bottom: 0;
}

.partition-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.partition-name {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 6px;
}

.partition-space {
  margin-top: 8px;
}

.space-bar {
  margin-bottom: 4px;
}

.space-text {
  font-size: 13px;
  color: #606266;
}
</style>
