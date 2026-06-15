// src/router.ts
import { createRouter, createWebHistory } from 'vue-router'
const routes = [
  { path: '/', redirect: () => '/works' },
  { path: '/works', component: () => import('./views/Overview.vue'), props: true },
  { path: '/works/:wid', component: () => import('./views/Overview.vue'), props: true },
  { path: '/works/:wid/characters', component: () => import('./views/Characters.vue'), props: true },
  { path: '/works/:wid/matrix', component: () => import('./views/Matrix.vue'), props: true },
  { path: '/works/:wid/inspirations', component: () => import('./views/Inspirations.vue'), props: true },
  { path: '/works/:wid/report', component: () => import('./views/Report.vue'), props: true },
  { path: '/works/:wid/read', component: () => import('./views/Reader.vue'), props: true },
  { path: '/works/:wid/outline', component: () => import('./views/Outline.vue'), props: true },
]
export const router = createRouter({ history: createWebHistory(), routes })
