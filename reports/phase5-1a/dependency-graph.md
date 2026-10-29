# src/job_matching 跨层依赖（Phase5-1A 实测）

| 源模块 | 目标模块 |
|---|---|
| annotation.freeze | core |
| annotation.gold_gate | annotation |
| annotation.pii | domain.pii_masking |
| annotation.pool | annotation |
| annotation.pool | core |
| annotation.pool | domain.job_rules |
| annotation.pool | domain.skills_lexicon |
| annotation.pool | pair_features |
| annotation.pool | preprocess_education |
| annotation.resume_intake | annotation |
| annotation.resume_intake | core |
| annotation.resume_intake | infra.documents |
| education.dataset | core |
| education.evaluator | metrics_classification |
| education.labels | config |
| education.labels | preprocess_education |
| education.predictor | core |
| education.rules | baseline_education |
| evaluation.metrics | metrics_ranking |
| evaluation.statistical_tests | metrics_ranking |
| independent_eval.baselines | core |
| independent_eval.baselines | domain.job_rules |
| independent_eval.baselines | inference.predictor |
| independent_eval.bootstrap | evaluation.statistical_tests |
| independent_eval.bootstrap | metrics_ranking |
| independent_eval.dataset | annotation.freeze |
| independent_eval.dataset | core |
| independent_eval.metrics | metrics_ranking |
| inference.predictor | models.gradient_boosting |
| inference.predictor | models.mlp |
| inference.predictor | models.ranknet |
| inference.predictor | models.ridge |
| inference.predictor | training.feature_map |
| models.base | evaluation.metrics |
| models.gradient_boosting | evaluation.metrics |
| models.mlp | evaluation.metrics |
| models.mlp | training |
| models.ranknet | core |
| models.ranknet | evaluation.metrics |
| models.ranknet | training |
| models.ranknet | training.pair_sampler |
| models.ridge | evaluation.metrics |
| pair_features | domain.job_rules |
| service.api | core |
| service.errors | core |
| service.explanations | domain.job_rules |
| service.explanations | preprocess_skills |
| service.job_parser | core |
| service.job_parser | domain.job_rules |
| service.job_parser | domain.pii_masking |
| service.job_parser | education.predictor |
| service.job_parser | education.rules |
| service.logging_utils | domain.pii_masking |
| service.matching | job_matching |
| service.matching | domain.job_rules |
| service.matching | preprocess_skills |
| service.model_registry | core |
| service.model_registry | education.predictor |
| service.model_registry | inference.predictor |
| service.resume_parser | core |
| service.resume_parser | domain.pii_masking |
| service.settings | core |
| service.skills_normalize | core |
| service.skills_normalize | domain.pii_masking |
| service.skills_normalize | domain.skills_lexicon |
| service.skills_normalize | preprocess_skills |
| service.text_extract | infra.documents |
| training.checkpoints | core |
| training.config_train | core |
| training.dataset | core |
| training.feature_map | job_matching |
| training.feature_map | pair_features |
| training.feature_map | preprocess_skills |
| training.trainer | core |

## 第三方库依赖（按模块）

| 模块 | 第三方库 |
|---|---|
| annotation.agreement | __future__, collections |
| annotation.arbitration | __future__, pandas, pathlib |
| annotation.blind_guard | __future__ |
| annotation.completion | __future__ |
| annotation.consent | __future__, re |
| annotation.dedup | __future__, collections, hashlib, math, re, unicodedata |
| annotation.freeze | __future__, json, numpy, pandas, pathlib, shutil, time |
| annotation.gold_gate | __future__ |
| annotation.importer | __future__, json, pandas, pathlib |
| annotation.pii | __future__ |
| annotation.pool | __future__, json, numpy, pandas, pathlib, re |
| annotation.resume_intake | __future__, csv, json, pathlib, re, zipfile |
| annotation.schema | __future__, datetime, re |
| baseline_education | __future__, collections, json, numpy, pandas, re, time |
| baseline_ranking | __future__, numpy, pandas, time |
| config | __future__, pathlib, yaml |
| core | __future__, hashlib, json, logging, numpy, os, pathlib, sys, time, unicodedata |
| domain.job_rules | __future__, re |
| domain.pii_masking | __future__, re |
| domain.skills_lexicon | __future__, re |
| education.dataset | __future__, json, numpy, pandas, pathlib |
| education.evaluator | __future__, numpy |
| education.labels | __future__, numpy |
| education.neural_model | __future__, pathlib, torch |
| education.predictor | __future__, json, numpy, pathlib, torch |
| education.rules | __future__, numpy |
| education.tfidf_model | __future__, numpy, pathlib, pickle, sklearn |
| education.tokenizer | __future__, json, numpy, pathlib |
| education.trainer | __future__, numpy, pathlib, random, time, torch |
| education_data | __future__, numpy, pandas, pathlib, time |
| embeddings | __future__, ast, numpy, pandas, pathlib, time |
| evaluation.error_analysis | __future__, numpy, pandas |
| evaluation.metrics | __future__, numpy, pandas, scipy |
| evaluation.statistical_tests | __future__, numpy |
| independent_eval.baselines | __future__, json, numpy, pathlib, sklearn |
| independent_eval.bootstrap | __future__, numpy |
| independent_eval.dataset | __future__, json, numpy, pandas, pathlib |
| independent_eval.metrics | __future__, numpy |
| inference.predictor | __future__, json, numpy, pathlib |
| infra.documents | __future__, fitz, pathlib, re, zipfile |
| metrics_classification | __future__, numpy |
| metrics_ranking | __future__, numpy, pandas |
| models.base | __future__, importlib, numpy, torch |
| models.gradient_boosting | __future__, itertools, joblib, numpy, pathlib, sklearn, time |
| models.mlp | __future__, itertools, numpy, pathlib, time, torch |
| models.ranknet | __future__, itertools, numpy, pathlib, time, torch |
| models.ridge | __future__, itertools, joblib, numpy, pathlib, sklearn, time |
| pair_features | __future__, json, numpy, pandas, re |
| pipeline | __future__, json, numpy, pandas, pathlib, subprocess, sys, time, torch |
| policy | __future__, dataclasses, numpy, pandas |
| preprocess_education | __future__, numpy, re, unicodedata |
| preprocess_job | __future__, json, pandas, pathlib |
| preprocess_resume | __future__, json, pandas, pathlib |
| preprocess_risk | __future__, numpy, pandas, pathlib |
| preprocess_skills | __future__, ast, json, re, unicodedata |
| reporting | __future__, pathlib, time |
| schema | __future__, dataclasses, numpy, pandas |
| service.api | __future__, base64, dataclasses, fastapi, pathlib, pydantic, re, time, typing, uvicorn |
| service.contracts | __future__, dataclasses, typing |
| service.errors | __future__, re |
| service.explanations | __future__, re |
| service.job_parser | __future__, pathlib, re |
| service.logging_utils | __future__, logging, uuid |
| service.matching | __future__, collections, dataclasses, json, time |
| service.model_registry | __future__, dataclasses, pathlib, typing |
| service.requirements | __future__, re |
| service.resume_parser | __future__, pathlib, re |
| service.settings | __future__, dataclasses, os, pathlib |
| service.skills_normalize | __future__, re |
| service.text_extract | __future__, pathlib, tempfile, zipfile |
| split_matching | __future__, numpy, pandas, pathlib, time |
| training.checkpoints | __future__, json, numpy, pandas, pathlib, platform, sklearn, time, torch |
| training.config_train | __future__, pathlib, yaml |
| training.dataset | __future__, dataclasses, numpy, pandas, pathlib |
| training.feature_map | __future__, json, numpy, pandas, pathlib |
| training.pair_sampler | __future__, dataclasses, numpy |
| training.trainer | __future__, numpy, pathlib, random, time, torch |
