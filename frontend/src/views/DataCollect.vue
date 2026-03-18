<template>
  <div>
    <div class="page-header">
      <h2>数据采集</h2>
      <p>支持本地文件上传、URL批量采集和客户端远程推送</p>
    </div>

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

    <el-tabs v-model="activeTab" type="border-card">
      <!-- Local Upload Tab -->
      <el-tab-pane label="📁 本地文件上传" name="local">
        <el-form :model="uploadForm" label-width="100px" style="max-width: 600px">
          <el-form-item label="目标数据集" required>
            <el-select v-model="uploadForm.datasetId" placeholder="选择数据集" style="width:100%">
              <el-option v-for="d in datasets" :key="d.id" :label="d.name" :value="d.id" />
            </el-select>
            <el-button link style="margin-left:8px" @click="goToCreateDataset">+ 新建数据集</el-button>
          </el-form-item>
        </el-form>

        <el-upload
          ref="uploadRef"
          class="upload-area"
          drag
          multiple
          :auto-upload="false"
          accept="image/*"
          :on-change="handleFileChange"
          :file-list="fileList"
          :limit="500"
        >
          <el-icon class="el-icon--upload" size="48"><UploadFilled /></el-icon>
          <div class="el-upload__text">将图片拖到此处，或<em>点击上传</em></div>
          <template #tip>
            <div class="el-upload__tip">支持 JPG/PNG/BMP/WebP，单次最多 500 张</div>
          </template>
        </el-upload>

        <div v-if="fileList.length" style="margin-top:16px">
          <el-alert type="info" :closable="false" show-icon>
            已选择 {{ fileList.length }} 张图片
          </el-alert>
          <div style="margin-top:12px">
            <el-progress v-if="uploadProgress > 0" :percentage="uploadProgress" />
          </div>
          <el-button
            type="primary"
            :loading="uploading"
            style="margin-top:12px"
            @click="startUpload"
            :disabled="!uploadForm.datasetId"
          >
            开始上传
          </el-button>
          <el-button @click="fileList = []">清空</el-button>
        </div>
      </el-tab-pane>

      <!-- Upload with Labels Tab -->
      <el-tab-pane label="🏷️ 带标签上传" name="with-labels">
        <el-alert type="info" :closable="false" show-icon style="margin-bottom:16px">
          <template #default>
            上传已标注的数据集（YOLO格式）。请选择 images 文件夹中的图片和 labels 文件夹中的 .txt 标签文件。
            标签文件名需要与图片文件名对应（例如：image.jpg 对应 image.txt）。
          </template>
        </el-alert>

        <el-form :model="labelUploadForm" label-width="100px" style="max-width: 600px">
          <el-form-item label="目标数据集" required>
            <el-select v-model="labelUploadForm.datasetId" placeholder="选择数据集" style="width:100%">
              <el-option v-for="d in datasets" :key="d.id" :label="d.name" :value="d.id" />
            </el-select>
            <el-button link style="margin-left:8px" @click="goToCreateDataset">+ 新建数据集</el-button>
          </el-form-item>
        </el-form>

        <el-row :gutter="20">
          <el-col :span="8">
            <h4>选择图片文件</h4>
            <el-upload
              ref="imageUploadRef"
              class="upload-area"
              drag
              multiple
              :auto-upload="false"
              accept="image/*,.bmp"
              :on-change="handleImageFilesChange"
              :file-list="imageFiles"
              :limit="500"
            >
              <el-icon class="el-icon--upload" size="48"><UploadFilled /></el-icon>
              <div class="el-upload__text">选择图片文件</div>
              <template #tip>
                <div class="el-upload__tip">支持 JPG/PNG/BMP/WebP</div>
              </template>
            </el-upload>
            <div v-if="imageFiles.length" style="margin-top:12px">
              <el-tag type="success">已选择 {{ imageFiles.length }} 个图片</el-tag>
            </div>
          </el-col>

          <el-col :span="8">
            <h4>选择标签文件（可选）</h4>
            <el-upload
              ref="labelUploadRef"
              class="upload-area"
              drag
              multiple
              :auto-upload="false"
              accept=".txt"
              :on-change="handleLabelFilesChange"
              :file-list="labelFiles"
              :limit="500"
            >
              <el-icon class="el-icon--upload" size="48"><Document /></el-icon>
              <div class="el-upload__text">选择标签文件</div>
              <template #tip>
                <div class="el-upload__tip">YOLO格式 .txt 文件</div>
              </template>
            </el-upload>
            <div v-if="labelFiles.length" style="margin-top:12px">
              <el-tag type="info">已选择 {{ labelFiles.length }} 个标签</el-tag>
            </div>
          </el-col>

          <el-col :span="8">
            <h4>选择类别文件（可选）</h4>
            <el-upload
              ref="classesUploadRef"
              class="upload-area"
              drag
              :auto-upload="false"
              accept=".txt,.names,.yaml,.yml"
              :on-change="handleClassesFileChange"
              :file-list="classesFileList"
              :limit="1"
            >
              <el-icon class="el-icon--upload" size="48"><Document /></el-icon>
              <div class="el-upload__text">选择 classes.txt</div>
              <template #tip>
                <div class="el-upload__tip">每行一个类别名称，如：<br/>person<br/>car<br/>dog</div>
              </template>
            </el-upload>
            <div v-if="classesFile" style="margin-top:12px">
              <el-tag type="warning">{{ classesFile.name }}</el-tag>
            </div>
          </el-col>
        </el-row>

        <div v-if="imageFiles.length" style="margin-top:20px">
          <el-alert type="warning" :closable="false" show-icon v-if="labelFiles.length === 0">
            未选择标签文件，图片将作为未标注数据上传
          </el-alert>
          <el-alert type="info" :closable="false" show-icon v-else-if="labelFiles.length > 0 && !classesFile">
            准备上传 {{ imageFiles.length }} 张图片和 {{ labelFiles.length }} 个标签文件。未提供 classes.txt，类别将自动命名为 class_0、class_1…
          </el-alert>
          <el-alert type="success" :closable="false" show-icon v-else>
            准备上传 {{ imageFiles.length }} 张图片、{{ labelFiles.length }} 个标签文件和类别文件
          </el-alert>
          <div style="margin-top:12px">
            <el-progress v-if="labelUploadProgress > 0" :percentage="labelUploadProgress" />
          </div>
          <el-button
            type="primary"
            :loading="labelUploading"
            style="margin-top:12px"
            @click="startLabelUpload"
            :disabled="!labelUploadForm.datasetId"
          >
            开始上传
          </el-button>
          <el-button @click="clearLabelUpload">清空</el-button>
        </div>

        <div v-if="labelUploadResult" style="margin-top:16px">
          <el-result
            icon="success"
            :title="`上传完成：${labelUploadResult.uploaded} 张图片，共 ${labelUploadResult.total_annotations} 个标注`"
          >
            <template #sub-title v-if="labelUploadResult.classes && labelUploadResult.classes.length">
              识别到 {{ labelUploadResult.classes.length }} 个类别：{{ labelUploadResult.classes.join('、') }}
            </template>
          </el-result>
        </div>
      </el-tab-pane>

      <!-- URL Collection Tab -->
      <el-tab-pane label="🌐 URL批量采集" name="url">
        <el-form :model="urlForm" label-width="100px" style="max-width: 700px">
          <el-form-item label="目标数据集" required>
            <el-select v-model="urlForm.datasetId" placeholder="选择数据集" style="width:100%">
              <el-option v-for="d in datasets" :key="d.id" :label="d.name" :value="d.id" />
            </el-select>
            <el-button link style="margin-left:8px" @click="goToCreateDataset">+ 新建数据集</el-button>
          </el-form-item>
          <el-form-item label="图片URL列表">
            <el-input
              v-model="urlForm.urlText"
              type="textarea"
              :rows="10"
              placeholder="每行一个URL，例如：
https://example.com/image1.jpg
https://example.com/image2.png"
            />
            <div style="margin-top:6px;color:#909399;font-size:12px">
              共 {{ urlList.length }} 个URL
            </div>
          </el-form-item>
        </el-form>

        <el-button
          type="primary"
          :loading="collecting"
          :disabled="!urlForm.datasetId || !urlList.length"
          @click="startCollect"
        >
          开始采集
        </el-button>

        <div v-if="collectResult" style="margin-top:16px">
          <el-result
            :icon="collectResult.failed === 0 ? 'success' : 'warning'"
            :title="`采集完成：成功 ${collectResult.collected} 张，失败 ${collectResult.failed} 张`"
          />
        </div>
      </el-tab-pane>

      <!-- Client API Tab -->
      <el-tab-pane label="📡 客户端远程推送" name="client">
        <div class="client-info">
          <el-alert type="info" title="客户端采集说明" :closable="false" show-icon>
            <template #default>
              远程客户端通过HTTP API向平台推送图片数据，需要携带 <code>X-Api-Token</code> 请求头。
            </template>
          </el-alert>

          <el-card style="margin-top:16px" shadow="never">
            <template #header><span>API 接入信息</span></template>
            <el-descriptions :column="1" border>
              <el-descriptions-item label="上传端点">
                <code>POST /api/v1/collect/upload</code>
              </el-descriptions-item>
              <el-descriptions-item label="批量上传">
                <code>POST /api/v1/collect/batch-upload</code>
              </el-descriptions-item>
              <el-descriptions-item label="获取数据集列表">
                <code>GET /api/v1/collect/datasets</code>
              </el-descriptions-item>
              <el-descriptions-item label="认证方式">
                请求头 <code>X-Api-Token: &lt;token&gt;</code>
              </el-descriptions-item>
            </el-descriptions>
          </el-card>

          <el-card style="margin-top:16px" shadow="never">
            <template #header><span>Python 客户端示例代码</span></template>
            <pre class="code-block">{{ clientSampleCode }}</pre>
          </el-card>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { UploadFilled, Document } from '@element-plus/icons-vue'
import { datasetApi } from '@/api'
import { useDatasetStore } from '@/stores/dataset'
import { useProjectStore } from '@/stores/project'
import { storeToRefs } from 'pinia'

const route = useRoute()
const router = useRouter()
const store = useDatasetStore()
const projectStore = useProjectStore()
const { datasets } = storeToRefs(store)
const { hasProject, projectId } = storeToRefs(projectStore)

const activeTab = ref(route.query.dataset ? 'local' : 'local')
const uploadRef = ref()
const fileList = ref([])
const uploading = ref(false)
const uploadProgress = ref(0)
const collecting = ref(false)
const collectResult = ref(null)

// Label upload refs
const imageUploadRef = ref()
const labelUploadRef = ref()
const classesUploadRef = ref()
const imageFiles = ref([])
const labelFiles = ref([])
const classesFileList = ref([])
const classesFile = ref(null)
const labelUploading = ref(false)
const labelUploadProgress = ref(0)
const labelUploadResult = ref(null)

const uploadForm = ref({ datasetId: route.query.dataset || '' })
const urlForm = ref({ datasetId: route.query.dataset || '', urlText: '' })
const labelUploadForm = ref({ datasetId: route.query.dataset || '' })

const urlList = computed(() =>
  urlForm.value.urlText
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l.startsWith('http'))
)

const clientSampleCode = `import requests

API_BASE = "http://localhost:8000/api/v1"
TOKEN = "your-secret-token-change-this"
HEADERS = {"X-Api-Token": TOKEN}

# Get dataset list
datasets = requests.get(f"{API_BASE}/collect/datasets", headers=HEADERS).json()
dataset_id = datasets["datasets"][0]["id"]

# Upload a single image
with open("image.jpg", "rb") as f:
    response = requests.post(
        f"{API_BASE}/collect/upload",
        headers=HEADERS,
        data={"dataset_id": dataset_id},
        files={"file": ("image.jpg", f, "image/jpeg")},
    )
print(response.json())

# Upload with annotations (YOLO format: class_id, cx, cy, w, h)
import json
annotations = [{"class_id": 0, "x_center": 0.5, "y_center": 0.5, "bbox_width": 0.3, "bbox_height": 0.4}]
with open("image.jpg", "rb") as f:
    response = requests.post(
        f"{API_BASE}/collect/upload",
        headers=HEADERS,
        data={"dataset_id": dataset_id, "annotations_json": json.dumps(annotations)},
        files={"file": ("image.jpg", f, "image/jpeg")},
    )
`

onMounted(() => store.fetchDatasets())

watch(projectId, () => {
  store.fetchDatasets()
  uploadForm.value.datasetId = ''
  urlForm.value.datasetId = ''
  labelUploadForm.value.datasetId = ''
})

function handleFileChange(file, list) {
  fileList.value = list
}

async function startUpload() {
  if (!uploadForm.value.datasetId) {
    ElMessage.warning('请先选择数据集')
    return
  }
  uploading.value = true
  uploadProgress.value = 0
  try {
    const formData = new FormData()
    fileList.value.forEach((f) => formData.append('files', f.raw))
    await datasetApi.uploadImages(uploadForm.value.datasetId, formData, (e) => {
      uploadProgress.value = Math.round((e.loaded / e.total) * 100)
    })
    ElMessage.success(`成功上传 ${fileList.value.length} 张图片`)
    fileList.value = []
    uploadProgress.value = 0
  } finally {
    uploading.value = false
  }
}

async function startCollect() {
  collecting.value = true
  collectResult.value = null
  try {
    const res = await datasetApi.collectFromUrls(urlForm.value.datasetId, {
      dataset_id: urlForm.value.datasetId,
      urls: urlList.value,
    })
    collectResult.value = res
  } finally {
    collecting.value = false
  }
}

function handleImageFilesChange(file, list) {
  imageFiles.value = list
}

function handleLabelFilesChange(file, list) {
  labelFiles.value = list
}

function handleClassesFileChange(file, list) {
  classesFileList.value = list
  classesFile.value = list.length > 0 ? list[list.length - 1].raw : null
}

async function startLabelUpload() {
  if (!labelUploadForm.value.datasetId) {
    ElMessage.warning('请先选择数据集')
    return
  }
  if (!imageFiles.value.length) {
    ElMessage.warning('请先选择图片文件')
    return
  }

  labelUploading.value = true
  labelUploadProgress.value = 0
  labelUploadResult.value = null

  try {
    const formData = new FormData()

    // Append image files
    imageFiles.value.forEach((f) => formData.append('image_files', f.raw))

    // Append label files
    labelFiles.value.forEach((f) => formData.append('label_files', f.raw))

    // Append classes file if provided
    if (classesFile.value) {
      formData.append('classes_file', classesFile.value)
    }

    const res = await datasetApi.uploadImagesWithLabels(
      labelUploadForm.value.datasetId,
      formData,
      (e) => {
        labelUploadProgress.value = Math.round((e.loaded / e.total) * 100)
      }
    )

    labelUploadResult.value = res
    ElMessage.success(`成功上传 ${res.uploaded} 张图片，共 ${res.total_annotations} 个标注`)

    // Clear after successful upload
    clearLabelUpload()
  } catch (error) {
    ElMessage.error('上传失败：' + (error.response?.data?.detail || error.message))
  } finally {
    labelUploading.value = false
  }
}

function clearLabelUpload() {
  imageFiles.value = []
  labelFiles.value = []
  classesFileList.value = []
  classesFile.value = null
  labelUploadProgress.value = 0
}

function goToCreateDataset() {
  if (!projectId.value) {
    ElMessage.warning('请先在页面顶部选择项目')
    router.push('/projects')
    return
  }
  router.push(`/projects/${projectId.value}`)
  ElMessage.info('请在项目页创建数据集')
}
</script>

<style scoped>
.upload-area { margin-top: 16px; width: 100%; }
.client-info { max-width: 800px; }
.code-block {
  background: #1e2130;
  color: #abb2bf;
  padding: 16px;
  border-radius: 8px;
  font-size: 13px;
  overflow-x: auto;
  line-height: 1.6;
  white-space: pre;
}
code {
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
}
</style>
