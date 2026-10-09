"""Sprint 1 demo: upstream health-check routines on the simulated channel.

Run with ``make demo-01``.
"""

import tempfile
from pathlib import Path

from stanza.routines import RoutineRunner
from stanza.utils import load_device_config
from trainer.routines import register_builtin_routines

DEVICE = Path(__file__).resolve().parents[1] / "devices" / "single_channel.yaml"


def main(base_dir: Path | None = None) -> None:
    """Run noise_floor_measurement and global_accumulation, then print results."""
    register_builtin_routines()
    out_dir = base_dir or Path(tempfile.mkdtemp(prefix="trainer-demo-"))
    runner = RoutineRunner(configs=[load_device_config(DEVICE)], base_dir=out_dir)

    noise = runner.run("noise_floor_measurement")
    print(
        f"noise_floor_measurement: mean {noise['current_mean'] * 1e12:.2f} pA, "
        f"std {noise['current_std'] * 1e12:.2f} pA"
    )

    # leakage_test arrives with Sprint 2; supply its result in upstream's shape.
    runner.results.store(
        "leakage_test", {"max_safe_voltage_bound": 1.5, "min_safe_voltage_bound": -1.5}
    )
    result = runner.run("global_accumulation")
    print(
        "global_accumulation: channel turn-on (saturation) at "
        f"{result['global_turn_on_voltage']:.3f} V"
    )
    print(f"data logged under {out_dir}")


if __name__ == "__main__":
    main()
