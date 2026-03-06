<template>
  <div>
    <div class="page-header">
      <h2>客户端 API 文档</h2>
      <p>为远程数据采集客户端提供接入指南和测试工具</p>
    </div>

    <el-row :gutter="16">
      <!-- API Info -->
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span>API 接入信息</span></template>

          <el-form label-width="120px">
            <el-form-item label="服务器地址">
              <el-input v-model="serverUrl" readonly>
                <template #append>
                  <el-button @click="copy(serverUrl)">复制</el-button>
                </template>
              </el-input>
            </el-form-item>
            <el-form-item label="API Token">
              <el-input v-model="apiToken" show-password>
                <template #append>
                  <el-button @click="copy(apiToken)">复制</el-button>
                </template>
              </el-input>
              <div style="font-size:12px;color:#f56c6c;margin-top:4px">
                ⚠️ 请在 backend/.env 中修改 CLIENT_API_TOKEN 为安全的随机字符串
              </div>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- API Test Tool -->
        <el-card shadow="never" style="margin-top:16px">
          <template #header><span>在线测试</span></template>
          <el-form label-width="100px">
            <el-form-item label="目标数据集">
              <el-select v-model="testDatasetId" placeholder="选择数据集" style="width:100%">
                <el-option v-for="d in datasets" :key="d.id" :label="d.name" :value="d.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="测试图片">
              <el-upload :auto-upload="false" :on-change="onTestFileChange" :show-file-list="false">
                <el-button>选择图片</el-button>
                <span v-if="testFile" style="margin-left:8px;font-size:13px">{{ testFile.name }}</span>
              </el-upload>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="testing" :disabled="!testDatasetId || !testFile" @click="testUpload">
                测试上传
              </el-button>
            </el-form-item>
          </el-form>

          <div v-if="testResult">
            <el-alert :type="testResult.success ? 'success' : 'error'" :closable="false" show-icon>
              <pre style="font-size:12px;white-space:pre-wrap">{{ JSON.stringify(testResult, null, 2) }}</pre>
            </el-alert>
          </div>
        </el-card>
      </el-col>

      <!-- Code Samples -->
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div style="display:flex;align-items:center;gap:12px">
              <span>代码示例</span>
              <el-radio-group v-model="codeLang" size="small">
                <el-radio-button value="python">Python</el-radio-button>
                <el-radio-button value="curl">cURL</el-radio-button>
                <el-radio-button value="js">JavaScript</el-radio-button>
              </el-radio-group>
            </div>
          </template>

          <pre class="code-block">{{ currentCode }}</pre>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { collectionApi, datasetApi } from '@/api'
import { useDatasetStore } from '@/stores/dataset'
import { storeToRefs } from 'pinia'

const store = useDatasetStore()
const { datasets } = storeToRefs(store)

const serverUrl = ref(window.location.origin)
const apiToken = ref('your-secret-token-change-this')
const codeLang = ref('python')
const testDatasetId = ref('')
const testFile = ref(null)
const testing = ref(false)
const testResult = ref(null)

onMounted(() => store.fetchDatasets())

function onTestFileChange(file) {
  testFile.value = file.raw
}

async function testUpload() {
  testing.value = true
  testResult.value = null
  try {
    const formData = new FormData()
    formData.append('dataset_id', testDatasetId.value)
    formData.append('file', testFile.value)
    const res = await collectionApi.clientUpload(formData, apiToken.value)
    testResult.value = { success: true, ...res }
    ElMessage.success('测试上传成功')
  } catch (e) {
    testResult.value = { success: false, error: e.response?.data?.detail || e.message }
  } finally {
    testing.value = false
  }
}

function copy(text) {
  navigator.clipboard.writeText(text)
  ElMessage.success('已复制到剪贴板')
}

const pythonCode = computed(() => `import requests
import json

API_BASE = "${serverUrl.value}/api/v1"
TOKEN = "${apiToken.value}"
HEADERS = {"X-Api-Token": TOKEN}
DATASET_ID = "${testDatasetId.value || '<dataset_id>'}"

# 1. 获取数据集列表
datasets = requests.get(
    f"{API_BASE}/collect/datasets",
    headers=HEADERS
).json()
print("Datasets:", datasets)

# 2. 上传单张图片
with open("image.jpg", "rb") as f:
    resp = requests.post(
        f"{API_BASE}/collect/upload",
        headers=HEADERS,
        data={"dataset_id": DATASET_ID},
        files={"file": ("image.jpg", f, "image/jpeg")},
    )
print("Upload result:", resp.json())

# 3. 带标注上传 (YOLO格式: class_id, cx, cy, w, h)
annotations = [
    {"class_id": 0, "x_center": 0.5, "y_center": 0.5,
     "bbox_width": 0.3, "bbox_height": 0.4}
]
with open("image.jpg", "rb") as f:
    resp = requests.post(
        f"{API_BASE}/collect/upload",
        headers=HEADERS,
        data={
            "dataset_id": DATASET_ID,
            "annotations_json": json.dumps(annotations)
        },
        files={"file": ("image.jpg", f, "image/jpeg")},
    )
print("Upload with annotation:", resp.json())

# 4. 批量上传
files_to_upload = ["img1.jpg", "img2.jpg", "img3.jpg"]
files = [("files", (fn, open(fn, "rb"), "image/jpeg")) for fn in files_to_upload]
resp = requests.post(
    f"{API_BASE}/collect/batch-upload",
    headers=HEADERS,
    data={"dataset_id": DATASET_ID},
    files=files,
)
print("Batch upload:", resp.json())
`)

const curlCode = computed(() => `# 获取数据集列表
curl -X GET \\
  "${serverUrl.value}/api/v1/collect/datasets" \\
  -H "X-Api-Token: ${apiToken.value}"

# 上传图片
curl -X POST \\
  "${serverUrl.value}/api/v1/collect/upload" \\
  -H "X-Api-Token: ${apiToken.value}" \\
  -F "dataset_id=${testDatasetId.value || '<dataset_id>'}" \\
  -F "file=@/path/to/image.jpg"

# 带标注上传
curl -X POST \\
  "${serverUrl.value}/api/v1/collect/upload" \\
  -H "X-Api-Token: ${apiToken.value}" \\
  -F "dataset_id=${testDatasetId.value || '<dataset_id>'}" \\
  -F 'annotations_json=[{"class_id":0,"x_center":0.5,"y_center":0.5,"bbox_width":0.3,"bbox_height":0.4}]' \\
  -F "file=@/path/to/image.jpg"
`)

const jsCode = computed(() => `const API_BASE = "${serverUrl.value}/api/v1";
const TOKEN = "${apiToken.value}";
const DATASET_ID = "${testDatasetId.value || '<dataset_id>'}";

// Upload image
async function uploadImage(file) {
  const formData = new FormData();
  formData.append("dataset_id", DATASET_ID);
  formData.append("file", file);

  const response = await fetch(\`\${API_BASE}/collect/upload\`, {
    method: "POST",
    headers: { "X-Api-Token": TOKEN },
    body: formData,
  });
  return response.json();
}

// Upload with annotation
async function uploadWithAnnotation(file, annotations) {
  const formData = new FormData();
  formData.append("dataset_id", DATASET_ID);
  formData.append("annotations_json", JSON.stringify(annotations));
  formData.append("file", file);

  const response = await fetch(\`\${API_BASE}/collect/upload\`, {
    method: "POST",
    headers: { "X-Api-Token": TOKEN },
    body: formData,
  });
  return response.json();
}

// Usage
const fileInput = document.querySelector('input[type="file"]');
fileInput.addEventListener('change', async (e) => {
  const result = await uploadImage(e.target.files[0]);
  console.log("Uploaded:", result);
});
`)

const currentCode = computed(() => {
  if (codeLang.value === 'python') return pythonCode.value
  if (codeLang.value === 'curl') return curlCode.value
  return jsCode.value
})
</script>

<style scoped>
.code-block {
  background: #1e2130;
  color: #abb2bf;
  padding: 16px;
  border-radius: 8px;
  font-size: 12px;
  overflow-x: auto;
  line-height: 1.7;
  white-space: pre;
  max-height: 500px;
  overflow-y: auto;
}
</style>
