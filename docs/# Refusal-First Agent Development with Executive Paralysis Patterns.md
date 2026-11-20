  
```
# Refusal-First Agent Development with Executive Paralysis Patterns

## Overview

In human ADHD, “executive paralysis” describes a high-cortisol freeze state: the agent (person) can see the messy kitchen (complex goal + many sub-tasks) but cannot initiate action. The brain treats every fork, sponge, and crumb as equal priority, floods the prefrontal cortex, and falls back to a low-effort numbing behavior (phone scrolling).

The same failure mode appears in LLM-based agents:

- Overwhelming tool choice / multi-step plans
- Competing constraints (safety, cost, latency, user intent)
- Recursive self-critique or planning loops
- “Stuck” states where the agent keeps reasoning but never calls a tool or produces an output

**Refusal-first** development flips the default: the agent is required to evaluate and (when appropriate) refuse *before* any substantive action. Combining refusal-first principles with the practical break-out techniques from executive-paralysis research produces agents that are both safer and less prone to getting stuck.

## Core Mapping

| Human Executive Paralysis | Agent Equivalent | Refusal-First Countermeasure |
|---------------------------|------------------|------------------------------|
| Whole kitchen looks like 400 equal tasks | Large goal + many tools / sub-goals | Force a single-category entry point |
| Internal yelling + guilt | Recursive self-critique or safety over-thinking | Explicit early refusal gate + short circuit |
| Phone as numbing anesthesia | Infinite reasoning / “thinking” tokens | Hard timeout + minimal viable action |
| Shame (“Are you going to sit there all night?”) locks the brakes | Harsh error messages or repeated failure feedback | Warm, non-punitive recovery prompts |
| Standing up for 60 seconds breaks the spell | First successful tool call or small output | Design for immediate tiny success |

## Design Principles

### 1. Refusal Gate First
Every agent turn begins with an explicit refusal check:

```
if violates_safety_policy(input) or violates_user_constraints(input): return refuse_with_explanation()  
```
Never let planning or tool selection begin until this gate has passed. This prevents the agent from entering a high-cognitive-load state on requests it should never attempt.

### 2. Single-Category Entry Point
When the goal is complex, the agent (or the orchestrator) must shrink the target to **one category** before any further planning:

- Bad: “Clean the entire kitchen / solve the full multi-hop research task.”
- Good: “Just collect all the cups / just fetch the primary source document.”

Implementation pattern:

```python
def get_next_atomic_action(goal: str) -> str:
    """
    Force the agent to propose only a single, concrete, low-scope action.
    Reject any plan that contains more than one category of work.
    """
    ...
```
**3. Momentum via Minimal Viable Action**  
Once a refusal has been cleared, require the agent to produce a 60-second-equivalent action:  
* Call one tool with the smallest useful parameters  
* Emit a single intermediate artifact  
* Write one short status update  
The first successful external action usually collapses the paralysis loop.  
**4. Non-Punitive Recovery**  
When the agent fails or loops:  
* Avoid language that increases “shame” (harsh system messages, score penalties that feel like scolding).  
* Use warm, directive recovery: “The previous attempt was too broad. Let’s only grab the cups this time.”  
**5. Explicit Freeze Detection**  
Monitor for classic paralysis signals:  
* High reasoning-token count with zero tool calls  
* Repeated similar plans without progress  
* Oscillation between two options  
On detection, inject a single-category forced action or escalate to a human / higher-privilege controller.  
## Practical Implementation Sketch  
```
class RefusalFirstAgent:
    def __init__(self, safety_policy, tools):
        self.safety_policy = safety_policy
        self.tools = tools

    def step(self, user_input: str, state: dict) -> dict:
        # 1. Refusal gate (always first)
        refusal = self.safety_policy.check(user_input, state)
        if refusal:
            return {"type": "refusal", "message": refusal}

        # 2. Detect paralysis
        if self._is_paralyzed(state):
            return self._force_single_category_action(state)

        # 3. Generate only a single-category next action
        action = self._propose_atomic_action(user_input, state)
        if not self._is_single_category(action):
            return self._force_single_category_action(state)

        # 4. Execute the tiny action
        result = self._execute(action)
        return {"type": "action", "result": result}

    def _is_paralyzed(self, state) -> bool:
        return (
            state.get("reasoning_tokens", 0) > THRESHOLD
            and state.get("tool_calls", 0) == 0
        )
```
## Recommended Prompt Patterns  
**System prompt fragment (refusal + anti-paralysis):**  
```
You operate under a refusal-first policy.
1. Before any planning or tool use, check whether the request should be refused. If yes, refuse immediately and stop.
2. If the request is allowed, never attempt the whole task at once. Select exactly one narrow category of work and perform only that.
3. Prefer the smallest possible successful action that produces observable progress.
4. If you notice yourself generating long reasoning without a concrete next step, stop and emit a single atomic action instead.
```
**Recovery prompt (when freeze is detected):**  
```
You appear stuck. Ignore the full goal for now.
Just do the equivalent of “grab all the cups and put them by the sink.”
Propose and execute one tiny, concrete action only.
```
## Benefits  
* Safety is evaluated before expensive reasoning → lower risk of harmful side-effects.  
* Agents escape analysis paralysis faster.  
* Observable progress increases reliability and makes debugging easier.  
* The same techniques that help ADHD humans (tiny starts, reduced shame, external structure) transfer cleanly to agent loops.  
## Summary Checklist for Developers  
* Refusal / safety gate runs before any planning or tool selection  
* Complex goals are automatically reduced to a single category  
* First action after clearance is deliberately tiny  
* Freeze detection + non-punitive recovery path exists  
* System prompts explicitly encode both refusal-first and anti-paralysis rules  
By treating agent “stuckness” the same way we treat human executive paralysis—acknowledge the freeze, refuse what should be refused, then force one small successful step—you get agents that are safer, more reliable, and less likely to sit on the digital couch scrolling forever.  
