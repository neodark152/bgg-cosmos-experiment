import os
import json
import time
import yaml
import subprocess
from datetime import datetime, timezone
from fractions import Fraction

import numpy as np
import requests


def now():
    return datetime.now(timezone.utc).isoformat()


def load_cfg(path="experiments/config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def jlog(path, obj):
    obj["time"] = now()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(
            "CMD failed:\n{}\nSTDERR:\n{}".format(" ".join(cmd), p.stderr)
        )
    return p.stdout


def cli_json(cmd):
    return json.loads(run(cmd))


def height(rpc):
    r = requests.get(rpc + "/status", timeout=5)
    r.raise_for_status()
    return int(r.json()["result"]["sync_info"]["latest_block_height"])


def wait_block(rpc, old_h):
    for _ in range(30):
        h = height(rpc)
        if h > old_h:
            return h
        time.sleep(1)
    return height(rpc)


def threshold_power(theta, base: int) -> int:
    """
    计算绝对 voting power 阈值。

    当 theta = 0.5 时，使用严格多数：
        floor(base / 2) + 1

    其他 theta 使用：
        ceil(theta * base)
    """
    t = Fraction(str(theta))

    if t == Fraction(1, 2):
        return base // 2 + 1

    return (base * t.numerator + t.denominator - 1) // t.denominator


def threshold_formula(theta, base_name: str) -> str:
    t = Fraction(str(theta))

    if t == Fraction(1, 2):
        return f"floor({base_name} / 2) + 1"

    return f"ceil({theta} * {base_name})"


def qval(cfg, valoper):
    cmd = [
        cfg["binary"], "query", "staking", "validator", valoper,
        "--node", cfg["node_rpc"],
        "-o", "json",
    ]
    data = cli_json(cmd)
    v = data.get("validator", data)
    return int(v.get("tokens", "0")), v.get("status", ""), v


def state(cfg):
    a, ast, _ = qval(cfg, cfg["attacker_valoper"])
    h, hst, _ = qval(cfg, cfg["honest_valoper"])

    total = a + h
    rho = a / total if total > 0 else 0.0

    return {
        "attacker_power": a,
        "honest_power": h,
        "total_power": total,
        "rho_A": rho,
        "attacker_status": ast,
        "honest_status": hst,
    }


def delegate(cfg, from_acct, valoper, amount):
    cmd = [
        cfg["binary"], "tx", "staking", "delegate",
        valoper, f"{int(amount)}{cfg['denom']}",
        "--from", from_acct,
        "--chain-id", cfg["chain_id"],
        "--home", cfg["home"],
        "--node", cfg["node_rpc"],
        "--keyring-backend", cfg["keyring_backend"],
        "--gas", str(cfg.get("gas", "auto")),
        "--gas-adjustment", str(cfg.get("gas_adjustment", "1.5")),
        "--fees", str(cfg.get("fees", "5000" + cfg["denom"])),
        "-y",
        "-o", "json",
    ]
    return cli_json(cmd)


def main():
    cfg = load_cfg()
    np.random.seed(int(cfg["seed"]))

    os.makedirs(cfg["results_dir"], exist_ok=True)
    events = os.path.join(cfg["results_dir"], "events.jsonl")
    summary_path = os.path.join(cfg["results_dir"], "summary.json")

    for p in [events, summary_path]:
        if os.path.exists(p):
            os.remove(p)

    T_action = None
    T_reserve_submitted = None
    T_reserve_effective = None
    T_old = None
    T_post = None

    action_triggered = False
    reserve_submitted = False
    reserve_effective = False
    old_reached = False
    post_reached = False

    reserve_amount = int(cfg["reserve_units"]) * int(cfg["stake_unit"])

    if "M_power" not in cfg:
        raise ValueError(
            "config.yaml 必须设置 M_power。"
            "M_power 是本地实验配置的基准 voting power，不能用实时 total_power 替代。"
        )

    M_power = int(cfg["M_power"])
    K_power = reserve_amount

    old_threshold_power = threshold_power(cfg["theta_old"], M_power)
    math_threshold_power = threshold_power(cfg["theta_post"], M_power + K_power)

    old_threshold_formula = threshold_formula(cfg["theta_old"], "M_power")
    math_threshold_formula = threshold_formula(cfg["theta_post"], "M_power + K_power")

    h0 = height(cfg["node_rpc"])
    s0 = state(cfg)

    honest_before_reserve = None
    expected_honest_after_reserve = None

    jlog(events, {
        "event": "NETWORK_STARTED",
        "height": h0,
        "state": s0,
        "params": cfg,
        "thresholds": {
            "M_power": M_power,
            "K_power": K_power,
            "reserve_amount": reserve_amount,
            "theta_old": cfg["theta_old"],
            "theta_post": cfg["theta_post"],
            "old_threshold_power": old_threshold_power,
            "math_threshold_power": math_threshold_power,
            "old_formula": old_threshold_formula,
            "math_formula": math_threshold_formula,
        },
    })

    post_end_height = None

    for step in range(1, int(cfg["max_steps"]) + 1):
        h_before = height(cfg["node_rpc"])

        dA = int(np.random.poisson(float(cfg["lambda_A"])))
        dH = int(np.random.poisson(float(cfg["lambda_H"])))

        amount_A = dA * int(cfg["stake_unit"])
        amount_H = dH * int(cfg["stake_unit"])

        jlog(events, {
            "event": "POISSON_SAMPLED",
            "step": step,
            "height": h_before,
            "poisson_attacker": dA,
            "poisson_honest": dH,
            "attacker_generated": amount_A,
            "honest_generated": amount_H,
        })

        if amount_A > 0:
            tx = delegate(cfg, cfg["attacker_account"], cfg["attacker_valoper"], amount_A)
            jlog(events, {
                "event": "ATTACK_DELEGATED",
                "step": step,
                "height": h_before,
                "amount": amount_A,
                "txhash": tx.get("txhash"),
            })

        if amount_H > 0:
            tx = delegate(cfg, cfg["honest_account"], cfg["honest_valoper"], amount_H)
            jlog(events, {
                "event": "HONEST_DELEGATED",
                "step": step,
                "height": h_before,
                "amount": amount_H,
                "txhash": tx.get("txhash"),
            })

        h_now = wait_block(cfg["node_rpc"], h_before)
        time.sleep(float(cfg.get("step_sleep_seconds", 3)))

        s = state(cfg)

        jlog(events, {
            "event": "STATE_OBSERVED",
            "step": step,
            "height": h_now,
            **s,
        })

        # T_old:
        # 攻击者 voting power 首次达到原始阈值。
        if not old_reached and s["attacker_power"] >= old_threshold_power:
            old_reached = True
            T_old = h_now

            jlog(events, {
                "event": "OLD_THRESHOLD_REACHED",
                "step": step,
                "height": h_now,
                "attacker_power": s["attacker_power"],
                "rho_A": s["rho_A"],
                "theta_old": cfg["theta_old"],
                "M_power": M_power,
                "old_threshold_power": old_threshold_power,
                "threshold_formula": old_threshold_formula,
            })

        # T_math:
        # 攻击者 voting power 首次达到防守后数学阈值。
        # 注意：这里不再用 rho_A >= theta_post。
        if not post_reached and s["attacker_power"] >= math_threshold_power:
            post_reached = True
            T_post = h_now

            jlog(events, {
                "event": "MATH_THRESHOLD_REACHED",
                "step": step,
                "height": h_now,
                "attacker_power": s["attacker_power"],
                "rho_A": s["rho_A"],
                "theta_post": cfg["theta_post"],
                "M_power": M_power,
                "K_power": K_power,
                "math_threshold_power": math_threshold_power,
                "threshold_formula": math_threshold_formula,
            })

        # Action trigger:
        # 防御动作仍然用攻击者当前 voting power share 触发。
        if not action_triggered and s["rho_A"] >= float(cfg["theta_action"]):
            action_triggered = True
            T_action = h_now

            jlog(events, {
                "event": "ACTION_TRIGGERED",
                "step": step,
                "height": h_now,
                "rho_A": s["rho_A"],
                "theta_action": cfg["theta_action"],
                "attacker_power": s["attacker_power"],
                "honest_power": s["honest_power"],
                "total_power": s["total_power"],
            })

        # Reserve delegation:
        # expected_honest_after_reserve 必须在 reserve 提交前即时计算。
        if action_triggered and not reserve_submitted:
            s_before_reserve = state(cfg)
            honest_before_reserve = s_before_reserve["honest_power"]
            expected_honest_after_reserve = honest_before_reserve + reserve_amount

            tx = delegate(cfg, cfg["reserve_account"], cfg["honest_valoper"], reserve_amount)

            reserve_submitted = True
            T_reserve_submitted = h_now

            jlog(events, {
                "event": "RESERVE_DELEGATION_SUBMITTED",
                "step": step,
                "height": h_now,
                "amount": reserve_amount,
                "txhash": tx.get("txhash"),
                "honest_before_reserve": honest_before_reserve,
                "expected_honest_after_reserve": expected_honest_after_reserve,
            })

        # Reserve effective:
        # 只有 honest_power 真正达到 expected_honest_after_reserve，
        # 才记录 RESERVE_ALL_EFFECTIVE。
        if reserve_submitted and not reserve_effective:
            s2 = state(cfg)

            if (
                expected_honest_after_reserve is not None
                and s2["honest_power"] >= expected_honest_after_reserve
            ):
                reserve_effective = True
                T_reserve_effective = h_now
                post_end_height = h_now + int(cfg["post_defense_blocks"])

                jlog(events, {
                    "event": "RESERVE_ALL_EFFECTIVE",
                    "step": step,
                    "height": h_now,
                    "honest_power": s2["honest_power"],
                    "honest_before_reserve": honest_before_reserve,
                    "expected_honest_after_reserve": expected_honest_after_reserve,
                    "rho_A": s2["rho_A"],
                    "post_defense_blocks": int(cfg["post_defense_blocks"]),
                    "post_end_height": post_end_height,
                })

        # reserve 生效后只继续观察 post_defense_blocks 个块。
        if reserve_effective and height(cfg["node_rpc"]) >= post_end_height:
            break

    final_h = height(cfg["node_rpc"])
    final_s = state(cfg)

    summary = {
        "run_id": cfg["run_id"],
        "seed": cfg["seed"],
        "params": cfg,

        "thresholds": {
            "M_power": M_power,
            "K_power": K_power,
            "reserve_amount": reserve_amount,
            "theta_old": cfg["theta_old"],
            "theta_post": cfg["theta_post"],
            "old_threshold_power": old_threshold_power,
            "math_threshold_power": math_threshold_power,
            "old_formula": old_threshold_formula,
            "math_formula": math_threshold_formula,
        },

        "T_action_trigger": T_action,
        "T_action_tx_submitted": T_reserve_submitted,
        "T_reserve_all_effective": T_reserve_effective,
        "T_old": T_old,
        "T_math": T_post,

        "action_triggered": action_triggered,
        "reserve_submitted": reserve_submitted,
        "reserve_effective": reserve_effective,
        "old_threshold_reached": old_reached,
        "math_threshold_reached": post_reached,

        "reserve_effective_before_old_threshold": (
            T_reserve_effective is not None and
            (T_old is None or T_reserve_effective < T_old)
        ),
        "reserve_effective_before_math_threshold": (
            T_reserve_effective is not None and
            (T_post is None or T_reserve_effective < T_post)
        ),

        "post_defense_blocks": cfg["post_defense_blocks"],
        "post_end_height": post_end_height,

        "final_height": final_h,
        "final_state": final_s,
        "events_path": events,
        "summary_path": summary_path,
    }

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    jlog(events, {
        "event": "RUN_FINISHED",
        "height": final_h,
        "summary_path": summary_path,
    })

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()