<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    width="480px"
    destroy-on-close
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-form label-width="120px" size="default">
      <el-form-item label="ONNX opset">
        <el-input-number v-model="form.opset" :min="9" :max="23" :step="1" controls-position="right" style="width: 160px" />
      </el-form-item>
      <el-form-item label="动态输入尺寸">
        <el-switch v-model="form.dynamic" />
        <div class="hint">关闭则固定输入尺寸，便于部分推理框架部署</div>
      </el-form-item>
      <el-form-item label="导出 batch">
        <el-input-number v-model="form.batch" :min="1" :max="64" :step="1" controls-position="right" style="width: 160px" />
      </el-form-item>
      <el-form-item label="简化图 onnxsim">
        <el-switch v-model="form.simplify" />
        <div class="hint">需安装 onnxsim；失败时可关闭</div>
      </el-form-item>
      <el-form-item label="FP16 (half)">
        <el-switch v-model="form.half" />
      </el-form-item>
      <el-form-item label="指定 imgsz">
        <el-checkbox v-model="form.useImgsz">覆盖默认输入边长</el-checkbox>
        <el-input-number
          v-show="form.useImgsz"
          v-model="form.imgsz"
          :min="32"
          :max="8192"
          :step="32"
          controls-position="right"
          style="width: 160px; margin-left: 8px"
        />
        <div v-if="form.useImgsz" class="hint">建议与训练时 imgsz 一致</div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="loading" @click="submit">导出并下载</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { buildTrainingJobOnnxUrl, buildTrainingModelOnnxUrl, downloadOnnxExport } from '@/api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '导出 ONNX' },
  kind: { type: String, required: true, validator: (v) => v === 'job' || v === 'model' },
  jobId: { type: String, default: '' },
  modelId: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

const loading = ref(false)
const form = ref({
  opset: 18,
  dynamic: false,
  batch: 1,
  simplify: false,
  half: false,
  imgsz: 640,
  useImgsz: false,
})

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      form.value = {
        opset: 18,
        dynamic: false,
        batch: 1,
        simplify: false,
        half: false,
        imgsz: 640,
        useImgsz: false,
      }
    }
  },
)

function buildOpts() {
  const o = {
    opset: form.value.opset,
    dynamic: form.value.dynamic,
    batch: form.value.batch,
    simplify: form.value.simplify,
    half: form.value.half,
  }
  if (form.value.useImgsz && form.value.imgsz != null) {
    o.imgsz = Number(form.value.imgsz)
  }
  return o
}

async function submit() {
  if (props.kind === 'job' && !props.jobId) {
    ElMessage.warning('缺少任务 ID')
    return
  }
  if (props.kind === 'model' && !props.modelId) {
    ElMessage.warning('缺少模型 ID')
    return
  }
  const path =
    props.kind === 'job'
      ? buildTrainingJobOnnxUrl(props.jobId, buildOpts())
      : buildTrainingModelOnnxUrl(props.modelId, buildOpts())
  loading.value = true
  try {
    await downloadOnnxExport(path)
    ElMessage.success('ONNX 已开始下载（服务端在 CPU 上导出，大模型可能需等待片刻）')
    emit('update:modelValue', false)
  } catch (e) {
    ElMessage.error(e?.message || '导出失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.hint {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  line-height: 1.4;
}
</style>
