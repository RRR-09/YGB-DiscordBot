# About

A contracted Discord bot for a community Discord server.

## If slow to start/shutdown/restart:

There is a strange issue with discord.py and pynacl that leads it to hang in some cases. Running `poetry run pip install pynacl -I --no-binary pynacl` after the standard `poetry install` should fix any issues.

# Functions (and items to manually test):

## Basic Functions

1. Invite Logging
   - Monitors who joined from where
