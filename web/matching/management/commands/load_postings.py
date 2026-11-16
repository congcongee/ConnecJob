"""통합 공고 표(data/processed/postings.csv) → Posting 테이블 : python manage.py load_postings

공고 표를 다시 만들면 (code/build_postings.py) 이 명령을 다시 실행. 표 전체를 지우고 새로 넣음.
"""
from datetime import date

import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction

from recommend import DATA_DIR
from matching.models import Posting


def to_date(text):
  try:
    return date.fromisoformat(text[:10])
  except ValueError: # '' (상시·형식 불명)
    return None


class Command(BaseCommand):
  help = "postings.csv 를 Posting 테이블로 불러오기 (기존 공고는 지움)"

  def handle(self, *args, **options):
    path = DATA_DIR / "processed" / "postings.csv"
    df = pd.read_csv(path, dtype=str, keep_default_na=False) # 빈칸을 NaN 대신 '' 로
    rows = []
    for r in df.to_dict("records"):
      rows.append(Posting(
        doc_id=r["doc_id"], source=r["source"], title=r["title"], company=r["기업명"],
        category=r["category"], size=r["기업규모"], region=r["시도"], career=r["경력"],
        deadline=to_date(r["마감일"]), url=r["url"], tech_tags=r["기술태그"], cert_tags=r["자격증태그"],
        job_groups="" if r["직무묶음"] == "범위밖" else r["직무묶음"], content=r["page_content"]))
    with transaction.atomic(): # 중간에 실패하면 예전 공고가 그대로 남음
      Posting.objects.all().delete()
      Posting.objects.bulk_create(rows, batch_size=2000)
    self.stdout.write(f"공고 {len(rows)}건을 불러왔습니다.")
