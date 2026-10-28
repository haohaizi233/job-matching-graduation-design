# 开发环境搭建与维护（graduation-design）

> 适用项目：大学生就业岗位画像与简历智能匹配（毕业设计）
> 环境名称：`graduation-design`　Python：3.11　目标平台：Windows (PowerShell / CMD)
> 最近更新：2026-10-28

---

## 1. 环境概述

| 项目 | 值 |
|---|---|
| Conda 环境名 | `graduation-design` |
| Python 版本 | 3.11（当前 3.11.18） |
| Conda 安装位置 | `C:\Users\MemoryLeak\miniconda3`（Miniconda3 py312_24.9.2-0，conda 24.9.2） |
| 环境实际路径 | `C:\Users\MemoryLeak\miniconda3\envs\graduation-design` |
| GPU | NVIDIA GeForce RTX 2050（4 GB 显存），驱动 581.80 |
| CUDA Toolkit | 12.4（`nvcc` V12.4.131），PyTorch 采用 CUDA 12.1 官方预编译 wheel |
| 环境用途 | 简历/岗位数据处理、岗位画像特征抽取、文本向量与语义匹配、排序建模、Chinese-SkillSpan 训练与评测 |

**Python 3.11 的选择依据**：任务默认要求 3.11；项目内 `requirements-train.txt`（torch 2.1.2 / transformers 4.37.1）、
`requirements-common.txt`（transformers 4.40.2 / numpy 1.26.4）与 `benchmark_profile/requirements.txt`
（numpy 2.1.3 / scipy 1.15.3 / matplotlib 3.10.0）中的所有包均提供 Python 3.11 的官方 wheel，无 3.11 不兼容项，
故未做降级。`requirements-common.txt` 中“Use a NEW Python 3.10 environment”的注释针对该外部复现子流程的历史配方，
本环境经验证可在 3.11 下安装同一组版本，如需逐位复现该子流程的结果，请按其说明另建 3.10 环境。

---

## 2. 本机 Conda 审计结果（2026-10-28）

| 项 | 结果 |
|---|---|
| `conda` 是否在 PATH | **否**（PowerShell 中直接执行 `conda` 会报 CommandNotFoundException） |
| 可用 Conda | `C:\Users\MemoryLeak\miniconda3\Scripts\conda.exe`、`C:\Users\MemoryLeak\miniconda3\condabin\conda.bat` |
| 其他 Conda 安装 | `D:\APP\Anaconda3`（Anaconda3 2024.10-1，Python 3.12.7，注册表已登记，未使用、未改动） |
| 已有环境 | `base`（3.12.7）、`3.10`、`3.12`（位于 `C:\Users\MemoryLeak\.conda\envs`）——**均未修改、未删除** |
| `graduation-design` 是否已存在 | 否，本次全新创建 |
| 网络来源 | pip 全局配置使用阿里云 PyPI 镜像（`https://mirrors.aliyun.com/pypi/simple/`） |
| PyTorch 下载渠道 | 官方 `https://download.pytorch.org/whl/cu121` 在本机实测约 350–500 KB/s 且中途连接中断（下载到 196 MB 停滞），改用其镜像 `https://mirrors.aliyun.com/pytorch-wheels/cu121/` 配合 `curl` 断点续传完成，wheel 内容与官方一致（`torch-2.1.2+cu121-cp311-cp311-win_amd64.whl`，2,473,957,547 字节） |

> **重要**：本次操作全程未触碰 `base`、`3.10`、`3.12` 三个既有环境，也未修改任何全局 PATH 或 shell 初始化脚本。

---

## 3. 创建环境

### 3.1 从零创建（本次实际执行的命令）

```powershell
# PowerShell（conda 不在 PATH 时必须使用完整路径）
& "C:\Users\MemoryLeak\miniconda3\Scripts\conda.exe" create -n graduation-design python=3.11 pip -y
```

### 3.2 从定义文件复现（推荐用于新机器）

```powershell
& "C:\Users\MemoryLeak\miniconda3\Scripts\conda.exe" env create -f environment.yml
# 若只想更新已存在的环境：
& "C:\Users\MemoryLeak\miniconda3\Scripts\conda.exe" env update -f environment.yml --prune
```

`environment.yml` 位于项目根目录，只包含相对依赖描述，不引用本机绝对路径。

### 3.3 PyTorch CUDA wheel 的安装（网络受限时）

`environment.yml` 中的 `torch==2.1.2+cu121` 会自动从 PyTorch 官方索引安装。若官方索引过慢或中断，
可先用 `curl` 断点续传下载 wheel，再本地安装（wheel 与官方文件逐字节一致）：

```powershell
# 1) 断点续传下载（-C - 可续传；--speed-limit 遇停滞自动重试）
curl.exe -L -C - --speed-limit 20000 --speed-time 30 --retry 2 `
  -o "$env:TEMP\gd_wheels\torch-2.1.2+cu121-cp311-cp311-win_amd64.whl" `
  "https://mirrors.aliyun.com/pytorch-wheels/cu121/torch-2.1.2%2Bcu121-cp311-cp311-win_amd64.whl"

# 2) 校验大小（应为 2473957547 字节）
(Get-Item "$env:TEMP\gd_wheels\torch-2.1.2+cu121-cp311-cp311-win_amd64.whl").Length

# 3) 本地安装（其余依赖仍从 PyPI 源解析）
& "C:\Users\MemoryLeak\miniconda3\envs\graduation-design\python.exe" `
  -m pip install "$env:TEMP\gd_wheels\torch-2.1.2+cu121-cp311-cp311-win_amd64.whl"
```

可用镜像（同一官方 wheel 的分发镜像，任选其一）：

| 镜像 | 地址 |
|---|---|
| 阿里云 pytorch-wheels | `https://mirrors.aliyun.com/pytorch-wheels/cu121/` |
| 上海交大 pytorch-wheels | `https://mirror.sjtu.edu.cn/pytorch-wheels/cu121/` |
| 官方（默认） | `https://download.pytorch.org/whl/cu121/` |

> **易错点**：不要直接 `pip install torch` —— PyPI 默认源只会提供 CPU 版（本项目搭建过程中曾被误装 `torch 2.14.1` CPU 版，
> 随后用上面的 CUDA wheel 覆盖修正）。安装后务必用第 6.3 条自检 `torch.cuda.is_available()`。

---

## 4. 激活环境

### PowerShell（推荐）

```powershell
# 方式 A：一次性调用，不改动任何全局配置（自动化脚本首选）
& "C:\Users\MemoryLeak\miniconda3\Scripts\conda.exe" run -n graduation-design python your_script.py

# 方式 B：在当前会话中激活（仅影响当前窗口，关闭即失效）
& "C:\Users\MemoryLeak\miniconda3\shell\condabin\conda-hook.ps1"
conda activate graduation-design
```

若 `conda-hook.ps1` 不存在，使用：

```powershell
Import-Module "C:\Users\MemoryLeak\miniconda3\Scripts\Conda.psd1" -ErrorAction SilentlyContinue
# 或直接调用环境内解释器（最稳妥，无需激活）：
& "C:\Users\MemoryLeak\miniconda3\envs\graduation-design\python.exe" your_script.py
```

### CMD

```bat
call "C:\Users\MemoryLeak\miniconda3\Scripts\activate.bat" graduation-design
python your_script.py
```

> **禁止**：不要为图方便把 Conda 写入系统 PATH，也不要执行 `conda init` 修改全局 shell 配置（本次搭建未做任何此类修改）。

---

## 5. 依赖清单与版本依据

### 5.1 已安装（核心 + 训练栈）

| 包 | 版本 | 用途 | 依据 |
|---|---|---|---|
| python | 3.11 | 解释器 | 任务默认要求，全依赖链验证通过 |
| numpy | 1.26.4 | 数值计算 | 与 `requirements-common.txt` 一致；必须 <2.0（见 5.2） |
| pandas | 2.2.3 | CSV/DataFrame 处理 | 根目录数据集 README 示例与 `scripts/` 中 4 处 import |
| scipy | 1.15.3 | 统计检验 / bootstrap | `benchmark_profile/requirements.txt` |
| scikit-learn | 1.5.2 | 指标、切分、排序基线 | `seqeval` 的必需依赖，同时服务于匹配/排序实验 |
| matplotlib | 3.10.0 | 图表 | 8 个脚本 import；`benchmark_profile` 固定版本 |
| Pillow | 11.1.0 | 图像处理 | `reproduction/` 绘图脚本；`benchmark_profile` 固定版本 |
| reportlab | 4.2.5 | PDF 报告/图表输出 | `reproduction/` 中 16 处 import |
| PyMuPDF | 1.24.14 | PDF 文本提取（简历解析） | 代码中 `import fitz` |
| jieba | 0.42.1 | 中文分词 | `requirements-repro.txt` 固定 `>=0.42.1` |
| PyYAML | 6.0.2 | 配置/清单解析 | 代码中 `import yaml` |
| requests | 2.32.3 | HTTP 请求 | `requirements-common.txt` 固定版本 |
| tqdm | 4.67.1 | 进度条 | transformers/peft 的必需依赖 |
| huggingface_hub | 0.26.2 | 模型/数据集下载 | 代码中 2 处 import；满足 transformers 4.40.2 的 `<1.0` 约束 |
| tokenizers | 0.19.1 | 分词器 | transformers 4.40.2 要求 `>=0.19,<0.20` |
| transformers | 4.40.2 | 编码器模型 / Trainer | `requirements-common.txt` 固定版本（见 5.2） |
| safetensors | 0.4.3 | 权重格式 | `requirements-common.txt` 固定版本 |
| sentencepiece | 0.2.0 | 子词分词 | `requirements-common.txt` 固定版本 |
| torch | 2.1.2+cu121 | 训练/推理 | `requirements-train.txt` 固定 `torch==2.1.2`；CUDA 构建来自 PyTorch 官方索引 |
| pytorch-crf | 0.7.2 | CRF 序列解码 | `requirements-train.txt` 固定版本（导入名 `torchcrf`） |
| seqeval | 1.2.2 | 序列标注 F1 | 代码中 2 处 import |
| peft | 0.10.0 | LoRA 微调 | 代码中 4 处 import |

### 5.2 版本冲突与取舍记录

| 冲突 | 处理 | 理由 |
|---|---|---|
| `requirements-train.txt` numpy==1.26.3 vs `requirements-common.txt` numpy==1.26.4 vs `benchmark_profile` numpy==2.1.3 | 统一为 **numpy 1.26.4** | torch 2.1.x 以 numpy 1.x ABI 编译，在 numpy 2.x 下无法运行；1.26.3→1.26.4 为补丁级差异 |
| `requirements-train.txt` transformers==4.37.1 vs `requirements-common.txt` transformers==4.40.2 | 统一为 **transformers 4.40.2** | 训练配方注明“较新的 transformers 仍可运行，仅不承诺与冻结结果逐位一致”；4.40.2 同时满足外部复现子流程的精确固定 |
| `requirements-train.txt` 中 `pytorch-crf` vs 代码 `import torchcrf` | 无需改动 | `pytorch-crf` 包的导入名就是 `torchcrf`，两者是同一依赖 |
| `benchmark_profile` 的 numpy 2.1.3 | 放弃，沿用 1.26.4 | 与 torch 2.1.2 冲突；scipy 1.15.3 / matplotlib 3.10.0 / Pillow 11.1.0 在 numpy 1.26 下同样可用 |

**复现精度提示**：如需对 `JobBERT 3M 0.4331` 做逐位复现，须另建环境并严格使用
`requirements-train.txt` 的 torch==2.1.2 + transformers==4.37.1 + numpy==1.26.3。

### 5.3 未安装的可选依赖（按需安装）

| 包 | 何时需要 | 安装命令 |
|---|---|---|
| fastapi / uvicorn / python-multipart | 后端服务接口（当前代码零引用） | `pip install fastapi uvicorn python-multipart` |
| sentence-transformers | 需要现成的句向量/语义相似度模型时 | `pip install sentence-transformers` |
| python-docx | 解析 DOCX 简历（当前代码零引用） | `pip install python-docx` |
| datasets | 用 `datasets` 库流式读取 HF 数据集（当前仅用 huggingface_hub 下载） | `pip install datasets` |
| accelerate | 多卡/混合精度训练 | `pip install accelerate` |
| python-dotenv | 希望自动加载 `.env` 文件（当前脚本只读 `os.environ`） | `pip install python-dotenv` |
| openai / 裁剪后的 LLM SDK | 调用 LLM API 做标注或岗位画像增强 | 见 `chinese-skillspan-benchmark` 各脚本头部说明 |
| LLaMA-Factory | Qwen/LLaMA 系列监督微调（`llamafactory_train_allow_local_ckpt.py`） | 按其官方文档安装，建议单独环境 |
| spacy_pkuseg | 备选中文分词引擎（仅 1 个评测脚本使用） | `pip install spacy-pkuseg` |

---

## 6. 验证环境

```powershell
$py = "C:\Users\MemoryLeak\miniconda3\envs\graduation-design\python.exe"

# 6.1 版本与路径
& $py --version
& $py -c "import sys; print(sys.executable)"

# 6.2 关键包导入自检
& $py -c "import numpy,pandas,scipy,sklearn,matplotlib,PIL,reportlab,fitz,jieba,yaml,requests,tqdm;print('base stack ok')"

# 6.3 Hugging Face / Transformers 组
& $py -c "import torch,transformers,tokenizers,huggingface_hub,safetensors,sentencepiece,torchcrf,seqeval,peft;print('torch',torch.__version__,'| transformers',transformers.__version__,'| cuda',torch.cuda.is_available(),torch.cuda.get_device_name(0) if torch.cuda.is_available() else '-')"

# 6.4 依赖一致性
& $py -m pip check

# 6.5 数据集可读性（只读样例）
& $py -c "import pandas as pd; d=pd.read_csv(r'D:\desktop\毕业设计\data\raw\job-resume-matching\matches.csv',nrows=5); print(d.shape); print(d.columns.tolist())"
```

---

## 7. 数据集清单（只读审计，未做任何修改）

> **路径说明（2026-10-28 工程化整理）**：原始数据集已统一迁入 `data\raw\`，下表「文件」列为**数据集内部相对路径**，
> 实际位置前缀见 `docs/datasets/README.md`。迁移仅做同卷目录移动，字节内容 SHA-256 逐文件一致，字段与行数未变。

| 文件（相对 `data\raw\`） | 大小 | 编码 | 字段数 | 说明 |
|---|---:|---|---:|---|
| `job-resume-matching\cv.csv` | 185.0 MB | UTF-8（无 BOM） | 11 | 9,544 条候选人简历画像，含 768 维文本向量 |
| `job-resume-matching\job.csv` | 31.4 MB | UTF-8（无 BOM） | 10 | 1,167 条岗位描述与要求，含 768 维文本向量 |
| `job-resume-matching\matches.csv` | 18.8 MB | UTF-8（无 BOM） | 13 | 122,560 条人岗兼容性记录（6 项打分 + 排序标签） |
| `other\all_df.csv\all_df.csv` | 23.8 MB | **UTF-8 带 BOM** | 8 | 中文招聘岗位表（岗位、公司、薪资、经验、学历、地址、类型、风险概率） |
| `job-education\default\train\19w_0701.csv` | 239.0 MB | UTF-8（无 BOM） | 9 | 岗位→学历抽取训练集，约 19 万条（system/user/assistant 对话格式） |
| `job-education\default\validation\4w_0708.csv` | 57.7 MB | UTF-8（无 BOM） | 9 | 验证集，约 4 万条 |
| `job-education\default\test\2w_0716.csv` | 28.9 MB | UTF-8（无 BOM） | 9 | 测试集，约 2 万条 |
| `job-education\annotated\2w_0716_eval.csv` | 28.9 MB | UTF-8（无 BOM） | 12 | 人工标注评测集（含新旧模型结果对比列） |
| `chinese-skillspan-benchmark/`（项目根目录，**未迁移**） | — | UTF-8 | — | 独立 Git 仓库：中文岗位技能跨度抽取基准（数据、脚本、评测器、论文复现） |

**读取注意事项**

1. 所有 CSV 均为 UTF-8；只有 `other/all_df.csv/all_df.csv` 带 BOM，读取时建议统一：
   ```python
   pd.read_csv(path, encoding="utf-8-sig")   # 兼容有无 BOM 两种情况
   ```
2. `cv.csv` / `job.csv` 的 `embedding` 列是字符串形式的 768 维向量，需 `ast.literal_eval` + `np.array(..., dtype=np.float32)` 还原。
3. `job-education` 三个 CSV 为多行文本字段（岗位描述含换行），**不要用文本编辑器打开**，请用 pandas 读取。
4. 原始数据集均为只读资产：本次审计未修改、未重新下载任何数据文件。（2026-10-28 工程化整理另做了一次**同卷目录移动**，仅变更存放位置、不改字节内容，见 `reports/workspace-reorganization.md`。）

---

## 8. 导出与复现

```powershell
# 导出当前环境（供他人复现）
& "C:\Users\MemoryLeak\miniconda3\envs\graduation-design\python.exe" -m pip freeze > requirements.lock.txt

# 生成新的 environment.yml
& "C:\Users\MemoryLeak\miniconda3\Scripts\conda.exe" env export -n graduation-design --no-builds > environment.lock.yml
```

> `environment.yml`（项目根目录）是**人工维护的主定义**，只保留直接依赖；`requirements.lock.txt` 用于精确锁定，二者分工不同，不要互相覆盖。

---

## 9. 故障排查

| 现象 | 原因 | 解决办法 |
|---|---|---|
| `conda : 无法将"conda"项识别为…` | Conda 未加入 PATH | 使用完整路径 `C:\Users\MemoryLeak\miniconda3\Scripts\conda.exe`，或 `condabin\conda.bat`；不要改全局 PATH |
| `conda run` 提示 `Could Not Find C:\WINDOWS\TEMP\....bat` | Windows 临时文件回收的无害告警 | 可忽略，不影响执行结果 |
| 中文/空格路径导致脚本报错 | 旧式路径拼接未加引号 | PowerShell 中一律写 `& $py "D:\desktop\毕业设计\xxx.py"`；Python 内用 `pathlib.Path` |
| pip 报 `SSL: CERTIFICATE_VERIFY_FAILED` | 企业代理/自签证书 | `pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org ...`，或配置 `PIP_CERT` |
| pip 报 `ReadTimeoutError` / `ConnectionError` | 网络波动或镜像不可达 | 重试；或临时切换官方源 `--index-url https://pypi.org/simple`；PyTorch 必须走 `download.pytorch.org` |
| 下载 CUDA 版 torch 极慢或停滞（本项目实测 350–500 KB/s，196 MB 处连接中断） | 本机到 `download.pytorch.org` 的链路带宽低、长连接易被代理中断 | 按 3.3 使用国内镜像 + `curl -C -` 断点续传；下载期间不要同时跑其他大流量任务 |
| `A module that is compiled using NumPy 1.x cannot be run in NumPy 2.0.x` | 误装了 numpy 2.x | `pip install "numpy==1.26.4"`（torch 2.1.x 不支持 numpy 2） |
| `torch.cuda.is_available() == False` | 驱动过旧或安装了 CPU 版 torch | 确认驱动 ≥ 530；用 `pip install torch==2.1.2 --index-url https://download.pytorch.org/whl/cu121 --force-reinstall` 重装 CUDA 版 |
| CUDA out of memory（4 GB 显存） | 批量过大/模型过大 | 减小 `per_device_train_batch_size`、启用梯度累积与 `fp16`，或使用 CPU/较小编码器 |
| `import torchcrf` 报错但 `pytorch-crf` 已装 | 安装了同名的错误包 | 确认装的是 `pytorch-crf==0.7.2`（PyPI），不是 `torchcrf` 或 `pytorch_crf` 其他来源 |
| 想离线使用 HF 模型 | 反复联网校验 | 先 `huggingface-cli download ...` 预下载，再设 `HF_HUB_OFFLINE=1` |

---

## 10. 维护约定

1. **不修改** `base`、`3.10`、`3.12` 等既有环境；新增包一律装入 `graduation-design`。
2. 新增依赖时：先写入 `environment.yml` 的对应分组，再安装，最后更新本文件的 5.1/5.3 表格。
3. 不使用 `--no-deps` 绕过依赖冲突；冲突按 5.2 的方式求解兼容组合并记录理由。
4. 大型训练框架（CUDA 版 PyTorch 等）安装前须确认磁盘与网络条件（CUDA 版约 2.5 GB）。
5. 数据集目录 `data\raw\`（含 `job-resume-matching\`、`job-education\`、`other\all_df.csv\`）保持只读；后续数据处理产物一律写入 `data\interim\` 或 `data\processed\`，切勿回写原始数据。

---

## 11. 本次搭建验证记录（2026-10-28）

```
Python            3.11.18   C:\Users\MemoryLeak\miniconda3\envs\graduation-design\python.exe
torch             2.1.2+cu121   cuda_available=True   device=NVIDIA GeForce RTX 2050
transformers      4.40.2    tokenizers 0.19.1    huggingface_hub 0.26.2
numpy             1.26.4    pandas 2.2.3    scipy 1.15.3    scikit-learn 1.5.2
matplotlib        3.10.0    Pillow 11.1.0    reportlab 4.2.5    PyMuPDF 1.24.14
jieba             0.42.1    PyYAML 6.0.2    requests 2.32.3    tqdm 4.67.1
pytorch-crf       0.7.2     seqeval 1.2.2    peft 0.10.0
pip check         No broken requirements found.
数据集冒烟测试     matches (200,13) / job (5,10) / all_df (5,8) / embedding dim (768,) 均可读取
```

**本次过程中的实际问题与处置**

| 问题 | 处置 |
|---|---|
| `conda` 不在 PowerShell PATH | 全程使用 `C:\Users\MemoryLeak\miniconda3\Scripts\conda.exe` 完整路径，未改全局 PATH |
| 官方 `download.pytorch.org` 下载停滞（196 MB 处 0 速率） | 改用阿里云镜像 + `curl -C -` 断点续传，2,473,957,547 字节下载完整 |
| 4 路并行分块下载实测聚合 583 KB/s，与单路相当 | 判定瓶颈为总带宽而非单连接限速，放弃并行方案 |
| 早期一次并发安装触发 `WinError 32`（PIL 文件被占用），且被 `pytorch-crf` 连带安装了 CPU 版 `torch 2.14.1` | 用 CUDA wheel 覆盖安装 `torch 2.1.2+cu121`，`--force-reinstall` 修复 Pillow，最终 `pip check` 通过 |

