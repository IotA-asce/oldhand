# Render from the repository root: vhs examples/demo/oldhand-demo.tape
# VHS writes into docs/img so the committed GIF is the one the README shows.
Output docs/img/oldhand-demo.gif

Set Shell "bash"
Set FontSize 22
Set Width 1280
Set Height 720
Set MarginFill "#0d1117"
Set Margin 24
Set Theme "Dracula"
Set TypingSpeed 30ms

Hide
Type "export PYTHONPATH=$PWD/src PS1='$ '"
Enter
Type "clear"
Enter
Show

# 0-9s: establish the problem and the local-first constraint.
Type "# A coding agent wants to merge config defaults into staging"
Enter
Sleep 3s
Type "# Oldhand keeps the reviewed reason local and readable"
Enter
Sleep 4s
Type "python3 -B examples/run_demo.py"
Enter

# 9-30s: hold the real, deterministic before-and-after scenario.
Sleep 17s

# 30-40s: make the agent-facing retrieval outcome linger long enough to read.
Type "# The fresh session retrieved the verified constraint before changing code"
Enter
Sleep 7s

# 40-50s: close with the actual safety claim from the scenario.
Type "# Local Markdown. Local SQLite. No account, model, or network."
Enter
Sleep 7s
