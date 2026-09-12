"""Vulture whitelist: names genuinely used but invisible to static analysis.

mnemobrain.cli.main is the console-script entry point (pyproject
[project.scripts]); nothing inside the package calls it.
"""

mnemobrain.cli.main
