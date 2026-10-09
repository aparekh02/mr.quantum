"""Sprint 2 demo: the full upstream tune-up on the simulated double dot.

Run with ``make demo-02``.
"""

import tempfile
from pathlib import Path

from trainer.lab import SimulatedLab
from trainer.workflows import DQD_WITH_SENSOR_TUNEUP, run_steps

DEVICE = Path(__file__).resolve().parents[1] / "devices" / "dqd_with_sensor.yaml"


def main(base_dir: Path | None = None) -> None:
    """Run every tune-up step and print what each upstream routine concluded."""
    out_dir = base_dir or Path(tempfile.mkdtemp(prefix="trainer-demo-"))
    lab = SimulatedLab.from_yaml(DEVICE, base_dir=out_dir)
    results = run_steps(lab, DQD_WITH_SENSOR_TUNEUP)

    for side in ("side_B", "side_A"):
        b = results[f"{side}/leakage_test"]
        print(
            f"{side} leakage_test: safe range {b['min_safe_voltage_bound']:.2f} V .. "
            f"{b['max_safe_voltage_bound']:.2f} V"
        )
        g = results[f"{side}/global_accumulation"]["global_turn_on_voltage"]
        print(f"{side} global_accumulation: turn-on {g:.3f} V")
        res = results[f"{side}/reservoir_characterization"][
            "reservoir_characterization"
        ]
        cut = ", ".join(f"{k} {v['cutoff_voltage']:.3f} V" for k, v in res.items())
        print(f"{side} reservoir_characterization: cutoffs {cut}")

    peak = results["find_sensor_peak"]
    print(f"find_sensor_peak: Coulomb peak at PB = {peak['best_peak_voltage']:.4f} V")
    stable = results["find_stable_sensor_peak"]
    print(
        "find_stable_sensor_peak: parked on the flank at PB = "
        f"{stable['best_peak_max_gradient_voltage']:.4f} V"
    )
    gradients = results["run_compensation"]["compensation_gradients"]
    print(
        "run_compensation: "
        + ", ".join(f"{g} {v:+.3f} V/V" for g, v in gradients.items())
    )
    sweeps = results["run_dqd_search"]["run_dqd_search"]
    found = [(sw, sq) for sw in sweeps for sq in sw["dqd_squares"]]
    if found:
        sw, sq = found[0]
        print(
            f"run_dqd_search: double dot found at outer barriers "
            f"{sw['outer_barrier_voltage']:.3f} V, inner {sw['inner_barrier_voltage']:.3f} V "
            f"(score {sq['total_score']:.2f})"
        )
    else:
        print("run_dqd_search: no double dot found")
    print(f"model calls: {lab.models_client.calls}")
    print(
        f"simulated lab time: {lab.simulator.clock.now():.0f} s; data under {out_dir}"
    )


if __name__ == "__main__":
    main()
