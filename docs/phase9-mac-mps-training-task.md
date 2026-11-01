# Role：高级机器学习工程师 + Apple Silicon GPU 性能工程师 + 毕业设计实验负责人

你现在接管项目 `job-matching-graduation-design` 在 macOS Apple Silicon 设备上的机器学习训练工作。

项目已从 Windows 训练机复制到当前 Mac。本次任务不是写一份训练计划，而是完成一次真正执行的 **Phase 9：Apple Silicon MPS 加速、高强度训练、模型优化与科研实验验收**。

必须在当前 Mac 上实际执行命令、修复兼容性、运行真实训练、生成模型与实验数据，并提供证据。

## 一、最高优先级任务

1. 识别当前 Mac 的实际 Apple 芯片、GPU 核心数、64GB 统一内存和 macOS 环境。
2. 将现有 PyTorch 模型完整适配 `torch.device("mps")`。
3. 证明前向计算、反向传播、梯度更新真实发生在 Apple GPU，而非静默使用 CPU。
4. 对现有 MLP、RankNet、CharCNN 实施完整训练。
5. 利用实际可用的 GPU 资源，执行分级压力测试、批量实验、超参数搜索和多随机种子实验。
6. 与现有 Windows / RTX 2050 历史模型进行公平对比。
7. 输出经过严格验证的新模型、统计指标、性能曲线、消融结果与论文实验材料。
8. 确保原有数据集、研究协议、模型和服务均不被破坏。

除非发现无法自行解决的权限、缺失数据或硬件阻断，否则不要停留在建议阶段，不要以“脚本已经准备好”作为完成任务的理由。

## 二、先理解仓库，不允许盲目重构

重点审计以下真实文件：

```text
src/job_matching/training/trainer.py
src/job_matching/education/trainer.py
scripts/model_training/train.py
scripts/model_training/run_all.py
scripts/model_training/evaluate.py
scripts/model_training/compare_models.py
scripts/model_training/verify_models.py
scripts/education_training/train.py
scripts/education_training/run_all.py
scripts/education_training/verify_models.py
tests/environment/test_gpu_training.py
configs/training/common.yaml
configs/training/mlp.yaml
configs/training/ranknet.yaml
configs/training/education_neural.yaml
configs/matching_splits.yaml
configs/phase7-preregistered-protocol-v1.json
docs/evaluation-protocol.md
docs/datasets/README.md
```

检查已有模型目录、训练记录、数据完整性、特征白名单、数据切分方案、Checkpoint 机制和评估体系。

保持原有 API、模型推理协议、manifest 结构和历史训练产物的兼容性。

所有新实验使用独立 Run ID，禁止覆盖历史模型。

## 三、P0：Apple Silicon 环境体检

实际运行并记录：

```bash
uname -m
sw_vers
sysctl -n machdep.cpu.brand_string
system_profiler SPHardwareDataType
system_profiler SPDisplaysDataType
sysctl -n hw.memsize
xcode-select -p
python3 --version
```

通过 Python 检查：

```python
import platform
import torch

print("arch:", platform.machine())
print("torch:", torch.__version__)
print("mps built:", torch.backends.mps.is_built())
print("mps available:", torch.backends.mps.is_available())
print("cuda available:", torch.cuda.is_available())
```

要求：

- 原生 ARM64 Python，不得在 Rosetta x86_64 环境里冒充原生运行。
- 为 macOS 创建独立 `.venv`，不能直接依赖 Windows 虚拟环境。
- 核对依赖版本兼容性，优先使用兼容的稳定 PyTorch。
- 不得擅自修改系统级 Python、macOS 设置或安装未经验证的 GPU 加速库。
- 检查可用磁盘容量、交换内存、内存压力。
- 生成环境快照，记录 CPU/GPU/OS/PyTorch/NumPy/BLAS 版本及 Git SHA。

如果 MPS 不可用，定位原因并尝试安全修复。无法解决时明确标记 `MPS_BLOCKED`，不得把 CPU 结果伪装成 GPU 结果。

## 四、P1：修复现有设备选择缺陷

目前 `resolve_device()` 主要识别 CUDA，Mac 会落到 CPU。学历 CharCNN 的设备选择也存在 Mac 兼容问题。

请建立统一设备选择策略：

```text
--device auto
--device mps
--device cuda
--device cpu
```

auto 优先级：

```text
CUDA（确实存在时）
  ↓
MPS（Apple Silicon）
  ↓
CPU
```

显式指定 `--device mps` 却无法使用时必须报错，不能悄悄改成 CPU。

修复所有必要的设备迁移、Tensor dtype、随机种子、同步、Checkpoint 和推理兼容问题。

特别检查：

- float64 / complex128 不兼容 MPS 的路径；
- NumPy → Tensor 转换；
- MPS 索引张量与数据张量设备一致性；
- `torch.mps.synchronize()` 同步计时；
- 模型参数与输入数据所在设备；
- CPU 加载 MPS 训练权重；
- MPS → CPU 跨设备评估；
- 不支持的算子是否发生 CPU fallback。

默认实验应检测 fallback，不允许静默混合执行。必要时可单独设置诊断实验，但必须显式标记 CPU fallback 并单独报告性能。

修复 `tests/environment/test_gpu_training.py`，使其支持 CUDA、MPS、CPU，并验证实际梯度、参数更新与设备归属。

新增 Mac MPS 测试，不得删除现有 CUDA 测试。

## 五、P2：训练基准测试与 GPU 压力测试

先做真实 workload benchmark，不直接把 64GB 内存全部占满。

按以下阶段执行：

### S0：正确性冒烟

- 在真实 MPS 上执行至少 50 次优化器更新。
- 检查 Loss、梯度、模型权重是否正常。
- 检查 NaN/Inf、设备失配、MPS 不支持算子。
- 与 CPU 推理结果比较，使用合理浮点容差。

### S1：CPU / MPS 公平基准

对 MLP、RankNet、CharCNN 使用相同数据、模型配置和随机种子分别测试。

记录：

- 数据加载时间；
- warmup 后的训练耗时；
- 每 epoch 耗时；
- samples/s 或 pairs/s；
- GPU/CPU 传输开销；
- 推理延迟；
- 加速比；
- 模型参数量；
- MPS 已分配内存与驱动内存（接口支持时）；
- 系统内存压力与 swap 使用量。

需要同步 GPU 后再测量耗时。每个基准重复至少 3 次，报告中位数与波动，不得使用单次最优值冒充稳定性能。

### S2：Batch Size 压力测试

针对适合 GPU 的模型逐级测试：

```text
128
256
512
1024
2048
4096
8192
```

RankNet 使用对应的 pair batch 配置。

超出模型有效样本规模的 batch 不应强制运行。按照吞吐、训练稳定性和内存压力选择最优 batch，而不是无条件选择最大值。

### S3：持续高负载训练

在设备稳定、训练结果有效且磁盘空间足够的前提下，安排最长约 2 小时的高强度实验预算。

通过真实模型训练、超参数试验和多种子重复利用 GPU，而不是运行无意义的随机矩阵死循环。

控制条件：

- 保持足够的系统可用内存，初始建议预留至少 12GB，并根据 macOS 内存压力动态调整；
- 不把统一内存总量误当成可独占的 GPU 显存；
- 不禁用 PyTorch MPS 内存保护；
- 不设置 `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0`；
- 若出现持续严重内存压力、异常 swap 增长、反复 OOM、thermal throttling 或系统不稳定，应自动降级或停止；
- GPU 密集实验默认串行，CPU 数据准备可根据资源情况适度并发。

生成完整 benchmark 原始数据。

## 六、P3：人岗匹配模型完整训练

保留四模型对照体系：

```text
Ridge Regression       CPU baseline
Gradient Boosting      CPU baseline
MLP                    MPS
RankNet                MPS
```

保留三个既有研究协议：

```text
candidate_cold
job_cold
double_cold
```

执行以下实验：

### A. 完整基线复现

四模型 × 三协议，验证数据和历史结果口径一致。

### B. MLP 深度搜索

在独立实验配置中研究：

```text
hidden layers:
[64, 32]
[128, 64]
[256, 128]
[512, 256]

learning rate:
1e-4
3e-4
1e-3
3e-3

weight decay:
0
1e-4
1e-3

dropout:
0.0
0.1
0.2
```

使用有预算限制的随机搜索或分阶段搜索，优先覆盖代表性组合，而非盲目运行完整笛卡尔积。

保留 Early Stopping、梯度裁剪、最优 Checkpoint 和合法的 Validation 选择。

### C. RankNet 深度搜索

研究：

- Pair batch size；
- 网络宽度；
- 学习率；
- 权重衰减；
- Dropout；
- 早停参数；
- 原协议允许范围内的 Pair Sampling 策略。

禁止把数据重复复制 N 次冒充新增样本。

禁止以测试集表现反向调整配对采样策略。

### D. 多随机种子稳定性

对 Validation 表现最好的候选配置实施至少 3 个独立随机种子实验。

报告均值、标准差、最佳/最差表现。

统计证据要与对应 query-level 排序协议保持一致。

## 七、P4：学历识别 CharCNN 强化训练

当前项目已有 TF-IDF 与 CharCNN 两类方案。

重点强化 CharCNN：

- Experiment A / B；
- slot / slot_title；
- none / slot_balanced / conflict_aware；
- 合法的 high-confidence 子集；
- 不同 Embedding Dimension；
- 不同 CNN Filters；
- 不同 Dropout；
- 学习率与 batch size；
- 多随机种子稳定性。

保留现有六标签任务定义与数据集口径。

输出：

```text
Micro-F1
Macro-F1
Per-label F1
Precision
Recall
Exact Match Ratio
Validation Loss
Confusion/Error Analysis
```

严格保持 `gold_holdout` 不参与训练、早停、阈值选择和模型选择。

模型与阈值确定后，只做规定的最终确认评估。

不要为了提高论文指标而改变金标准、补造标签或引入标签泄漏。

## 八、P5：模型对比与统计检验

按照现有评价协议，输出至少以下结果：

人岗匹配：

```text
NDCG@5
NDCG@10
Pairwise Accuracy
MAE
RMSE
Spearman
Kendall Tau-b
```

按原有协议可用性补充 query-level Bootstrap 95% CI 与配对差异分析。

必须清楚区分：

- 真实用户录用效果；
- 历史代理评分学习效果；
- 合成数据测试；
- 真实人工标注数据；
- Validation；
- Test；
- Human Gold Holdout。

本项目历史匹配训练目标属于代理偏好评分，不得把 NDCG 高分写成“真实招聘成功率高”。

所有超参数和模型方案先在合法 Validation 上锁定，再进行最终 Test 评估。

Phase 7 已预注册的协议不得被事后偷偷修改。新增模型试验统一登记为 exploratory experiment，不冒充预注册主结果。

## 九、P6：自动化实验系统

优先复用现有训练入口，按实际必要程度增加：

```text
scripts/mac_training/
    doctor.py
    mps_smoke.py
    benchmark.py
    run_experiments.py
    monitor_resources.py
    compare_results.py
    verify_runs.py
```

实际文件布局可以根据项目约定调整，不要为了凑目录而重复实现已有逻辑。

要求：

1. 使用唯一实验 Run ID；
2. 支持 `--device`、`--seed`、`--budget` 等必要参数；
3. 保存有效配置快照；
4. 支持意外中断后的安全恢复；
5. 保留失败日志，不隐瞒失败；
6. 支持终止信号下的合理 checkpoint 保存；
7. 实验输出使用追加和独立目录，不覆盖已有数据；
8. 防止两套流水线并发写入相同路径；
9. 实验结束可复现同等模型配置；
10. 在每个模型 manifest 中记录设备类型、版本与证据哈希。

历史模型产物不得删除、覆盖或静默替换为新模型。

## 十、P7：论文级实验材料

新报告写入：

```text
reports/mac-mps-training/<RUN_ID>/
```

必须生成：

```text
environment.json
device_validation.json
benchmark.csv
benchmark.json
experiments.csv
experiments.json
metrics_summary.json
resource_usage.csv
training_summary.md
model_comparison.md
ablation_report.md
reproducibility.md
failures.json
```

实际模型产物仍按项目约定使用独立模型目录与 manifest。

论文图表至少包含：

- CPU / MPS 训练吞吐对比；
- 不同 batch 的吞吐与显存占用曲线；
- Training Loss / Validation Loss；
- 模型对比图；
- 三个冷启动协议 NDCG 对比；
- 模型消融结果；
- 多随机种子误差棒。

所有图表必须由真实采集的数据生成，标注运行设备、样本规模和指标定义。

没有实际测到的指标写 `NOT_MEASURED`，不得估算成实际结果。

## 十一、P8：完成训练后的全链路验收

执行：

```text
MPS 真实训练验证
模型结果有限性验证
Checkpoint 加载验证
CPU 推理兼容验证
manifest 完整性验证
原有模型验证
相关训练单元测试
数据与切分一致性检查
核心回归测试
```

如本机具备条件，还应执行现有项目门禁，明确哪些测试未执行、为何未执行。

不允许改变测试断言来掩盖失败。

推荐模型必须证明其在现有服务推理环境中可以正常加载与预测，尤其要保证 MPS 训练出来的 PyTorch 权重能在 CPU 服务端正确使用。

不要直接更新生产默认模型指针。先提出可验证的候选推荐结果。

## 十二、任务执行纪律

本次任务的优先级：

**训练正确性 > 数据与实验纪律 > 模型泛化质量 > 有效吞吐 > GPU 利用率。**

必须实际执行，不得：

- 仅生成 TODO、Markdown 或空脚本；
- 只执行 Smoke 却报告 Full Training；
- 用 CPU 结果冒充 MPS；
- 使用 CUDA 假设处理 Apple GPU；
- 因 MPS 不可用而静默降级；
- 为了撑满 GPU 无意义扩大数据集；
- 修改 test / holdout 标签；
- 隐藏失败实验；
- 覆盖历史已验收模型；
- 为了提高分数破坏原有模型接口；
- 将大型 Checkpoint 自动提交 GitHub；
- 未经允许上传本地原始简历或个人信息。

不以 GPU 100% 利用率作为成功标准。对于现有小模型，如果 MPS 由于 kernel launch 或数据传输开销而比 CPU 慢，必须忠实记录，并把 CPU 保留为对应模型的推荐执行设备。

不要假设所有算法都可以通过 MPS 加速。

## 十三、立即开始实际工作

按照以下顺序直接行动：

```text
Step 1 识别 Mac 芯片、内存、运行环境
Step 2 检查数据集、原模型和 Git 状态
Step 3 建立 macOS ARM64 独立运行环境
Step 4 修复 MPS 设备选择与兼容问题
Step 5 执行真实 GPU 梯度与模型测试
Step 6 执行 CPU/MPS Benchmark
Step 7 搜索合理 Batch / Epoch / 超参数
Step 8 执行多协议完整模型训练
Step 9 执行多种子稳定性与消融实验
Step 10 完成最终评估与模型对比
Step 11 验证跨设备推理与既有回归
Step 12 生成实验报告及最终验收结论
```

在执行过程中，持续输出真实命令、当前步骤、完成实验数量、MPS 状态、有效吞吐以及发生的错误。

长时间训练应确保日志持续落盘和 checkpoint 安全保存。

**最终回答必须包含：**

1. 实际 Mac 芯片与 GPU 规格；
2. MPS 是否真实可用；
3. 原有设备兼容问题的修复内容；
4. 实际运行的命令；
5. 每个模型的实际训练设备、耗时与参数；
6. 新旧模型的公平指标对比；
7. CPU/MPS 实测加速比；
8. 最佳模型选择及依据；
9. 实际模型产物和报告路径；
10. 训练失败、跳过项与未完成项；
11. 可复现命令；
12. 最终验收评级。

验收评级：

- A：完整训练、模型对比、MPS 证据、跨设备验证全部通过。
- B：核心训练和验证完成，部分实验受资源预算限制。
- C：MPS 基础可用，但完整实验尚未执行。
- D：环境阻断或训练失败。

**现在从读取真实仓库与环境体检开始，随后立即进行 MPS 适配和训练。不要只给计划，尽可能在本次执行中完成实际训练。**
