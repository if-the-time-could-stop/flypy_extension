# -*- coding: utf-8 -*-
"""
将形码表 + 拼音库 合并生成 小鹤“音形码”
输出：每行  汉字<TAB>音形码（前两位：小鹤双拼；后两位：形码首+末）
约束：
- 若任一行形码长度 == 1，立即报错退出（视为上一步出错）
- 忽略拼音库中的空行与 '#' 之后的注释
- 拼音去调并将 ü 统一为 v
- 多音字 × 多形码 全部穷举
"""

from __future__ import annotations
import re
from typing import Dict, List, Tuple, Set
from collections import defaultdict

# ========== 路径配置（请按需修改） ==========
SHAPE_FILE = "./output.txt"     # 上一步输出：每行“汉字<TAB>形码”
PINYIN_DB_FILE = "./zdic.txt"       # Github 拼音库：每行“U+XXXX: pīnyīn”
OUT_FILE = "./xhe_final_yinxing.txt"     # 输出“汉字<TAB>音形码”
ERR_LOG = "./xhe_generate_error.log"     # 辅助日志
# ===========================================

# 你提供的小鹤双拼表（v 表示 ü）
_RAW_XIAOHE = """
Q iu
W ei
R uan
T ue, ve
Y un
U sh
I ch
O uo
P ie
S iong, ong
D ai
F en
G eng
H ang
J an
K ing, uai
L iang, uang
Z ou
X ia, ua
C ao
V ui
B in
N iao
M ian
"""

# 参与 longest-match 的常见声母（按长度降序匹配）
_INITIALS = [
    "zh", "ch", "sh",
    "b","p","m","f","d","t","n","l",
    "g","k","h","j","q","x","r","z","c","s",
    "y","w"
]

# 单韵母集合（用于零声母规则）
_SINGLE_VOWELS = {"a", "o", "e", "i", "u", "v"}

# 去声调并 ü→v
_TONE_MAP = str.maketrans({
    "ā":"a","á":"a","ǎ":"a","à":"a",
    "ē":"e","é":"e","ě":"e","è":"e",
    "ī":"i","í":"i","ǐ":"i","ì":"i",
    "ō":"o","ó":"o","ǒ":"o","ò":"o",
    "ū":"u","ú":"u","ǔ":"u","ù":"u",
    "ǖ":"v","ǘ":"v","ǚ":"v","ǜ":"v",
    "ü":"v",
    "ń":"n","ň":"n","ǹ":"n",
    "ḿ":"m"
})

def _remove_tone(s: str) -> str:
    s = s.strip().translate(_TONE_MAP)
    # 删除数字声调（如 ni3）
    s = re.sub(r"\d+$", "", s)
    return s

def _build_xiaohe_map(raw: str) -> Dict[str, str]:
    """
    将“键 字母 ← token 列表”解析为 token→键字母 的映射
    """
    m: Dict[str, str] = {}
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        key, toks = line.split(None, 1)
        key = key.strip().lower()
        for tok in toks.split(","):
            tok = tok.strip().lower()
            if tok:
                m[tok] = key
    return m

_XH = _build_xiaohe_map(_RAW_XIAOHE)

def _split_initial_final(pinyin: str) -> Tuple[str, str]:
    """
    最长匹配声母，返回 (initial, final)
    若找不到声母（以元音开头）→ initial=""
    """
    p = pinyin
    for init in sorted(_INITIALS, key=lambda s: -len(s)):
        if p.startswith(init):
            return init, p[len(init):]
    return "", p

def _xiaohe_double_for_zero_initial(final: str) -> Tuple[str, str]:
    """
    零声母规则：
      - 单韵母：x -> (x, x)
      - 复韵母：-> (首字母, 韵母键)
    """
    if not final:
        # 极端情况，不该发生
        return "", ""

    if final in _SINGLE_VOWELS or (len(final) == 1 and final.isalpha()):
        return final[0], final[0]

    # 复韵母：第二码取映射（优先完整匹配，其次最长匹配）
    second = None
    if final in _XH:
        second = _XH[final]
    else:
        for k in sorted(_XH.keys(), key=lambda s: -len(s)):
            if final.endswith(k):  # 后缀最长匹配
                second = _XH[k]
                break
        if second is None:
            # 实在匹配不到，保底：用首字母
            second = final[0]

    first = final[0]
    return first, second

def _xiaohe_double(pinyin: str) -> Tuple[str, str]:
    """
    将不带声调、已 ü→v 的拼音，转换为小鹤双拼的两码（字母、字母）
    规则：
      - 零声母：用 _xiaohe_double_for_zero_initial
      - 非零声母：
         * 第一位：声母键（若无映射，用声母首字母）
         * 第二位：韵母键（完整匹配；否则最长匹配后缀；再否则用韵母首字母）
    备注：
      - 这里不对 y/w 做“零声母化”，它们仍视作声母；只有真正以元音开头的音节才算零声母。
    """
    init, fin = _split_initial_final(pinyin)

    # 零声母
    if init == "":
        return _xiaohe_double_for_zero_initial(fin)

    # 第一位（声母）
    if init in _XH:
        first = _XH[init]
    else:
        first = init[0]  # 回退：首字母

    # 第二位（韵母）
    if fin in _XH:
        second = _XH[fin]
    else:
        matched = None
        for k in sorted(_XH.keys(), key=lambda s: -len(s)):
            if fin.endswith(k):
                matched = _XH[k]
                break
        second = matched if matched else (fin[0] if fin else "")

    if not first or not second:
        raise ValueError(f"无法映射拼音到小鹤双拼：{pinyin} -> ({init}, {fin})")

    return first, second

def _load_shape_table(path: str) -> Dict[str, List[str]]:
    """
    读取形码表：每行“汉字<TAB>形码”
    返回：汉字 -> [形码...]
    """
    mp: Dict[str, List[str]] = defaultdict(list)
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.rstrip("\n\r")
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                raise ValueError(f"形码表第{ln}行格式错误：{line}")
            ch, code = parts[0], parts[1]
            mp[ch].append(code)
    return mp

def _load_pinyin_db(path: str) -> Dict[str, List[str]]:
    """
    读取拼音库：每行“U+XXXX: pīnyīn  [# 注释]”
    忽略空行和 # 之后内容；去调、ü→v；多读音去重保序。
    返回：汉字 -> [pinyin...]
    """
    mp: Dict[str, List[str]] = defaultdict(list)
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            m = re.match(r"U\+([0-9A-Fa-f]+)\s*:\s*(.+)$", line)
            if not m:
                # 非法行跳过
                continue
            code_hex = m.group(1)
            payload = m.group(2).strip()
            try:
                ch = chr(int(code_hex, 16))
            except Exception:
                continue

            # 逗号分隔多个候选，再按空白细分
            raw_list: List[str] = []
            for block in payload.split(","):
                block = block.strip()
                if not block:
                    continue
                for token in block.split():
                    token = token.strip()
                    if token:
                        raw_list.append(token)

            # 归一：去调、转小写、ü→v
            norm_list: List[str] = []
            for p in raw_list:
                p0 = _remove_tone(p).lower().replace("ü", "v")
                if p0:
                    norm_list.append(p0)

            # 去重保序后加入
            seen: Set[str] = set()
            uniq: List[str] = []
            for p in norm_list:
                if p not in seen:
                    seen.add(p)
                    uniq.append(p)
            if uniq:
                mp[ch].extend(uniq)
    return mp

def main():
    shape_map = _load_shape_table(SHAPE_FILE)      # 汉字 -> [形码...]
    pinyin_map = _load_pinyin_db(PINYIN_DB_FILE)   # 汉字 -> [拼音...]

    out_lines: List[str] = []
    missing_pinyin: Set[str] = set()
    cannot_convert: List[Tuple[str, str]] = []  # (汉字, 拼音)

    # 逐字处理（保证同一汉字的行连续：先收集再统一 append）
    for ch, shape_list in shape_map.items():
        pinyins = pinyin_map.get(ch)
        if not pinyins:
            # 形码表里有，但拼音库没有
            missing_pinyin.add(ch)
            continue

        char_lines: List[str] = []

        for shape in shape_list:
            # 形码长度检查：若为 1，立即报错退出
            if len(shape) < 2:
                # 立刻报错（不写输出）
                with open(ERR_LOG, "w", encoding="utf-8") as ef:
                    ef.write("ERROR: 发现形码长度为 1 的条目，需回到上一步修正拆分/字根。\n")
                    ef.write(f"{ch}\t{shape}\n")
                raise SystemExit(f"形码长度为 1：{ch} -> {shape}（已写入 {ERR_LOG}）")

            # 形码后两位：首 + 末
            s_first, s_last = shape[0], shape[-1]

            for p in pinyins:
                try:
                    a, b = _xiaohe_double(p)  # 前两位
                except Exception:
                    cannot_convert.append((ch, p))
                    continue
                full = a + b + s_first + s_last
                char_lines.append(f"{ch}\t{full}")

        out_lines.extend(char_lines)

    # 写输出
    with open(OUT_FILE, "w", encoding="utf-8") as fo:
        for line in out_lines:
            fo.write(line + "\n")

    # 写辅助日志
    with open(ERR_LOG, "w", encoding="utf-8") as ef:
        if missing_pinyin:
            ef.write("MISSING PINYIN（形码表中存在、但拼音库缺失的汉字）：\n")
            ef.write("".join(sorted(missing_pinyin)) + "\n\n")
        if cannot_convert:
            ef.write("CANNOT CONVERT（无法按映射生成双拼的拼音）：\n")
            for ch, p in cannot_convert:
                ef.write(f"{ch}\t{p}\n")
            ef.write("\n")
        ef.write(f"SUMMARY: 输出行数 = {len(out_lines)}\n")

    print(f"完成。输出 {len(out_lines)} 行到 {OUT_FILE}；详情见 {ERR_LOG}。")
    if missing_pinyin:
        print(f"注意：有 {len(missing_pinyin)} 个汉字在拼音库中缺失拼音（见 {ERR_LOG}）。")
    if cannot_convert:
        print(f"注意：有 {len(cannot_convert)} 条拼音未能映射为双拼（见 {ERR_LOG}）。")

if __name__ == "__main__":
    main()
