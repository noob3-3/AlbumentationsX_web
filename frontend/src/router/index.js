import { createRouter, createWebHistory } from 'vue-router'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'

const routes = [
  {
    path: '/',
    component: () => import('@/views/Layout.vue'),
    children: [
      {
        path: '',
        redirect: '/dashboard',
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '概览', icon: 'Odometer' },
      },
      {
        path: 'projects',
        name: 'Projects',
        component: () => import('@/views/Projects.vue'),
        meta: { title: '项目管理', icon: 'Management' },
      },
      {
        path: 'projects/:id',
        name: 'ProjectDetail',
        component: () => import('@/views/ProjectDetail.vue'),
        meta: { title: '项目详情', icon: 'Management' },
      },
      {
        path: 'datasets/:id',
        name: 'DatasetDetail',
        component: () => import('@/views/DatasetDetail.vue'),
        meta: { title: '数据集详情', icon: 'Files' },
      },
      {
        path: 'datasets',
        redirect: (to) => {
          // 如果有 project 参数，重定向到项目详情页
          if (to.query.project) {
            return { path: `/projects/${to.query.project}` }
          }
          // 否则重定向到项目列表
          return { path: '/projects' }
        },
      },
      {
        path: 'collect',
        name: 'Collect',
        component: () => import('@/views/DataCollect.vue'),
        meta: { title: '数据采集', icon: 'Download' },
      },
      {
        path: 'augmentation',
        name: 'Augmentation',
        component: () => import('@/views/AugmentationNew.vue'),
        meta: { title: '数据增强', icon: 'MagicStick' },
      },
      {
        path: 'annotation',
        name: 'Annotation',
        component: () => import('@/views/Annotation.vue'),
        meta: { title: '数据标注', icon: 'EditPen' },
      },
      {
        path: 'training',
        name: 'Training',
        component: () => import('@/views/Training.vue'),
        meta: { title: '模型训练', icon: 'Cpu' },
      },
      {
        path: 'training/:id',
        name: 'TrainingDetail',
        component: () => import('@/views/TrainingDetail.vue'),
        meta: { title: '训练详情', icon: 'TrendCharts' },
      },
      {
        path: 'models',
        name: 'Models',
        component: () => import('@/views/Models.vue'),
        meta: { title: '模型管理', icon: 'Box' },
      },
      {
        path: 'deployments',
        name: 'ModelDeployment',
        component: () => import('@/views/ModelDeployment.vue'),
        meta: { title: '模型部署', icon: 'Rocket' },
      },
      {
        path: 'validation',
        name: 'ModelValidation',
        component: () => import('@/views/ModelValidation.vue'),
        meta: { title: '模型验证', icon: 'View' },
      },
      {
        path: 'client-api',
        name: 'ClientAPI',
        component: () => import('@/views/ClientAPI.vue'),
        meta: { title: '客户端API', icon: 'Connection' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  NProgress.start()
  document.title = `${to.meta?.title || 'Platform'} - VST`
  next()
})

router.afterEach(() => {
  NProgress.done()
})

export default router
