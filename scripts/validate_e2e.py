#!/usr/bin/env python3
"""
End-to-end validation using the day's export (digest JSON).

Validates:
- resolved_url: present and (where applicable) differs from input_url
- meta: title and description present for items
- 正文抽取: key_paragraphs present when content enrichment was used (optional)
- points: cluster-level points exist and are usable
- 前端展示: digest schema matches what the frontend expects so it can load and render

Usage:
    python scripts/validate_e2e.py
    python scripts/validate_e2e.py --digest exports/latest_digest.json
    python scripts/validate_e2e.py --digest exports/digest_20260227_120000.json
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Project root
ROOT = Path(__file__).resolve().parent.parent


def find_todays_digest(export_dir: Path) -> Optional[Path]:
    """Return path to latest_digest.json or newest digest_*.json from today."""
    latest = export_dir / "latest_digest.json"
    if latest.exists():
        return latest
    today = datetime.now().strftime("%Y%m%d")
    candidates = sorted(
        export_dir.glob("digest_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in candidates:
        if today in p.name or p.name.startswith("digest_"):
            return p
    return candidates[0] if candidates else None


def validate_digest_schema(data: dict) -> list[str]:
    """Check digest has the structure the frontend expects. Returns list of errors."""
    errors = []
    if not isinstance(data, dict):
        errors.append("Digest root must be an object")
        return errors

    for key in ("generated_at", "item_count", "clusters", "by_category"):
        if key not in data:
            errors.append(f"Missing top-level key: {key}")

    clusters = data.get("clusters")
    if clusters is not None and not isinstance(clusters, list):
        errors.append("'clusters' must be an array")
    elif isinstance(clusters, list):
        for i, c in enumerate(clusters):
            if not isinstance(c, dict):
                errors.append(f"clusters[{i}] must be an object")
                continue
            for k in ("cluster_id", "category", "headline", "points", "items"):
                if k not in c:
                    errors.append(f"clusters[{i}] missing key: {k}")
            items = c.get("items")
            if items is not None and isinstance(items, list):
                for j, it in enumerate(items):
                    if not isinstance(it, dict):
                        continue
                    for key in ("title", "input_url", "resolved_url", "source_id", "published_at", "description", "key_paragraphs"):
                        if key not in it:
                            errors.append(f"clusters[{i}].items[{j}] missing key: {key}")

    by_cat = data.get("by_category")
    if by_cat is not None and not isinstance(by_cat, dict):
        errors.append("'by_category' must be an object")

    return errors


def run_validation(digest_path: Path) -> dict:
    """Run all checks on digest JSON. Returns result dict with passes/failures and details."""
    result = {
        "digest_path": str(digest_path),
        "schema_ok": False,
        "resolved_url_ok": False,
        "meta_ok": False,
        "content_ok": False,
        "points_ok": False,
        "frontend_ready": False,
        "errors": [],
        "stats": {},
    }

    try:
        with open(digest_path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        result["errors"].append(f"File not found: {digest_path}")
        return result
    except json.JSONDecodeError as e:
        result["errors"].append(f"Invalid JSON: {e}")
        return result

    # Schema validation
    schema_errors = validate_digest_schema(data)
    if schema_errors:
        result["errors"].extend(schema_errors)
        return result
    result["schema_ok"] = True

    clusters = data.get("clusters", [])
    if not clusters:
        result["errors"].append("No clusters in digest")
        return result

    total_items = 0
    resolved_count = 0
    resolved_changed_count = 0
    title_count = 0
    description_count = 0
    key_paragraphs_count = 0
    points_nonempty_clusters = 0

    for c in clusters:
        items = c.get("items") or []
        total_items += len(items)
        points = c.get("points") or []
        if points:
            points_nonempty_clusters += 1

        for it in items:
            input_url = (it.get("input_url") or "").strip()
            resolved_url = (it.get("resolved_url") or "").strip()
            if resolved_url:
                resolved_count += 1
            if input_url and resolved_url and resolved_url != input_url:
                resolved_changed_count += 1
            if (it.get("title") or "").strip():
                title_count += 1
            if (it.get("description") or "").strip():
                description_count += 1
            kp = it.get("key_paragraphs") or []
            if isinstance(kp, list) and len(kp) > 0:
                key_paragraphs_count += 1

    result["stats"] = {
        "clusters": len(clusters),
        "items": total_items,
        "resolved_url_filled": resolved_count,
        "resolved_url_changed": resolved_changed_count,
        "title_filled": title_count,
        "description_filled": description_count,
        "items_with_key_paragraphs": key_paragraphs_count,
        "clusters_with_points": points_nonempty_clusters,
    }

    # resolved_url: all items should have it
    result["resolved_url_ok"] = total_items == 0 or resolved_count == total_items
    if not result["resolved_url_ok"]:
        result["errors"].append(
            f"resolved_url: only {resolved_count}/{total_items} items have resolved_url"
        )

    # meta: most items should have title and description (allow some missing for paywalls)
    result["meta_ok"] = title_count >= total_items // 2 and description_count >= total_items // 2
    if not result["meta_ok"]:
        result["errors"].append(
            f"meta: title filled {title_count}/{total_items}, description {description_count}/{total_items}"
        )

    # content (正文抽取): key_paragraphs are optional (only when export used --content)
    result["content_ok"] = True  # Report stat only; no error if zero (user may not have used --content)

    # points: at least some clusters should have points
    result["points_ok"] = points_nonempty_clusters >= (len(clusters) // 2) or len(clusters) <= 1
    if not result["points_ok"]:
        result["errors"].append(
            f"points: only {points_nonempty_clusters}/{len(clusters)} clusters have points"
        )

    # frontend: schema already validated; frontend can load this
    result["frontend_ready"] = result["schema_ok"] and result["resolved_url_ok"]

    return result


def main():
    parser = argparse.ArgumentParser(
        description="End-to-end validation: resolved_url, meta, content, points, frontend"
    )
    parser.add_argument(
        "--digest",
        type=Path,
        default=None,
        help="Path to digest JSON (default: exports/latest_digest.json or today's digest_*.json)",
    )
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=ROOT / "exports",
        help="Exports directory when --digest not provided",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if content or points are missing (default: report only)",
    )
    args = parser.parse_args()

    digest_path = args.digest
    if digest_path is None:
        export_dir = args.export_dir if args.export_dir.is_absolute() else ROOT / args.export_dir
        digest_path = find_todays_digest(export_dir)

    if digest_path is None or not digest_path.exists():
        if digest_path is None:
            print("No digest file found.", file=sys.stderr)
            print(
                "Run export with digest format first, e.g.:",
                file=sys.stderr,
            )
            print(
                "  python -m backend.app.cli export --formats txt,md,digest",
                file=sys.stderr,
            )
            print(
                "  python -m backend.app.cli export --formats txt,md,digest --content",
                file=sys.stderr,
            )
        else:
            print(f"Digest file not found: {digest_path}", file=sys.stderr)
        sys.exit(1)

    result = run_validation(digest_path)

    # Print report
    print("=" * 60)
    print("E2E validation:", digest_path.name)
    print("=" * 60)
    print(f"  Schema valid:     {result['schema_ok']}")
    print(f"  resolved_url:     {result['resolved_url_ok']}")
    print(f"  meta (title/desc): {result['meta_ok']}")
    print(f"  points:           {result['points_ok']}")
    print(f"  Frontend-ready:   {result['frontend_ready']}")
    stats = result.get("stats", {})
    if stats:
        print()
        print("  Stats:")
        print(f"    Clusters: {stats.get('clusters', 0)}")
        print(f"    Items: {stats.get('items', 0)}")
        print(f"    resolved_url filled: {stats.get('resolved_url_filled', 0)}")
        print(f"    resolved_url changed (vs input): {stats.get('resolved_url_changed', 0)}")
        print(f"    title filled: {stats.get('title_filled', 0)}")
        print(f"    description filled: {stats.get('description_filled', 0)}")
        print(f"    items with key_paragraphs: {stats.get('items_with_key_paragraphs', 0)}")
        print(f"    clusters with points: {stats.get('clusters_with_points', 0)}")
    if result["errors"]:
        print()
        print("  Errors:")
        for e in result["errors"]:
            print(f"    - {e}")
    print()

    if result["errors"]:
        if args.strict:
            sys.exit(1)
        print("Validation completed with issues (run with --strict to fail on errors).")
    else:
        print("All checks passed. Digest is ready for frontend display.")

    # Write result JSON for CI/audit
    out_path = ROOT / "exports" / f"validation_e2e_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"Result written to {out_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()
