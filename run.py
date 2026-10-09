"""Run the pipeline: data (snapshot.build) -> metrics (aggregate.build) -> story (charts.build).

    python run.py                          # every stage, every game
    python run.py --games 2021090900       # subset of games (Req 8.1)
    python run.py --stage metrics          # one stage, reading earlier tables from out/
    python run.py --rebuild                # ignore cached out/ tables (Req 8.4)
    python run.py --fixtures --stage data  # write + validate C1/C2 fixtures in out/fixtures/

Stage modules are imported lazily, so a stage whose module or build() doesn't
exist yet is skipped with a message (non-zero exit only if --stage names it).
"""

import argparse
import importlib
import sys

from config import Config

STAGES = {"data": "snapshot", "metrics": "aggregate", "story": "charts"}


def _stage_build(module_name):
    """Return module.build, or None if the module or its build() doesn't exist yet."""
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as err:
        if err.name != module_name:   # the module exists but one of its imports failed
            raise
        return None
    return getattr(module, "build", None)


def write_fixtures(cfg, stage=None):
    """Write the C1/C2 fixtures (and C3-C6 if contracts_metrics exists) to out/fixtures/."""
    import contracts_data

    contracts_data.fixture_c1c2(cfg)
    print(f"fixtures: wrote C1/C2 to {cfg.derived_dir / 'fixtures'}")
    if stage == "data":
        return
    try:
        contracts_metrics = importlib.import_module("contracts_metrics")
    except ModuleNotFoundError as err:
        if err.name != "contracts_metrics":
            raise
        contracts_metrics = None
    fixture_c3c6 = getattr(contracts_metrics, "fixture_c3c6", None)
    if fixture_c3c6 is None:
        print("fixtures: C3-C6 not available yet: contracts_metrics.fixture_c3c6 missing")
        return
    fixture_c3c6(cfg)
    print(f"fixtures: wrote C3-C6 to {cfg.derived_dir / 'fixtures'}")


def validate_c1c2_fixtures(cfg):
    """Re-read the C1/C2 fixtures from disk and validate them (stands in for the data stage)."""
    import pandas as pd

    import contracts_data

    fixture_dir = cfg.derived_dir / "fixtures"
    c1 = contracts_data.validate_c1(pd.read_parquet(fixture_dir / contracts_data.C1_FILE))
    c2 = contracts_data.validate_c2(pd.read_parquet(fixture_dir / contracts_data.C2_FILE))
    print(f"data: fixtures valid: C1 {len(c1)} rows, C2 {len(c2)} plays")


def run_stage(name, cfg, required):
    """Run one stage; return False if it was required (--stage) but isn't available yet."""
    if name == "data" and cfg.fixtures:
        validate_c1c2_fixtures(cfg)
        return True
    module_name = STAGES[name]
    build = _stage_build(module_name)
    if build is None:
        print(f"stage {name} not available yet: {module_name}.build missing",
              file=sys.stderr if required else sys.stdout)
        return not required
    print(f"stage {name}: {module_name}.build")
    build(cfg)
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="Open but Ignored pipeline: data -> metrics -> story.")
    parser.add_argument("--games", nargs="+", type=int, metavar="GAME_ID",
                        help="process only these gameIds (default: every tracking file)")
    parser.add_argument("--rebuild", action="store_true", help="ignore cached tables in out/")
    parser.add_argument("--stage", choices=list(STAGES),
                        help="run one stage only, reading the previous stage's tables from out/")
    parser.add_argument("--fixtures", action="store_true",
                        help="write fixtures to out/fixtures/ and have the stages read from there")
    args = parser.parse_args(argv)

    cfg = Config(games=args.games, rebuild=args.rebuild, fixtures=args.fixtures)
    if cfg.fixtures:
        write_fixtures(cfg, args.stage)

    names = [args.stage] if args.stage else list(STAGES)
    ok = all([run_stage(name, cfg, required=args.stage is not None) for name in names])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
