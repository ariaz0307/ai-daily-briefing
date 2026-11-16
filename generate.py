
import os
import json
import re
import html
import time
import datetime
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path

# ========================================
# 기본 설정
# ========================================

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)

KST = datetime.timezone(datetime.timedelta(hours=9))
NOW = datetime.datetime.now(KST)

MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite"
).strip()

API_KEY = os.environ.get(
    "GEMINI_API_KEY",
    ""
).strip()

FEEDS = [
    (
        "AI / LLM",
        "AI LLM agents OpenAI Google Anthropic"
    ),
    (
        "Automation",
        "AI agent enterprise workflow automation"
    ),
    (
        "Commerce",
        "agentic commerce ecommerce retail AI"
    ),
    (
        "Korea",
        "한국 이커머스 AI 에이전트 쇼핑"
    )
]


# ========================================
# RSS 수집
# ========================================

def fetch(url, timeout=20):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 AI-Daily-Briefing",
            "Accept": "application/rss+xml,application/xml,*/*"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout
    ) as response:
        return response.read()


def clean_text(value):
    value = value or ""

    value = re.sub(
        r"<[^>]*>",
        " ",
        value
    )

    value = html.unescape(value)

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()[:650]


def collect_news():
    items = []
    seen = set()

    for category, query in FEEDS:

        params = {
            "q": query + " when:3d",
            "hl": "ko",
            "gl": "KR",
            "ceid": "KR:ko"
        }

        url = (
            "https://news.google.com/rss/search?"
            + urllib.parse.urlencode(params)
        )

        try:
            root = ET.fromstring(fetch(url))

            for node in root.findall(".//item")[:18]:

                title = clean_text(
                    node.findtext("title")
                )

                link = (
                    node.findtext("link") or ""
                ).strip()

                description = clean_text(
                    node.findtext("description")
                )

                published = (
                    node.findtext("pubDate") or ""
                ).strip()

                if not title or not link:
                    continue

                normalized = title.lower()

                if normalized in seen:
                    continue

                seen.add(normalized)

                items.append({
                    "category": category,
                    "title": title,
                    "url": link,
                    "summary": description,
                    "published": published
                })

        except Exception as error:
            print(
                "RSS warning:",
                category,
                str(error)
            )

    return items[:65]


# ========================================
# Gemini API 호출
# ========================================

def call_gemini(prompt):

    if not API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing"
        )

    endpoint = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        + urllib.parse.quote(MODEL, safe="")
        + ":generateContent"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.25,
            "maxOutputTokens": 2800
        }
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(
            payload
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": API_KEY
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=100
        ) as response:
            result = json.load(response)

    except urllib.error.HTTPError as error:

        detail = error.read().decode(
            "utf-8",
            errors="replace"
        )

        print(
            "Gemini API HTTP status:",
            error.code
        )

        # API 오류 응답에 인증정보가
        # 포함되지 않도록 키 문자열 제거
        detail = detail.replace(
            API_KEY,
            "[REDACTED]"
        )

        print(
            "Gemini API error:",
            detail[:1500]
        )

        raise RuntimeError(
            "Gemini API request failed"
        ) from error

    candidates = result.get(
        "candidates",
        []
    )

    if not candidates:
        raise RuntimeError(
            "Gemini returned no candidates"
        )

    parts = candidates[0].get(
        "content",
        {}
    ).get("parts", [])

    raw = "".join(
        part.get("text", "")
        for part in parts
    )

    if not raw:
        raise RuntimeError(
            "Gemini returned empty content"
        )

    return json.loads(raw)


# ========================================
# AI 브리핑 생성
# ========================================

def generate_briefing(items):

    prompt = """
당신은 한국 이커머스 MD를 위한
AI 기술 뉴스 전문 편집자입니다.

제공된 RSS 뉴스 중 가장 중요한
뉴스 5건을 선정하세요.

관심 주제:
1. AI 및 LLM 기술
2. AI 에이전트
3. 업무 자동화와 생산성
4. 이커머스와 쇼핑 운영
5. 판매자 및 행사 운영 자동화

선정 기준:
- 최근 뉴스 우선
- 서로 다른 이슈 선정
- 광고성 기사 제외
- 중복 뉴스 제외
- 실제 업무 적용 가능성 중시

반드시 제공된 뉴스 정보만 사용하세요.
출처에 없는 사실이나 수치를
만들어내지 마세요.

각 뉴스에 대해 다음을 작성하세요.

1. title: 한국어 제목
2. summary: 핵심 내용 2문장
3. why_it_matters:
   쇼핑몰 MD 업무에 중요한 이유
4. action:
   실제 적용할 수 있는 기능 제안

정확히 5개를 선정하세요.

반드시 다음 JSON 구조로 출력하세요.

{
  "headline": "오늘의 핵심 한 문장",
  "items": [
    {
      "source_index": 0,
      "title": "뉴스 제목",
      "summary": "핵심 내용",
      "why_it_matters": "MD 업무 중요성",
      "action": "추천 적용 기능"
    }
  ]
}

source_index는 제공된 뉴스 목록의
index 값을 사용해야 합니다.

뉴스 목록:
"""

    sources = [
        {
            "index": index,
            **item
        }
        for index, item in enumerate(items)
    ]

    prompt += json.dumps(
        sources,
        ensure_ascii=False
    )

    result = call_gemini(prompt)

    output = []
    used = set()

    for item in result.get("items", []):

        index = item.get("source_index")

        if not isinstance(index, int):
            continue

        if index < 0 or index >= len(items):
            continue

        if index in used:
            continue

        used.add(index)

        source = items[index]

        output.append({
            "title": str(
                item.get("title", "")
            )[:160],
            "summary": str(
                item.get("summary", "")
            )[:700],
            "why_it_matters": str(
                item.get("why_it_matters", "")
            )[:600],
            "action": str(
                item.get("action", "")
            )[:350],
            "url": source["url"],
            "source": source["title"],
            "published": source["published"],
            "category": source["category"]
        })

        if len(output) == 5:
            break

    if len(output) != 5:
        raise RuntimeError(
            "Gemini did not return five valid news items"
        )

    return {
        "date": NOW.date().isoformat(),
        "generated_at": NOW.isoformat(),
        "headline": str(
            result.get("headline", "")
        )[:300],
        "items": output,
        "note": (
            "RSS 제목과 요약을 기반으로 "
            "AI가 생성했습니다. "
            "세부 내용은 원문을 확인하세요."
        )
    }


# ========================================
# 메인 실행
# ========================================

def main():

    print("AI Daily Briefing started")
    print("Date:", NOW.date())
    print("Gemini model:", MODEL)

    items = collect_news()

    print(
        "RSS candidates:",
        len(items)
    )

    if len(items) < 5:
        raise RuntimeError(
            "Not enough RSS candidates"
        )

    briefing = generate_briefing(items)

    output_file = (
        DOCS / "briefing.json"
    )

    output_file.write_text(
        json.dumps(
            briefing,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        "Successfully generated:",
        output_file
    )


if __name__ == "__main__":
    main()
