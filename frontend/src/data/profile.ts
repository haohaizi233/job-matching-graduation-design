import type {
  ProfileEducation,
  ProfileInternship,
  ProfileProject,
  ProfileRadarData,
  ProfileSkill,
} from '@/types'

export const profileHeroCopy = {
  title: '我的职业画像',
  subtitle:
    '基于你的简历、项目经历、实习经历等多源信息，构建专属你的职业能力画像\n帮助你更清晰地认识自己，找到更匹配的职业机会。',
}

export const profileBasic = {
  name: '李同学',
  gender: '女',
  age: '21岁',
  birth: '2002-09-15',
  phone: '138****5678',
  email: 'lixiaotong@stu.edu.cn',
  location: '浙江省 杭州市',
  status: '已完善',
}

export const radarData: ProfileRadarData = {
  dimensions: ['专业技能', '项目实践', '学习能力', '沟通协作', '问题解决'],
  scores: [90, 85, 78, 72, 80],
  avgScores: [75, 70, 68, 65, 72],
}

export const profileVersion = {
  version: 'v2.3',
  status: '当前版本',
  updateTime: '2024-10-21 14:36',
  desc: '基于简历、项目、实习等 5 个来源\n智能生成',
}

export const jobIntention = {
  targetPosition: '后端开发工程师 / Java开发工程师',
  industry: '互联网 · 人工智能 · 软件开发',
  city: '杭州 · 上海 · 深圳',
  salary: '15-25K',
  entryTime: '2025年7月',
}

export const coreSkills: ProfileSkill[] = [
  { name: 'Java', level: '精通' },
  { name: 'Python', level: '熟练' },
  { name: 'Vue.js', level: '熟练' },
  { name: 'MySQL', level: '熟练' },
  { name: '数据分析', level: '掌握' },
  { name: 'Spring Boot', level: '精通' },
  { name: 'Redis', level: '熟练' },
  { name: 'Linux', level: '掌握' },
  { name: 'Git', level: '熟练' },
  { name: 'Docker', level: '掌握' },
]

export const education: ProfileEducation = {
  school: '浙江大学',
  major: '计算机科学与技术',
  degree: '本科',
  period: '2021.09 ~ 2025.06',
  gpa: '3.8 / 4.0',
  ranking: '前10%',
}

export const projects: ProfileProject[] = [
  {
    id: 1,
    name: '校园二手交易平台（Vue + Spring Boot）',
    role: '个人项目 · 前端开发 · 后端开发',
    period: '2024.03 ~ 2024.06',
    highlights: [
      '基于 Vue3 + Spring Boot 开发的校园二手交易平台，支持用户发布、浏览、交易',
      '负责后端接口设计与开发，使用 MySQL 存储数据，Redis 缓存热点数据',
      '项目已部署到云服务器，支持千级用户访问',
    ],
  },
]

export const internships: ProfileInternship[] = [
  {
    id: 1,
    company: '阿里巴巴集团',
    position: '后端开发实习生',
    period: '2024.07 ~ 2024.09',
    location: '杭州',
    highlights: [
      '参与电商业务中后台系统的开发与维护，负责核心模块的后端接口开发',
      '使用 Java + Spring Boot + MySQL 完成数据开发与单元测试',
      '参与系统性能优化，接口响应时间提升 30%',
    ],
  },
]

export const evidenceSources = [
  { type: '原文提取', percent: '42%', desc: '来自你的简历、项目经历、实习经历等原始内容' },
  { type: '模型推断', percent: '38%', desc: '基于大模型对你的能力进行补充推断' },
  { type: '人工确认', percent: '20%', desc: '你手动编辑和确认的内容' },
]

export const profileTags = {
  advantage: ['逻辑思维强', '学习能力强', '动手能力强', '团队协作佳'],
  careerGoal: '希望在互联网公司从事开发工作，长期深耕云计算和分布式系统方向。',
  selfIntro:
    '热爱技术，具备扎实的计算机基础知识和编程能力。在校期间积极参与项目实践，有良好的学习能力和团队协作精神。',
}
