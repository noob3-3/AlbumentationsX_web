import { ElMessageBox } from 'element-plus'

/** 与后端 delete_dataset 行为一致：先删关联任务记录，再删数据集与磁盘目录；models 表通常不随数据集删除 */
const DATASET_DELETE_MESSAGE_HTML = `
<div style="line-height:1.65;text-align:left">
  <p style="margin:0 0 10px 0">此操作<strong>不可恢复</strong>，将删除：</p>
  <ul style="margin:0;padding-left:1.25em">
    <li>该数据集下全部图片、标注及磁盘上的数据集目录</li>
    <li>与该数据集关联的训练任务、数据增强任务、标注任务等记录</li>
  </ul>
  <p style="margin:12px 0 0 0;color:var(--el-text-color-secondary);font-size:13px">
    说明：项目「模型」页中的模型条目通常<strong>不会</strong>随数据集自动删除；如需清理请单独在模型页处理。
  </p>
</div>
`.trim()

export function confirmDatasetDelete() {
  return ElMessageBox.confirm(DATASET_DELETE_MESSAGE_HTML, '确认删除数据集？', {
    type: 'warning',
    confirmButtonText: '确认删除',
    cancelButtonText: '取消',
    distinguishCancelAndClose: true,
    dangerouslyUseHTMLString: true,
    customStyle: { maxWidth: '520px' },
  })
}

const PURGE_AUGMENTED_HTML = `
<div style="line-height:1.65;text-align:left">
  <p style="margin:0 0 10px 0">将删除该数据集中<strong>所有增强生成的图片</strong>及其标注，并清除数据增强任务记录。</p>
  <p style="margin:0;color:var(--el-text-color-secondary);font-size:13px">原图与数据集本身会保留。</p>
</div>
`.trim()

/** 仅清除增强数据（调用 DELETE ?purge_augmented_only=true） */
export function confirmPurgeAugmentedOnly() {
  return ElMessageBox.confirm(PURGE_AUGMENTED_HTML, '清除增强数据？', {
    type: 'warning',
    confirmButtonText: '确认清除',
    cancelButtonText: '取消',
    distinguishCancelAndClose: true,
    dangerouslyUseHTMLString: true,
    customStyle: { maxWidth: '480px' },
  })
}
