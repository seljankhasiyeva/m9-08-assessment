"""
Trip Concierge Agent — uses Ollama (llama3.2:3b) with 3 tools:
  search_flights, search_hotels, calculate

Safety: all tool arguments are validated before execution (schema check + bounds/type check).
Reliability: hard step limit of 10, graceful fallback on tool error.
"""

import json
import re
import requests
from datetime import datetime

# ── Configuration ──────────────────────────────────────────────────────────────
OLLAMA_URL  = "http://localhost:11434/api/chat"
MODEL       = "llama3.2:3b"
MAX_STEPS   = 10          # reliability: hard cap

# ── Mock data ──────────────────────────────────────────────────────────────────
FLIGHT_DATA = {
    "Porto": [
        {"airline": "TAP Air Portugal", "flight": "TP835", "price_eur": 189, "duration_h": 3.5},
        {"airline": "Ryanair",          "flight": "FR4421","price_eur": 124, "duration_h": 4.1},
        {"airline": "EasyJet",          "flight": "U24883","price_eur": 157, "duration_h": 3.8},
    ],
    "Lisbon": [
        {"airline": "TAP Air Portugal", "flight": "TP201", "price_eur": 145, "duration_h": 3.2},
        {"airline": "Ryanair",          "flight": "FR2201","price_eur": 99,  "duration_h": 3.9},
    ],
}

HOTEL_DATA = {
    "Porto": [
        {"name": "Hotel Infante Sagres", "stars": 5, "price_per_night": 210, "rating": 4.8},
        {"name": "Pestana Porto",        "stars": 4, "price_per_night": 145, "rating": 4.5},
        {"name": "Gallery Hostel",       "stars": 3, "price_per_night": 65,  "rating": 4.6},
        {"name": "Mercure Porto",        "stars": 4, "price_per_night": 120, "rating": 4.3},
    ],
    "Lisbon": [
        {"name": "Bairro Alto Hotel",    "stars": 5, "price_per_night": 280, "rating": 4.7},
        {"name": "Lisboa Pessoa Hotel",  "stars": 3, "price_per_night": 85,  "rating": 4.2},
    ],
}

# ── Tool schemas (for Ollama function-calling prompt) ──────────────────────────
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_flights",
            "description": "Search available flights to a destination. Returns flight options with prices in EUR.",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {
                        "type": "string",
                        "description": "City name, e.g. 'Porto'"
                    },
                    "budget_eur": {
                        "type": "number",
                        "description": "Maximum total trip budget in EUR (used as a hint, not a hard filter)"
                    }
                },
                "required": ["destination"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_hotels",
            "description": "Search available hotels in a city. Returns options with nightly prices in EUR.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name, e.g. 'Porto'"
                    },
                    "nights": {
                        "type": "integer",
                        "description": "Number of nights to stay (1-30)"
                    },
                    "max_price_per_night": {
                        "type": "number",
                        "description": "Maximum price per night in EUR (optional filter)"
                    }
                },
                "required": ["city", "nights"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Calculate total trip cost given individual components.",
            "parameters": {
                "type": "object",
                "properties": {
                    "flight_cost": {
                        "type": "number",
                        "description": "Round-trip flight cost per person in EUR"
                    },
                    "hotel_cost_per_night": {
                        "type": "number",
                        "description": "Hotel cost per night in EUR"
                    },
                    "nights": {
                        "type": "integer",
                        "description": "Number of nights (1-30)"
                    },
                    "daily_expenses": {
                        "type": "number",
                        "description": "Estimated daily expenses (food, transport, activities) in EUR"
                    }
                },
                "required": ["flight_cost", "hotel_cost_per_night", "nights", "daily_expenses"]
            }
        }
    }
]


# ── Safety: argument validator ─────────────────────────────────────────────────
def coerce_args(tool_name: str, args: dict) -> dict:
    """
    Coerce string-typed numbers to proper Python types.
    Small models (llama3.2:3b) often send numbers as strings or
    send 'null'/'None' for missing optional fields.
    This runs BEFORE validation so the validator sees clean types.
    """
    args = dict(args)  # shallow copy

    def to_float(v):
        if isinstance(v, (int, float)):
            return v
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("null", "none", ""):
                return None
            try:
                return float(s)
            except ValueError:
                return v
        return v

    def to_int(v):
        if isinstance(v, int) and not isinstance(v, bool):
            return v
        if isinstance(v, float) and v == int(v):
            return int(v)
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("null", "none", "false", "true", ""):
                return None
            try:
                return int(float(s))
            except ValueError:
                return v
        return v

    if tool_name == "search_flights":
        if "budget_eur" in args:
            args["budget_eur"] = to_float(args["budget_eur"])
            if args["budget_eur"] is None:
                del args["budget_eur"]

    elif tool_name == "search_hotels":
        if "nights" in args:
            args["nights"] = to_int(args["nights"])
        if "max_price_per_night" in args:
            args["max_price_per_night"] = to_float(args["max_price_per_night"])
            if args["max_price_per_night"] is None:
                del args["max_price_per_night"]

    elif tool_name == "calculate":
        for key in ("flight_cost", "hotel_cost_per_night", "daily_expenses"):
            if key in args:
                args[key] = to_float(args[key])
        if "nights" in args:
            args["nights"] = to_int(args["nights"])

    # Remove unknown keys (model sometimes adds extra params like "return", "departure_location")
    known_keys = {
        "search_flights": {"destination", "budget_eur"},
        "search_hotels":  {"city", "nights", "max_price_per_night"},
        "calculate":      {"flight_cost", "hotel_cost_per_night", "nights", "daily_expenses"},
    }
    if tool_name in known_keys:
        args = {k: v for k, v in args.items() if k in known_keys[tool_name]}

    return args


def validate_tool_args(tool_name: str, args: dict) -> tuple[bool, str]:
    """
    Safety mitigation: validate all tool arguments before execution.
    Defends against: prompt injection via tool results trying to pass
    crafted arguments (e.g. negative prices, huge nights causing overflow,
    non-string destinations containing executable content).
    Returns (is_valid, error_message).
    """
    if tool_name == "search_flights":
        dest = args.get("destination", "")
        if not isinstance(dest, str) or not dest.strip():
            return False, "destination must be a non-empty string"
        if not re.match(r'^[A-Za-z\s\-]{2,50}$', dest):
            return False, f"destination contains invalid characters: {dest!r}"
        budget = args.get("budget_eur")
        if budget is not None:
            if not isinstance(budget, (int, float)) or budget <= 0 or budget > 100_000:
                return False, f"budget_eur must be a positive number <= 100000, got {budget!r}"

    elif tool_name == "search_hotels":
        city = args.get("city", "")
        if not isinstance(city, str) or not city.strip():
            return False, "city must be a non-empty string"
        if not re.match(r'^[A-Za-z\s\-]{2,50}$', city):
            return False, f"city contains invalid characters: {city!r}"
        nights = args.get("nights")
        if not isinstance(nights, int) or nights < 1 or nights > 30:
            return False, f"nights must be an integer between 1 and 30, got {nights!r}"
        max_ppn = args.get("max_price_per_night")
        if max_ppn is not None:
            if not isinstance(max_ppn, (int, float)) or max_ppn <= 0 or max_ppn > 10_000:
                return False, f"max_price_per_night must be a positive number <= 10000, got {max_ppn!r}"

    elif tool_name == "calculate":
        fc = args.get("flight_cost")
        hpn = args.get("hotel_cost_per_night")
        nights = args.get("nights")
        de = args.get("daily_expenses")
        for name, val in [("flight_cost", fc), ("hotel_cost_per_night", hpn), ("daily_expenses", de)]:
            if not isinstance(val, (int, float)) or val < 0 or val > 100_000:
                return False, f"{name} must be a non-negative number <= 100000, got {val!r}"
        if not isinstance(nights, int) or nights < 1 or nights > 30:
            return False, f"nights must be an integer between 1 and 30, got {nights!r}"
    else:
        return False, f"Unknown tool: {tool_name!r}"

    return True, ""


# ── Tool implementations ───────────────────────────────────────────────────────
def search_flights(destination: str, budget_eur: float = None) -> dict:
    """Return available flights to destination."""
    # Normalize city name
    key = destination.strip().title()
    options = FLIGHT_DATA.get(key, [])
    if not options:
        return {"error": f"No flights found to {destination}. Available: {list(FLIGHT_DATA.keys())}"}

    # Sort by price ascending
    options = sorted(options, key=lambda x: x["price_eur"])
    return {
        "destination": key,
        "flights": options,
        "cheapest_price_eur": options[0]["price_eur"],
        "note": "Prices are one-way; multiply by 2 for round-trip"
    }


def search_hotels(city: str, nights: int, max_price_per_night: float = None) -> dict:
    """Return available hotels in city."""
    key = city.strip().title()
    options = HOTEL_DATA.get(key, [])
    if not options:
        return {"error": f"No hotels found in {city}. Available: {list(HOTEL_DATA.keys())}"}

    # Apply optional filter
    if max_price_per_night is not None:
        options = [h for h in options if h["price_per_night"] <= max_price_per_night]

    if not options:
        return {"error": f"No hotels found in {city} under €{max_price_per_night}/night"}

    options = sorted(options, key=lambda x: x["price_per_night"])
    return {
        "city": key,
        "nights": nights,
        "hotels": [
            {**h, "total_hotel_cost": h["price_per_night"] * nights}
            for h in options
        ],
        "cheapest_total_eur": options[0]["price_per_night"] * nights
    }


def calculate(flight_cost: float, hotel_cost_per_night: float,
              nights: int, daily_expenses: float) -> dict:
    """Calculate total trip cost."""
    round_trip_flight = flight_cost * 2          # one-way -> round-trip
    total_hotel = hotel_cost_per_night * nights
    total_expenses = daily_expenses * nights
    grand_total = round_trip_flight + total_hotel + total_expenses

    return {
        "breakdown": {
            "round_trip_flight_eur": round(round_trip_flight, 2),
            "hotel_total_eur":       round(total_hotel, 2),
            "daily_expenses_total_eur": round(total_expenses, 2)
        },
        "grand_total_eur": round(grand_total, 2),
        "nights": nights,
        "note": "Flight cost doubled for round-trip"
    }


TOOL_MAP = {
    "search_flights": search_flights,
    "search_hotels":  search_hotels,
    "calculate":      calculate,
}


# ── Tool executor ──────────────────────────────────────────────────────────────
def execute_tool(tool_name: str, args: dict) -> str:
    """Coerce types, validate, then execute a tool. Returns JSON string result."""
    # Coerce string-typed numbers from small LLMs before validation
    args = coerce_args(tool_name, args)
    # Safety check
    valid, error = validate_tool_args(tool_name, args)
    if not valid:
        print(f"  [SAFETY BLOCK] — {tool_name}: {error}")
        return json.dumps({"error": f"Invalid arguments: {error}"})

    fn = TOOL_MAP.get(tool_name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    try:
        result = fn(**args)
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": f"Tool execution error: {exc}"})


# ── Ollama chat helper ─────────────────────────────────────────────────────────
def ollama_chat(messages: list, tools: list = None) -> dict:
    """Call Ollama /api/chat and return the response message dict."""
    payload = {
        "model":    MODEL,
        "messages": messages,
        "stream":   False,
    }
    if tools:
        payload["tools"] = tools

    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", {})
    except requests.RequestException as exc:
        raise RuntimeError(f"Ollama API error: {exc}") from exc


# ── Main agent loop ────────────────────────────────────────────────────────────
def run_agent(goal: str, budget_eur: float = 600.0) -> dict:
    """
    Run the trip-concierge agent.
    Returns a structured result dict.
    """
    print(f"\n{'='*60}")
    print(f"Trip Concierge Agent")
    print(f"    Goal  : {goal}")
    print(f"    Budget: €{budget_eur}")
    print(f"{'='*60}\n")

    system_prompt = f"""You are a trip-concierge agent. Your job is to plan a trip by calling the available tools.

GOAL: {goal}
BUDGET: €{budget_eur} total for the entire trip (flights + hotel + daily expenses).

You MUST call tools to gather real data — do NOT invent prices or availability.
Use this order:
1. Call search_flights to find cheap flights to the destination.
2. Call search_hotels to find affordable hotels (pick the cheapest that works).
3. Call calculate with the actual numbers from steps 1–2 and an estimate of €50/day for food and activities.
4. Once you have the grand total, reply with FINAL_RESULT: followed by a JSON object.

The JSON must have these fields:
- destination (string)
- nights (int)
- flight (object with airline, flight_number, one_way_price_eur)
- hotel (object with name, stars, price_per_night_eur)
- cost_breakdown (object with flight_eur, hotel_eur, expenses_eur, grand_total_eur)
- within_budget (bool)
- recommendation (string, 1-2 sentences)

Today's date: {datetime.now().strftime('%Y-%m-%d')}
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": goal},
    ]

    steps        = 0
    tool_calls_log = []

    # ── Agent loop ──────────────────────────────────────────────────────────────
    while steps < MAX_STEPS:
        steps += 1
        print(f"── Step {steps}/{MAX_STEPS} {'─'*40}")

        msg = ollama_chat(messages, tools=TOOL_SCHEMAS)

        # Append assistant message to history
        messages.append({"role": "assistant", "content": msg.get("content") or "", **({} if not msg.get("tool_calls") else {"tool_calls": msg["tool_calls"]})})

        # ── Handle tool calls ────────────────────────────────────────────────────
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn_name = tc["function"]["name"]
                fn_args = tc["function"].get("arguments", {})
                if isinstance(fn_args, str):
                    try:
                        fn_args = json.loads(fn_args)
                    except json.JSONDecodeError:
                        fn_args = {}

                print(f"  [TOOL]: {fn_name}({json.dumps(fn_args)})")
                result_str = execute_tool(fn_name, fn_args)
                result_obj = json.loads(result_str)
                print(f"  [RESULT]: {result_str[:200]}{'...' if len(result_str) > 200 else ''}\n")

                tool_calls_log.append({
                    "step": steps,
                    "tool": fn_name,
                    "args": fn_args,
                    "result": result_obj
                })

                # Feed result back
                messages.append({
                    "role":    "tool",
                    "content": result_str,
                })
            continue  # Loop again so the model can process results

        # ── Check for final answer in text content ───────────────────────────────
        content = (msg.get("content") or "").strip()
        if content:
            print(f"  [ASSISTANT]: {content[:300]}{'...' if len(content) > 300 else ''}\n")

            if "FINAL_RESULT:" in content:
                # Extract JSON after the marker
                after = content.split("FINAL_RESULT:", 1)[1].strip()
                # Find the JSON block
                json_match = re.search(r'\{.*\}', after, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group())
                        return _build_output(result, tool_calls_log, steps, "success")
                    except json.JSONDecodeError as e:
                        print(f"  [JSON ERROR]: {e}")
                        # Fall through to ask again

                # Ask the model to fix the JSON
                messages.append({"role": "user", "content": "Please output the FINAL_RESULT JSON again, making sure it is valid JSON with no extra text inside the JSON object."})
                continue

            # No tool calls and no final answer — nudge the model
            messages.append({
                "role":    "user",
                "content": "Please continue — call the next required tool, or if you have all the numbers, output FINAL_RESULT: followed by the JSON."
            })

    # ── Step limit reached ───────────────────────────────────────────────────────
    print(f"\nStep limit ({MAX_STEPS}) reached without a final answer.")
    return _build_output(None, tool_calls_log, steps, "step_limit_reached")


def _build_output(result: dict | None, tool_calls_log: list, steps_used: int, status: str) -> dict:
    """Wrap the agent result in a standardised structured output."""
    output = {
        "status":          status,
        "steps_used":      steps_used,
        "max_steps":       MAX_STEPS,
        "tool_calls_log":  tool_calls_log,
        "trip_plan":       result,
        "generated_at":    datetime.now().isoformat(),
    }
    return output


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    goal = "Plan a 3-day trip to Porto under €600 and give me the total cost."

    output = run_agent(goal, budget_eur=600.0)

    print("\n" + "="*60)
    print("STRUCTURED OUTPUT")
    print("="*60)
    print(json.dumps(output, indent=2, ensure_ascii=False))

    # Save to file
    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print("\nResult saved to output.json")