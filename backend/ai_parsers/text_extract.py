import json
import re
from .common import EXPECTED_KEYS


_THINK_CLOSED_RE = re.compile(r'<(think|thinking|reasoning|thought|analysis)>.*?</\1>', re.I | re.S)


_THINK_OPEN_RE = re.compile(r'<(think|thinking|reasoning|thought|analysis)>', re.I)


_FENCE_RE = re.compile(r'```[a-zA-Z0-9_+-]*')


def extract_text(content) -> str:
    """Mengubah 'content' pesan model (str / list part / dict / None) menjadi teks biasa."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if any(k in content for k in EXPECTED_KEYS):
            return json.dumps(content, ensure_ascii=False)
        for k in ("text", "content", "output_text", "value"):
            v = content.get(k)
            if isinstance(v, (str, list, dict)):
                t = extract_text(v)
                if t:
                    return t
        return json.dumps(content, ensure_ascii=False)
    if isinstance(content, (list, tuple)):
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") in ("thinking", "reasoning", "redacted_thinking"):
                continue
            t = extract_text(p)
            if t:
                parts.append(t)
        return "\n".join(parts)
    return str(content)


def _looks_like_result(t: str) -> bool:
    """True bila teks (mis. dari reasoning_content) tampak memuat objek hasil analisis, bukan sekadar kurung kurawal
    dalam kalimat berpikir model (perintah shell, contoh jq, dst)."""
    return bool(t) and "{" in t and ('"diagnosis"' in t or '"anomalies"' in t or '"structures"' in t)


def extract_message_text(message) -> str:
    """Ambil teks jawaban dari objek 'message' respons chat-completions. Jika 'content' kosong atau
    tidak memuat objek JSON, coba 'reasoning_content'/'reasoning' (sebagian router menaruh jawaban di sana).
    Teks penalaran hanya diterima bila memuat kunci hasil yang diharapkan (lihat _looks_like_result); selain itu diabaikan."""
    if not isinstance(message, dict):
        return extract_text(message)
    main = extract_text(message.get("content"))
    if main.strip() and "{" in _strip_reasoning(main):
        return main
    for k in ("reasoning_content", "reasoning", "thinking"):
        alt = extract_text(message.get(k))
        if alt and _looks_like_result(alt):
            return (main + "\n" + alt) if main.strip() else alt
    for k in ("parsed", "function_call", "tool_calls"):
        v = message.get(k)
        if v:
            if k == "tool_calls" and isinstance(v, list):
                for tc in v:
                    args = (tc or {}).get("function", {}).get("arguments")
                    if isinstance(args, str) and "{" in args:
                        return args
            elif isinstance(v, dict):
                args = v.get("arguments")
                if isinstance(args, str) and "{" in args:
                    return args
                return json.dumps(v, ensure_ascii=False)
    return main


def _strip_reasoning(text: str) -> str:
    """Buang blok <think>…</think> (termasuk yang tidak ditutup) dan pagar kode markdown."""
    t = _THINK_CLOSED_RE.sub(" ", text)
    m = _THINK_OPEN_RE.search(t)
    if m:
        after = t[m.end():]
        # tag dibuka tapi tak pernah ditutup: sisa teks mungkin masih berisi JSON jawaban
        t = t[:m.start()] + (after if "{" in after and '"diagnosis"' in after else " ")
    t = _FENCE_RE.sub(" ", t).replace("```", " ")
    return t.strip()
