import type { ResumeItem, ResumeStat } from '@/types'

export const resumeStats: ResumeStat[] = [
  {
    key: 'total',
    name: '简历总数',
    value: '3',
    note: '已上传的简历文件',
    tone: 'blue',
    icon: 'file',
  },
  {
    key: 'parsed',
    name: '已完成解析',
    value: '2',
    note: '生成画像并可用于匹配',
    tone: 'green',
    icon: 'check',
  },
  {
    key: 'parsing',
    name: '解析中',
    value: '0',
    note: '正在解析的简历',
    tone: 'orange',
    icon: 'clock',
  },
  {
    key: 'attention',
    name: '需要处理',
    value: '1',
    note: '解析失败或需要人工处理',
    tone: 'red',
    icon: 'alert',
  },
]

export const resumeList: ResumeItem[] = [
  {
    id: 1,
    filename: '李同学_求职简历.pdf',
    filesize: '2.3 MB',
    uploadDate: '2024-10-21 14:28',
    status: 'done',
    statusText: '已完成',
    version: 'v2.3',
    versionDate: '2024-10-21',
    source: '手动上传',
    fileType: 'pdf',
  },
  {
    id: 2,
    filename: '李同学_实习简历.docx',
    filesize: '1.8 MB',
    uploadDate: '2024-10-15 09:12',
    status: 'partial',
    statusText: '部分解析',
    statusNote: '存在识别误差',
    version: 'v2.1',
    versionDate: '2024-10-15',
    source: '手动上传',
    fileType: 'word',
  },
  {
    id: 3,
    filename: '李同学_秋招简历.pdf',
    filesize: '2.6 MB',
    uploadDate: '2024-10-10 20:36',
    status: 'retry',
    statusText: '待重试',
    statusNote: '扫描版可能需要OCR',
    version: '-',
    versionDate: '',
    source: '手动上传',
    fileType: 'pdf',
  },
]

export const parseWorkflow = [
  {
    step: 1,
    title: '上传简历',
    desc: '支持 PDF、DOCX、TXT 格式',
    icon: 'file',
    tone: 'blue',
  },
  {
    step: 2,
    title: '文本提取',
    desc: '系统自动解析简历内容，提取关键信息',
    icon: 'search',
    tone: 'blue',
  },
  {
    step: 3,
    title: '画像生成',
    desc: '基于提取的内容生成个人能力画像',
    icon: 'chart',
    tone: 'green',
  },
  {
    step: 4,
    title: '人工确认',
    desc: '核对解析结果，确保信息准确\n（如遇解析不完整可手动编辑）',
    icon: 'user',
    tone: 'blue',
  },
]

export const faqList = [
  {
    id: 1,
    question: '扫描版 PDF 无法解析怎么办?',
    answer:
      '如果你的简历是扫描版或图片格式，系统将自动使用 OCR 技术进行文字识别，但可能存在识别误差，建议上传可编辑的 PDF 或 DOCX 文件以获得更好的效果。',
    extra: '遇到识别不完整时，可以点击"重新解析"，或上传更清晰的文件。',
  },
  {
    id: 2,
    question: '上传后多久可以完成解析?',
    answer: '通常在 1-2 分钟内完成解析，复杂的简历可能需要更长时间，请耐心等待。',
    extra: '演示页面只模拟进度；真实处理时间以服务端返回结果为准。',
  },
  {
    id: 3,
    question: '解析结果不准确怎么办?',
    answer: '你可以在解析完成后手动编辑和补充信息，或重新上传更清晰的简历文件。',
    extra: '修改信息后，可以重新生成画像和智能匹配结果。',
  },
]

export const heroCopy = {
  title: '简历管理',
  subtitle: '上传和管理你的简历，系统将自动解析简历内容，生成专属的个人能力画像，\n为你推荐更匹配的岗位机会。',
}
