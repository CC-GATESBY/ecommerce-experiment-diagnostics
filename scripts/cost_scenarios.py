"""COST-01: bounded synthetic baskets, Decimal arithmetic, no real-data reads."""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import io
import json
from pathlib import Path
import re
import shutil


VERSION = "cost01-fixed-fee-v1"
PRECISION = 50
MAX_BYTES = 128 * 1024 * 1024
STRATEGIES = (
    "REFERENCE", "ABSORB", "PASS_HALF", "PASS_FULL",
    "ADD_SAME_CATEGORY", "ADD_NEW_CATEGORY",
)
REFERENCES = STRATEGIES[:2]


def number(value, name, minimum=None, maximum=None):
    """Reject float input and nonfinite values; never silently clip a domain."""
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError(f"{name}: use an exact decimal string or integer")
    try:
        out = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{name}: invalid decimal") from exc
    if not out.is_finite():
        raise ValueError(f"{name}: must be finite")
    if minimum is not None and out < minimum:
        raise ValueError(f"{name}: below allowed minimum")
    if maximum is not None and out > maximum:
        raise ValueError(f"{name}: above allowed maximum")
    return out


@dataclass(frozen=True)
class Basket:
    s0: Decimal
    m0: Decimal
    h: int
    l0: Decimal = Decimal("4")

    def __post_init__(self):
        for name in ("s0", "m0", "l0"):
            maximum = Decimal(1) if name == "m0" else None
            object.__setattr__(self, name, number(getattr(self, name), name, 0, maximum))
        if self.s0 <= 0:
            raise ValueError("S0: must be positive")
        if type(self.h) is not int or self.h < 1:
            raise ValueError("H: must be a positive integer")


def strategies(basket, fee="3", half="0.50", add_factor="1.25", add_l="5"):
    fee = number(fee, "fee", 0)
    half = number(half, "partial pass", 0, 1)
    factor = number(add_factor, "add factor", 1)
    add_l = number(add_l, "add fulfillment", basket.l0)
    if factor <= 1 or add_l <= basket.l0:
        raise ValueError("Added goods require higher goods and fulfillment costs")
    with localcontext() as ctx:
        ctx.prec = PRECISION
        s0, h, l0 = basket.s0, basket.h, basket.l0
        c0 = (1 - basket.m0) * s0
        rows = []
        for strategy in STRATEGIES:
            s, c, l, count, f = s0, c0, l0, h, fee
            if strategy == "REFERENCE":
                f = Decimal(0)
            elif strategy == "PASS_HALF":
                s += half * fee * h
            elif strategy == "PASS_FULL":
                s += fee * h
            elif strategy.startswith("ADD_"):
                s, c, l = factor * s0, factor * c0, add_l
                count += int(strategy == "ADD_NEW_CATEGORY")
            charge = f * count
            rows.append(dict(strategy=strategy, S=s, C=c, L=l, H_strategy=count,
                             f=f, fixed_charge=charge, unit_contribution=s-c-l-charge))
        return rows


def threshold(reference, strategy):
    """Return a comparison status instead of dividing by nonpositive margins."""
    reference = number(reference, "reference contribution")
    strategy = number(strategy, "strategy contribution")
    out = dict(r_required=None, allowed_probability_decline=None,
               required_probability_lift=None, max_p_ref_if_lift_required=None)
    if reference <= 0:
        return dict(out, status="reference_nonpositive_ratio_not_applicable")
    if strategy <= 0:
        return dict(out, status="strategy_nonpositive_cannot_recover_positive_reference")
    with localcontext() as ctx:
        ctx.prec = PRECISION
        r = reference / strategy
        if r <= 1:
            return dict(out, r_required=r, allowed_probability_decline=1-r,
                        status="decline_bound_or_no_decline")
        return dict(out, r_required=r, required_probability_lift=r-1,
                    max_p_ref_if_lift_required=1/r,
                    status="lift_required_feasibility_depends_on_unknown_p_ref")


def normalized(contribution, r):
    """r is a probability ratio, not a probability: values above one can be valid."""
    contribution = number(contribution, "contribution")
    r = number(r, "r", 0)
    with localcontext() as ctx:
        ctx.prec = PRECISION
        return r * contribution


def pairwise_boundary(contribution_a, contribution_b):
    result = threshold(contribution_b, contribution_a)
    return result["r_required"]


def load_config(path):
    config = json.loads(Path(path).read_text(), parse_float=Decimal)
    required = {"version", "run_id", "evidence_type", "currency", "net_sales",
                "merchandise_margin", "charge_categories", "base_fulfillment",
                "shock_fee_per_category", "partial_pass_fraction",
                "add_sales_and_cost_factor", "add_fulfillment", "demand_retention",
                "main_case", "assumptions"}
    if set(config) != required:
        raise ValueError("Missing or unexpected configuration fields")
    if (config["version"], config["evidence_type"], config["currency"]) != (
            VERSION, "synthetic_scenario", "EUR_scenario"):
        raise ValueError("Wrong scenario version or evidence identity")
    if not re.fullmatch(r"[a-z0-9-]+", config["run_id"]):
        raise ValueError("Invalid run_id")
    for key, expected in (("net_sales", ("20", "40", "80")),
                          ("merchandise_margin", ("0.20", "0.30", "0.40")),
                          ("demand_retention", ("1.00", "0.95", "0.90", "0.80", "0.70"))):
        values = [number(v, key, 0) for v in config[key]]
        if values != list(map(Decimal, expected)):
            raise ValueError(f"{key}: differs from the frozen COST-01 grid")
    if config["charge_categories"] != [1, 2, 3] or any(
            type(h) is not int for h in config["charge_categories"]):
        raise ValueError("charge_categories: differs from the frozen grid")
    for key, expected in (("base_fulfillment", "4"), ("shock_fee_per_category", "3"),
                          ("partial_pass_fraction", "0.5"), ("add_sales_and_cost_factor", "1.25"),
                          ("add_fulfillment", "5")):
        if number(config[key], key) != Decimal(expected):
            raise ValueError(f"{key}: differs from the frozen COST-01 assumptions")
    main = config["main_case"]
    if set(main) != {"S0", "m0", "H"} or type(main["H"]) is not int or (
            number(main["S0"], "main S0"), number(main["m0"], "main m0"), main["H"]) != (
            Decimal(40), Decimal("0.3"), 2):
        raise ValueError("Main case cannot be selected after seeing the results")
    return config


def build_tables(config):
    tables = {name: [] for name in (
        "synthetic_baskets.csv", "strategy_comparison.csv",
        "demand_thresholds.csv", "demand_sensitivity.csv")}
    meta = {key: config[key] for key in ("version", "run_id", "evidence_type", "currency")}
    with localcontext() as ctx:
        ctx.prec = PRECISION
        for s in config["net_sales"]:
            for m in config["merchandise_margin"]:
                for h in config["charge_categories"]:
                    basket = Basket(s, m, h, config["base_fulfillment"])
                    shared = dict(meta, basket_id=f"S{s}_m{int(basket.m0*100)}_H{h}",
                                  S0=basket.s0, m0=basket.m0, C0=(1-basket.m0)*basket.s0,
                                  L0=basket.l0, H0=h)
                    tables["synthetic_baskets.csv"].append(shared)
                    results = strategies(basket, config["shock_fee_per_category"],
                                         config["partial_pass_fraction"],
                                         config["add_sales_and_cost_factor"], config["add_fulfillment"])
                    refs = {r["strategy"]: r["unit_contribution"] for r in results[:2]}
                    for row in results:
                        u = row["unit_contribution"]
                        tables["strategy_comparison.csv"].append(dict(
                            shared, **row, delta_unit_vs_reference=u-refs["REFERENCE"],
                            delta_unit_vs_absorb=u-refs["ABSORB"]))
                        for ref, value in refs.items():
                            tables["demand_thresholds.csv"].append(dict(
                                meta, basket_id=shared["basket_id"], strategy=row["strategy"],
                                reference=ref, reference_contribution=value,
                                unit_contribution=u, contribution_difference=u-value,
                                **threshold(value, u)))
                        # Reference probabilities remain fixed; only action demand is varied.
                        rs = ["1.00"] if row["strategy"] in REFERENCES else config["demand_retention"]
                        for r in rs:
                            value = normalized(u, r)
                            tables["demand_sensitivity.csv"].append(dict(
                                meta, basket_id=shared["basket_id"], strategy=row["strategy"],
                                r=Decimal(r), probability_role=("fixed_reference" if
                                row["strategy"] in REFERENCES else "hypothetical_action"),
                                unit_contribution=u, normalized_expected_contribution=value,
                                delta_expected_vs_reference=value-refs["REFERENCE"],
                                delta_expected_vs_absorb=value-refs["ABSORB"]))
    return tables


def csv_bytes(rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: format(v, "f") if isinstance(v, Decimal) else v for k, v in row.items()})
    return out.getvalue().encode("utf-8")


def run(config_path, output_dir):
    config = load_config(config_path)
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError("Output directory already exists; choose a new directory")
    content = {name: csv_bytes(rows) for name, rows in build_tables(config).items()}
    total = sum(map(len, content.values()))
    if total > MAX_BYTES:
        raise ValueError("Output exceeds the 128 MiB budget")
    if not output.parent.is_dir():
        raise ValueError("Output parent must already exist")
    if shutil.disk_usage(output.parent).free < total:
        raise ValueError("Insufficient free disk")
    output.mkdir()
    for name, data in content.items():
        with (output/name).open("xb") as f:
            f.write(data)
    return {"run_id": config["run_id"], "version": VERSION, "output_bytes": total,
            "config_sha256": hashlib.sha256(Path(config_path).read_bytes()).hexdigest(),
            "outputs": {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                        for name, data in content.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/cost_scenarios.json")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        result = run(args.config, args.output_dir)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f"COST-01 failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
