<script setup lang="ts">
import { useData } from 'vitepress'
const { theme } = useData()
const url = theme.value.pagesUrl as string
</script>

<template>
  <div class="pages-url-panel">
    <p class="pages-url-kicker">在线文档</p>
    <p class="pages-url-title">CI 发布地址</p>
    <a class="pages-url-link" :href="url" target="_blank" rel="noreferrer">{{ url }}</a>
    <p class="pages-url-hint">构建时写入 <code>CI_PAGES_URL</code></p>
  </div>
</template>
