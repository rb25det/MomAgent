from __future__ import annotations

import json
import hashlib
import difflib
from pathlib import Path
from datetime import datetime

from prompts.builder import build_prompt


OUT_DIR = Path("out_prompts")
OUT_DIR.mkdir(exist_ok=True)


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def make_base_config() -> dict:
    """Flaskの write_config_json が作る形に合わせた最小 config"""
    return {
        "user": {
            "nickname": "テスト太郎",
            "gender": "male",
            "age": 23,
            "grade": "M1",
            "role_status": "student",
            "life": {
                "wake_time_weekday": "07:00",
                "sleep_time_weekday": "00:30",
                "wake_time_holiday": "10:00",
                "sleep_time_holiday": "02:00",
                "average_sleep_hours": 6.5,
                "active_time_slots": ["morning", "evening"],
            },
            "health": {
                "breakfast_frequency_level": 1,
                "exercise_frequency_per_week": 2,
            },
            "topic_weights": {
                "job_hunting": 1.0,
                "health": 1.0,
            },
            "worry_now": "締切が近いのに集中できない",
        },
        "mother_model": {
            "strict_kind": 0.0,
            "quiet_talkative": 0.0,
            "dialect_type": "normal",
            "listen_deeply": 1.0,
            "give_clear_advice": 1.0,
            "praise_a_lot": 0.0,
            "topic_initiation_frequency": 0.5,
            "topic_weight_seriousness": 0.5,
        },
        "generated_model_name": "elyza-mom",
    }


def apply_variant(cfg: dict, variant: dict) -> dict:
    new_cfg = json.loads(json.dumps(cfg, ensure_ascii=False))
    for k, v in variant.items():
        obj = new_cfg
        parts = k.split(".")
        for p in parts[:-1]:
            obj = obj[p]
        obj[parts[-1]] = v
    return new_cfg


# ★追加：Windowsでも安全なファイル名にする
_INVALID = '<>:"/\\|?*'


def _sanitize_filename(s: str, max_len: int = 140) -> str:
    out = s
    for ch in _INVALID:
        out = out.replace(ch, "_")
    out = out.replace(" ", "_")
    out = out.replace("\n", "_")
    if len(out) > max_len:
        out = out[:max_len] + "_TRUNC"
    return out


def variant_name(variant: dict) -> str:
    chunks = []
    for k, v in variant.items():
        if isinstance(v, (dict, list)):
            vv = json.dumps(v, ensure_ascii=False, sort_keys=True)
        else:
            vv = str(v)
        vv = _sanitize_filename(vv)
        chunks.append(f"{k}={vv}")
    return "__".join(chunks)


def write_case(case_id: int, variant: dict, prompt: str) -> Path:
    stamp = f"{case_id:04d}"
    name = variant_name(variant) if variant else "BASELINE"
    digest = sha1(prompt)
    path = OUT_DIR / f"{stamp}__{name}__{digest}.txt"
    path.write_text(prompt, encoding="utf-8")
    return path


def unified_diff(a: str, b: str, a_name: str, b_name: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            a.splitlines(),
            b.splitlines(),
            fromfile=a_name,
            tofile=b_name,
            lineterm="",
        )
    )


def main():
    base = make_base_config()

    # ====== テストしたいパラメータ（母＋ユーザ） ======
    grid = {
        # ---- mother_model（既存）----
        "mother_model.dialect_type": ["normal", "kansai", "hakata"],
        "mother_model.strict_kind": [-0.8, -0.4, 0.0, 0.4, 0.8],
        "mother_model.quiet_talkative": [-0.8, -0.4, 0.0, 0.4, 0.8],
        "mother_model.listen_deeply": [0.0, 1.0],
        "mother_model.give_clear_advice": [0.0, 1.0],
        "mother_model.praise_a_lot": [0.0, 1.0],
        "mother_model.topic_initiation_frequency": [0.1, 0.5, 1.0],
        "mother_model.topic_weight_seriousness": [0.2, 0.5, 0.8],

        # ---- user（追加）----
        "user.nickname": ["テスト太郎", "横田さん", "あなた"],

        # 性別/年齢/学年/立場：builder.pyが使っていれば差分が出る（未使用ならchanged=Falseになる）
        "user.gender": ["male", "female", "other", None],
        "user.age": [18, 23, 30, None],
        "user.grade": ["B4", "M1", "M2", None],
        "user.role_status": ["student", "worker", None],

        # 生活リズム
        "user.life.wake_time_weekday": ["06:30", "07:00", None],
        "user.life.sleep_time_weekday": ["23:30", "00:30", None],
        "user.life.wake_time_holiday": ["09:00", "10:00", None],
        "user.life.sleep_time_holiday": ["01:00", "02:00", None],
        "user.life.average_sleep_hours": [4.5, 6.5, 8.0, None],
        "user.life.active_time_slots": [
            [],
            ["morning"],
            ["night"],
            ["morning", "evening", "night"],
        ],

        # 健康
        "user.health.breakfast_frequency_level": [0, 1, 2, None],
        "user.health.exercise_frequency_per_week": [0, 2, 5, None],

        # 話題嗜好（辞書丸ごと差し替えでテスト）
        "user.topic_weights": [
            {},
            {"job_hunting": 1.0},
            {"health": 1.0, "money": 1.0},
            {"love": 1.0, "school": 1.0},
        ],

        # 今の悩み
        "user.worry_now": ["", "研究が進まない", "人間関係がしんどい"],
    }

    # 「1要素ずつ変える」モード
    cases: list[dict] = [{}]  # baseline
    for key, values in grid.items():
        for v in values:
            cases.append({key: v})

    report_lines = []
    report_lines.append(f"# Prompt tuning report ({datetime.now().isoformat(timespec='seconds')})")
    report_lines.append("")
    report_lines.append(f"- cases: {len(cases)}")
    report_lines.append("")

    base_prompt = build_prompt(base)
    base_path = write_case(0, {}, base_prompt)

    report_lines.append("## Baseline")
    report_lines.append(f"- file: `{base_path}`")
    report_lines.append("")

    for i, variant in enumerate(cases[1:], start=1):
        cfg = apply_variant(base, variant)
        prompt = build_prompt(cfg)
        path = write_case(i, variant, prompt)

        d = unified_diff(base_prompt, prompt, "BASELINE", path.name)
        changed = (sha1(base_prompt) != sha1(prompt))

        report_lines.append(f"## Case {i:04d}: {variant}")
        report_lines.append(f"- changed: **{changed}**")
        report_lines.append(f"- file: `{path}`")
        report_lines.append("")
        report_lines.append("```diff")
        diff_lines = d.splitlines()
        if len(diff_lines) > 300:
            report_lines.extend(diff_lines[:300])
            report_lines.append("... (diff truncated)")
        else:
            report_lines.extend(diff_lines)
        report_lines.append("```")
        report_lines.append("")

    (OUT_DIR / "report.md").write_text("\n".join(report_lines), encoding="utf-8")

    print("Done.")
    print(f"- baseline: {base_path}")
    print(f"- report:   {OUT_DIR / 'report.md'}")
    print(f"- outputs:  {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
