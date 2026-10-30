import { apiRequest } from './http'
import type { ProfileRow } from './types'

/** 画像可人工编辑字段（后端 EDITABLE_PROFILE_FIELDS） */
export const EDITABLE_PROFILE_FIELDS = [
  'education_level',
  'major',
  'graduation_year',
  'employment_intention',
  'preferred_cities',
  'employment_type',
] as const

export type EditableProfileField = (typeof EDITABLE_PROFILE_FIELDS)[number]

export async function getProfile(): Promise<ProfileRow | null> {
  try {
    const data = await apiRequest<{ profile: ProfileRow }>('/students/me/profile')
    return data.profile
  } catch (e) {
    // 尚未上传简历时后端返回 NOT_FOUND，前端按“无画像”处理
    if ((e as { code?: string }).code === 'NOT_FOUND') return null
    throw e
  }
}

export async function saveProfile(input: {
  edits: Partial<Record<EditableProfileField, unknown>>
  confirm?: boolean
  note?: string
  expectedVersion?: number | null
}): Promise<ProfileRow> {
  const data = await apiRequest<{ profile: ProfileRow }>('/students/me/profile', {
    method: 'PUT',
    json: {
      edits: input.edits,
      confirm: input.confirm ?? false,
      note: input.note ?? null,
      expected_version: input.expectedVersion ?? null,
    },
  })
  return data.profile
}

export async function listProfileVersions(): Promise<ProfileRow[]> {
  const data = await apiRequest<{ versions: ProfileRow[] }>('/students/me/profile/versions')
  return data.versions
}

export async function getProfileVersion(version: number): Promise<ProfileRow> {
  const data = await apiRequest<{ profile: ProfileRow }>(`/students/me/profile/versions/${version}`)
  return data.profile
}

/** 从画像字段对象里取人工可读值 */
export function fieldValue(profile: ProfileRow | null, key: string): unknown {
  const f = profile?.profile_data?.profile?.[key]
  return f && typeof f === 'object' ? (f as { value?: unknown }).value : undefined
}
