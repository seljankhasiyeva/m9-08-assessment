# Trip Concierge Agent

A multi-tool agent that plans a budget trip by autonomously deciding which tools to call and in what order.

---

## Scenario & Tools

**Scenario:** Trip Concierge

**Goal given to agent:** *"Plan a 3-day trip to Porto under €600 and give me the total cost."*

**Three tools:**

| Tool | Why chosen |
|---|---|
| `search_flights` | Fetches available flights with prices — the agent must pick the cheapest option that fits the budget |
| `search_hotels` | Fetches hotel options in the destination city — the agent filters by nightly price |
| `calculate` | Adds up flight (×2 round-trip) + hotel nights + daily expenses to produce a grand total |

These three tools form a natural dependency chain: you need flight prices before you can calculate totals, and hotel prices before the calculation is complete. The agent cannot short-circuit any step — it is forced to reason and call tools in the right order itself.

**Model:** `llama3.2:3b` via Ollama (local inference, no cloud API required)

---

## Reliability Note — Step Limit & Failure Handling

`MAX_STEPS = 10` is enforced as a hard loop cap in `agent.py`.

**What it protects against:**
- An LLM that gets confused and keeps calling the same tool in a loop
- A model that never commits to a final answer and keeps appending "let me also check..."
- Runaway CPU time on a local model

**How failure is handled:**
- If a tool returns an error (e.g. unknown destination), the error string is passed back to the model as a tool result so the model can recover (e.g. try a different city name)
- If the step limit is reached without a final answer, the agent returns `{"status": "step_limit_reached", ...}` with whatever partial tool call logs were accumulated — the run does not crash
- If the model's JSON is malformed, the agent catches the parse error, tells the model to retry, and continues the loop rather than crashing

---

## Safety Note — Argument Validation

**Mitigation implemented:** Every tool call's arguments are validated by `validate_tool_args()` before the tool function is ever invoked.

**What it checks:**
- `destination` / `city` must be a string matching `^[A-Za-z\s\-]{2,50}$` — rejects anything containing digits, shell metacharacters, or SQL/HTML injection attempts
- `budget_eur` / `max_price_per_night` / cost fields must be positive floats within a sane upper bound (≤ €100,000) — prevents integer-overflow tricks or negative-price exploits
- `nights` must be an integer between 1 and 30 — prevents a tool result from injecting `nights=999999` to cause absurd totals

**Attack it defends against:**
A prompt-injection attack where a malicious entry in the "flights database" or the user's own message tries to pass crafted arguments to a tool — for example, a flight search result that contains `"destination": "Porto; DROP TABLE flights; --"` embedded in text that the model might copy-paste into the next tool call. The regex check blocks non-alpha characters in string fields before any tool executes.

---

## Captured Run

```
============================================================
Trip Concierge Agent
    Goal  : Plan a 3-day trip to Porto under €600 and give me the total cost.
    Budget: €600.0
============================================================

-- Step 1/10 ------------------------------------------
  [TOOL]: search_flights({"destination": "Porto", "budget_eur": "600"})
  [RESULT]: {"destination": "Porto", "flights": [{"airline": "Ryanair", "flight": "FR4421", "price_eur": 124, "duration_h": 4.1}, {"airline": "EasyJet", "flight": "U24883", "price_eur": 157, "duration_h": 3.8}, ...], "cheapest_price_eur": 124, "note": "Prices are one-way; multiply by 2 for round-trip"}

-- Step 3/10 ------------------------------------------
  [TOOL]: search_hotels({"city": "Porto", "nights": "3"})
  [RESULT]: {"city": "Porto", "nights": 3, "hotels": [{"name": "Gallery Hostel", "stars": 3, "price_per_night": 65, "rating": 4.6, "total_hotel_cost": 195}, ...], "cheapest_total_eur": 195}

-- Step 9/10 ------------------------------------------
  [TOOL]: calculate({"nights": "3", "daily_expenses": "50", "flight_cost": "124", "hotel_cost_per_night": "65"})
  [RESULT]: {"breakdown": {"round_trip_flight_eur": 248.0, "hotel_total_eur": 195.0, "daily_expenses_total_eur": 150.0}, "grand_total_eur": 593.0, "nights": 3, "note": "Flight cost doubled for round-trip"}

-- Step 8/10 ------------------------------------------
  [ASSISTANT]: FINAL_RESULT: (parsed successfully)

============================================================
STRUCTURED OUTPUT
============================================================
{
  "status": "success",
  "steps_used": 8,
  "max_steps": 10,
  "tool_calls_log": [
    {"step": 1, "tool": "search_flights", "args": {"destination": "Porto", "budget_eur": "600"}, "result": {"cheapest_price_eur": 124, ...}},
    {"step": 3, "tool": "search_hotels",  "args": {"city": "Porto", "nights": "3"}, "result": {"cheapest_total_eur": 195, ...}},
    {"step": 9, "tool": "calculate",      "args": {"flight_cost": "124", "hotel_cost_per_night": "65", "nights": "3", "daily_expenses": "50"}, "result": {"grand_total_eur": 593.0, ...}}
  ],
  "trip_plan": {
    "destination": "Porto",
    "nights": 3,
    "flight": {
      "airline": "Ryanair",
      "flight_number": "FR4421",
      "one_way_price_eur": 124
    },
    "hotel": {
      "name": "Gallery Hostel",
      "stars": 3,
      "price_per_night_eur": 65
    },
    "cost_breakdown": {
      "flight_eur": 248,
      "hotel_eur": 195,
      "expenses_eur": 150,
      "grand_total_eur": 593
    },
    "within_budget": true,
    "recommendation": "This itinerary should fit your budget of 600 EUR. However, please note that prices may vary depending on the time of year and availability."
  },
  "generated_at": "2026-06-28T23:46:16.711422"
}

Result saved to output.json
```

The agent chose its own tool sequence (flights -> hotels -> calculate -> answer) without any hardcoded script. The structured `trip_plan` JSON is directly parseable by another program.

---

## How to Run

```bash
# 1. Make sure Ollama is running with llama3.2:3b
ollama serve
ollama pull llama3.2:3b

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the agent
python agent.py

# Output is printed to terminal and saved to output.json
```

---

## File Structure

```
.
├── agent.py          # Main agent with tools, validation, and loop
├── requirements.txt  # Python dependencies (only `requests`)
├── output.json       # Saved structured result from last run
└── README.md
```