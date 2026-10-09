# Open but Ignored vs. Over-Targeted

QBs don't spread the ball by who is open: they feed their WR1. Using player tracking 0.4 s before the throw on 7,257 targeted passes (2021 Weeks 1–8), we estimate each route runner's chance of being targeted from how open he is (separation, defender closing speed, traffic in the throwing lane), his depth and his distance from the QB, then compare it with who actually got the ball. Cooper Kupp drew 84 targets against 51 expected (+33 Targets Over Expected on 227 routes), and all ten most over-targeted receivers are wide receivers. At the other end, Cincinnati's C.J. Uzomah got 20 targets against 39 expected (−19) while his teammate Tee Higgins was +21. The model can't see route quality or a QB's trust, so TOE measures how far a QB's choice departs from openness, not how good the receiver is.

![Headline view of the dashboard](results/headline.png)

## Method

- **Data:** NFL Big Data Bowl 2023 tracking, plays, players and PFF scouting (8,557 pass plays, 122 games). Play direction is standardized so the offense always moves toward +x.
- **Snapshot:** every player at 0–5 frames before the pass is released. Eligible receivers are WR, TE and RB (FB counted as RB) with PFF role "Pass Route".
- **Target:** parsed from `playDescription` and matched to the play's offensive players (96.3% of throws).
- **Openness:** separation − 0.5 s × the nearest defender's closing speed − 0.5 × a throwing-lane penalty, measured 0.4 s before release.
- **Expected targets:** logistic model on openness, depth, distance from the QB and pressure, normalized so each play sums to 1. 5-fold cross-validation grouped by game: AUC 0.60, top-1 accuracy 34% (random ≈ 22%).
- **TOE:** targets − expected targets. Receivers need at least 100 routes to be ranked (136 qualify).

## Run it

The data isn't in the repo. Download the [Big Data Bowl 2023 files](https://www.kaggle.com/competitions/nfl-big-data-bowl-2023/data) into `data/` (with tracking in `data/tracking/`).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                      # data stage (C1/C2) then metrics (C3–C6), about 45 s
python -c "from config import Config; from export_dashboard import build_dashboard_json; build_dashboard_json(Config())"
cd visualisation && npm install && npm run dev   # dashboard at http://localhost:3000
```

## Outputs

- `visualisation/public/data/receivers.json`: the dashboard's input, one row per receiver per week.
- `results/data_report.json`: source counts, exclusions, target match rate and integrity checks.
- `results/model_report.json`: model coefficients and cross-validation scores.
- `out/`: generated tables C1–C6 (git-ignored, rebuilt by `python run.py`).

Built on-site with Kiro; the spec is in `.kiro/specs/open-but-ignored/`. Data: [NFL Big Data Bowl 2023](https://www.kaggle.com/competitions/nfl-big-data-bowl-2023).
