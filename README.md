![logo_ironhack_blue 7](https://user-images.githubusercontent.com/23629340/40541063-a07a0a8a-601a-11e8-91b5-2f13e4e6b441.png)

# Assessment | Ship a Multi-Tool Agent

## Overview

This is your chance to put the second half of the unit together. You'll build a small but genuinely useful **agent** that uses **three tools** to accomplish a real, multi-step goal — deciding its own steps, the way an agent should — and returns a **structured result**. Then you'll show you understand the grown-up parts: one reliability safeguard and one safety mitigation.

No RAG is required here. This is about **agents and tool use**: an agent that reasons, calls tools, and acts.

## What You'll Build

An agent (use **Google ADK**, or a hand-rolled loop if you prefer — your choice) that:

- has **three tools** it can call,
- is given a **multi-step goal** it can't satisfy with a single tool call,
- **decides for itself** which tools to use and in what order,
- returns a **structured final result** (e.g. a small JSON object or a clearly formatted report), and
- is **bounded** (a step limit) and **guarded** (one safety mitigation you implement and explain).

### Pick a scenario (or invent your own)

Choose one that interests you — these are starting points, not requirements:

- **Trip concierge** — tools: `search_flights`, `search_hotels`, `calculate`. Goal: "Plan a 3-day trip to Porto under €600 and give me the total." Output: a structured itinerary with a cost breakdown.
- **Order assistant** — tools: `lookup_order`, `check_warranty`, `calculate`. Goal: "I want two more of my last order — total cost, and is it still under warranty?" Output: a structured summary.
- **Study planner** — tools: `list_topics`, `estimate_effort`, `calculate`. Goal: "Build me a study plan for the exam with total hours." Output: a structured plan.

Your tools can use small local data files (like the `orders.json` you've seen) or return mock data — the focus is the **agent's behaviour**, not a real backend.

## Requirements

Your submission must include:

1. **A working agent** with three tools that solves the multi-step goal by its own tool choices (not a script you hardwired).
2. **A structured output** — the final answer in a parseable, well-shaped form, not just free text.
3. **A step limit** so the agent cannot loop forever, with a sensible cap.
4. **One safety mitigation** that you implement and can justify — for example, treating tool results as untrusted data, validating a tool's arguments before acting, or requiring confirmation before a "destructive" tool runs.
5. **A README** in your repo covering:
   - which scenario and three tools you chose, and why,
   - one **reliability** note (how your step limit / failure handling protects the run),
   - one **safety** note (the mitigation you added and what attack it defends against),
   - a captured run showing the agent's tool calls and structured result.

## Submission

Work on a branch, commit your code and README, open a Pull Request, and paste its link into the submission box.

**Deadline:** Sunday 28 June 2026, 23:59 local time. Late submissions are scored at 70% maximum.

## Grading Rubric (100 pts)

| Area | What we look for | Points |
|---|---|---|
| **Agent works** | Three tools; the multi-step goal is solved by the agent's own tool choices | 30 |
| **Structured output** | Final result is well-shaped and parseable, not free text | 15 |
| **Reliability** | A working step limit; graceful handling when a tool fails or the goal can't be met | 20 |
| **Safety** | A real mitigation, correctly implemented and clearly justified | 20 |
| **README & run** | Clear tool choices, reliability + safety notes, and a captured run | 15 |

## Quality Bar

- The agent **decides its own steps** — reviewers should see tool calls it chose, not a fixed script
- The output is genuinely **structured** and could be consumed by another program
- Both the **step limit** and the **safety mitigation** actually run, and you can explain what each protects against
- No API key is committed to the repo
