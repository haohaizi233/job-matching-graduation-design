# UI 资源库说明（大学生就业岗位画像与简历智能匹配系统）

本目录存放设计稿与前端可用素材。所有资源已按 **英文 kebab-case 语义命名** 并分类，
原始中文文件名与新文件名的完整对照见 [`asset-mapping.csv`](asset-mapping.csv)（UTF-8 BOM，可直接用 Excel 打开）。

## 目录结构

```
UI/
├── README.md                  本说明
├── asset-mapping.csv          旧文件名 → 新文件名 完整映射（含去重与别名记录）
├── assets/                    ★ 前端直接使用的素材
│   ├── images/
│   │   ├── logo/              系统标识
│   │   ├── banner/            页面头图 / 通栏背景
│   │   ├── illustration/      插画（登录页、宣传位等）
│   │   └── avatar/            示例头像
│   └── icons/
│       ├── nav/               侧边导航图标（默认态 + -active 选中态）
│       ├── topbar/            顶栏图标（搜索、通知）
│       ├── company/           企业标识（含无 Logo 时的通用地球标）
│       ├── job/               岗位卡片元信息（地点、发布时间）
│       ├── action/            工具栏操作与视图切换（列表/卡片、重置、重跑）
│       ├── feedback/          反馈动作与反馈中心统计卡（tile/ 下为浅色底块变体）
│       ├── status/            岗位状态（已投递、已面试、匹配成功、再次推荐）
│       ├── match/             智能匹配页指标图标（技能覆盖、学历匹配等）
│       ├── rank/              排名徽章 rank-01 ~ rank-20
│       ├── upload/            简历上传与解析状态图标
│       └── common/            通用图标（文件类型、用户、设备、提示等）
├── mockups/                   整页设计稿（按页面流程编号 01~10，仅作对照，不进前端包）
├── _reference/                校对用预览图与原始说明文档
└── html/                      预留（当前为空）
```

## 命名规范

- **kebab-case 英文语义名**，不含序号与中文，避免 URL 编码 / 打包问题。
- 同名 `.svg` 与 `.png` 为同一图标的两种格式：**优先用 SVG**（矢量、体积小、可随 CSS 改色），PNG 为位图备份（多为 512px 透明底）。
- 状态后缀：`-active` 亮蓝选中态、`-muted` 灰蓝弱化态、`-red / -blue / -orange / -gold` 颜色态、`-tile` 浅色圆角底块版、`-soft` 柔和渐变版。
- 排名徽章固定 `rank-01` … `rank-20` 两位补零。

## 图标对照表

### nav/ 侧边导航

| 文件（.svg/.png 成对） | 中文 | 说明 |
| --- | --- | --- |
| `dashboard` / `dashboard-active` | 工作台 | |
| `resume` / `resume-active` | 简历管理 | |
| `profile` / `profile-active` | 我的画像 | |
| `jobs` / `jobs-active` | 岗位探索 | |
| `matching` / `matching-active` | 智能匹配 | |
| `history` / `history-active` | 推荐历史 | |
| `feedback` / `feedback-active` | 反馈中心 | |
| `settings` | 个人设置 | 默认态与选中态为同一文件，无 `-active` 版本 |

### topbar/ 顶栏

| 文件 | 中文 |
| --- | --- |
| `search` | 顶部搜索 |
| `notification` | 消息通知 |

### company/ 企业标识

| 文件 | 中文 |
| --- | --- |
| `alibaba` | 阿里巴巴 |
| `tencent` | 腾讯（蓝色文字 Logo） |
| `tencent-qq` | 腾讯 QQ |
| `bytedance` | 字节跳动 |
| `meituan` | 美团 |
| `baidu` | 百度 |
| `huawei` | 华为（红色花瓣 Logo） |
| `generic-globe` | 通用企业标（蓝色环绕地球，无 Logo 企业占位） |

### job/ 岗位卡片

| 文件 | 中文 |
| --- | --- |
| `location` | 岗位地点（定位） |
| `publish-time` | 发布时间（时钟） |

### action/ 工具栏操作

| 文件 | 中文 |
| --- | --- |
| `rerun-match` | 重新运行匹配（蓝色刷新） |
| `reset-filter` | 重置筛选（刷新箭头） |
| `view-list` / `view-list-active` | 列表模式（未选中 / 选中白色） |
| `view-grid` | 卡片模式（四宫格） |
| `trend-up` | 推荐岗位总数（蓝色斜箭头） |

### feedback/ 反馈

| 文件 | 中文 |
| --- | --- |
| `thumb-up-muted` / `thumb-up-blue` | 感兴趣（灰蓝 / 蓝色点赞） |
| `thumb-down-muted` / `thumb-down-red` | 不感兴趣（灰蓝 / 红色点踩） |
| `not-relevant` | 不相关（灰蓝圆圈叉号） |
| `interview-gained` | 获得面试（灰蓝时钟气泡） |
| `today-feedback` | 今日反馈（消息气泡） |
| `interested-job` | 感兴趣岗位（点赞） |
| `applied-job` | 已投递岗位（纸飞机） |
| `pending-suggestion` | 待处理建议（时钟） |
| `feedback-trend` | 反馈趋势（信息符号） |
| `feedback-rating` | 反馈效果（满意度星标） |
| `improvement-up` | 较上月提升（绿色上升箭头） |
| `optimization-tip` | 优化建议（橙色灯泡） |
| `job-bookmark` | 岗位收藏（橙色星标） |
| `job-external-link` | 岗位外链（外链跳转） |

> `feedback/tile/` 内为前 4 个图标带浅色圆角底块的变体（仅 PNG）。

### status/ 岗位状态

| 文件 | 中文 |
| --- | --- |
| `match-success` | 匹配成功（绿色对勾） |
| `applied` | 已投递（纸飞机） |
| `interviewed` | 已面试（日历） |
| `recommend-again` | 再次推荐（外链） |

### match/ 智能匹配指标

| 文件 | 中文 |
| --- | --- |
| `profile-version` | 画像版本（紫色加号） |
| `start-match` | 开始匹配（白色闪光） |
| `skill-coverage` | 技能覆盖（绿色对勾） |
| `education-match` | 学历匹配（蓝色毕业帽） |
| `project-relevance` | 项目相关性（紫色文档） |
| `intent-aligned` | 求职意向一致（橙红靶心） |
| `bookmark-star` | 收藏岗位（灰蓝空心星） |
| 排名徽章 | 见 `rank/rank-01`、`rank/rank-02`（见下方别名说明） |

### rank/ 排名徽章

`rank-01`（金色）… `rank-20`（灰色），`.svg` + `.png` 成对。

### upload/ 简历上传与解析

| 文件 | 中文 |
| --- | --- |
| `upload-cloud` | 上传新简历（云端图标） |
| `upload-drag` | 拖拽上传（云朵上箭头） |
| `upload-file` | 选择文件上传（白色上传箭头） |
| `upload-arrow-blue` | 附加变体（蓝色上传箭头） |
| `upload-info` | 上传说明（蓝色信息提示） |
| `arrow-right-blue` | 更多说明（蓝色右箭头） |
| `arrow-right-muted` | 常见问题（灰蓝右箭头） |
| `parse-complete` | 解析完成（绿色勾选） |
| `file-word` | Word 文件（蓝色 W 文档） |
| `parse-warning` | 部分解析（橙色警告） |
| `parse-error` | 解析待重试（红色警告） |

### common/ 通用图标（仅 PNG）

| 文件 | 中文 | 文件 | 中文 |
| --- | --- | --- | --- |
| `checkbox-expand` | 勾选框（带下拉箭头） | `document-solid` | 文档（实心） |
| `edit-pencil` | 编辑（铅笔） | `palette` | 调色板 |
| `check-square-green` | 绿色方块对勾 | `target-solid` | 靶心（实心） |
| `check-circle-mint` | 绿色圆形对勾 | `target-purple-tile` | 靶心（紫底） |
| `school` | 学校建筑 | `settings-gear` | 设置（齿轮） |
| `user-solid` | 用户（实心） | `clipboard-list` | 清单 |
| `user-outline-tile` | 用户（轮廓·浅底） | `arrow-back-tile` | 返回箭头（浅底） |
| `user-muted` | 用户（灰色） | `graduation-cap-tile` | 毕业帽（浅底） |
| `user-tile` | 用户（浅底） | `help-circle-muted` | 帮助（灰色问号） |
| `user-clock` | 用户时钟（待处理） | `help-blue-tile` | 帮助（蓝色问号·浅底） |
| `shield-solid` | 盾牌（实心） | `document-blue-tile` | 文档（蓝底） |
| `shield-outline-tile` | 盾牌（轮廓·浅底） | `document-purple-tile` | 文档（紫底） |
| `shield-check-tile` | 盾牌对勾（浅底） | `document-tile-blue-light` | 文档（浅蓝底） |
| `shield-check-hexagon` | 盾牌对勾（绿六边形） | `document-tile-blue-glossy` | 文档（蓝底光感） |
| `lock-tile` | 锁（浅底） | `document-orange` | 浅橙折角文档（公告） |
| `lock-muted` | 锁（灰色） | `file-pdf` / `file-pdf-alt` | PDF 文档（两版） |
| `eye-off-muted` | 隐藏密码（灰色） | `code-tile` | 代码 `</>`（浅底） |
| `monitor` | 显示器 | `bulb-tile` | 灯泡（浅底） |
| `mobile-outline-tile` | 手机（轮廓·浅底） | `company-building-tile` | 企业大楼（浅底） |
| `mobile-solid-tile` | 手机（实心·浅底） | `calendar-tile` | 日历（浅底） |
| `bell-solid` | 铃铛（实心） | `clock-orange-tile` | 时钟（橙色·浅底） |
| `bell-alert-tile` | 提醒铃铛（橙色·浅底） | `clock-orange-soft` | 时钟（橙色柔和） |
| `megaphone-tile` | 喇叭（浅底） | `chart-bar-mint` | 柱状图（薄荷底） |
| `megaphone-orange` | 喇叭（橙色·重要提示） | `chart-bar-mint-soft` | 柱状图（薄荷柔和） |
| `mail-outline-tile` | 信封（轮廓·浅底） | `warning-triangle-red` | 警告三角（红色） |
| `mail-solid-tile` | 信封（实心·浅底） | `search-tile` | 放大镜（浅底） |
| `chat-tile` | 消息气泡（浅底） | `skill-add-orange` | 技能标签加号（橙红） |
| `social-qq` / `social-wechat` / `social-weibo` | QQ / 微信 / 微博 | `skill-add-gold` | 技能标签加号（金黄） |

## images/ 图片素材

| 文件 | 中文 |
| --- | --- |
| `logo/logo-title.png` | 系统横版标题 Logo（毕业帽 + 系统名） |
| `banner/banner-settings.png` | 「个人设置」页头插画横幅 |
| `banner/banner-campus.png` | 校园风景通栏背景（无文字） |
| `illustration/login-hero.png` | 登录页插画（校园 + 简历匹配悬浮卡） |
| `illustration/slogan-career-start.png` | 宣传插画（奔跑毕业生 +「让每一位大学生找到更合适的职业起点」） |
| `illustration/ai-resume-wide.png` | AI 简历插画（宽幅，含用户卡/时间检索） |
| `illustration/ai-resume-card.png` | AI 简历插画（方形，含 AI 徽标） |
| `avatar/avatar-sample.png` | 示例头像 |

## mockups/ 设计稿（按页面流程排序）

| 文件 | 页面 |
| --- | --- |
| `01-login.png` | 登录 |
| `02-dashboard.png` | 工作台 |
| `03-resume.png` | 简历管理 |
| `04-profile.png` | 我的画像 |
| `05-jobs-list.png` | 岗位探索（列表） |
| `06-job-detail.png` | 岗位详情 |
| `07-matching.png` | 智能匹配 |
| `08-history.png` | 推荐历史 |
| `09-feedback.png` | 反馈中心 |
| `10-settings.png` | 个人设置 |

## 已知重复与别名（已在整理时去重）

| 保留文件 | 原重复文件 | 说明 |
| --- | --- | --- |
| `rank/rank-01.png/.svg` | `PNG透明背景/03_排名第一_橙金徽章`、`SVG矢量/03_排名第一_橙金徽章` | 智能匹配页「排名第一」徽章与 rank-01 完全相同 |
| `rank/rank-02.png/.svg` | `PNG透明背景/08_排名第二_银灰徽章`、`SVG矢量/08_排名第二_银灰徽章` | 智能匹配页「排名第二」徽章与 rank-02 完全相同 |
| `nav/settings.png/.svg` | `选中态_亮蓝色/08_个人设置` | 个人设置默认态与选中态为同一文件 |

## 前端接入建议

1. 将 `UI/assets/` 整体拷贝到前端工程（如 `src/assets/`），`mockups/`、`_reference/` 不参与构建。
2. 图标优先内联 SVG 或 `import xxx from '@/assets/icons/xxx.svg'`；位图场景再取同名 PNG。
3. 导航选中态切换：默认态文件名 + `-active` 后缀对应同一图标，注意 `settings` 无选中态版本。
4. `_reference/icon-overview-check-only.png` 为 `icons/upload/` 一组 11 个图标的校对总览图，可对照查含义。
