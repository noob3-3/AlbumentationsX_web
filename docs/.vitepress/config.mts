import { defineConfig } from 'vitepress'

function pagesBase(): string {
  const pagesUrl = process.env.CI_PAGES_URL
  if (pagesUrl) {
    try {
      const pathname = new URL(pagesUrl).pathname
      return pathname.endsWith('/') ? pathname : `${pathname}/`
    } catch { /* fall through */ }
  }
  const explicit = process.env.CI_PAGES_BASE
  if (explicit) return explicit.endsWith('/') ? explicit : `${explicit}/`
  return '/'
}

const base = pagesBase()

function pagesUrl(): string {
  const fromCi = process.env.CI_PAGES_URL
  if (fromCi) return fromCi.endsWith('/') ? fromCi : `${fromCi}/`
  return '/'
}

export default defineConfig({
  title: 'VST Platform',
  description: 'VST 目标检测训练平台使用说明',
  lang: 'zh-CN',
  base,
  srcExclude: ['[A-Z]*.md', 'manual/**'],
  ignoreDeadLinks: true,
  themeConfig: {
    pagesUrl: pagesUrl(),
    nav: [
      { text: '首页', link: '/' },
      { text: '使用说明', link: '/guide/getting-started' },
      { text: '在线地址', link: pagesUrl() }
    ],
    sidebar: [
      {
        text: '开始',
        items: [
          { text: '开始使用', link: '/guide/getting-started' },
          { text: '软件授权', link: '/guide/license' }
        ]
      },
      {
        text: '数据',
        items: [
          { text: '项目管理', link: '/guide/projects' },
          { text: '数据采集', link: '/guide/collect' },
          { text: '数据增强', link: '/guide/augmentation' },
          { text: '数据标注', link: '/guide/annotation' }
        ]
      },
      {
        text: '模型',
        items: [
          { text: '模型训练', link: '/guide/training' },
          { text: '模型管理', link: '/guide/models' },
          { text: '模型部署', link: '/guide/deployment' },
          { text: '模型验证', link: '/guide/validation' }
        ]
      },
      {
        text: '集成',
        items: [
          { text: '客户端 API', link: '/guide/client-api' },
          { text: '常见问题', link: '/guide/faq' }
        ]
      }
    ],
    outline: { level: [2, 3], label: '本页目录' },
    search: { provider: 'local' },
    lastUpdated: { text: '上次更新' },
    docFooter: { prev: '上一页', next: '下一页' }
  }
})
