#!/usr/bin/env python3
"""Built-in txjx zzc merge support."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter


KEEP_ROLLBACKS = 3


@dataclass(frozen=True)
class ZzcScheme:
    root: Path
    schema: str
    ops: Path
    zzc_dir: Path
    char_dict: Path
    char_parts: Path
    index: Path
    cache_version: Path
    rollback_logs: Path


def find_scheme(root: Path) -> ZzcScheme | None:
    matches = sorted(root.glob("*.zzc.dict.yaml"))
    if not matches:
        return None
    ops = matches[0]
    schema = ops.name.removesuffix(".zzc.dict.yaml")
    zzc_dir = root / "zzc"
    return ZzcScheme(
        root=root,
        schema=schema,
        ops=ops,
        zzc_dir=zzc_dir,
        char_dict=root / f"{schema}.danzi.dict.yaml",
        char_parts=zzc_dir / "char_parts.tsv",
        index=zzc_dir / "index.tsv",
        cache_version=zzc_dir / "cache_version.txt",
        rollback_logs=zzc_dir / "撤回合并",
    )


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def parse_dict_row(line: str) -> tuple[str, str] | None:
    if not line or line.startswith("#"):
        return None
    parts = line.rstrip("\n").split("\t")
    if len(parts) < 2:
        return None
    word, code = parts[0], parts[1]
    if not word or not code:
        return None
    return word, code


def parse_ops_line(line: str) -> dict[str, str] | None:
    text = line.rstrip("\n")
    stripped = text.strip()
    if not stripped or stripped in {"---", "..."}:
        return None
    if stripped.startswith("#") or stripped.startswith("name:") or stripped.startswith("version:"):
        return None
    if stripped.startswith("sort:") or stripped.startswith("use_preset_vocabulary:") or stripped.startswith("columns:"):
        return None
    if stripped.startswith("- ") or stripped.startswith("  - "):
        return None

    parts = text.split("\t")
    if len(parts) >= 2:
        word = parts[0].strip()
        code_part = parts[1].strip()
        code, sep, comment = code_part.partition("#")
        if sep:
            comment_parts = comment.strip().split()
            mark_token = comment_parts[0] if comment_parts else ""
            mark = mark_token[:1]
            code = code.strip()
            if mark in {"+", "-", "!", "^"} and word and code:
                row = {"mark": mark, "word": word, "code": code}
                if mark_token == "+a":
                    row["append"] = "1"
                if len(comment_parts) >= 2 and comment_parts[1].isdigit():
                    row["tx"] = comment_parts[1]
                return row

    if len(parts) == 3:
        mark, word, code = parts
        if mark in {"+", "-", "!", "^"} and word and code:
            return {"mark": mark, "word": word, "code": code}
    return None


def ops_header(schema: str) -> str:
    return "\n".join(
        [
            "# Rime dictionary",
            "# encoding: utf-8",
            "---",
            f"name: {schema}.zzc",
            'version: "2026-06-20"',
            "sort: by_weight",
            "use_preset_vocabulary: false",
            "columns:",
            "  - text",
            "  - code",
            "...",
        ]
    ) + "\n"


def format_ops_row(row: dict[str, str]) -> str:
    mark = row["mark"]
    mark_token = "+a" if mark == "+" and row.get("append") else mark
    comment = mark_token
    if row.get("tx"):
        comment += f" {row['tx']}"
    return f"{row['word']}\t{row['code']} #{comment}"


def load_ops(scheme: ZzcScheme) -> list[dict[str, str]]:
    ops: list[dict[str, str]] = []
    sources = (
        scheme.ops,
        scheme.root / f"{scheme.schema}.zzc.ops.tsv",
        scheme.zzc_dir / "ops.tsv",
        scheme.zzc_dir / "pending.tsv",
    )
    for source in sources:
        if not source.exists():
            continue
        for line in read_text(source).splitlines():
            row = parse_ops_line(line)
            if row:
                ops.append(row)
    return ops


def row_key(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (
        row.get("mark", ""),
        row.get("word", ""),
        row.get("code", ""),
        row.get("append", ""),
        row.get("tx", ""),
    )


def write_ops(scheme: ZzcScheme, ops: list[dict[str, str]]) -> None:
    body = "\n".join(format_ops_row(row) for row in ops)
    write_text(scheme.ops, ops_header(scheme.schema) + (body + "\n" if body else ""))
    for legacy in (
        scheme.root / f"{scheme.schema}.zzc.ops.tsv",
        scheme.zzc_dir / "ops.tsv",
        scheme.zzc_dir / "pending.tsv",
    ):
        if legacy.exists():
            write_text(legacy, "")


def reconcile_ops_between_roots(source: Path, target: Path, logger=print) -> bool:
    source_scheme = find_scheme(source)
    target_scheme = find_scheme(target)
    if not source_scheme or not target_scheme:
        return False
    if source_scheme.schema != target_scheme.schema:
        logger(f"[zzc] 跳过合并操作记录：方案不同 {source_scheme.schema} / {target_scheme.schema}")
        return False

    combined: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for row in load_ops(source_scheme) + load_ops(target_scheme):
        key = row_key(row)
        if key in seen:
            continue
        seen.add(key)
        combined.append(row)

    before_source = len(load_ops(source_scheme))
    before_target = len(load_ops(target_scheme))
    if not combined:
        return False
    write_ops(source_scheme, combined)
    write_ops(target_scheme, combined)
    changed = len(combined) != before_source or len(combined) != before_target
    if changed:
        logger(f"[zzc] 已汇总两边操作记录：source={before_source} target={before_target} merged={len(combined)}")
    return changed


def rebuild_char_parts(scheme: ZzcScheme) -> int:
    if not scheme.char_dict.exists():
        return 0
    parts: dict[str, list[tuple[str, str, str, str]]] = {}
    for line in read_text(scheme.char_dict).splitlines():
        row = parse_dict_row(line)
        if not row:
            continue
        text, code = row
        if len(text) != 1 or len(code) < 3:
            continue
        value = (code[0], code[1], code[2], code)
        bucket = parts.setdefault(text, [])
        if value not in bucket:
            bucket.append(value)
    lines = [
        f"{text}\t{value[0]}\t{value[1]}\t{value[2]}\t{value[3]}"
        for text, values in sorted(parts.items())
        for value in values
    ]
    write_text(scheme.char_parts, "\n".join(lines) + ("\n" if lines else ""))
    return len(lines)


def final_rows_from_ops(ops: list[dict[str, str]]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    deleted: set[tuple[str, str]] = set()
    for row in reversed(ops):
        key = (row["word"], row["code"])
        if row["mark"] == "!":
            deleted.add(key)
            continue
        if row["mark"] == "^":
            continue
        if key in seen or key in deleted or not is_merge_code(key[1]):
            continue
        seen.add(key)
        rows.append(key)
    rows.sort(key=lambda item: (len(item[1]), item[1], item[0]))
    return rows


def is_merge_code(code: str) -> bool:
    return 3 <= len(code) <= 6 and code.isalpha()


def latest_order_map(ops: list[dict[str, str]]) -> dict[str, list[str]]:
    latest_tx_by_code: dict[str, str] = {}
    for row in ops:
        if row["mark"] == "^" and row.get("tx"):
            latest_tx_by_code[row["code"]] = row["tx"]
    order_map: dict[str, list[str]] = {}
    seen_by_code: dict[str, set[str]] = {}
    for row in ops:
        if row["mark"] != "^" or latest_tx_by_code.get(row["code"]) != row.get("tx"):
            continue
        seen = seen_by_code.setdefault(row["code"], set())
        if row["word"] in seen:
            continue
        seen.add(row["word"])
        order_map.setdefault(row["code"], []).append(row["word"])
    return order_map


def reorder_dict_lines(lines: list[str], order_map: dict[str, list[str]]) -> list[str]:
    if not order_map:
        return lines
    buckets: dict[str, list[tuple[int, str, str]]] = {}
    for index, line in enumerate(lines):
        row = parse_dict_row(line)
        if row and row[1] in order_map:
            buckets.setdefault(row[1], []).append((index, row[0], line))
    sorted_buckets: dict[str, list[str]] = {}
    for code, rows in buckets.items():
        rank = {word: idx for idx, word in enumerate(order_map.get(code, []))}
        rows.sort(key=lambda item: (rank.get(item[1], 1_000_000), item[0]))
        sorted_buckets[code] = [line for _, _, line in rows]
    out: list[str] = []
    inserted: set[str] = set()
    for line in lines:
        row = parse_dict_row(line)
        if row and row[1] in sorted_buckets:
            code = row[1]
            if code not in inserted:
                out.extend(sorted_buckets[code])
                inserted.add(code)
            continue
        out.append(line)
    return out


def prune_rollback_logs(scheme: ZzcScheme) -> None:
    if not scheme.rollback_logs.exists():
        return
    logs = sorted(
        [p for p in scheme.rollback_logs.iterdir() if p.is_dir() and p.name.lower() != "logs"],
        key=lambda p: p.name,
        reverse=True,
    )
    for old in logs[KEEP_ROLLBACKS:]:
        shutil.rmtree(old, ignore_errors=True)


def resolve_target_dicts(scheme: ZzcScheme, target_dicts: tuple[str, ...] = ()) -> tuple[Path, ...]:
    if not target_dicts:
        return ()
    out: list[Path] = []
    for item in target_dicts:
        path = Path(item)
        if not path.is_absolute():
            path = scheme.root / item
        out.append(path)
    return tuple(out)


def dict_code_at(lines: list[str], index: int) -> str | None:
    row = parse_dict_row(lines[index])
    if not row or not is_merge_code(row[1]):
        return None
    return row[1]


def find_insert_index(lines: list[str], code: str) -> int:
    valid_indexes: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        row = parse_dict_row(line)
        if row and is_merge_code(row[1]):
            valid_indexes.append((index, row[1]))
    if not valid_indexes:
        return len(lines)

    same_indexes = [index for index, row_code in valid_indexes if row_code == code]
    if same_indexes:
        return same_indexes[0]

    previous_code = ""
    for _, row_code in valid_indexes:
        if row_code < code and row_code > previous_code:
            previous_code = row_code

    if previous_code:
        insert_after = max(index for index, row_code in valid_indexes if row_code == previous_code)
        index = insert_after + 1
        while index < len(lines) and dict_code_at(lines, index) == previous_code:
            index += 1
        return index

    return valid_indexes[0][0]


def insert_rows_by_code(lines: list[str], rows: list[tuple[str, str]]) -> list[str]:
    out = list(lines)
    for word, code in sorted(rows, key=lambda item: (item[1], item[0])):
        index = find_insert_index(out, code)
        out.insert(index, f"{word}\t{code}")
    return out


def create_rollback_log(scheme: ZzcScheme, ops_count: int, keep_count: int, target_dicts: tuple[Path, ...]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_dir = scheme.rollback_logs / stamp
    dict_dir = log_dir / "dicts"
    dict_dir.mkdir(parents=True, exist_ok=True)
    manifest = [
        f"created_at={datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"schema={scheme.schema}",
        f"ops_count={ops_count}",
        f"keep_count={keep_count}",
        f"root={scheme.root}",
        f"ops_path={scheme.ops}",
        "target_paths=" + "|".join(str(p) for p in target_dicts if p.exists()),
    ]
    if scheme.ops.exists():
        shutil.copy2(scheme.ops, log_dir / "before_zzc.dict.yaml")
    for path in target_dicts:
        if path.exists():
            shutil.copy2(path, dict_dir / path.name)
    write_text(log_dir / "manifest.txt", "\n".join(manifest) + "\n")
    prune_rollback_logs(scheme)
    return log_dir


def merge_into_real_dicts(scheme: ZzcScheme, target_dicts: tuple[Path, ...], ops: list[dict[str, str]], keep_rows: list[tuple[str, str]], order_map: dict[str, list[str]], logger=print) -> None:
    words_to_remove = {row["word"] for row in ops if row["mark"] in {"+", "-"} and not row.get("append")}
    exact_to_remove = {(row["word"], row["code"]) for row in ops if row["mark"] == "!"}
    for path in target_dicts:
        if not path.exists():
            continue
        kept: list[str] = []
        removed = 0
        for line in read_text(path).splitlines():
            row = parse_dict_row(line)
            if row:
                word, code = row
                if word in words_to_remove or (word, code) in exact_to_remove:
                    removed += 1
                    continue
            kept.append(line)
        kept = reorder_dict_lines(kept, order_map)
        write_text(path, "\n".join(kept) + "\n")
        logger(f"[zzc] 已整理 {path.name}，移除 {removed} 条")
    target = target_dicts[0] if target_dicts else None
    if target is not None and target.exists() and keep_rows:
        lines = read_text(target).splitlines()
        lines = insert_rows_by_code(lines, keep_rows)
        write_text(target, "\n".join(lines) + "\n")
        logger(f"[zzc] 已写入最终 zzc 词条：{target.name}，{len(keep_rows)} 条")


def touch_cache_version(scheme: ZzcScheme) -> None:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    write_text(scheme.cache_version, f"{stamp}\n")


def clear_ops(scheme: ZzcScheme) -> None:
    write_ops(scheme, [])
    touch_cache_version(scheme)


def clear_runtime_cache(scheme: ZzcScheme, logger=print) -> None:
    removed = 0
    for group_file in scheme.zzc_dir.glob("group_*.tsv"):
        group_file.unlink()
        removed += 1
    write_text(scheme.index, "")
    write_text(scheme.zzc_dir / "runtime_exact.tsv", "")
    logger(f"[zzc] 已清空运行快照：group={removed}")


def merge_root(root: Path, target_dicts: tuple[str, ...] = (), logger=print) -> bool:
    scheme = find_scheme(root)
    if not scheme:
        logger(f"[zzc] 未找到 *.zzc.dict.yaml：{root}")
        return False
    resolved_targets = resolve_target_dicts(scheme, target_dicts)
    if not resolved_targets:
        raise ValueError("请先选择合并目标码表。")
    missing = [path for path in resolved_targets if not path.exists()]
    if missing:
        raise FileNotFoundError("合并目标码表不存在：" + "，".join(str(path) for path in missing))
    started = perf_counter()
    char_count = rebuild_char_parts(scheme)
    logger(f"[zzc] 已重建 char_parts.tsv：{char_count} 字")
    ops = load_ops(scheme)
    keep_rows = final_rows_from_ops(ops)
    logger(f"[zzc] 待合并操作：{len(ops)} 条；最终写入：{len(keep_rows)} 条")
    if not ops:
        return False
    log_dir = create_rollback_log(scheme, len(ops), len(keep_rows), resolved_targets)
    logger(f"[zzc] 已创建撤回备份：{log_dir.relative_to(scheme.zzc_dir)}")
    merge_into_real_dicts(scheme, resolved_targets, ops, keep_rows, latest_order_map(ops), logger=logger)
    clear_ops(scheme)
    clear_runtime_cache(scheme, logger=logger)
    logger(f"[zzc] 合并完成，用时 {perf_counter() - started:.1f} 秒")
    return True


def copy_managed_files(source_root: Path, target_root: Path, target_dicts: tuple[str, ...] = (), logger=print) -> None:
    scheme = find_scheme(source_root)
    if not scheme:
        return
    files = [
        source_root / f"{scheme.schema}.zzc.dict.yaml",
        source_root / "zzc" / "char_parts.tsv",
        source_root / "zzc" / "index.tsv",
        source_root / "zzc" / "runtime_exact.tsv",
        source_root / "zzc" / "cache_version.txt",
    ]
    files.extend(resolve_target_dicts(scheme, target_dicts))
    for path in files:
        if not path.exists():
            continue
        rel = path.relative_to(source_root)
        dest = target_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        logger(f"[zzc] 回写 {rel.as_posix()}")
