
import json
import os
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load API key from .env
load_dotenv(override=True)

app = Flask(__name__)

# Get Gemini API key
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("Gemini API key not found in .env file")

# Connect to Gemini
client = genai.Client(
    api_key=api_key,
    http_options=types.HttpOptions(timeout=30000)
)


# Homepage
@app.route("/")
def home():
    return render_template("index.html")


# Results page
@app.route("/results")
def results():
    return render_template("results.html")


@app.route("/destination-image")
def destination_image():
    """Find a freely reusable Commons image for any user-entered destination."""
    destination = request.args.get("destination", "").strip()
    if not destination or len(destination) > 120:
        return jsonify({"success": False}), 400

    params = urlencode({
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f'intitle:"{destination}" (landscape OR city OR travel)',
        "gsrnamespace": 6, "gsrlimit": 8,
        "prop": "imageinfo", "iiprop": "url|extmetadata",
        "iiurlwidth": 1800,
    })
    url = "https://commons.wikimedia.org/w/api.php?" + params
    req = Request(url, headers={"User-Agent": "TravelMateAI/1.0 (destination photo lookup)"})
    try:
        with urlopen(req, timeout=5) as response:
            payload = json.load(response)
        pages = (payload.get("query") or {}).get("pages") or {}
        # Keep Unicode letters so destinations written in non-Latin scripts
        # (for example, 東京) can still be checked against Commons file titles.
        query_words = set(re.findall(r"[^\W_]+", destination.casefold(), re.UNICODE))
        candidates = []
        for page in pages.values():
            title_words = set(re.findall(
                r"[^\W_]+", page.get("title", "").casefold(), re.UNICODE
            ))
            overlap = query_words & title_words
            info = (page.get("imageinfo") or [{}])[0]
            image_url = info.get("thumburl") or info.get("url")
            # For multi-word places, require a strong title match. A near-match
            # is better served by the neutral fallback than an unrelated photo.
            minimum_match = max(1, (2 * len(query_words) + 2) // 3)
            if image_url and len(overlap) >= minimum_match:
                candidates.append((len(overlap), page, info, image_url))
        if not candidates:
            return jsonify({"success": False})

        _, page, info, image_url = max(candidates, key=lambda item: item[0])
        metadata = info.get("extmetadata", {})
        artist = re.sub(r"<[^>]*>", "", metadata.get("Artist", {}).get("value", ""))
        license_name = metadata.get("LicenseShortName", {}).get("value", "")
        description_url = info.get("descriptionurl", "https://commons.wikimedia.org/")
        return jsonify({
            "success": True,
            "image": image_url,
            "credit": " · ".join(part for part in (artist, license_name) if part),
            "source": description_url,
        })
    except Exception as error:
        app.logger.info("Destination image lookup unavailable (%s).", type(error).__name__)
        return jsonify({"success": False})



def validate_plan(plan, trip_days, trip_budget):
    """Check that Gemini returned every dashboard section in the expected shape."""
    required_sections = {
        "trip_summary", "hotels", "itinerary", "food", "transport",
        "budget_breakdown",
    }
    if not isinstance(plan, dict) or not required_sections.issubset(plan):
        return "The itinerary is missing required sections. Please try again."

    if not isinstance(plan["trip_summary"], str) or not plan["trip_summary"].strip():
        return "The itinerary summary was empty. Please try again."

    hotels = plan["hotels"]
    if not isinstance(hotels, list) or len(hotels) != 2:
        return "The hotel recommendations were incomplete. Please try again."
    for hotel in hotels:
        if (
            not isinstance(hotel, dict)
            or not all(isinstance(hotel.get(key), str) and hotel[key].strip()
                       for key in ("name", "type", "description"))
            or not isinstance(hotel.get("estimated_price"), int)
            or isinstance(hotel.get("estimated_price"), bool)
            or hotel["estimated_price"] < 0
        ):
            return "A hotel recommendation was incomplete. Please try again."

    itinerary = plan["itinerary"]
    if not isinstance(itinerary, list) or len(itinerary) != trip_days:
        return "The day-by-day itinerary was incomplete. Please try again."
    for day_number, day in enumerate(itinerary, start=1):
        if (
            not isinstance(day, dict)
            or day.get("day") != day_number
            or not isinstance(day.get("title"), str)
            or not day["title"].strip()
            or not isinstance(day.get("activities"), list)
            or not 1 <= len(day["activities"]) <= 3
            or not all(isinstance(item, str) and item.strip() for item in day["activities"])
        ):
            return "A day in the itinerary was incomplete. Please try again."

    for section_name, expected_count in (("food", 3), ("transport", 2)):
        recommendations = plan[section_name]
        if not isinstance(recommendations, list) or len(recommendations) != expected_count:
            return f"The {section_name} recommendations were incomplete. Please try again."
        for item in recommendations:
            if (
                not isinstance(item, dict)
                or not all(isinstance(item.get(key), str) and item[key].strip()
                           for key in ("name", "description"))
                or not isinstance(item.get("estimated_price"), int)
                or isinstance(item.get("estimated_price"), bool)
                or item["estimated_price"] < 0
            ):
                return f"A {section_name} recommendation was incomplete. Please try again."

    budget_parts = ("accommodation", "food", "transport", "activities", "buffer")
    breakdown = plan["budget_breakdown"]
    if not isinstance(breakdown, dict) or not all(
        isinstance(breakdown.get(key), int)
        and not isinstance(breakdown[key], bool)
        and breakdown[key] >= 0
        for key in (*budget_parts, "total")
    ):
        return "The budget breakdown was incomplete. Please try again."
    if breakdown["total"] != trip_budget or sum(
        breakdown[key] for key in budget_parts
    ) != trip_budget:
        return "The generated budget did not match your total budget. Please try again."

    return None


# Generate travel plan
@app.route("/generate-plan", methods=["POST"])
def generate_plan():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "No trip details received."}), 400

    destination = data.get("destination", "")
    starting_location = data.get("startingLocation", "")
    if not isinstance(destination, str) or not isinstance(starting_location, str):
        return jsonify({"success": False, "error": "Please enter valid trip details."}), 400
    destination = destination.strip()
    starting_location = starting_location.strip()

    try:
        budget = int(data.get("budget", ""))
        days = int(data.get("days", ""))
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "error": "Enter a whole-number budget and trip length."
        }), 400

    if not destination or budget < 1 or days < 1:
        return jsonify({
            "success": False,
            "error": "Enter a destination, a positive budget, and a positive number of travel days."
        }), 400

    prompt = f"""
    You are a practical travel planner. Return only one valid JSON object with
    exactly these fields and no markdown fences or extra commentary:
    {{
      "trip_summary": "A concise 1-2 sentence overview",
      "hotels": [
        {{"name": "Name or type of place", "type": "Stay type", "description": "Why it suits this trip", "estimated_price": 0}},
        {{"name": "Name or type of place", "type": "Stay type", "description": "Why it suits this trip", "estimated_price": 0}}
      ],
      "itinerary": [
        {{"day": 1, "title": "Short day title", "activities": ["Practical activity", "Practical activity"]}}
      ],
      "food": [
        {{"name": "Food or place", "description": "Useful concise detail", "estimated_price": 0}}
      ],
      "transport": [
        {{"name": "Transport option", "description": "Useful concise detail", "estimated_price": 0}}
      ],
      "budget_breakdown": {{
        "accommodation": 0, "food": 0, "transport": 0,
        "activities": 0, "buffer": 0, "total": 0
      }}
    }}

    Requirements:
    - Keep the summary, descriptions, and activities short and useful.
    - Give exactly two hotel options, {days} itinerary days numbered in order,
      three food recommendations, and two transport suggestions.
    - Use realistic, practical recommendations for the destination and trip.
    - All estimated_price and budget_breakdown values must be whole-number
      amounts in Indian rupees (INR). Prices are estimates only.
    - Do not claim hotel availability, prices, or bookings are confirmed.
    - Make the five budget categories add up exactly to the total budget;
      set budget_breakdown.total to exactly the user's budget below.
    - Do not include fields beyond the structure shown.

    Destination: {destination}
    Starting location: {starting_location or "Not specified"}
    Total budget: INR {budget}
    Duration: {days} days
    """

    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        if not response.text:
            return jsonify({
                "success": False,
                "error": "The travel planner returned an empty plan. Please try again."
            }), 502

        try:
            plan = json.loads(response.text)
        except json.JSONDecodeError:
            app.logger.warning("Gemini returned a response that was not valid JSON.")
            return jsonify({
                "success": False,
                "error": "The travel planner returned an unreadable plan. Please try again."
            }), 502

        validation_error = validate_plan(plan, days, budget)
        if validation_error:
            app.logger.warning("Gemini returned an incomplete or invalid travel plan.")
            return jsonify({"success": False, "error": validation_error}), 502

        return jsonify({"success": True, "plan": plan})

    except Exception as error:
        # Keep provider details and credentials out of browser responses and logs.
        app.logger.error("TravelMate generation failed (%s).", type(error).__name__)
        return jsonify({
            "success": False,
            "error": "We couldn't generate your travel plan right now. Please try again shortly."
        }), 502


if __name__ == "__main__":
    app.run(debug=True)
