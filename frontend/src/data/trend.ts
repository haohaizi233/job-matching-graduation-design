import type { TrendDataset, TrendRange } from '@/types'

/** 生成从 startISO 起共 n 个、均匀分布在 totalDays 天内的日期序列（YYYY-MM-DD） */
function dateSeries(startISO: string, totalDays: number, n: number): string[] {
  const start = new Date(`${startISO}T00:00:00`)
  const step = totalDays / (n - 1)
  return Array.from({ length: n }, (_, i) => {
    const d = new Date(start.getTime() + Math.round(i * step) * 86400000)
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    const dd = String(d.getDate()).padStart(2, '0')
    return `${d.getFullYear()}-${mm}-${dd}`
  })
}

/** 近30天：推荐岗位数 / 高匹配岗位数（数据点数 = 29） */
const recommended30 = [
  34, 41, 39, 48, 57, 55, 53, 47, 52, 57, 63, 59, 67, 63, 72, 80, 85, 91, 89, 84, 92, 88, 97, 92, 94, 103, 92, 91, 98,
]
const highMatch30 = [
  21, 16, 20, 25, 27, 22, 16, 21, 27, 26, 33, 32, 27, 34, 38, 43, 37, 31, 39, 37, 40, 42, 36, 43, 50, 47, 42, 46, 42,
]

const dataset30: TrendDataset = {
  recommended: recommended30,
  highMatch: highMatch30,
  dates: dateSeries('2024-09-23', 28, recommended30.length),
  axisLabels: ['09-21', '09-25', '09-29', '10-03', '10-07', '10-11', '10-15', '10-21'],
}

const dataset7: TrendDataset = {
  recommended: recommended30.slice(-7),
  highMatch: highMatch30.slice(-7),
  dates: ['2024-10-15', '2024-10-16', '2024-10-17', '2024-10-18', '2024-10-19', '2024-10-20', '2024-10-21'],
  axisLabels: ['10-15', '10-16', '10-17', '10-18', '10-19', '10-20', '10-21'],
}

const recommended90 = [12, 19, 26, 27, 36, 41, 46, 45, 61, 63, 67, 69, 80, 90, 88, 98]
const highMatch90 = [6, 8, 12, 11, 17, 20, 24, 20, 26, 29, 31, 28, 32, 38, 36, 42]

const dataset90: TrendDataset = {
  recommended: recommended90,
  highMatch: highMatch90,
  dates: dateSeries('2024-07-21', 92, recommended90.length),
  axisLabels: ['07-21', '08-04', '08-18', '09-01', '09-15', '09-29', '10-13', '10-21'],
}

export const trendDatasets: Record<TrendRange, TrendDataset> = {
  7: dataset7,
  30: dataset30,
  90: dataset90,
}
