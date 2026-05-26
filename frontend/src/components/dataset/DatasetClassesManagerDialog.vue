<template>
  <el-dialog
    v-model="visible"
    title="类别管理"
    width="580px"
    destroy-on-close
    @open="onOpen"
  >
    <el-alert type="info" :closable="false" style="margin-bottom: 12px">
      序号即 class_id（0、1、2…）。保存后标注中的类别名会与下表对齐。删除类别会移除该类别在所有图片上的标注。
    </el-alert>
    <el-form label-width="96px" style="margin-bottom: 12px">
      <el-form-item label="标注任务">
        <el-radio-group v-model="labelTask">
          <el-radio value="detect">水平框检测</el-radio>
          <el-radio value="obb">旋转框 / OBB</el-radio>
          <el-radio value="segment">实例分割</el-radio>
          <el-radio value="semantic">语义分割（-sem）</el-radio>
          <el-radio value="pose">姿态（*-pose.pt）</el-radio>
        </el-radio-group>
        <div style="margin-top:4px;color:#909399;font-size:12px;line-height:1.5">
          与训练页可选基础权重联动；自建数据集或未带标签导入时也应在此设为 OBB 后再训练。
        </div>
      </el-form-item>
    </el-form>
    <el-table :data="rows" border size="small" max-height="380">
      <el-table-column type="index" label="ID" width="56" />
      <el-table-column label="类别名称" min-width="200">
        <template #default="{ row }">
          <el-input v-model="row.name" placeholder="类别名称" clearable />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="88" align="center">
        <template #default="{ row, $index }">
          <el-button link type="danger" size="small" @click="removeRow($index, row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div style="margin-top: 12px">
      <el-button type="primary" plain :icon="Plus" @click="addRow">添加类别</el-button>
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { datasetApi } from '@/api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  datasetId: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'success'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const rows = ref([])
/** detect | obb | pose */
const labelTask = ref('detect')
const saving = ref(false)
/** 打开对话框时服务端已有的类别名（用于判断删除是否走 API） */
const serverNames = ref(new Set())

function syncRowsFromDataset(ds) {
  const lt = String(ds?.label_task || 'detect').toLowerCase()
  labelTask.value = ['obb', 'pose', 'segment', 'semantic'].includes(lt) ? lt : 'detect'
  const cls = ds?.classes && ds.classes.length ? [...ds.classes] : []
  serverNames.value = new Set(cls.filter(Boolean))
  rows.value = cls.length
    ? cls.map((n, i) => ({ name: n || `class_${i}` }))
    : [{ name: 'class_0' }]
}

async function onOpen() {
  if (!props.datasetId) return
  try {
    const ds = await datasetApi.get(props.datasetId)
    syncRowsFromDataset(ds)
  } catch {
    ElMessage.error('加载数据集失败')
    rows.value = [{ name: 'class_0' }]
    serverNames.value = new Set()
    labelTask.value = 'detect'
  }
}

function addRow() {
  rows.value.push({ name: `class_${rows.value.length}` })
}

async function removeRow(index, row) {
  const name = (row.name || '').trim()
  if (!name) {
    rows.value.splice(index, 1)
    if (rows.value.length === 0) rows.value.push({ name: 'class_0' })
    return
  }
  if (!serverNames.value.has(name)) {
    rows.value.splice(index, 1)
    if (rows.value.length === 0) rows.value.push({ name: 'class_0' })
    return
  }
  try {
    await ElMessageBox.confirm(
      `删除类别「${name}」将同时删除该类别在所有图片上的标注，是否继续？`,
      '确认删除',
      { type: 'warning' },
    )
    await datasetApi.deleteClass(props.datasetId, name)
    const ds = await datasetApi.get(props.datasetId)
    syncRowsFromDataset(ds)
    ElMessage.success('已删除')
    emit('success')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

async function save() {
  const names = rows.value.map((r) => (r.name || '').trim())
  if (names.some((n) => !n)) {
    ElMessage.warning('请填写全部类别名称，或删掉空行后再保存')
    return
  }
  const dup = names.find((n, i) => names.indexOf(n) !== i)
  if (dup) {
    ElMessage.warning(`存在重复类别名：${dup}`)
    return
  }
  saving.value = true
  try {
    await datasetApi.update(props.datasetId, { classes: names, label_task: labelTask.value })
    ElMessage.success('类别已保存')
    visible.value = false
    emit('success')
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}
</script>
