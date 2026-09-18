# Render from the repository root: vhs examples/demo/lore-demo.tape
# VHS writes outside the checkout so generated media is never committed by accident.
Output /tmp/lore-terminal-demo.gif

Set Shell "zsh"
Set FontSize 24
Set Width 1280
Set Height 720
Set MarginFill "#0d1117"
Set Margin 24
Set Theme { "Dracula" }
Set TypingSpeed 35ms

# 0--9s: establish the problem and local-first constraint.
Type "# A coding agent wants to merge config defaults into staging"
Enter
Sleep 3s
Type "# Lore keeps the reviewed reason local and readable"
Enter
Sleep 4s
Type "python3 -B examples/run_demo.py"
Enter

# 10--31s: hold the real, deterministic before-and-after scenario.
Sleep 17s

# 31--43s: make the agent-facing retrieval outcome linger long enough to read.
Type "# The fresh session retrieved the verified constraint before changing code"
Enter
Sleep 8s

# 43--52s: close with the actual safety/property claim from the scenario.
Type "# Local Markdown. Local SQLite. No account, model, or network."
Enter
Sleep 8s
