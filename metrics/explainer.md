# NFL Metrics, in Plain English

This is a no-jargon guide to what our project measures and why. If you have never
watched American football, start here. It explains the game pieces we use, then the
numbers we build on top of them.

## The game, in 60 seconds

Two teams. One has the ball (the **offense**) and tries to move it forward down a long
rectangular field toward the other team's end. The other team (the **defense**) tries to
stop them. The field is 120 yards long end to end (100 yards of play plus two 10-yard
scoring zones) and 53.3 yards wide.

The offense gets a series of attempts called **downs** to move the ball forward. They
have 4 downs to move it at least 10 yards; if they do, they get a fresh set of 4. The
commentary shorthand "3rd and 2" means it is the 3rd attempt and 2 yards are still
needed. The spot they must reach for a fresh set is the **line to gain** (the "sticks").
The spot the ball starts each play is the **line of scrimmage (LOS)**.

A play starts at the **snap**: the ball is handed back to begin the action. On the plays
we study, the quarterback then throws the ball — a **pass play**.

## The players we care about

- **Quarterback (QB):** the thrower. Every play we study is him deciding where to throw.
- **Receivers:** the players allowed to catch the pass. We care about three kinds:
  - **WR (wide receiver):** fast, lines up near the sidelines, the main pass catchers.
  - **TE (tight end):** bigger, lines up near the middle; sometimes catches, sometimes
    blocks.
  - **RB (running back):** lines up behind the QB; sometimes catches short passes,
    sometimes blocks.
- **Defenders:** the 11 players trying to stop the catch. The ones assigned to shadow
  receivers are in **coverage**; the ones charging the QB are the **pass rush**.

Each side has 11 players on the field, so every play has 22 players plus the ball.

## What a "route" is

When the ball is snapped, each receiver runs a planned path to get open — that path is a
**route**. A receiver who runs a route is an eligible target for that play. A TE or RB
who stays back to block is NOT running a route, so we exclude them. One receiver running
one route on one play is what we call a **Route** in our data.

## "Open," and why it is the whole point

A receiver is **open** when he has space from the nearest defender, so a throw to him is
likely to be caught. Our project asks a simple question a coach cares about:

> When a receiver gets open, does the QB actually throw to him? And if not, who gets the
> ball instead?

To answer it we need to measure openness at the exact moment the QB lets go of the ball
(the **release**). We measure each receiver's openness and compare the most open option
with who was actually thrown to.

## The tracking data

The NFL puts sensors on players and the ball. Ten times per second, we get each player's
position and motion. The fields we use:

- **x, y:** where the player is on the field, in yards.
- **s:** speed, in yards per second.
- **dir:** the direction the player is moving (a compass-style angle).
- **o:** the direction the player's body is facing (orientation) — not always the same as
  where he is moving.
- **event:** labels on special moments, like "ball_snap" and "pass_forward" (the throw).

Each 0.1-second slice is a **frame**. We mostly look at the frame of the throw, and a few
frames just before it.

### One wrinkle: which way is forward?

Teams switch ends, so in the raw data the offense sometimes moves left-to-right and
sometimes right-to-left. Before measuring anything we flip every "leftward" play so the
offense always moves the same way (toward increasing x). Otherwise "5 yards downfield"
would mean opposite things on different plays. This flip is called **standardizing
direction**.

## The numbers we build

Everything below is computed at the moment of the throw (and 0.4 seconds before, to be
explained).

### Separation
The distance in yards from a receiver to the nearest defender. Bigger = more open. This
is the simplest openness idea.

### Closing speed
Separation alone can lie: a receiver can have 3 yards of space that is vanishing because
a defender is sprinting at him. **Closing speed** is how fast that gap is shrinking.
We subtract it, so space that is about to disappear counts for less.

### Lane penalty
Even a defender who is not the closest body can wreck a throw if he is standing
**between the receiver and the QB** — right in the ball's flight path, ready to knock it
down or intercept. The **lane penalty** measures how directly a defender sits in that
throwing lane, and we subtract it too.

### Openness Score (the composite)
We combine the three into one number, in yards:

```
openness = separation
         − 0.5 × closing_speed      (space that is disappearing counts less)
         − 0.5 × lane_penalty       (a defender in the throwing lane counts against you)
```

Higher = more genuinely open. This single number is our measure of "how catchable is a
throw to this receiver right now." (The 0.5 weights are starting values we can tune.)

### Why 0.4 seconds before the throw?
At the exact release, defenders are already reacting to the throw and breaking toward the
ball, which makes everyone look suddenly covered. So we primarily measure openness a few
frames earlier — about 0.4 seconds before release — which better reflects what the QB saw
when he decided. We still compute it at the release too, as a cross-check.

## From openness to the insight

### Most open
On each play, the receiver with the highest Openness Score is the **most open** option.

### Expected targets (a small prediction)
We fit a simple statistical model that estimates, for each receiver on a play, the
probability he was the one thrown to — based on how open he was, how far downfield, how
far from the QB, and whether the QB was under pressure. This gives each receiver an
**expected target** share: how often a receiver like this, this open, usually gets the
ball.

### Targets Over Expected (TOE)
For each receiver we add up (actually thrown to) minus (expected to be thrown to):

- **Positive TOE = over-targeted:** the QB's favorite, who gets the ball even when he is
  not the open man.
- **Negative TOE = open but ignored:** he gets open but the ball goes elsewhere.

That contrast — open-but-ignored vs. over-targeted — is the story.

### Man vs. zone
Defenses cover receivers two broad ways. **Man** coverage: each defender shadows one
specific receiver. **Zone** coverage: each defender guards an area of the field. We split
our results by these because who gets open changes a lot between them.

### Who got it instead
When the most open receiver was ignored, we record who actually got the ball — for
example "open wide receiver ignored, covered running back got a short checkdown instead."
That is the pattern a coach can act on.

## The one chart

The headline is a scatter plot: each receiver's **open rate** (how often he got open) on
one axis against his **target share** (how often he was thrown to) on the other, drawn
separately for man and zone. A diagonal line marks "fair share." Players above it are
over-targeted; players below it are open but ignored. The most extreme names are labeled.

That is the whole idea: measure who gets open, measure who gets the ball, and show the
gap.
