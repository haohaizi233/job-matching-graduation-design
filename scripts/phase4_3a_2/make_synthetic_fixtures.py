# -*- coding: utf-8 -*-
"""生成合成简历测试夹具（仅用于工具链验证，is_synthetic 语义，永不进人工 Gold）。

用法: python scripts/phase4_3a_2/make_synthetic_fixtures.py
产物: tests/fixtures/synthetic_resumes/{resume_synth_01.txt,.csv,.jsonl,.docx}
"""
from __future__ import annotations

import csv
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _bootstrap  # noqa: F401,E402

from job_matching.core import ROOT  # noqa: E402

OUT = ROOT / "tests" / "fixtures" / "synthetic_resumes"

TXT = (
    "求职意向：数据分析师。教育背景：本科，2027 届，统计学专业。\n"
    "项目经历：参与数据平台建设，负责报表体系与指标口径治理。\n"
    "技能：python、sql、数据分析、etl。\n"
    "（合成测试夹具，非真实个人简历）\n"
)

CSV_ROWS = [
    {"resume_text": "求职意向：Java 开发工程师。教育背景：本科，2027 届。"
                    "项目经历：参与微服务后端开发。技能：java、spring、mysql。",
     "target_position": "Java 开发工程师", "skills": "java,spring,mysql",
     "education_level": "本科", "graduation_cohort": "2027", "employment_type": "校招",
     "years_experience": "1", "city": "上海", "salary_expectation": "面议",
     "license": "synthetic-generated-local"},
    {"resume_text": "求职意向：软件测试。教育背景：本科，2027 届。"
                    "项目经历：负责接口测试与自动化脚本。技能：selenium、python、测试用例。",
     "target_position": "软件测试", "skills": "selenium,python,测试用例",
     "education_level": "本科", "graduation_cohort": "2027", "employment_type": "校招",
     "years_experience": "0", "city": "北京", "salary_expectation": "面议",
     "license": "synthetic-generated-local"},
]

JSONL_ROW = {
    "resume_text": "求职意向：Web 前端开发。教育背景：本科，2027 届。"
                   "项目经历：负责管理后台前端开发。技能：javascript、vue、css。",
    "target_position": "Web 前端开发", "skills": "javascript,vue,css",
    "education_level": "本科", "graduation_cohort": "2027", "employment_type": "校招",
    "years_experience": "1", "city": "深圳", "salary_expectation": "面议",
    "license": "synthetic-generated-local",
}

DOCX_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body>"
    "<w:p><w:r><w:t>求职意向：数据分析实习生。教育背景：本科，2027 届。</w:t></w:r></w:p>"
    "<w:p><w:r><w:t>项目经历：参与数据分析报告撰写。技能：python、sql、tableau。</w:t></w:r></w:p>"
    "<w:p><w:r><w:t>（合成测试夹具，非真实个人简历）</w:t></w:r></w:p>"
    "</w:body></w:document>"
)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "resume_synth_01.txt").write_text(TXT, encoding="utf-8", newline="\n")

    with open(OUT / "resume_synth_02.csv", "w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=list(CSV_ROWS[0].keys()), lineterminator="\n")
        w.writeheader()
        for r in CSV_ROWS:
            w.writerow(r)

    with open(OUT / "resume_synth_03.jsonl", "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(JSONL_ROW, ensure_ascii=False, sort_keys=True) + "\n")

    with zipfile.ZipFile(OUT / "resume_synth_04.docx", "w") as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
                   'package/2006/content-types"><Default Extension="xml" '
                   'ContentType="application/xml"/></Types>')
        z.writestr("word/document.xml", DOCX_XML)

    print(json.dumps({"status": "ok", "out": str(OUT.relative_to(ROOT)).replace("\\", "/"),
                      "files": sorted(p.name for p in OUT.iterdir())},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
