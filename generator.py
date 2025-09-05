import re

# ===== 路径配置 =====
ROOT_FILE = "parts.txt"          # 字根表
DICT_FILE = "chaizi-jt.txt"           # 拆分库
OUTPUT_FILE = "output.txt"       # 生成的码表
MISSING_LOG = "missing.log"      # 缺失字根日志
SINGLECODE_LOG = "singlecode.log"  # 单码失败日志

# ===== 特殊替换规则 =====
REPLACEMENTS = {
    "甘一": "其上",
    "目一": "具上",
    "于八": "余下",
}

def apply_replacements(parts):
    """应用替换规则"""
    s = "".join(parts)
    for k, v in REPLACEMENTS.items():
        s = s.replace(k, v)
    return list(s)  # 拆成部件列表


# ===== 文件读取 =====
def load_roots(path):
    """加载字根表"""
    rootmap = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            letter = line[0]
            for root in line[1:]:
                rootmap[root] = letter
    return rootmap


def load_decomposition(path):
    """加载拆分库"""
    decomposition = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            char, *parts = line.split("\t")
            decomposition[char] = [list(p) for p in parts]
    return decomposition


# ===== 拆分与取码 =====
def expand_part(part, decomposition, rootmap, visited, missing_roots):
    """递归展开某个部件，直到落到字根表或失败"""
    if part in rootmap:
        return [part]
    if part in visited:
        return None  # 避免死循环
    visited.add(part)

    if part in decomposition:
        for sub_parts in decomposition[part]:
            sub_parts = apply_replacements(sub_parts)
            expanded = []
            success = True
            for sp in sub_parts:
                res = expand_part(sp, decomposition, rootmap, visited, missing_roots)
                if res is None:
                    success = False
                    break
                expanded.extend(res)
            if success:
                return expanded

    # 无法继续拆分 → 记入缺失字根
    missing_roots.add(part)
    return None


def get_code_for_decomp(parts, decomposition, rootmap, missing_roots, singlecode_chars, char):
    """获取某种拆分方式的编码"""
    expanded = []
    for p in apply_replacements(parts):
        res = expand_part(p, decomposition, rootmap, set(), missing_roots)
        if res is None:
            return None
        expanded.extend(res)

    codes = [rootmap[p] for p in expanded if p in rootmap]
    if not codes:
        return None

    # 如果拆分结果只有 1 位编码 → 视为失败
    if len(codes) == 1:
        singlecode_chars.append((char, "".join(parts)))
        return None

    # 取码逻辑：首二三末
    if len(codes) >= 4:
        return codes[0] + codes[1] + codes[2] + codes[-1]
    else:
        return "".join(codes)


# ===== 主程序 =====
def main():
    rootmap = load_roots(ROOT_FILE)
    decomposition = load_decomposition(DICT_FILE)

    missing_roots = set()
    singlecode_chars = []

    missing_lines = []  # 暂存缺失日志

    with open(OUTPUT_FILE, "w", encoding="utf-8") as fout:
        for char, decomps in decomposition.items():
            success = False
            for parts in decomps:
                code = get_code_for_decomp(parts, decomposition, rootmap,
                                           missing_roots, singlecode_chars, char)
                if code:
                    fout.write(f"{char}\t{code}\n")
                    success = True
            if not success:
                for parts in decomps:
                    missing_lines.append(f"{char}\t{''.join(parts)}\n")

    # 写缺失字根日志
    with open(MISSING_LOG, "w", encoding="utf-8") as flog:
        flog.write("".join(sorted(missing_roots)) + "\n")
        flog.writelines(missing_lines)

    # 写单码失败日志
    with open(SINGLECODE_LOG, "w", encoding="utf-8") as slog:
        for char, parts in singlecode_chars:
            slog.write(f"{char}\t{parts}\n")


if __name__ == "__main__":
    main()
