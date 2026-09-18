# Lore terminal demo

This directory contains the source for Lore's 45--60 second launch demo. It
is deliberately a recording recipe, not a checked-in GIF: the only content it
shows comes from the deterministic, offline `examples/run_demo.py` scenario.
The sample project is fictional and copied to a temporary directory before
Lore indexes or searches it.

## Preview the exact scenario

From the repository root, run:

```bash
python3 -B examples/run_demo.py
python3 -B -m unittest examples.test_run_demo
```

Compare the first command's output with
[`TRANSCRIPT.md`](TRANSCRIPT.md). The test both asserts the important lines
and verifies that the source sample remains untouched.

## Record the demo

Install [VHS](https://github.com/charmbracelet/vhs) on the recording machine,
then, from the repository root, render to a temporary output file:

```bash
vhs examples/demo/lore-demo.tape
open /tmp/lore-terminal-demo.gif
```

The tape uses only standard VHS commands and writes `/tmp/lore-terminal-demo.gif`,
so rendering does not add a binary artifact to the checkout. It budgets 52
seconds: a short setup statement, the before-and-after result, the local
search result, and a closing frame. If the installed VHS version differs,
confirm the tape grammar with `vhs --help` before recording.

For a final recording check, run the two Python commands above and inspect the
rendered GIF for legibility, a 45--60 second duration, and the absence of real
project data. Do not claim the animation itself is a benchmark; it is a
fictional workflow demonstration.
