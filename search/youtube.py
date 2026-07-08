"""
search/youtube.py — YouTube surgical video search.
Optional: Gemini full-video analysis when GEMINI_API_KEY is set.
"""
import re, time, requests
from urllib.parse import quote_plus
from cram.config import RESULTS_PER_SOURCE, REQUEST_TIMEOUT, GEMINI_API_KEY
from cram.log import log, dim, yellow
from cram.search.base import cached_search


def _fetch_transcript(video_id: str) -> str:
    """Attempt to extract auto-captions from YouTube page."""
    try:
        r = requests.get(
            f"https://www.youtube.com/watch?v={video_id}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        r.raise_for_status()
        tracks = re.findall(r'"captionTracks":(\[.*?\])', r.text)
        if tracks:
            t = __import__("json").loads(tracks[0])
            if t:
                tr_url = t[0].get("baseUrl", "")
                if tr_url:
                    tr = requests.get(tr_url, timeout=10)
                    tr.raise_for_status()
                    segments = re.findall(r'<text[^>]*>([^<]+)</text>', tr.text)
                    return " ".join(segments)[:2000]
    except Exception:
        pass
    return ""


def tool_gemini_youtube(video_id: str, clinical_question: str) -> str:
    """
    Send YouTube video to Gemini for surgical content extraction.
    Free tier: 1M tokens/min on gemini-1.5-flash.
    Requires GEMINI_API_KEY from aistudio.google.com.
    """
    if not GEMINI_API_KEY:
        return "[GEMINI_API_KEY not set — YouTube full analysis unavailable]"
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            f"This is a medical/surgical video. Extract information relevant to:\n"
            f"{clinical_question}\n\n"
            f"Structure your response as:\n"
            f"TECHNIQUE: [surgical steps demonstrated]\n"
            f"INSTRUMENTS: [specific tools used]\n"
            f"ANATOMY: [landmarks called out]\n"
            f"COMPLICATIONS: [any shown or discussed]\n"
            f"EVIDENCE CITED: [any studies or outcomes mentioned by the presenter]\n"
            f"KEY QUOTES: [specific statements about outcomes/evidence, under 15 words each]"
        )
        response = model.generate_content([
            {"video_metadata": {"video_uri": f"https://www.youtube.com/watch?v={video_id}"}},
            prompt,
        ])
        return response.text[:2000]
    except Exception as e:
        log(yellow(f"     ⚠  Gemini YouTube error for {video_id}: {e}"))
        return _fetch_transcript(video_id)


@cached_search("YouTube")
def tool_youtube(query: str, max_results: int = RESULTS_PER_SOURCE,
                 clinical_question: str = "") -> list[dict]:
    results = []
    log(dim(f"     🎬 YouTube ← \"{query[:72]}\""))
    try:
        r = requests.get(
            "https://www.youtube.com/results",
            params={"search_query": f"{query} surgery technique medical"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        seen, count = set(), 0
        for vid in re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', r.text):
            if vid in seen or count >= max_results:
                continue
            seen.add(vid)
            # Use Gemini if available, otherwise fall back to transcript scraping
            if GEMINI_API_KEY and clinical_question:
                content = tool_gemini_youtube(vid, clinical_question)
            else:
                content = _fetch_transcript(vid)
            results.append({
                "source":  "YouTube",
                "url":     f"https://www.youtube.com/watch?v={vid}",
                "title":   f"[Video+Analysis] {query}" if content else f"[Video] {query}",
                "snippet": content[:500] if content else "Surgical video (content unavailable)",
            })
            count += 1
        log(dim(f"     🎬 → {len(results)} videos"))
        time.sleep(0.3)
    except Exception as e:
        log(yellow(f"     ⚠  YouTube error: {e}"))
    return results
