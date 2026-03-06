<template>
  <el-config-provider :locale="zhCn">
    <router-view />
  </el-config-provider>
</template>

<script setup>
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
</script>

<style>
*,
*::before,
*::after {
  box-sizing: border-box;
}

html, body, #app {
  height: 100%;
  margin: 0;
  padding: 0;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

h1, h2, h3, h4, h5, h6, p, ul, ol, dl, figure, blockquote, fieldset {
  margin: 0;
  padding: 0;
}

.page-header {
  margin-bottom: 20px;
}

.page-header h2 {
  font-size: 22px;
  font-weight: 600;
  color: #303133;
}

.page-header p {
  margin-top: 6px;
  color: #909399;
  font-size: 14px;
}
</style>
