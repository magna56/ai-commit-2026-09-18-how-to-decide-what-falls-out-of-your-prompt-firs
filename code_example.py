"""
How to decide what falls out of your prompt first.

Implements the priority-tree pruner a prompt assembler needs: rank siblings,
prune lowest-first until the messages fit a token budget, and resolve ties by
looking ahead at each branch's children.

`PromptNode` and `prune_to_budget` are the parts to lift. Build your own tree
and call it with your model's limit.

Run: python3 code_example.py
"""
# REQUIRES: none (standard library only)

from dataclasses import dataclass, field

# ---------------------------------------------------------------- knobs ----
TOKEN_BUDGET = 120   # shrink this and watch the prune order chew inward
CHARS_PER_TOKEN = 4  # rough estimate; swap in a real tokenizer for production


# ------------------------------------------------------ the liftable core ----
@dataclass(eq=False)
class PromptNode:
    """One element of a prompt. `priority` ranks it against its SIBLINGS only,
    which is the whole point: a 200 here never competes with a 0 in a different
    branch. `pass_priority` marks a wrapper as transparent, so its children
    compete in the parent's scope instead of forming their own."""
    name: str
    priority: int = 0
    text: str = ""
    children: list = field(default_factory=list)
    pass_priority: bool = False
    keep_with: str = None          # prune this node when its partner is pruned

    def tokens(self) -> int:
        return (len(self.text) // CHARS_PER_TOKEN) + sum(c.tokens() for c in self.children)

    def flatten(self):
        """Resolve pass_priority in place: a transparent wrapper's children are
        lifted into the parent's sibling list, carrying their own priorities."""
        lifted = []
        for c in self.children:
            c.flatten()
            lifted.extend(c.children if c.pass_priority else [c])
        self.children = lifted
        return self


def _lookahead(node: PromptNode) -> int:
    """The tie-break the docs bury: when two siblings share a priority, the
    renderer looks at their DIRECT children and cuts into whichever branch
    holds the lowest-priority child."""
    return min((c.priority for c in node.children), default=node.priority)


def _next_leaf(node: PromptNode):
    """Walk down from the root, at each level taking the child that should lose
    first. Recomputed after every removal, which is what makes the two branches
    take turns once their parents tie."""
    if not node.children:
        return None
    child = min(node.children, key=lambda c: (c.priority, _lookahead(c)))
    return (node, child) if not child.children else _next_leaf(child)


def prune_order(root: PromptNode) -> list:
    """Every leaf, in the order it would be dropped."""
    tree, out = root.flatten(), []
    while True:
        found = _next_leaf(tree)
        if not found:
            return out
        parent, leaf = found
        parent.children.remove(leaf)
        # a container that just lost its last child is not itself content, so it
        # drops out silently rather than appearing as one more thing to prune
        if leaf.text:
            out.append(leaf)


def prune_to_budget(root: PromptNode, budget: int):
    """Drop lowest-priority leaves until the tree fits. Returns (kept, dropped)."""
    order = prune_order(copy_of(root))
    live, dropped = list(order), []

    def total():
        return sum(len(n.text) // CHARS_PER_TOKEN for n in live)

    for node in order:
        if total() <= budget:
            break
        if node in live:
            live.remove(node)
            dropped.append(node)
            # an orphaned tool call is worse than neither: take its partner too
            for other in list(live):
                if other.keep_with == node.name:
                    live.remove(other)
                    dropped.append(other)
    return live, dropped


def copy_of(node: PromptNode) -> PromptNode:
    return PromptNode(node.name, node.priority, node.text,
                      [copy_of(c) for c in node.children],
                      node.pass_priority, node.keep_with)


# ------------------------------------------------------------------ demo ----
def readme_tree(with_parent_priorities: bool) -> PromptNode:
    """The README's own example. The only difference between the two runs is
    whether the two parents carry a priority at all."""
    u, s = (1, 2) if with_parent_priorities else (0, 0)
    return PromptNode("root", children=[
        PromptNode("UserMessage", u, children=[
            PromptNode("A", 100, "A" * 200), PromptNode("B", 0, "B" * 200)]),
        PromptNode("SystemMessage", s, children=[
            PromptNode("C", 200, "C" * 200), PromptNode("D", 20, "D" * 200)]),
    ])


def main():
    for flag, label in [(True, "parents ranked 1 and 2"), (False, "parents unranked")]:
        order = [n.name for n in prune_order(readme_tree(flag))]
        print(f"  {label:<24} prune order: {' -> '.join(order)}")
    print("  the only change is the parents. A at 100 outlives D at 20 in one and not the other.\n")

    agent = PromptNode("root", children=[
        PromptNode("system", 900, children=[PromptNode("rules", 10, "Never edit files outside the repo. " * 3)]),
        PromptNode("wrapper", 500, pass_priority=True, children=[
            PromptNode("tool_req", 60, "call: read_file(src/app.py) " * 2, keep_with="tool_res"),
            PromptNode("tool_res", 50, "result: 400 lines of app.py " * 4)]),
        PromptNode("history", 10, children=[
            PromptNode("turn1", 5, "user asked about tests " * 6),
            PromptNode("turn2", 9, "user asked about deploys " * 6)]),
    ])
    print(f"agent prompt: {agent.tokens()} tokens, budget {TOKEN_BUDGET}")
    kept, dropped = prune_to_budget(agent, TOKEN_BUDGET)
    print(f"  kept   : {', '.join(n.name for n in kept)}")
    print(f"  dropped: {', '.join(n.name for n in dropped)}")
    print(f"  total  : {sum(len(n.text) // CHARS_PER_TOKEN for n in kept)} tokens\n")

    print("  'rules' has the LOWEST number in the tree (10) and survives, because its parent")
    print("  is ranked 900. History's turns carry 5 and 9 and go first. tool_req is tied to")
    print("  tool_res, so an orphaned request can never outlive the answer it refers to.")


if __name__ == "__main__":
    main()
