# 毕业设计 Conda 环境验收报告

- **验收日期**：2026-10-28
- **项目根目录**：`D:\desktop\毕业设计`
- **Conda 环境**：`graduation-design`
- **验收方式**：全部项目均实际执行命令与测试代码后取结果，不引用历史日志
- **结论**：**B. 有条件通过：基本可用，但存在非阻断性问题**

> 本次验收未修改/升级/降级任何依赖，未删除或重建环境，未改动原始 CSV、训练数据与模型权重，未重新下载数据集，未下载任何模型权重。

---

## 1. 环境摘要

| 项目 | 实测值 |
|---|---|
| Conda 环境实际路径 | `C:\Users\MemoryLeak\miniconda3\envs\graduation-design` |
| Conda 安装路径 / 版本 | `C:\Users\MemoryLeak\miniconda3` / 24.9.2 |
| Python | 3.11.18（64 位，`sys.executable` 指向上述环境） |
| pip | 26.2.2（同一环境 site-packages） |
| PyTorch | **2.1.2+cu121** |
| CUDA Runtime（`torch.version.cuda`） | **12.1** |
| cuDNN | 8.8.1（8801），可用 |
| GPU 名称 | **NVIDIA GeForce RTX 2050**，计算能力 (8, 6)，1 块设备 |
| GPU 显存 | 4.00 GB（`get_device_properties` 实测） |
| 驱动 | 581.80 |
| NumPy | **1.26.4** |
| 其他关键版本 | pandas 2.2.3 / scipy 1.15.3 / scikit-learn 1.5.2 / transformers 4.40.2 / tokenizers 0.19.1 / huggingface_hub 0.26.2 / peft 0.10.0 / pytorch-crf 0.7.2 / seqeval 1.2.2 |

---

## 2. 验收结果表

| # | 测试名称 | 状态 | 实际证据 | 异常信息 | 改进建议 |
|---|---|---|---|---|---|
| 1 | 环境隔离（`test_conda.py`，6 项） | **PASS** | `sys.executable`/`sys.prefix`/`sys.base_prefix`/`CONDA_PREFIX` 全部等于环境根；`CONDA_DEFAULT_ENV=graduation-design`；pip 26.2.2 属同一 site-packages；`sys.path` 无全局 site-packages | 无 | 保持用 `conda run -n graduation-design` 执行脚本 |
| 2 | 依赖完整性（`pip check`） | **PASS** | `No broken requirements found.`，退出码 0 | 无 | — |
| 3 | CUDA 初始化与设备识别（`test_torch_cuda.py`，10 项） | **PASS** | `torch.cuda.init()` 成功；识别 RTX 2050 / capability (8,6) / 4.00GB；cuDNN 8801 可用；无 DLL 加载错误、无驱动兼容告警 | 无 | — |
| 4 | GPU 真实计算（同上） | **PASS** | 512×512 矩阵乘 0.095s、1024×1024 矩阵乘 0.002s；与 CPU 结果最大偏差 6.5e-05 / 1.6e-04（float32 正常误差）；无 NaN/Inf；显存峰值 11.1 / 20.1 MB | 无 | — |
| 5 | GPU 训练（`test_gpu_training.py`，9 项） | **PASS** | 见第 3 节 | 无 | — |
| 6 | NumPy/PyTorch ABI 兼容（`test_numpy_compat.py`，7 项） | **PASS** | `torch.tensor(numpy)`、`torch.from_numpy`、`tensor.numpy()`、NumPy→CUDA→NumPy 全部正确；6 种 dtype 双向一致；未出现 `_ARRAY_API not found` / `Numpy is not available` | 无 | 维持 numpy 1.26.x，勿升级到 2.x |
| 7 | AI/NLP 依赖（`test_nlp_dependencies.py`，33 项） | **PASS** | 17 个组件 import + 功能测试通过（tokenizers 编码、BertModel 随机初始化前向、safetensors 读写、sklearn 训练 accuracy 0.967、seqeval f1 1.00、torchcrf CRF、jieba 分词、PyYAML 解析） | 首次运行 2 项**假 FAIL**：测试脚本用分发包名 `scikit-learn`/`PyYAML` 去 import（导入名应为 `sklearn`/`yaml`）。修正脚本后复测 33 项全通过。属**测试代码缺陷**，非环境故障 | 报告中保留该记录；后续新增依赖时注意分发名≠导入名 |
| 8 | 数据集验收（`test_dataset_loading.py`，25 项） | **PASS** | 见第 4 节 | 无 | — |
| 9 | 端到端训练链路（`test_e2e_pipeline.py`，6 项） | **PASS** | 真实 `matches.csv` 512 行 → 特征/标签转换 → CUDA → MLP 前向 → CrossEntropy → backward → AdamW 20 步，Loss 1.037560 → 0.652925 | 无 | 属基础设施冒烟，非业务模型验收 |
| 10 | 环境可复现性（`test_reproducibility.py`，8 项） | **PASS（1 项 WARN）** | `environment.yml` 声明 python=3.11、`torch==2.1.2+cu121`、`--extra-index-url` 官方索引；无本机绝对路径；21 个直接依赖声明版本与实装**逐项一致** | **WARN**：子项目冻结配方与统一环境有 4 处差异（numpy 1.26.3 / 2.1.3 vs 1.26.4；torch 2.1.2 vs 2.1.2+cu121；transformers 4.37.1 vs 4.40.2） | 差异与取舍理由已写入 `docs/environment-setup.md`；如需逐位复现 JobBERT 3M 0.4331，另建严格配方环境 |

**核心项判定**：环境隔离 ✅ / 依赖完整性 ✅ / CUDA 初始化 ✅ / GPU 计算 ✅ / GPU 训练 ✅ / NumPy 兼容 ✅ / 数据集 ✅ / NLP 组件 ✅ / 环境可复现 ✅ —— 9 项全部通过，**无核心 FAIL**。

---

## 3. GPU 训练实测结果

| 项目 | 实测值 |
|---|---|
| 实际运行设备 | `cuda:0` — NVIDIA GeForce RTX 2050 |
| 模型 | MLP：Linear(32→64) + ReLU + Linear(64→64) + ReLU + Linear(64→4) |
| 优化器 / 损失 | AdamW(lr=1e-3) / CrossEntropyLoss |
| 数据 | batch=64、32 维模拟特征（`torch.manual_seed(42)`），模型与数据均在 CUDA |
| 训练步数 | **40 步**（前向 → loss → backward → step → synchronize） |
| Loss 变化 | **1.389322 → 0.725761**（最小 0.725761 / 最大 1.389322；前 5 步均值 1.362062，后 5 步均值 0.773011） |
| 单步单调性 | 本次 40 步严格单调下降（作为参考项记录，不作为判定依据） |
| 梯度是否正常 | ✅ 所有步骤所有参数梯度均为有限值 |
| 参数是否更新 | ✅ 首个参数张量最大变化 4.640381e-02，训练后参数无 NaN/Inf |
| CUDA 同步 | ✅ 每步 `torch.cuda.synchronize()` 均成功 |
| 显存峰值 | **16.41 MB** |
| 总耗时 | **0.313 s**（40 步） |

补充：用真实数据 `matches.csv` 前 512 行做的端到端链路（读取→特征→CUDA→训练 20 步）Loss 1.037560 → 0.652925，耗时 0.141 s，显存峰值 16.47 MB，训练后训练集准确率 0.674（**仅链路验证，不作为模型指标**）。

---

## 4. 数据集验收结果

| 文件 | 大小 | 编码 | 字段/行数 | 关键字段 | 可用性 |
|---|---:|---|---|---|---|
| `cv.csv` | 185.0 MB | UTF-8 无 BOM | 11 列 / **9,544 行** | `candidate_id`、`resume_text`、`clean_skills`、`education_text`、`experience_text`、`years_experience`、`inferred_category`、`embedding` | ✅ 可用于候选人画像与向量检索 |
| `job.csv` | 31.4 MB | UTF-8 无 BOM | 10 列 / **1,167 行** | `job_id`、`job_title`、`category`、`job_description`、`clean_skills`、`education_text`、`years_required`、`embedding` | ✅ 可用于岗位画像建模 |
| `matches.csv` | 18.8 MB | UTF-8 无 BOM | 13 列 / **122,560 行** | `candidate_id`、`job_id`、`label_strength`、6 项打分、`candidate_rank` | ✅ 可用于匹配/排序建模（见下方限制） |
| `all_df.csv/all_df.csv` | 23.8 MB | **UTF-8 带 BOM** | 8 列 | `job_name`、`company_name`、`job_salary`、`work_experience`、`educational_requirements`、`company_address`、`job_type`、`scam_probability` | ✅ 中文岗位-学历-经验结构化表 |
| `job-education/default/train/19w_0701.csv` | 239.0 MB | UTF-8 无 BOM | 9 列 / ~19 万 | `job_id`、`system`、`user`、`assistant` | ✅ 岗位→学历抽取训练集 |
| `job-education/default/validation/4w_0708.csv` | 57.7 MB | UTF-8 无 BOM | 9 列 / ~4 万 | 同上 | ✅ 验证集 |
| `job-education/default/test/2w_0716.csv` | 28.9 MB | UTF-8 无 BOM | 9 列 / ~2 万 | 同上 | ✅ 测试集 |
| `job-education/annotated/2w_0716_eval.csv` | 28.9 MB | UTF-8 无 BOM | 12 列 | `job_id`、`user`、`assistant`、人工正确结果、新旧模型判定列 | ✅ 人工标注评测集 |

**实测数据质量**

- 三个主表前 2000 行**零空值**，表头字段与 README 数据字典**完全一致**。
- **关联字段完整可用**：`matches.csv` 中 9,532 个 `candidate_id` 100% 命中 `cv.csv`；1,164 个 `job_id` 100% 命中 `job.csv`。
- **真实匹配标签存在**：`label_strength` = medium_positive 70,636 / weak_positive 51,150 / strong_positive 774（3 档），另有 6 维连续打分特征。
- `embedding` 列可解析为 **768 维 float32** 向量。
- `job-education` 三个切分的 `user`/`assistant` 无空值、文本长度正常，训练/验证/测试切分齐备。

**分级结论（三者不同）**

1. **文件读取成功**：8 个数据文件全部可读取 ✅
2. **数据结构有效**：编码、表头、字段类型、关联键全部符合数据字典 ✅
3. **可用于模型训练**：可用于画像抽取、语义匹配与排序建模 ✅，但 `matches.csv` **只包含正样本记录**（README 明确声明），做二分类或成对排序时**必须自行采样负例**，并按 `candidate_id` 切分训练/验证/测试（README 推荐），否则会高估性能。

**关于 `nonameee12233/job-resume-matching`**：本地根目录为 Hugging Face 数据集快照（README 为 HF 数据集卡片、`.gitattributes` 为 LFS 规则、`.cache/huggingface/download` 下存在 `cv.csv`/`job.csv`/`matches.csv` 下载元数据）。本地元数据文件仅含 etag/sha/时间戳，**不含 repo id 字符串**，无法从本地文件自证仓库名；但文件清单与字段结构与该数据集 README 数据字典完全一致，判定为该数据集的本地快照（**未重新下载、未联网核对**）。

---

## 5. 风险分析

**必须立即修复**：无（核心验收项 0 FAIL）。

**可暂缓处理**

| 风险 | 影响 | 建议 |
|---|---|---|
| 子项目冻结配方与统一环境存在版本差异（numpy 1.26.3/2.1.3、torch 2.1.2、transformers 4.37.1） | 逐位复现 `JobBERT 3M 0.4331` 时结果可能不一致 | 已在 `docs/environment-setup.md` 记录取舍理由；需要逐位复现时另建严格配方环境 |
| `accelerate 1.15.0` 作为 peft 传递依赖被安装，但未在 `environment.yml` 显式声明 | 复现时版本可能漂移 | 补记到 `environment.yml` 或确认无用后卸载 |
| 无 `requirements.lock.txt` 精确锁文件 | 换机复现时传递依赖可能变化 | 版本稳定后 `pip freeze > requirements.lock.txt` |

**未来训练阶段才需要解决**

| 风险 | 影响 | 建议 |
|---|---|---|
| RTX 2050 仅 4 GB 显存 | 训练 RoBERTa-wwm-ext-large 级别模型会 OOM | 小 batch + 梯度累积 + fp16，或改用较小编码器 |
| `matches.csv` 仅正样本 | 无法直接做二分类/成对排序 | 按 `candidate_id` 切分并采样负例 |
| sentence-transformers / datasets / fastapi / python-docx 未安装 | 后续业务需要时缺失 | 按实际需求再装，不要预先堆积依赖 |
| Hugging Face 权重下载依赖网络 | 训练时可能中断 | 预先缓存权重，必要时 `HF_HUB_OFFLINE=1` |

---

## 6. 最终验收结论

### **B. 有条件通过：基本可用，但存在非阻断性问题**

**理由**

1. 9 项核心验收项（环境隔离、依赖完整性、CUDA 初始化、GPU 计算、GPU 训练、NumPy 兼容、数据集、NLP 组件、环境可复现）**全部 PASS，0 项 FAIL**，且每项均有实际运行证据（退出码、数值输出、显存/耗时指标）。
2. GPU 训练为**真实计算**：模型与数据在 CUDA 上完成 40 步前向/反向/参数更新，梯度有限、参数确有更新（Δmax 4.64e-02）、Loss 1.389322→0.725761、CUDA 同步成功，不满足"仅 `is_available()` 即通过"的低标准。
3. NumPy 1.26.4 与 torch 2.1.2+cu121 双向转换全部正确，**未出现任何 ABI 报错**，重点验收项通过。
4. 未定为"完全通过（A）"的原因：存在 3 项**非阻断性**问题——① 子项目冻结配方与统一环境的版本差异（WARN）；② `accelerate` 未在 `environment.yml` 显式声明；③ 4 GB 显存与纯正样本数据对后续训练构成约束。这些不影响当前开发，但需在训练阶段处理。

**结论**：环境可**立即进入毕设模型开发阶段**（岗位画像抽取、语义匹配、排序建模）；进入正式训练前请先处理第 5 节"未来训练阶段"条目。

---

## 7. 测试代码与产物清单

```
D:\desktop\毕业设计\
├── tests\environment\
│   ├── test_conda.py               环境隔离与解释器一致性（6 项）
│   ├── test_torch_cuda.py          PyTorch/CUDA 实测 + GPU 矩阵运算（10 项）
│   ├── test_gpu_training.py        GPU 真实训练冒烟（9 项）
│   ├── test_numpy_compat.py        NumPy/PyTorch ABI 兼容（7 项）
│   ├── test_nlp_dependencies.py    AI/NLP 依赖与功能测试（33 项）
│   ├── test_dataset_loading.py     本地数据集验收（25 项）
│   ├── test_e2e_pipeline.py        端到端训练链路（真实数据小样本，6 项）
│   └── test_reproducibility.py     环境可复现性（8 项）
└── reports\
    ├── environment-acceptance.md   本报告
    └── environment-acceptance.json 结构化结果（含全部实测数值）
```

**复跑方式**

```powershell
$conda = "C:\Users\MemoryLeak\miniconda3\Scripts\conda.exe"
foreach ($t in @("test_conda","test_torch_cuda","test_gpu_training","test_numpy_compat",
                 "test_nlp_dependencies","test_dataset_loading","test_e2e_pipeline",
                 "test_reproducibility")) {
    Write-Output "===== $t ====="
    & $conda run -n graduation-design --no-capture-output python "D:\desktop\毕业设计\tests\environment\$t.py"
    Write-Output "EXIT=$LASTEXITCODE"
}
```

测试代码与正式业务代码分离，全部为只读验收脚本（仅向系统临时目录写入一次 safetensors 往返测试文件并已删除）。
