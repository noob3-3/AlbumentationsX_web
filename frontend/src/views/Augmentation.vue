<template>
  <div>
    <div class="page-header">
      <h2>数据增强</h2>
      <p>使用数据增强技术对目标检测数据集进行自动增强</p>
    </div>

    <!-- Project Warning -->
    <el-alert
      v-if="!hasProject"
      type="warning"
      title="请先在页面顶部选择一个项目"
      description="选择项目后，下方数据集列表将只显示该项目的数据集"
      :closable="false"
      style="margin-bottom: 16px"
      show-icon
    />

    <el-row :gutter="16">
      <!-- Create Job -->
      <el-col :span="10">
        <el-card shadow="never">
          <template #header><span>创建增强任务</span></template>
          <el-form :model="form" label-width="100px">
            <el-form-item label="源数据集" required>
              <el-select
                v-model="form.dataset_id"
                placeholder="选择数据集"
                style="width:100%"
                :disabled="!hasProject"
              >
                <el-option v-for="d in datasets" :key="d.id" :label="`${d.name} (${d.image_count}张)`" :value="d.id" />
              </el-select>
              <span v-if="!hasProject" class="hint">请先选择项目</span>
              <span v-else-if="datasets.length === 0" class="hint">当前项目暂无数据集</span>
            </el-form-item>

            <el-form-item label="增强倍数">
              <el-input-number v-model="form.multiplier" :min="1" :max="20" />
              <span class="hint">每张原始图片生成 {{ form.multiplier }} 张增强图片</span>
            </el-form-item>

            <el-form-item label="增强配置">
              <el-radio-group v-model="configMode">
                <el-radio value="default">使用默认配置</el-radio>
                <el-radio value="custom">自定义配置</el-radio>
              </el-radio-group>
            </el-form-item>

            <div v-if="configMode === 'custom'">
              <el-form-item label="选择变换">
                <el-checkbox-group v-model="selectedTransforms">
                  <el-row>
                    <el-col :span="12" v-for="t in availableTransforms" :key="t.name">
                      <el-checkbox :value="t.name" :label="t.name">{{ t.name }}</el-checkbox>
                    </el-col>
                  </el-row>
                </el-checkbox-group>
              </el-form-item>
            </div>

            <el-form-item>
              <el-button
                type="primary"
                :loading="creating"
                :disabled="!form.dataset_id"
                @click="createJob"
              >
                创建增强任务
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- Default transforms preview -->
        <el-card shadow="never" style="margin-top:16px">
          <template #header><span>默认增强变换列表</span></template>
          <el-scrollbar height="300px">
            <div v-for="t in defaultConfig.transforms" :key="t.name" class="transform-item">
              <span class="transform-name">{{ t.name }}</span>
              <span class="transform-params">p={{ t.params?.p || 0.5 }}</span>
            </div>
          </el-scrollbar>
        </el-card>
      </el-col>

      <!-- Jobs List -->
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>增强任务列表</span>
              <el-button size="small" :icon="Refresh" @click="fetchJobs">刷新</el-button>
            </div>
          </template>

          <el-empty v-if="!jobs.length" description="暂无增强任务" />

          <div v-else>
            <el-card
              v-for="job in jobs"
              :key="job.id"
              class="job-card"
              shadow="never"
              :class="job.status"
            >
              <div class="job-header">
                <div>
                  <el-tag :type="statusType(job.status)" size="small">{{ statusText(job.status) }}</el-tag>
                  <span class="job-id">{{ job.id.slice(0, 8) }}...</span>
                </div>
                <span class="job-time">{{ formatDate(job.created_at) }}</span>
              </div>

              <div class="job-meta">
                <span>倍数: <strong>×{{ job.multiplier }}</strong></span>
                <span>目标: <strong>{{ job.total_images }}</strong> 张</span>
                <span>已完成: <strong>{{ job.processed_images }}</strong> 张</span>
              </div>

              <el-progress
                v-if="job.status === 'running'"
                :percentage="Math.round(job.processed_images / Math.max(job.total_images, 1) * 100)"
                :striped="true"
                :striped-flow="true"
                :duration="5"
              />

              <div v-if="job.status === 'completed' && job.output_dataset_id" style="margin-top:8px">
                <el-button
                  link type="primary" size="small"
                  @click="$router.push(`/datasets/${job.output_dataset_id}`)"
                >
                  查看输出数据集 →
                </el-button>
              </div>

              <div v-if="job.error_message" class="error-msg">{{ job.error_message }}</div>
            </el-card>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { augmentationApi, datasetApi } from '@/api'
import { useDatasetStore } from '@/stores/dataset'
import { useProjectStore } from '@/stores/project'
import { storeToRefs } from 'pinia'

const store = useDatasetStore()
const projectStore = useProjectStore()
const { datasets } = storeToRefs(store)
const { hasProject, projectId } = storeToRefs(projectStore)

const form = ref({ dataset_id: '', multiplier: 3, config: null })
const configMode = ref('default')
const selectedTransforms = ref([])
const creating = ref(false)
const jobs = ref([])
const availableTransforms = ref([])
const defaultConfig = ref({ transforms: [] })

let refreshTimer = null

const statusType = (s) => ({ pending: 'info', running: 'warning', completed: 'success', failed: 'danger' })[s] || ''
const statusText = (s) => ({ pending: '等待中', running: '增强中', completed: '已完成', failed: '失败' })[s] || s
const formatDate = (d) => d ? new Date(d).toLocaleString('zh-CN', { hour12: false }) : '-'

onMounted(async () => {
  await Promise.all([
    store.fetchDatasets(),
    fetchJobs(),
    fetchTransforms(),
  ])
  // Auto-refresh running jobs
  refreshTimer = setInterval(() => {
    if (jobs.value.some((j) => j.status === 'running' || j.status === 'pending')) {
      fetchJobs()
    }
  }, 3000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})

watch(projectId, () => {
  store.fetchDatasets()
  form.value.dataset_id = ''
})

async function fetchJobs() {
  const res = await augmentationApi.listJobs()
  jobs.value = res.items
}

async function fetchTransforms() {
  const [transRes, configRes] = await Promise.all([
    augmentationApi.listTransforms(),
    augmentationApi.getDefaultConfig(),
  ])
  availableTransforms.value = transRes.transforms
  defaultConfig.value = configRes.config
  selectedTransforms.value = defaultConfig.value.transforms.map((t) => t.name)
}

async function createJob() {
  creating.value = true
  try {
    let config = null
    if (configMode.value === 'custom' && selectedTransforms.value.length) {
      config = {
        transforms: selectedTransforms.value.map((name) => ({ name, params: { p: 0.5 } })),
      }
    }
    await augmentationApi.createJob({
      dataset_id: form.value.dataset_id,
      multiplier: form.value.multiplier,
      config,
    })
    ElMessage.success('增强任务已创建并开始运行')
    await fetchJobs()
  } finally {
    creating.value = false
  }
}
</script>

<style scoped>
.hint { margin-left: 8px; color: #909399; font-size: 12px; }

.transform-item {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid #f5f5f5;
  font-size: 13px;
}
.transform-name { color: #409eff; font-weight: 500; }
.transform-params { color: #909399; }

.job-card {
  margin-bottom: 12px;
  border-left: 3px solid #dcdfe6;
}
.job-card.running { border-left-color: #e6a23c; }
.job-card.completed { border-left-color: #67c23a; }
.job-card.failed { border-left-color: #f56c6c; }

.job-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.job-id { margin-left: 8px; color: #909399; font-size: 12px; }
.job-time { color: #909399; font-size: 12px; }
.job-meta { display: flex; gap: 16px; font-size: 13px; color: #606266; margin-bottom: 8px; }
.error-msg { color: #f56c6c; font-size: 12px; margin-top: 6px; }
</style>
