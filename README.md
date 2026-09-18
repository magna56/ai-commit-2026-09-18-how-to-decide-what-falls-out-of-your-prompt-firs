# How to Decide What Falls Out of Your Prompt First

**TL;DR:** Prompt priorities rank siblings, not the whole prompt. What survives a token budget is decided by where a piece sits in the tree, not by how big its number is.

Published from [The AI Commit](https://theaicommit.com/#2026-09-18/code) — Building Agents & MCP, 2026-09-18.

## Run

```bash
python3 code_example.py
```

## Output

```
  parents ranked 1 and 2   prune order: B -> A -> D -> C
  parents unranked         prune order: B -> D -> A -> C
  the only change is the parents. A at 100 outlives D at 20 in one and not the other.

agent prompt: 139 tokens, budget 120
  kept   : turn2, tool_res, tool_req, rules
  dropped: turn1
  total  : 105 tokens

  'rules' has the LOWEST number in the tree (10) and survives, because its parent
  is ranked 900. History's turns carry 5 and 9 and go first. tool_req is tied to
  tool_res, so an orphaned request can never outlive the answer it refers to.

```

## Code

See [`code_example.py`](code_example.py).
