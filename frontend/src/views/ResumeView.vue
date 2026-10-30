<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { useToast } from '@/composables/useToast'
import { mapResumeToItem } from '@/api/mappers'
import {
  deleteResume,
  fileToBase64,
  listResumes,
  reparseResume,
  uploadResumeJson,
} from '@/api/resumes'
import { faqList, heroCopy, parseWorkflow, resumeStats } from '@/data/resume'
import type { ResumeItem } from '@/types'

import TopBar from '@/components/dashboard/TopBar.vue'
import SideNav from '@/components/dashboard/SideNav.vue'

const { show } = useToast()

// 联调：简历列表来自业务 API（上传即解析出学生画像）
const resumeList = ref<ResumeItem[]>([])
const loading = ref(true)
const uploading = ref(false)

async function refresh() {
  const rows = await listResumes()
  resumeList.value = rows.map(mapResumeToItem)
}

onMounted(async () => {
  try {
    await refresh()
  } catch (e) {
    show(e instanceof Error ? e.message : '简历列表加载失败')
  } finally {
    loading.value = false
  }
})

const stats = computed(() => {
  const total = resumeList.value.length
  const done = resumeList.value.filter((r) => r.status === 'done' || r.status === 'partial').length
  const parsing = resumeList.value.filter((r) => r.status === 'running').length
  const attention = resumeList.value.filter((r) => r.status === 'retry').length

  return resumeStats.map((s) => {
    if (s.key === 'total') return { ...s, value: String(total) }
    if (s.key === 'parsed') return { ...s, value: String(done) }
    if (s.key === 'parsing') return { ...s, value: String(parsing) }
    return { ...s, value: String(attention) }
  })
})

const dragOver = ref(false)
const openFaq = ref<number | string | null>(null)
const openMenu = ref<number | string | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

function openFileDialog() {
  fileInput.value?.click()
}

function handleDragEnter(e: DragEvent) {
  e.preventDefault()
  dragOver.value = true
}

function handleDragLeave(e: DragEvent) {
  e.preventDefault()
  dragOver.value = false
}

function handleDrop(e: DragEvent) {
  e.preventDefault()
  dragOver.value = false
  const files = e.dataTransfer?.files
  if (files && files.length > 0) {
    handleFileUpload(files[0])
  }
}

function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files && input.files.length > 0) {
    handleFileUpload(input.files[0])
  }
  input.value = ''
}

async function handleFileUpload(file: File) {
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!ext || !['pdf', 'docx', 'txt'].includes(ext)) {
    show('仅支持 PDF、DOCX、TXT 格式')
    return
  }
  if (file.size > 10 * 1024 * 1024) {
    show('单个简历文件不能超过 10MB')
    return
  }
  uploading.value = true
  show('文件已添加，正在上传解析…')
  try {
    const contentBase64 = await fileToBase64(file)
    await uploadResumeJson({ fileName: file.name, contentBase64 })
    await refresh()
    show('上传成功，已生成学生画像，请到「我的画像」核对并确认')
  } catch (e) {
    show(e instanceof Error ? e.message : '简历上传失败')
  } finally {
    uploading.value = false
  }
}

function toggleFaq(id: number | string) {
  openFaq.value = openFaq.value === id ? null : id
}

function toggleMenu(id: number | string) {
  openMenu.value = openMenu.value === id ? null : id
}

function handleViewDetail(item: ResumeItem) {
  openMenu.value = null
  show(`《${item.filename}》解析状态：${item.statusText}${item.statusNote ? `（${item.statusNote}）` : ''}`)
}

async function handleRetry(item: ResumeItem) {
  openMenu.value = null
  show(`正在重新解析《${item.filename}》…`)
  try {
    await reparseResume(String(item.id))
    await refresh()
    show(`《${item.filename}》重新解析完成`)
  } catch (e) {
    show(e instanceof Error ? e.message : '重新解析失败')
  }
}

function handleDownload(_item: ResumeItem) {
  openMenu.value = null
  show('简历文件下载接口暂未开放（文件为私有存储）')
}

async function handleDelete(item: ResumeItem) {
  openMenu.value = null
  try {
    await deleteResume(String(item.id))
    await refresh()
    show(`已删除《${item.filename}》`)
  } catch (e) {
    show(e instanceof Error ? e.message : '删除失败')
  }
}

function handleDemo(name: string) {
  show(`「${name}」功能开发中`)
}
</script>

<template>
  <div class="app-shell">
    <TopBar />
    <SideNav active-key="resume" />

    <main class="workspace">
      <!-- Hero Banner -->
      <section class="hero">
        <div class="hero-bg" />
        <div class="hero-content">
          <h1>{{ heroCopy.title }}</h1>
          <p>{{ heroCopy.subtitle }}</p>
        </div>
      </section>

      <!-- Stats -->
      <section class="stats-grid" aria-label="简历统计">
        <article v-for="stat in stats" :key="stat.key" class="stat-card" :class="stat.tone">
          <div class="stat-icon">
            <svg v-if="stat.icon === 'file'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
              <path d="M13 2v7h7M8 14h8M8 18h6" />
            </svg>
            <svg v-else-if="stat.icon === 'check'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
              <path d="M5 12l5 5L20 7" />
            </svg>
            <svg v-else-if="stat.icon === 'clock'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 7v5l3 3" />
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <path d="M12 9v4M12 17h.01" />
            </svg>
          </div>
          <div class="stat-content">
            <div class="stat-name">{{ stat.name }}</div>
            <div class="stat-value">{{ stat.value }}</div>
            <div class="stat-note">{{ stat.note }}</div>
          </div>
        </article>
      </section>

      <!-- Main Grid -->
      <div class="main-grid">
        <!-- Upload -->
        <section class="panel upload-panel">
          <div class="panel-header">
            <svg class="header-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M6.5 19a5.5 5.5 0 0 1-1-10.9A7 7 0 0 1 19 9.5 5 5 0 0 1 18 19z" />
            </svg>
            <h2>上传新简历</h2>
          </div>
          <p class="upload-desc">支持 PDF、DOCX、TXT 格式，系统将自动解析简历内容，提取你的教育背景、工作经历、技能特长等信息。</p>
          <div
            class="dropzone"
            :class="{ dragover: dragOver }"
            @dragenter="handleDragEnter"
            @dragleave="handleDragLeave"
            @dragover.prevent
            @drop="handleDrop"
            @click="openFileDialog"
          >
            <svg class="upload-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 16V4M8 8l4-4 4 4M4 14v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" />
            </svg>
            <p class="drop-text">拖拽简历文件到此处，或<button class="link-btn" type="button" @click.stop="openFileDialog">点击上传</button></p>
            <p class="drop-hint">支持 PDF、DOCX、TXT 格式，单个文件不超过 10MB</p>
            <button class="btn-primary" type="button" @click.stop="openFileDialog">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 16V4M8 8l4-4 4 4M4 14v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" />
              </svg>
              选择文件上传
            </button>
            <input ref="fileInput" type="file" accept=".pdf,.docx,.txt" @change="handleFileSelect" hidden />
          </div>
          <div class="upload-tip">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 16v-4M12 8h.01" />
            </svg>
            <p>建议使用结构清晰、内容完整的简历文件，以获得更好的解析效果。<br />支持格式：PDF、DOCX、TXT | 文件大小：不超过 10MB</p>
          </div>
        </section>

        <!-- Workflow -->
        <section class="panel workflow-panel">
          <div class="panel-header">
            <h2>简历解析流程</h2>
            <button class="link-btn" type="button" @click="handleDemo('详细说明')">
              查看详细说明
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
          <div class="workflow-steps">
            <div v-for="step in parseWorkflow" :key="step.step" class="step-item">
              <div class="step-number" :class="{ active: step.step === 1 }">{{ step.step }}</div>
              <div class="step-icon" :class="step.tone">
                <svg v-if="step.icon === 'file'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
                  <path d="M13 2v7h7" />
                </svg>
                <svg v-else-if="step.icon === 'search'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="11" cy="11" r="8" />
                  <path d="M21 21l-4.35-4.35" />
                </svg>
                <svg v-else-if="step.icon === 'chart'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M4 20V10M10 20V4M16 20v-6M22 20V8" />
                </svg>
                <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="8" r="4" />
                  <path d="M4 21v-1a8 8 0 0 1 16 0v1" />
                </svg>
              </div>
              <div class="step-content">
                <h3>{{ step.title }}</h3>
                <p>{{ step.desc }}</p>
              </div>
            </div>
          </div>
        </section>

        <!-- Resume List -->
        <section class="panel list-panel">
          <div class="panel-header">
            <h2>我的简历列表</h2>
            <span class="count">共 {{ resumeList.length }} 份简历</span>
          </div>
          <table class="resume-table">
            <thead>
              <tr>
                <th>文件名</th>
                <th>上传时间</th>
                <th>解析状态</th>
                <th>画像版本</th>
                <th>数据来源</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in resumeList" :key="item.id">
                <td>
                  <div class="file-cell">
                    <div class="file-icon" :class="item.fileType">
                      {{ item.fileType === 'word' ? 'W' : 'PDF' }}
                    </div>
                    <div>
                      <div class="filename">{{ item.filename }}</div>
                      <div class="filesize">{{ item.filesize }}</div>
                    </div>
                  </div>
                </td>
                <td class="date-cell">{{ item.uploadDate }}</td>
                <td>
                  <div class="status-cell" :class="item.status">
                    <span class="status-dot">{{ item.status === 'done' ? '✓' : '!' }}</span>
                    {{ item.statusText }}
                  </div>
                  <div v-if="item.statusNote" class="status-note">{{ item.statusNote }}</div>
                </td>
                <td>
                  <div class="version">{{ item.version }}</div>
                  <div v-if="item.versionDate" class="version-date">{{ item.versionDate }}</div>
                </td>
                <td><span class="tag">{{ item.source }}</span></td>
                <td>
                  <div class="actions">
                    <button type="button" class="action-btn" @click="handleViewDetail(item)">
                      {{ item.status === 'retry' ? '重新解析' : '查看' }}
                    </button>
                    <button type="button" class="action-btn" :class="{ danger: item.status === 'retry' }" @click="item.status === 'retry' ? handleDelete(item) : handleDownload(item)">
                      {{ item.status === 'retry' ? '删除' : '下载' }}
                    </button>
                    <button type="button" class="menu-btn" @click="toggleMenu(item.id)">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="5" r="1" />
                        <circle cx="12" cy="12" r="1" />
                        <circle cx="12" cy="19" r="1" />
                      </svg>
                    </button>
                    <div v-if="openMenu === item.id" class="action-menu">
                      <button type="button" @click="handleViewDetail(item)">查看详情</button>
                      <button type="button" @click="handleRetry(item)">重新解析</button>
                      <button type="button" @click="handleDelete(item)">删除简历</button>
                    </div>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="resumeList.some((r) => r.status === 'retry')" class="warn-banner">
            <div class="warn-icon">!</div>
            <div class="warn-content">
              <strong>解析失败提示</strong>
              <p>你的简历《李同学_秋招简历.pdf》可能是扫描版或图片格式，系统未能识别到完整的文本内容。<br />建议上传可编辑的 PDF 或 DOCX 文件，或点击"重新解析"使用 OCR 技术进行识别。</p>
            </div>
            <button type="button" class="btn-outline" @click="handleDemo('重新解析')">重新解析</button>
          </div>
        </section>

        <!-- FAQ -->
        <section class="panel faq-panel">
          <div class="panel-header">
            <h2>常见问题</h2>
            <button class="link-btn" type="button" @click="handleDemo('更多')">
              更多
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>
          <div class="faq-list">
            <div v-for="faq in faqList" :key="faq.id" class="faq-item" :class="{ open: openFaq === faq.id }">
              <button class="faq-question" type="button" @click="toggleFaq(faq.id)">
                <span class="q-mark">?</span>
                <span class="q-text">{{ faq.question }}</span>
                <svg class="arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M9 5l7 7-7 7" />
                </svg>
              </button>
              <div class="faq-answer">
                <p>{{ faq.answer }}</p>
                <p class="extra">{{ faq.extra }}</p>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
}
.workspace {
  margin-left: 198px;
  padding: 75px 57px 35px 17px;
  background: linear-gradient(180deg, #f4f9ff 0%, #f8fbff 100%);
}

.hero {
  height: 138px;
  border-radius: 12px;
  position: relative;
  overflow: hidden;
  background: linear-gradient(110deg, #eff7ff 0%, #daeaff 47%, #b8d8ff 75%, #c1d3ff 100%);
  margin-bottom: 12px;
  padding: 0 37px;
  display: flex;
  align-items: center;
}
.hero-content {
  position: relative;
  z-index: 1;
}
.hero-content h1 {
  font-size: 30px;
  margin: 0 0 8px;
  font-weight: 800;
  letter-spacing: -1px;
  color: #101d46;
}
.hero-content p {
  margin: 0;
  line-height: 1.75;
  color: #41567f;
  font-size: 14px;
  font-weight: 500;
  white-space: pre-line;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}
.stat-card {
  height: 113px;
  background: white;
  border: 1px solid #edf2f8;
  border-radius: 12px;
  display: flex;
  gap: 16px;
  align-items: flex-start;
  padding: 16px 18px;
  box-shadow: 0 4px 14px rgba(45, 78, 139, 0.045);
}
.stat-icon {
  width: 52px;
  height: 52px;
  border-radius: 13px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.stat-icon svg {
  width: 32px;
  height: 32px;
}
.stat-card.blue .stat-icon {
  background: linear-gradient(140deg, #eaf2ff, #c5d8ff);
  color: #2874ff;
}
.stat-card.green .stat-icon {
  background: linear-gradient(145deg, #e8faf6, #ccf1e8);
  color: #03b58c;
}
.stat-card.orange .stat-icon {
  background: linear-gradient(145deg, #fff2e5, #ffe2cf);
  color: #ff7e17;
}
.stat-card.red .stat-icon {
  background: linear-gradient(145deg, #ffeff0, #ffdde0);
  color: #fc4c56;
}
.stat-name {
  font-size: 13px;
  font-weight: 700;
  color: #1c2d55;
}
.stat-value {
  font-size: 26px;
  font-weight: 800;
  line-height: 1.25;
  margin: 4px 0 6px;
  letter-spacing: -0.5px;
}
.stat-note {
  font-size: 12px;
  color: #8898b7;
  white-space: nowrap;
}

.main-grid {
  display: grid;
  grid-template-columns: minmax(0, 2.04fr) minmax(320px, 1fr);
  gap: 12px 14px;
}
.panel {
  background: white;
  border: 1px solid #edf2f7;
  border-radius: 12px;
  padding: 18px;
  box-shadow: 0 4px 14px rgba(45, 78, 139, 0.045);
}
.panel-header {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-bottom: 13px;
}
.panel-header h2 {
  font-size: 17px;
  font-weight: 800;
  margin: 0;
  color: #101d46;
}
.header-icon {
  width: 24px;
  height: 24px;
  color: #176dff;
}
.count {
  font-size: 12px;
  color: #8594ae;
}
.link-btn {
  border: 0;
  background: transparent;
  color: #2167f3;
  font-size: 12px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-left: auto;
}
.link-btn svg {
  width: 14px;
  height: 14px;
}

.upload-desc {
  font-size: 13px;
  color: #7082a2;
  margin: 5px 0 15px 36px;
}
.dropzone {
  border: 1.5px dashed #c1d9ff;
  border-radius: 9px;
  height: 213px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: linear-gradient(145deg, #fcfdff 0%, #f8fbff 58%, #f2f8ff 100%);
  transition: background 0.2s, border-color 0.2s;
  cursor: pointer;
}
.dropzone.dragover {
  background: #e8f3ff;
  border-color: #2472ff;
}
.upload-icon {
  width: 70px;
  height: 65px;
  color: #2875ff;
  margin: -4px 0 4px;
}
.drop-text {
  font-size: 15px;
  color: #1c2c50;
  margin: 0 0 5px;
  font-weight: 600;
}
.drop-hint {
  font-size: 13px;
  color: #7889aa;
  margin: 0;
}
.btn-primary {
  height: 38px;
  min-width: 193px;
  background: #2269fa;
  color: white;
  border: 0;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
  margin: 16px 0 0;
}
.btn-primary:hover {
  background: #095af2;
}
.btn-primary svg {
  width: 18px;
  height: 18px;
}
.upload-tip {
  margin-top: 8px;
  min-height: 54px;
  background: linear-gradient(90deg, #e8f3ff, #eef7ff);
  border-radius: 10px;
  display: flex;
  align-items: center;
  padding: 6px 16px;
  gap: 15px;
  color: #6e82a6;
}
.upload-tip svg {
  width: 24px;
  height: 24px;
  color: #2072ff;
  flex-shrink: 0;
}
.upload-tip p {
  font-size: 12px;
  line-height: 1.55;
  margin: 0;
}

.workflow-steps {
  position: relative;
  margin-top: 19px;
}
.step-item {
  display: grid;
  grid-template-columns: 32px 47px minmax(0, 1fr);
  gap: 12px;
  align-items: center;
  margin-bottom: 14px;
  position: relative;
  min-height: 58px;
}
.step-item:last-child {
  margin-bottom: 0;
}
.step-number {
  height: 27px;
  width: 27px;
  border-radius: 50%;
  background: #e9eef7;
  color: #3d4c68;
  display: grid;
  place-items: center;
  font-size: 13px;
  font-weight: 700;
}
.step-number.active {
  background: #236bff;
  color: white;
}
.step-icon {
  height: 47px;
  width: 47px;
  border-radius: 13px;
  background: linear-gradient(135deg, #eff6ff, #e5f1ff);
  display: grid;
  place-items: center;
  color: #2373ff;
}
.step-icon.green {
  background: #e4f8f5;
  color: #03b88c;
}
.step-icon svg {
  width: 27px;
  height: 27px;
}
.step-content h3 {
  font-size: 13px;
  font-weight: 750;
  margin: 0;
  color: #1f2c4d;
}
.step-content p {
  margin: 3px 0 0;
  line-height: 1.6;
  color: #8191ae;
  font-size: 12px;
  white-space: pre-line;
}

.resume-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.resume-table th {
  height: 41px;
  background: #f3f6fb;
  color: #637393;
  font-weight: 700;
  padding: 0 11px;
  text-align: left;
}
.resume-table td {
  height: 52px;
  border-bottom: 1px solid #edf1f8;
  padding: 7px 11px;
  color: #526483;
}
.file-cell {
  display: flex;
  align-items: center;
  gap: 13px;
}
.file-icon {
  width: 27px;
  height: 32px;
  border-radius: 5px;
  display: grid;
  place-items: center;
  color: white;
  font-size: 9px;
  font-weight: 800;
}
.file-icon.pdf {
  background: linear-gradient(160deg, #ff7777, #fb393a);
}
.file-icon.word {
  background: linear-gradient(160deg, #51a0ff, #176ee9);
  font-size: 17px;
}
.filename {
  font-size: 12px;
  font-weight: 700;
  color: #28385c;
}
.filesize {
  font-size: 11px;
  color: #7f90ac;
  margin-top: 3px;
}
.date-cell {
  white-space: pre-line;
}
.status-cell {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  font-weight: 700;
}
.status-dot {
  width: 17px;
  height: 17px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: white;
  font-size: 11px;
}
.status-cell.done {
  color: #00b58e;
}
.status-cell.done .status-dot {
  background: #05bc93;
}
.status-cell.partial {
  color: #f69a17;
}
.status-cell.partial .status-dot {
  background: #ffb21b;
}
.status-cell.retry {
  color: #fe4a55;
}
.status-cell.retry .status-dot {
  background: #fe5054;
}
.status-note {
  font-size: 10px;
  color: #8a98b2;
  margin-top: 3px;
}
.version {
  font-size: 12px;
}
.version-date {
  font-size: 11px;
  color: #7f90ac;
  margin-top: 3px;
}
.tag {
  background: #eef3f8;
  color: #778ba8;
  font-size: 11px;
  padding: 3px 6px;
  border-radius: 4px;
}
.actions {
  display: flex;
  gap: 3px;
  align-items: center;
  position: relative;
}
.action-btn {
  background: none;
  border: 0;
  color: #1768ff;
  font-size: 12px;
  font-weight: 700;
  padding: 3px 4px;
}
.action-btn.danger {
  color: #fe5154;
}
.menu-btn {
  border: 0;
  background: none;
  padding: 1px 4px;
  color: #203251;
}
.menu-btn svg {
  width: 18px;
  height: 18px;
}
.action-menu {
  position: absolute;
  right: 0;
  top: 28px;
  width: 125px;
  padding: 5px;
  background: white;
  box-shadow: 0 8px 28px rgba(36, 60, 103, 0.17);
  border-radius: 7px;
  border: 1px solid #eef2f8;
  z-index: 10;
}
.action-menu button {
  display: block;
  width: 100%;
  border: 0;
  background: none;
  text-align: left;
  padding: 8px;
  color: #344260;
  font-size: 12px;
}
.action-menu button:hover {
  background: #eff5ff;
}

.warn-banner {
  border: 1px solid #ffdbb7;
  border-radius: 10px;
  margin-top: 6px;
  background: linear-gradient(100deg, #fff7f0, #fffbf7);
  display: flex;
  align-items: center;
  gap: 13px;
  padding: 10px 15px;
  min-height: 65px;
}
.warn-icon {
  width: 24px;
  height: 24px;
  background: #fe7b18;
  color: white;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 17px;
  font-weight: 800;
  flex-shrink: 0;
}
.warn-content {
  flex: 1;
}
.warn-content strong {
  color: #ff781c;
  font-size: 13px;
}
.warn-content p {
  color: #78869e;
  font-size: 11px;
  line-height: 1.4;
  margin: 2px 0 0;
}
.btn-outline {
  border: 1px solid #ff8539;
  background: white;
  border-radius: 6px;
  color: #fe7225;
  font-weight: 700;
  font-size: 12px;
  padding: 7px 15px;
  white-space: nowrap;
}

.faq-list {
  margin-top: 10px;
}
.faq-item {
  border-bottom: 1px solid #edf0f5;
  padding: 9px 1px 11px;
}
.faq-item:last-child {
  border-bottom: none;
}
.faq-question {
  display: grid;
  grid-template-columns: 23px minmax(0, 1fr) 18px;
  gap: 12px;
  align-items: start;
  width: 100%;
  background: transparent;
  border: 0;
  text-align: left;
}
.q-mark {
  height: 20px;
  width: 20px;
  border-radius: 50%;
  background: linear-gradient(135deg, #739efa, #3979ff);
  display: grid;
  place-items: center;
  color: white;
  font-size: 13px;
  font-weight: 800;
}
.q-text {
  font-size: 13px;
  font-weight: 750;
  line-height: 1.5;
  color: #243451;
}
.arrow {
  width: 18px;
  height: 18px;
  color: #33456e;
  transition: transform 0.2s;
}
.faq-item.open .arrow {
  transform: rotate(90deg);
}
.faq-answer {
  margin: 5px 8px 0 35px;
  color: #8290aa;
  font-size: 12px;
  line-height: 1.55;
  display: none;
}
.faq-item.open .faq-answer {
  display: block;
}
.faq-answer .extra {
  margin-top: 5px;
}

@media (max-width: 1190px) {
  .workspace {
    padding-right: 18px;
  }
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .main-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 1000px) {
  .workspace {
    margin-left: 76px;
  }
}
@media (max-width: 540px) {
  .workspace {
    margin-left: 0;
    padding: 70px 10px 82px;
  }
}
</style>
