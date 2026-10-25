import json
import re
from .common import EXPECTED_KEYS
from .text_extract import _FENCE_RE, _strip_reasoning, extract_text


def _iter_json_objects(text: str, limit: int = 40):
    """Menghasilkan kandidat objek {...} (kurung seimbang, sadar string). Objek yang terpotong
    juga dihasilkan. Kandidat bersarang di dalam objek utuh dilewati."""
    n, i, produced = len(text), 0, 0
    while i < n and produced < limit:
        if text[i] != '{':
            i += 1
            continue
        depth, in_str, esc, end = 0, False, False, -1
        for j in range(i, n):
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end != -1:
            yield text[i:end + 1]
            produced += 1
            i = end + 1
        else:
            yield text[i:]       # terpotong
            produced += 1
            i += 1               # coba kurung berikutnya (mungkin '{' tadi hanyalah noise)


def _json5_lite(s: str) -> str:
    """Normalisasi 'JSON longgar' (JS/Python-like) menjadi JSON baku, sadar string."""
    s = s.replace('\u201c', '"').replace('\u201d', '"').replace('\u2018', "'").replace('\u2019', "'")
    out, i, n, prev = [], 0, len(s), '{'

    def need_comma():
        if prev == 'v':
            out.append(',')

    while i < n:
        ch = s[i]
        if ch in ' \t\r\n':
            out.append(ch)
            i += 1
            continue
        if ch == '/' and i + 1 < n and s[i + 1] == '/':
            while i < n and s[i] != '\n':
                i += 1
            continue
        if ch == '/' and i + 1 < n and s[i + 1] == '*':
            k = s.find('*/', i + 2)
            i = n if k == -1 else k + 2
            continue
        if ch in '"\'':
            q, buf = ch, []
            i += 1
            while i < n:
                c = s[i]
                if c == '\\' and i + 1 < n:
                    nxt = s[i + 1]
                    buf.append("'" if nxt == "'" else c + nxt)
                    i += 2
                    continue
                if c == q:
                    if q == '"':
                        # kutip penutup sah hanya jika diikuti , : } ] atau akhir teks
                        k = i + 1
                        while k < n and s[k] in ' \t\r\n':
                            k += 1
                        if k >= n or s[k] in ',:}]':
                            break
                        # koma hilang: kutip penutup lalu langsung key berikutnya ("a" "b": ...)
                        if s[k] == '"' and k > i + 1 and re.match(r'"[^"\n]{1,60}"\s*:', s[k:k + 80]):
                            break
                        buf.append('\\"')   # kutip tak ter-escape di dalam string
                        i += 1
                        continue
                    break
                if c == '"':
                    buf.append('\\"')
                elif c == '\n':
                    buf.append('\\n')
                elif c == '\r':
                    buf.append('\\r')
                elif c == '\t':
                    buf.append('\\t')
                elif ord(c) >= 0x20:
                    buf.append(c)
                i += 1
            i += 1
            # string ini key jika setelahnya ':' ; selain itu nilai
            if prev != ':':
                need_comma()
            out.append('"' + ''.join(buf) + '"')
            prev = 'v'
            continue
        if ch in '{[':
            if prev != ':':
                need_comma()
            out.append(ch)
            prev = ch
            i += 1
            continue
        if ch in '}]':
            out.append(ch)
            prev = 'v'
            i += 1
            continue
        if ch in ',:':
            if ch == ',' and prev in (',', '{', '[', ':'):
                i += 1          # koma ganda / koma liar
                continue
            out.append(ch)
            prev = ch
            i += 1
            continue
        if ch in '-+.0123456789':
            j = i
            while j < n and s[j] in '-+.0123456789eE':
                j += 1
            if prev != ':':
                need_comma()
            tok = s[i:j].lstrip('+')
            out.append(tok if tok not in ('-', '.', '') else '0')
            prev = 'v'
            i = j
            continue
        if ch.isalpha() or ch in '_$':
            j = i
            while j < n and (s[j].isalnum() or s[j] in '_$'):
                j += 1
            word = s[i:j]
            k = j
            while k < n and s[k] in ' \t\r\n':
                k += 1
            is_key = k < n and s[k] == ':' and prev != ':'
            if prev != ':':
                need_comma()
            if is_key:
                out.append('"' + word + '"')
            elif word.lower() in ('true', 'false'):
                out.append(word.lower())
            elif word.lower() in ('none', 'null', 'nil', 'undefined', 'nan', 'infinity'):
                out.append('null')
            else:
                out.append('"' + word + '"')
            prev = 'v'
            i = j
            continue
        i += 1   # karakter asing -> abaikan
    res = ''.join(out)
    res = re.sub(r',\s*([}\]])', r'\1', res)
    res = re.sub(r':\s*([}\]])', r': null\1', res)
    return res


def repair_truncated_json(json_str: str) -> str:
    """Menutup string/kurung JSON secara otomatis jika terpotong oleh batasan token."""
    stack, in_string, escape = [], False, False
    for char in json_str:
        if escape:
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if not in_string:
            if char in '{[':
                stack.append(char)
            elif char == '}' and stack and stack[-1] == '{':
                stack.pop()
            elif char == ']' and stack and stack[-1] == '[':
                stack.pop()
    if escape:
        json_str += '\\'
    if in_string:
        json_str += '"'
    json_str = json_str.rstrip()
    if json_str.endswith(':'):
        json_str += ' null'          # nilai terpotong tepat setelah ':'
    elif json_str.endswith(','):
        json_str = json_str[:-1]     # koma menggantung
    elif stack and stack[-1] == '{' and re.search(r'[{,]\s*"[^"]*"$', json_str):
        json_str += ': null'         # key menggantung tanpa nilai
    while stack:
        json_str += '}' if stack.pop() == '{' else ']'
    return re.sub(r',\s*([}\]])', r'\1', json_str)


def _try_load(candidate: str):
    """Coba beberapa strategi; kembalikan (obj, mode) atau (None, None)."""
    try:
        return json.loads(candidate, strict=False), 'direct'
    except Exception:
        pass
    try:
        loose = _json5_lite(candidate)
        try:
            return json.loads(loose, strict=False), 'repaired'
        except Exception:
            pass
        try:
            return json.loads(repair_truncated_json(loose), strict=False), 'truncated-repaired'
        except Exception:
            pass
    except Exception:
        pass
    try:
        import ast
        obj = ast.literal_eval(candidate)
        if isinstance(obj, (dict, list)):
            return obj, 'literal-eval'
    except Exception:
        pass
    return None, None


def _score_obj(obj) -> int:
    if not isinstance(obj, dict):
        return -1
    low = {str(k).lower() for k in obj.keys()}
    s = sum(2 for k in EXPECTED_KEYS if k in low)
    if 'diagnosis' in low or 'diagnosa' in low:
        s += 5
    if s < 2:  # dibungkus: {"result": {...}} dst.
        for k in ('result', 'results', 'data', 'response', 'output', 'analysis', 'report', 'hasil'):
            v = obj.get(k)
            if isinstance(v, dict) and _score_obj(v) >= 5:
                return 6
    return s


def parse_with_mode(raw_content):
    """Parse JSON dari keluaran model apa pun. Mengembalikan (dict|None, mode)."""
    raw = extract_text(raw_content)
    if not raw or not raw.strip():
        return None, 'empty'
    text = _strip_reasoning(raw)
    if not text:
        text = _FENCE_RE.sub(' ', raw).replace('```', ' ').strip()

    best, best_mode, best_score = None, None, -2
    # jalur cepat: seluruh teks adalah JSON
    obj, mode = _try_load(text) if text.lstrip()[:1] in '{[' else (None, None)
    if isinstance(obj, list):
        obj = next((x for x in obj if isinstance(x, dict)), None)
    if isinstance(obj, dict) and _score_obj(obj) >= 5:
        return obj, mode

    for cand in _iter_json_objects(text):
        obj, mode = _try_load(cand)
        if isinstance(obj, list):
            obj = next((x for x in obj if isinstance(x, dict)), None)
        sc = _score_obj(obj)
        if sc > best_score:
            best, best_mode, best_score = obj, mode, sc
        if sc >= 9:
            break
    if best is not None and best_score >= 0:
        # ada objek tapi tak bernilai (mis. contoh skema) -> hanya terima jika punya kunci yang dikenal
        if best_score >= 2:
            return best, best_mode
    return None, 'none'
