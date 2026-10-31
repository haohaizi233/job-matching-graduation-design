# 15 education 模型决策层一致性与 label flip 统计

- 证据：`reports/phase4-3b/15-education-decision-consistency.json`
- 提交：`d7babaa16da2`　运行目录数：16　live 复现：**RUN**（每 split 上限 2000 条）
- 口径：决策层一致性与 label flip 统计；不评价学历抽取精度，不使用任何人工 Gold 结论（H2 仍 BLOCKED）

## A. 决策层自洽（归档 proba → 阈值二值化 vs 归档 pred）

| 运行 | split | 记录数 | 决策位 | label flip | 翻转率 | 一致 |
|---|---|---|---|---|---|---|
| education/charcnn/charcnn-final-20261028-212510 | predictions_validation_pseudo.npz | 45226 | 271356 | 0 | 0.0 | 是 |
| education/charcnn/charcnn-final-20261028-212510 | predictions_gold_holdout_human.npz | 736 | 4416 | 0 | 0.0 | 是 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | predictions_validation_pseudo.npz | 45226 | 271356 | 0 | 0.0 | 是 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | predictions_gold_holdout_human.npz | 736 | 4416 | 0 | 0.0 | 是 |
| education/charcnn/charcnn-final-confw-20261028-221032 | predictions_validation_pseudo.npz | 45226 | 271356 | 0 | 0.0 | 是 |
| education/charcnn/charcnn-final-confw-20261028-221032 | predictions_gold_holdout_human.npz | 736 | 4416 | 0 | 0.0 | 是 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | predictions_validation_pseudo.npz | 45226 | 271356 | 0 | 0.0 | 是 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | predictions_gold_holdout_human.npz | 736 | 4416 | 0 | 0.0 | 是 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | predictions_validation_pseudo.npz | 45226 | 271356 | 0 | 0.0 | 是 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | predictions_gold_holdout_human.npz | 736 | 4416 | 0 | 0.0 | 是 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | predictions_validation_pseudo.npz | 45226 | 271356 | 0 | 0.0 | 是 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | predictions_gold_holdout_human.npz | 736 | 4416 | 0 | 0.0 | 是 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | predictions_validation_pseudo.npz | 45226 | 271356 | 0 | 0.0 | 是 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | predictions_gold_holdout_human.npz | 736 | 4416 | 0 | 0.0 | 是 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | predictions_validation_pseudo.npz | 45226 | 271356 | 0 | 0.0 | 是 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | predictions_gold_holdout_human.npz | 736 | 4416 | 0 | 0.0 | 是 |
| education/charcnn/charcnn-smoke-charcnn-20261028-211941 | predictions_validation_pseudo.npz | 3000 | 18000 | 0 | 0.0 | 是 |
| education/charcnn/charcnn-smoke-charcnn-20261028-211941 | predictions_gold_holdout_human.npz | 736 | 4416 | 0 | 0.0 | 是 |
| education/tfidf/tfidf-final-20261028-212254 | predictions_validation_pseudo.npz | 45226 | 271356 | 0 | 0.0 | 是 |
| education/tfidf/tfidf-final-20261028-212254 | predictions_gold_holdout_human.npz | 736 | 4416 | 0 | 0.0 | 是 |
| education/tfidf/tfidf-final-balanced-20261028-212312 | predictions_validation_pseudo.npz | 45226 | 271356 | 0 | 0.0 | 是 |
| education/tfidf/tfidf-final-balanced-20261028-212312 | predictions_gold_holdout_human.npz | 736 | 4416 | 0 | 0.0 | 是 |
| education/tfidf/tfidf-final-confw-20261028-220908 | predictions_validation_pseudo.npz | 45226 | 271356 | 0 | 0.0 | 是 |
| education/tfidf/tfidf-final-confw-20261028-220908 | predictions_gold_holdout_human.npz | 736 | 4416 | 0 | 0.0 | 是 |
| education/tfidf/tfidf-final-highconf-20261028-221021 | predictions_validation_pseudo.npz | 45226 | 271356 | 0 | 0.0 | 是 |
| education/tfidf/tfidf-final-highconf-20261028-221021 | predictions_gold_holdout_human.npz | 736 | 4416 | 0 | 0.0 | 是 |
| education/tfidf/tfidf-final-holdout-20261028-212556 | predictions_validation_pseudo.npz | 45226 | 271356 | 0 | 0.0 | 是 |
| education/tfidf/tfidf-final-holdout-20261028-212556 | predictions_gold_holdout_human.npz | 736 | 4416 | 0 | 0.0 | 是 |
| education/tfidf/tfidf-final-title-20261028-212332 | predictions_validation_pseudo.npz | 45226 | 271356 | 0 | 0.0 | 是 |
| education/tfidf/tfidf-final-title-20261028-212332 | predictions_gold_holdout_human.npz | 736 | 4416 | 0 | 0.0 | 是 |
| education/tfidf/tfidf-smoke-tfidf-20261028-211845 | predictions_validation_pseudo.npz | 3000 | 18000 | 0 | 0.0 | 是 |
| education/tfidf/tfidf-smoke-tfidf-20261028-211845 | predictions_gold_holdout_human.npz | 736 | 4416 | 0 | 0.0 | 是 |

## B. LOAD + PREDICT 复现（真实加载 checkpoint 重新前向推理）

| 运行 | split | 对比记录 | max\|Δproba\| | mean\|Δproba\| | label flip | ε 内 |
|---|---|---|---|---|---|---|
| education/charcnn/charcnn-final-20261028-212510 | predictions_validation_pseudo.npz | 2000 | 8.631e-05 | 5.873e-06 | 0 | 否 |
| education/charcnn/charcnn-final-20261028-212510 | predictions_gold_holdout_human.npz | 736 | 6.267e-05 | 5.484e-06 | 0 | 否 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | predictions_validation_pseudo.npz | 2000 | 6.902e-05 | 2.356e-05 | 0 | 否 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | predictions_gold_holdout_human.npz | 736 | 6.902e-05 | 2.061e-05 | 0 | 否 |
| education/charcnn/charcnn-final-confw-20261028-221032 | predictions_validation_pseudo.npz | 2000 | 8.717e-05 | 1.225e-05 | 0 | 否 |
| education/charcnn/charcnn-final-confw-20261028-221032 | predictions_gold_holdout_human.npz | 736 | 7.337e-05 | 1.082e-05 | 0 | 否 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | predictions_validation_pseudo.npz | 2000 | 1.050e-04 | 1.838e-05 | 0 | 否 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | predictions_gold_holdout_human.npz | 736 | 1.050e-04 | 1.738e-05 | 0 | 否 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | predictions_validation_pseudo.npz | 2000 | 6.601e-05 | 9.675e-06 | 0 | 否 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | predictions_gold_holdout_human.npz | 736 | 4.837e-05 | 8.480e-06 | 0 | 否 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | predictions_validation_pseudo.npz | 2000 | 1.161e-04 | 6.024e-06 | 0 | 否 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | predictions_gold_holdout_human.npz | 736 | 1.161e-04 | 6.530e-06 | 0 | 否 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | predictions_validation_pseudo.npz | 2000 | 8.768e-05 | 8.157e-06 | 0 | 否 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | predictions_gold_holdout_human.npz | 736 | 1.234e-04 | 7.522e-06 | 0 | 否 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | predictions_validation_pseudo.npz | 2000 | 8.410e-05 | 1.300e-05 | 0 | 否 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | predictions_gold_holdout_human.npz | 736 | 8.711e-05 | 1.373e-05 | 0 | 否 |
| education/charcnn/charcnn-smoke-charcnn-20261028-211941 | predictions_validation_pseudo.npz | 2000 | 5.227e-05 | 1.027e-05 | 0 | 否 |
| education/charcnn/charcnn-smoke-charcnn-20261028-211941 | predictions_gold_holdout_human.npz | 736 | 4.798e-05 | 1.036e-05 | 0 | 否 |
| education/tfidf/tfidf-final-20261028-212254 | predictions_validation_pseudo.npz | 2000 | 2.902e-08 | 6.719e-09 | 0 | 是 |
| education/tfidf/tfidf-final-20261028-212254 | predictions_gold_holdout_human.npz | 736 | 2.902e-08 | 6.460e-09 | 0 | 是 |
| education/tfidf/tfidf-final-balanced-20261028-212312 | predictions_validation_pseudo.npz | 2000 | 2.958e-08 | 7.708e-09 | 0 | 是 |
| education/tfidf/tfidf-final-balanced-20261028-212312 | predictions_gold_holdout_human.npz | 736 | 2.942e-08 | 6.787e-09 | 0 | 是 |
| education/tfidf/tfidf-final-confw-20261028-220908 | predictions_validation_pseudo.npz | 2000 | 2.949e-08 | 8.737e-09 | 0 | 是 |
| education/tfidf/tfidf-final-confw-20261028-220908 | predictions_gold_holdout_human.npz | 736 | 2.949e-08 | 7.545e-09 | 0 | 是 |
| education/tfidf/tfidf-final-highconf-20261028-221021 | predictions_validation_pseudo.npz | 2000 | 2.953e-08 | 6.384e-09 | 0 | 是 |
| education/tfidf/tfidf-final-highconf-20261028-221021 | predictions_gold_holdout_human.npz | 736 | 2.912e-08 | 5.390e-09 | 0 | 是 |
| education/tfidf/tfidf-final-holdout-20261028-212556 | predictions_validation_pseudo.npz | 2000 | 2.963e-08 | 6.572e-09 | 0 | 是 |
| education/tfidf/tfidf-final-holdout-20261028-212556 | predictions_gold_holdout_human.npz | 736 | 2.641e-08 | 5.970e-09 | 0 | 是 |
| education/tfidf/tfidf-final-title-20261028-212332 | predictions_validation_pseudo.npz | 2000 | 2.980e-08 | 6.848e-09 | 0 | 是 |
| education/tfidf/tfidf-final-title-20261028-212332 | predictions_gold_holdout_human.npz | 736 | 2.980e-08 | 6.291e-09 | 0 | 是 |
| education/tfidf/tfidf-smoke-tfidf-20261028-211845 | predictions_validation_pseudo.npz | 2000 | 2.969e-08 | 5.701e-09 | 0 | 是 |
| education/tfidf/tfidf-smoke-tfidf-20261028-211845 | predictions_gold_holdout_human.npz | 736 | 2.884e-08 | 5.777e-09 | 0 | 是 |

## C. 跨运行 label flip 统计（同 record_key）

### predictions_validation_pseudo.npz

| 运行 A | 运行 B | 共有记录 | 决策位 | label flip | 翻转率 |
|---|---|---|---|---|---|
| education/charcnn/charcnn-final-20261028-212510 | education/charcnn/charcnn-final-balanced-20261028-212534 | 45226 | 271356 | 50 | 0.00018426 |
| education/charcnn/charcnn-final-20261028-212510 | education/charcnn/charcnn-final-confw-20261028-221032 | 45226 | 271356 | 89 | 0.00032798 |
| education/charcnn/charcnn-final-20261028-212510 | education/charcnn/charcnn-final-highconf-20261028-221117 | 45226 | 271356 | 13001 | 0.04791123 |
| education/charcnn/charcnn-final-20261028-212510 | education/charcnn/charcnn-final-holdout-20261028-212622 | 45226 | 271356 | 51 | 0.00018794 |
| education/charcnn/charcnn-final-20261028-212510 | education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | 45226 | 271356 | 297 | 0.0010945 |
| education/charcnn/charcnn-final-20261028-212510 | education/charcnn/charcnn-final-vloss-20261028-213415 | 45226 | 271356 | 74 | 0.0002727 |
| education/charcnn/charcnn-final-20261028-212510 | education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | 45226 | 271356 | 112 | 0.00041274 |
| education/charcnn/charcnn-final-20261028-212510 | education/charcnn/charcnn-smoke-charcnn-20261028-211941 | 3000 | 18000 | 121 | 0.00672222 |
| education/charcnn/charcnn-final-20261028-212510 | education/tfidf/tfidf-final-20261028-212254 | 45226 | 271356 | 3012 | 0.01109981 |
| education/charcnn/charcnn-final-20261028-212510 | education/tfidf/tfidf-final-balanced-20261028-212312 | 45226 | 271356 | 3009 | 0.01108875 |
| education/charcnn/charcnn-final-20261028-212510 | education/tfidf/tfidf-final-confw-20261028-220908 | 45226 | 271356 | 3007 | 0.01108138 |
| education/charcnn/charcnn-final-20261028-212510 | education/tfidf/tfidf-final-highconf-20261028-221021 | 45226 | 271356 | 3821 | 0.01408113 |
| education/charcnn/charcnn-final-20261028-212510 | education/tfidf/tfidf-final-holdout-20261028-212556 | 45226 | 271356 | 3362 | 0.01238963 |
| education/charcnn/charcnn-final-20261028-212510 | education/tfidf/tfidf-final-title-20261028-212332 | 45226 | 271356 | 24275 | 0.08945813 |
| education/charcnn/charcnn-final-20261028-212510 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 3000 | 18000 | 234 | 0.013 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/charcnn/charcnn-final-confw-20261028-221032 | 45226 | 271356 | 79 | 0.00029113 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/charcnn/charcnn-final-highconf-20261028-221117 | 45226 | 271356 | 12991 | 0.04787438 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/charcnn/charcnn-final-holdout-20261028-212622 | 45226 | 271356 | 33 | 0.00012161 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | 45226 | 271356 | 283 | 0.00104291 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/charcnn/charcnn-final-vloss-20261028-213415 | 45226 | 271356 | 50 | 0.00018426 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | 45226 | 271356 | 82 | 0.00030219 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/charcnn/charcnn-smoke-charcnn-20261028-211941 | 3000 | 18000 | 124 | 0.00688889 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/tfidf/tfidf-final-20261028-212254 | 45226 | 271356 | 2986 | 0.01100399 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/tfidf/tfidf-final-balanced-20261028-212312 | 45226 | 271356 | 2979 | 0.0109782 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/tfidf/tfidf-final-confw-20261028-220908 | 45226 | 271356 | 2973 | 0.01095609 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/tfidf/tfidf-final-highconf-20261028-221021 | 45226 | 271356 | 3795 | 0.01398532 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/tfidf/tfidf-final-holdout-20261028-212556 | 45226 | 271356 | 3320 | 0.01223485 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/tfidf/tfidf-final-title-20261028-212332 | 45226 | 271356 | 24247 | 0.08935494 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 3000 | 18000 | 237 | 0.01316667 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/charcnn/charcnn-final-highconf-20261028-221117 | 45226 | 271356 | 12976 | 0.0478191 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/charcnn/charcnn-final-holdout-20261028-212622 | 45226 | 271356 | 56 | 0.00020637 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | 45226 | 271356 | 286 | 0.00105397 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/charcnn/charcnn-final-vloss-20261028-213415 | 45226 | 271356 | 53 | 0.00019532 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | 45226 | 271356 | 27 | 9.95e-05 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/charcnn/charcnn-smoke-charcnn-20261028-211941 | 3000 | 18000 | 123 | 0.00683333 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/tfidf/tfidf-final-20261028-212254 | 45226 | 271356 | 2931 | 0.01080131 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/tfidf/tfidf-final-balanced-20261028-212312 | 45226 | 271356 | 2928 | 0.01079025 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/tfidf/tfidf-final-confw-20261028-220908 | 45226 | 271356 | 2922 | 0.01076814 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/tfidf/tfidf-final-highconf-20261028-221021 | 45226 | 271356 | 3766 | 0.01387845 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/tfidf/tfidf-final-holdout-20261028-212556 | 45226 | 271356 | 3287 | 0.01211324 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/tfidf/tfidf-final-title-20261028-212332 | 45226 | 271356 | 24202 | 0.08918911 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 3000 | 18000 | 236 | 0.01311111 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/charcnn/charcnn-final-holdout-20261028-212622 | 45226 | 271356 | 13000 | 0.04790755 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | 45226 | 271356 | 12754 | 0.04700099 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/charcnn/charcnn-final-vloss-20261028-213415 | 45226 | 271356 | 12993 | 0.04788175 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | 45226 | 271356 | 12955 | 0.04774171 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/charcnn/charcnn-smoke-charcnn-20261028-211941 | 3000 | 18000 | 905 | 0.05027778 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/tfidf/tfidf-final-20261028-212254 | 45226 | 271356 | 15859 | 0.05844352 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/tfidf/tfidf-final-balanced-20261028-212312 | 45226 | 271356 | 15856 | 0.05843247 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/tfidf/tfidf-final-confw-20261028-220908 | 45226 | 271356 | 15850 | 0.05841035 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/tfidf/tfidf-final-highconf-20261028-221021 | 45226 | 271356 | 15070 | 0.0555359 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/tfidf/tfidf-final-holdout-20261028-212556 | 45226 | 271356 | 15555 | 0.05732322 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/tfidf/tfidf-final-title-20261028-212332 | 45226 | 271356 | 30868 | 0.11375462 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 3000 | 18000 | 1050 | 0.05833333 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | 45226 | 271356 | 260 | 0.00095815 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/charcnn/charcnn-final-vloss-20261028-213415 | 45226 | 271356 | 33 | 0.00012161 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | 45226 | 271356 | 75 | 0.00027639 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/charcnn/charcnn-smoke-charcnn-20261028-211941 | 3000 | 18000 | 121 | 0.00672222 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/tfidf/tfidf-final-20261028-212254 | 45226 | 271356 | 2971 | 0.01094872 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/tfidf/tfidf-final-balanced-20261028-212312 | 45226 | 271356 | 2970 | 0.01094503 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/tfidf/tfidf-final-confw-20261028-220908 | 45226 | 271356 | 2966 | 0.01093029 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/tfidf/tfidf-final-highconf-20261028-221021 | 45226 | 271356 | 3812 | 0.01404797 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/tfidf/tfidf-final-holdout-20261028-212556 | 45226 | 271356 | 3321 | 0.01223854 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/tfidf/tfidf-final-title-20261028-212332 | 45226 | 271356 | 24244 | 0.08934389 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 3000 | 18000 | 234 | 0.013 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/charcnn/charcnn-final-vloss-20261028-213415 | 45226 | 271356 | 273 | 0.00100606 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | 45226 | 271356 | 299 | 0.00110187 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/charcnn/charcnn-smoke-charcnn-20261028-211941 | 3000 | 18000 | 137 | 0.00761111 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/tfidf/tfidf-final-20261028-212254 | 45226 | 271356 | 3209 | 0.01182579 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/tfidf/tfidf-final-balanced-20261028-212312 | 45226 | 271356 | 3196 | 0.01177789 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/tfidf/tfidf-final-confw-20261028-220908 | 45226 | 271356 | 3196 | 0.01177789 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/tfidf/tfidf-final-highconf-20261028-221021 | 45226 | 271356 | 4042 | 0.01489556 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/tfidf/tfidf-final-holdout-20261028-212556 | 45226 | 271356 | 3075 | 0.01133198 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/tfidf/tfidf-final-title-20261028-212332 | 45226 | 271356 | 24462 | 0.09014726 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 3000 | 18000 | 250 | 0.01388889 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | 45226 | 271356 | 76 | 0.00028007 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | education/charcnn/charcnn-smoke-charcnn-20261028-211941 | 3000 | 18000 | 119 | 0.00661111 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | education/tfidf/tfidf-final-20261028-212254 | 45226 | 271356 | 2964 | 0.01092292 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | education/tfidf/tfidf-final-balanced-20261028-212312 | 45226 | 271356 | 2971 | 0.01094872 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | education/tfidf/tfidf-final-confw-20261028-220908 | 45226 | 271356 | 2967 | 0.01093398 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | education/tfidf/tfidf-final-highconf-20261028-221021 | 45226 | 271356 | 3809 | 0.01403691 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | education/tfidf/tfidf-final-holdout-20261028-212556 | 45226 | 271356 | 3298 | 0.01215378 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | education/tfidf/tfidf-final-title-20261028-212332 | 45226 | 271356 | 24247 | 0.08935494 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 3000 | 18000 | 232 | 0.01288889 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | education/charcnn/charcnn-smoke-charcnn-20261028-211941 | 3000 | 18000 | 129 | 0.00716667 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | education/tfidf/tfidf-final-20261028-212254 | 45226 | 271356 | 2918 | 0.0107534 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | education/tfidf/tfidf-final-balanced-20261028-212312 | 45226 | 271356 | 2901 | 0.01069075 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | education/tfidf/tfidf-final-confw-20261028-220908 | 45226 | 271356 | 2901 | 0.01069075 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | education/tfidf/tfidf-final-highconf-20261028-221021 | 45226 | 271356 | 3761 | 0.01386002 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | education/tfidf/tfidf-final-holdout-20261028-212556 | 45226 | 271356 | 3274 | 0.01206533 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | education/tfidf/tfidf-final-title-20261028-212332 | 45226 | 271356 | 24181 | 0.08911172 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 3000 | 18000 | 242 | 0.01344444 |
| education/charcnn/charcnn-smoke-charcnn-20261028-211941 | education/tfidf/tfidf-final-20261028-212254 | 3000 | 18000 | 337 | 0.01872222 |
| education/charcnn/charcnn-smoke-charcnn-20261028-211941 | education/tfidf/tfidf-final-balanced-20261028-212312 | 3000 | 18000 | 338 | 0.01877778 |
| education/charcnn/charcnn-smoke-charcnn-20261028-211941 | education/tfidf/tfidf-final-confw-20261028-220908 | 3000 | 18000 | 338 | 0.01877778 |
| education/charcnn/charcnn-smoke-charcnn-20261028-211941 | education/tfidf/tfidf-final-highconf-20261028-221021 | 3000 | 18000 | 314 | 0.01744444 |
| education/charcnn/charcnn-smoke-charcnn-20261028-211941 | education/tfidf/tfidf-final-holdout-20261028-212556 | 3000 | 18000 | 344 | 0.01911111 |
| education/charcnn/charcnn-smoke-charcnn-20261028-211941 | education/tfidf/tfidf-final-title-20261028-212332 | 3000 | 18000 | 1661 | 0.09227778 |
| education/charcnn/charcnn-smoke-charcnn-20261028-211941 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 3000 | 18000 | 333 | 0.0185 |
| education/tfidf/tfidf-final-20261028-212254 | education/tfidf/tfidf-final-balanced-20261028-212312 | 45226 | 271356 | 23 | 8.476e-05 |
| education/tfidf/tfidf-final-20261028-212254 | education/tfidf/tfidf-final-confw-20261028-220908 | 45226 | 271356 | 17 | 6.265e-05 |
| education/tfidf/tfidf-final-20261028-212254 | education/tfidf/tfidf-final-highconf-20261028-221021 | 45226 | 271356 | 865 | 0.00318769 |
| education/tfidf/tfidf-final-20261028-212254 | education/tfidf/tfidf-final-holdout-20261028-212556 | 45226 | 271356 | 360 | 0.00132667 |
| education/tfidf/tfidf-final-20261028-212254 | education/tfidf/tfidf-final-title-20261028-212332 | 45226 | 271356 | 22839 | 0.08416619 |
| education/tfidf/tfidf-final-20261028-212254 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 3000 | 18000 | 30 | 0.00166667 |
| education/tfidf/tfidf-final-balanced-20261028-212312 | education/tfidf/tfidf-final-confw-20261028-220908 | 45226 | 271356 | 6 | 2.211e-05 |
| education/tfidf/tfidf-final-balanced-20261028-212312 | education/tfidf/tfidf-final-highconf-20261028-221021 | 45226 | 271356 | 866 | 0.00319138 |
| education/tfidf/tfidf-final-balanced-20261028-212312 | education/tfidf/tfidf-final-holdout-20261028-212556 | 45226 | 271356 | 379 | 0.00139669 |
| education/tfidf/tfidf-final-balanced-20261028-212312 | education/tfidf/tfidf-final-title-20261028-212332 | 45226 | 271356 | 22836 | 0.08415513 |
| education/tfidf/tfidf-final-balanced-20261028-212312 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 3000 | 18000 | 33 | 0.00183333 |
| education/tfidf/tfidf-final-confw-20261028-220908 | education/tfidf/tfidf-final-highconf-20261028-221021 | 45226 | 271356 | 860 | 0.00316927 |
| education/tfidf/tfidf-final-confw-20261028-220908 | education/tfidf/tfidf-final-holdout-20261028-212556 | 45226 | 271356 | 373 | 0.00137458 |
| education/tfidf/tfidf-final-confw-20261028-220908 | education/tfidf/tfidf-final-title-20261028-212332 | 45226 | 271356 | 22834 | 0.08414776 |
| education/tfidf/tfidf-final-confw-20261028-220908 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 3000 | 18000 | 33 | 0.00183333 |
| education/tfidf/tfidf-final-highconf-20261028-221021 | education/tfidf/tfidf-final-holdout-20261028-212556 | 45226 | 271356 | 1055 | 0.00388788 |
| education/tfidf/tfidf-final-highconf-20261028-221021 | education/tfidf/tfidf-final-title-20261028-212332 | 45226 | 271356 | 23478 | 0.08652103 |
| education/tfidf/tfidf-final-highconf-20261028-221021 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 3000 | 18000 | 35 | 0.00194444 |
| education/tfidf/tfidf-final-holdout-20261028-212556 | education/tfidf/tfidf-final-title-20261028-212332 | 45226 | 271356 | 23171 | 0.08538967 |
| education/tfidf/tfidf-final-holdout-20261028-212556 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 3000 | 18000 | 33 | 0.00183333 |
| education/tfidf/tfidf-final-title-20261028-212332 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 3000 | 18000 | 1476 | 0.082 |

### predictions_gold_holdout_human.npz

| 运行 A | 运行 B | 共有记录 | 决策位 | label flip | 翻转率 |
|---|---|---|---|---|---|
| education/charcnn/charcnn-final-20261028-212510 | education/charcnn/charcnn-final-balanced-20261028-212534 | 736 | 4416 | 0 | 0.0 |
| education/charcnn/charcnn-final-20261028-212510 | education/charcnn/charcnn-final-confw-20261028-221032 | 736 | 4416 | 27 | 0.00611413 |
| education/charcnn/charcnn-final-20261028-212510 | education/charcnn/charcnn-final-highconf-20261028-221117 | 736 | 4416 | 205 | 0.0464221 |
| education/charcnn/charcnn-final-20261028-212510 | education/charcnn/charcnn-final-holdout-20261028-212622 | 736 | 4416 | 27 | 0.00611413 |
| education/charcnn/charcnn-final-20261028-212510 | education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | 736 | 4416 | 29 | 0.00656703 |
| education/charcnn/charcnn-final-20261028-212510 | education/charcnn/charcnn-final-vloss-20261028-213415 | 736 | 4416 | 27 | 0.00611413 |
| education/charcnn/charcnn-final-20261028-212510 | education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | 736 | 4416 | 27 | 0.00611413 |
| education/charcnn/charcnn-final-20261028-212510 | education/charcnn/charcnn-smoke-charcnn-20261028-211941 | 736 | 4416 | 51 | 0.01154891 |
| education/charcnn/charcnn-final-20261028-212510 | education/tfidf/tfidf-final-20261028-212254 | 736 | 4416 | 41 | 0.00928442 |
| education/charcnn/charcnn-final-20261028-212510 | education/tfidf/tfidf-final-balanced-20261028-212312 | 736 | 4416 | 41 | 0.00928442 |
| education/charcnn/charcnn-final-20261028-212510 | education/tfidf/tfidf-final-confw-20261028-220908 | 736 | 4416 | 41 | 0.00928442 |
| education/charcnn/charcnn-final-20261028-212510 | education/tfidf/tfidf-final-highconf-20261028-221021 | 736 | 4416 | 14 | 0.00317029 |
| education/charcnn/charcnn-final-20261028-212510 | education/tfidf/tfidf-final-holdout-20261028-212556 | 736 | 4416 | 43 | 0.00973732 |
| education/charcnn/charcnn-final-20261028-212510 | education/tfidf/tfidf-final-title-20261028-212332 | 736 | 4416 | 336 | 0.07608696 |
| education/charcnn/charcnn-final-20261028-212510 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 736 | 4416 | 14 | 0.00317029 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/charcnn/charcnn-final-confw-20261028-221032 | 736 | 4416 | 27 | 0.00611413 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/charcnn/charcnn-final-highconf-20261028-221117 | 736 | 4416 | 205 | 0.0464221 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/charcnn/charcnn-final-holdout-20261028-212622 | 736 | 4416 | 27 | 0.00611413 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | 736 | 4416 | 29 | 0.00656703 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/charcnn/charcnn-final-vloss-20261028-213415 | 736 | 4416 | 27 | 0.00611413 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | 736 | 4416 | 27 | 0.00611413 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/charcnn/charcnn-smoke-charcnn-20261028-211941 | 736 | 4416 | 51 | 0.01154891 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/tfidf/tfidf-final-20261028-212254 | 736 | 4416 | 41 | 0.00928442 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/tfidf/tfidf-final-balanced-20261028-212312 | 736 | 4416 | 41 | 0.00928442 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/tfidf/tfidf-final-confw-20261028-220908 | 736 | 4416 | 41 | 0.00928442 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/tfidf/tfidf-final-highconf-20261028-221021 | 736 | 4416 | 14 | 0.00317029 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/tfidf/tfidf-final-holdout-20261028-212556 | 736 | 4416 | 43 | 0.00973732 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/tfidf/tfidf-final-title-20261028-212332 | 736 | 4416 | 336 | 0.07608696 |
| education/charcnn/charcnn-final-balanced-20261028-212534 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 736 | 4416 | 14 | 0.00317029 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/charcnn/charcnn-final-highconf-20261028-221117 | 736 | 4416 | 232 | 0.05253623 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/charcnn/charcnn-final-holdout-20261028-212622 | 736 | 4416 | 0 | 0.0 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | 736 | 4416 | 2 | 0.0004529 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/charcnn/charcnn-final-vloss-20261028-213415 | 736 | 4416 | 0 | 0.0 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | 736 | 4416 | 0 | 0.0 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/charcnn/charcnn-smoke-charcnn-20261028-211941 | 736 | 4416 | 78 | 0.01766304 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/tfidf/tfidf-final-20261028-212254 | 736 | 4416 | 14 | 0.00317029 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/tfidf/tfidf-final-balanced-20261028-212312 | 736 | 4416 | 14 | 0.00317029 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/tfidf/tfidf-final-confw-20261028-220908 | 736 | 4416 | 14 | 0.00317029 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/tfidf/tfidf-final-highconf-20261028-221021 | 736 | 4416 | 41 | 0.00928442 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/tfidf/tfidf-final-holdout-20261028-212556 | 736 | 4416 | 16 | 0.00362319 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/tfidf/tfidf-final-title-20261028-212332 | 736 | 4416 | 309 | 0.06997283 |
| education/charcnn/charcnn-final-confw-20261028-221032 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 736 | 4416 | 41 | 0.00928442 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/charcnn/charcnn-final-holdout-20261028-212622 | 736 | 4416 | 232 | 0.05253623 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | 736 | 4416 | 230 | 0.05208333 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/charcnn/charcnn-final-vloss-20261028-213415 | 736 | 4416 | 232 | 0.05253623 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | 736 | 4416 | 232 | 0.05253623 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/charcnn/charcnn-smoke-charcnn-20261028-211941 | 736 | 4416 | 256 | 0.05797101 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/tfidf/tfidf-final-20261028-212254 | 736 | 4416 | 246 | 0.05570652 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/tfidf/tfidf-final-balanced-20261028-212312 | 736 | 4416 | 246 | 0.05570652 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/tfidf/tfidf-final-confw-20261028-220908 | 736 | 4416 | 246 | 0.05570652 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/tfidf/tfidf-final-highconf-20261028-221021 | 736 | 4416 | 219 | 0.04959239 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/tfidf/tfidf-final-holdout-20261028-212556 | 736 | 4416 | 244 | 0.05525362 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/tfidf/tfidf-final-title-20261028-212332 | 736 | 4416 | 453 | 0.10258152 |
| education/charcnn/charcnn-final-highconf-20261028-221117 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 736 | 4416 | 219 | 0.04959239 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | 736 | 4416 | 2 | 0.0004529 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/charcnn/charcnn-final-vloss-20261028-213415 | 736 | 4416 | 0 | 0.0 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | 736 | 4416 | 0 | 0.0 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/charcnn/charcnn-smoke-charcnn-20261028-211941 | 736 | 4416 | 78 | 0.01766304 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/tfidf/tfidf-final-20261028-212254 | 736 | 4416 | 14 | 0.00317029 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/tfidf/tfidf-final-balanced-20261028-212312 | 736 | 4416 | 14 | 0.00317029 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/tfidf/tfidf-final-confw-20261028-220908 | 736 | 4416 | 14 | 0.00317029 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/tfidf/tfidf-final-highconf-20261028-221021 | 736 | 4416 | 41 | 0.00928442 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/tfidf/tfidf-final-holdout-20261028-212556 | 736 | 4416 | 16 | 0.00362319 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/tfidf/tfidf-final-title-20261028-212332 | 736 | 4416 | 309 | 0.06997283 |
| education/charcnn/charcnn-final-holdout-20261028-212622 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 736 | 4416 | 41 | 0.00928442 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/charcnn/charcnn-final-vloss-20261028-213415 | 736 | 4416 | 2 | 0.0004529 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | 736 | 4416 | 2 | 0.0004529 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/charcnn/charcnn-smoke-charcnn-20261028-211941 | 736 | 4416 | 80 | 0.01811594 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/tfidf/tfidf-final-20261028-212254 | 736 | 4416 | 16 | 0.00362319 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/tfidf/tfidf-final-balanced-20261028-212312 | 736 | 4416 | 16 | 0.00362319 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/tfidf/tfidf-final-confw-20261028-220908 | 736 | 4416 | 16 | 0.00362319 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/tfidf/tfidf-final-highconf-20261028-221021 | 736 | 4416 | 43 | 0.00973732 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/tfidf/tfidf-final-holdout-20261028-212556 | 736 | 4416 | 14 | 0.00317029 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/tfidf/tfidf-final-title-20261028-212332 | 736 | 4416 | 311 | 0.07042572 |
| education/charcnn/charcnn-final-holdout-vloss-20261028-213521 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 736 | 4416 | 43 | 0.00973732 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | 736 | 4416 | 0 | 0.0 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | education/charcnn/charcnn-smoke-charcnn-20261028-211941 | 736 | 4416 | 78 | 0.01766304 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | education/tfidf/tfidf-final-20261028-212254 | 736 | 4416 | 14 | 0.00317029 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | education/tfidf/tfidf-final-balanced-20261028-212312 | 736 | 4416 | 14 | 0.00317029 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | education/tfidf/tfidf-final-confw-20261028-220908 | 736 | 4416 | 14 | 0.00317029 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | education/tfidf/tfidf-final-highconf-20261028-221021 | 736 | 4416 | 41 | 0.00928442 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | education/tfidf/tfidf-final-holdout-20261028-212556 | 736 | 4416 | 16 | 0.00362319 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | education/tfidf/tfidf-final-title-20261028-212332 | 736 | 4416 | 309 | 0.06997283 |
| education/charcnn/charcnn-final-vloss-20261028-213415 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 736 | 4416 | 41 | 0.00928442 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | education/charcnn/charcnn-smoke-charcnn-20261028-211941 | 736 | 4416 | 78 | 0.01766304 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | education/tfidf/tfidf-final-20261028-212254 | 736 | 4416 | 14 | 0.00317029 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | education/tfidf/tfidf-final-balanced-20261028-212312 | 736 | 4416 | 14 | 0.00317029 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | education/tfidf/tfidf-final-confw-20261028-220908 | 736 | 4416 | 14 | 0.00317029 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | education/tfidf/tfidf-final-highconf-20261028-221021 | 736 | 4416 | 41 | 0.00928442 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | education/tfidf/tfidf-final-holdout-20261028-212556 | 736 | 4416 | 16 | 0.00362319 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | education/tfidf/tfidf-final-title-20261028-212332 | 736 | 4416 | 309 | 0.06997283 |
| education/charcnn/charcnn-final-vloss-balanced-20261028-213450 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 736 | 4416 | 41 | 0.00928442 |
| education/charcnn/charcnn-smoke-charcnn-20261028-211941 | education/tfidf/tfidf-final-20261028-212254 | 736 | 4416 | 92 | 0.02083333 |
| education/charcnn/charcnn-smoke-charcnn-20261028-211941 | education/tfidf/tfidf-final-balanced-20261028-212312 | 736 | 4416 | 92 | 0.02083333 |
| education/charcnn/charcnn-smoke-charcnn-20261028-211941 | education/tfidf/tfidf-final-confw-20261028-220908 | 736 | 4416 | 92 | 0.02083333 |
| education/charcnn/charcnn-smoke-charcnn-20261028-211941 | education/tfidf/tfidf-final-highconf-20261028-221021 | 736 | 4416 | 65 | 0.0147192 |
| education/charcnn/charcnn-smoke-charcnn-20261028-211941 | education/tfidf/tfidf-final-holdout-20261028-212556 | 736 | 4416 | 94 | 0.02128623 |
| education/charcnn/charcnn-smoke-charcnn-20261028-211941 | education/tfidf/tfidf-final-title-20261028-212332 | 736 | 4416 | 387 | 0.08763587 |
| education/charcnn/charcnn-smoke-charcnn-20261028-211941 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 736 | 4416 | 65 | 0.0147192 |
| education/tfidf/tfidf-final-20261028-212254 | education/tfidf/tfidf-final-balanced-20261028-212312 | 736 | 4416 | 0 | 0.0 |
| education/tfidf/tfidf-final-20261028-212254 | education/tfidf/tfidf-final-confw-20261028-220908 | 736 | 4416 | 0 | 0.0 |
| education/tfidf/tfidf-final-20261028-212254 | education/tfidf/tfidf-final-highconf-20261028-221021 | 736 | 4416 | 27 | 0.00611413 |
| education/tfidf/tfidf-final-20261028-212254 | education/tfidf/tfidf-final-holdout-20261028-212556 | 736 | 4416 | 2 | 0.0004529 |
| education/tfidf/tfidf-final-20261028-212254 | education/tfidf/tfidf-final-title-20261028-212332 | 736 | 4416 | 297 | 0.06725543 |
| education/tfidf/tfidf-final-20261028-212254 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 736 | 4416 | 27 | 0.00611413 |
| education/tfidf/tfidf-final-balanced-20261028-212312 | education/tfidf/tfidf-final-confw-20261028-220908 | 736 | 4416 | 0 | 0.0 |
| education/tfidf/tfidf-final-balanced-20261028-212312 | education/tfidf/tfidf-final-highconf-20261028-221021 | 736 | 4416 | 27 | 0.00611413 |
| education/tfidf/tfidf-final-balanced-20261028-212312 | education/tfidf/tfidf-final-holdout-20261028-212556 | 736 | 4416 | 2 | 0.0004529 |
| education/tfidf/tfidf-final-balanced-20261028-212312 | education/tfidf/tfidf-final-title-20261028-212332 | 736 | 4416 | 297 | 0.06725543 |
| education/tfidf/tfidf-final-balanced-20261028-212312 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 736 | 4416 | 27 | 0.00611413 |
| education/tfidf/tfidf-final-confw-20261028-220908 | education/tfidf/tfidf-final-highconf-20261028-221021 | 736 | 4416 | 27 | 0.00611413 |
| education/tfidf/tfidf-final-confw-20261028-220908 | education/tfidf/tfidf-final-holdout-20261028-212556 | 736 | 4416 | 2 | 0.0004529 |
| education/tfidf/tfidf-final-confw-20261028-220908 | education/tfidf/tfidf-final-title-20261028-212332 | 736 | 4416 | 297 | 0.06725543 |
| education/tfidf/tfidf-final-confw-20261028-220908 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 736 | 4416 | 27 | 0.00611413 |
| education/tfidf/tfidf-final-highconf-20261028-221021 | education/tfidf/tfidf-final-holdout-20261028-212556 | 736 | 4416 | 29 | 0.00656703 |
| education/tfidf/tfidf-final-highconf-20261028-221021 | education/tfidf/tfidf-final-title-20261028-212332 | 736 | 4416 | 324 | 0.07336957 |
| education/tfidf/tfidf-final-highconf-20261028-221021 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 736 | 4416 | 0 | 0.0 |
| education/tfidf/tfidf-final-holdout-20261028-212556 | education/tfidf/tfidf-final-title-20261028-212332 | 736 | 4416 | 299 | 0.06770833 |
| education/tfidf/tfidf-final-holdout-20261028-212556 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 736 | 4416 | 29 | 0.00656703 |
| education/tfidf/tfidf-final-title-20261028-212332 | education/tfidf/tfidf-smoke-tfidf-20261028-211845 | 736 | 4416 | 324 | 0.07336957 |

## 边界

1. 本报告只描述**决策稳定性**（阈值口径是否可复现、不同训练变体间决策差异），不等于学历抽取准确率；
2. label flip 高不必然代表模型差，也可能是阈值按各自验证集分别选择所致；
3. 未使用任何人工 Gold 结论，H2 仍为 BLOCKED。
4. 数值容差口径：tfidf 系复现 max\|Δproba\| 约 3e-8（float64 级）；charcnn 系约 5e-5~1.2e-4，为 torch float32 前向在 CPU 多线程下的累积噪声，**32/32 split 的 label flip 全部为 0**，决策层完全可复现；`within_eps` 列按严格 1e-6 判定，charcnn 列的「否」仅指数值未进 1e-6，不表示决策不一致。
5. 本轮曾发现 `tfidf-final-title` 复现出现大量 label flip（3114/882），排查为复现脚本输入口径缺陷：该 run 的 `feature_map.input_mode=slot_title`，输入应为 `slot_education_norm ‖ job_title_norm`（与训练一致），脚本此前只喂 `slot_education_norm`。已按训练口径修复后重跑，该 run 的 max\|Δproba\| 降至 2.98e-8、label flip=0。
