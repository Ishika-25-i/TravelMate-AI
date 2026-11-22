const rawPlan = sessionStorage.getItem("travelPlan");
const destination = sessionStorage.getItem("destination") || "Your destination";
const budget = Number(sessionStorage.getItem("budget"));
const days = Number(sessionStorage.getItem("days"));
const money = new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0
});

async function loadDestinationImage() {
    try {
        const response = await fetch("/destination-image?destination=" + encodeURIComponent(destination));
        if (!response.ok) return;
        const data = await response.json();
        if (!data.success || !data.image) return;
        const banner = document.querySelector(".trip-banner");
        const photo = new Image();
        photo.onload = () => {
            banner.style.setProperty("--destination-photo", `url("${data.image.replace(/["\\\\]/g, "")}")`);
            const credit = document.getElementById("imageCredit");
            if (data.credit && data.source) {
                const link = document.createElement("a");
                link.href = data.source;
                link.target = "_blank";
                link.rel = "noopener noreferrer";
                link.textContent = "Photo: " + data.credit + " · Wikimedia Commons";
                credit.replaceChildren(link);
                credit.hidden = false;
            }
        };
        photo.src = data.image;
    } catch (error) {
        // The CSS fallback remains visible when Commons is unavailable.
    }
}

loadDestinationImage();

function showPlanError(message) {
    document.getElementById("planErrorMessage").textContent = message;
    document.getElementById("planError").hidden = false;
    document.querySelectorAll(".dashboard-section, .trip-banner").forEach(section => {
        section.hidden = true;
    });
    document.querySelector(".new-trip-btn").hidden = true;
}

function makeElement(tagName, className, text) {
    const element = document.createElement(tagName);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
}

function renderRecommendations(containerId, items, className, priceLabel) {
    const container = document.getElementById(containerId);
    items.forEach(item => {
        const card = makeElement("article", className);
        card.appendChild(makeElement("h3", "recommendation-title", item.name));
        card.appendChild(makeElement("p", "recommendation-copy", item.description));
        if (item.type) card.appendChild(makeElement("span", "stay-type", item.type));
        card.appendChild(makeElement("p", "recommendation-price",
            priceLabel + ": " + money.format(item.estimated_price)));
        container.appendChild(card);
    });
}

if (!rawPlan) {
    window.location.href = "/";
} else {
    let plan;
    try {
        plan = JSON.parse(rawPlan);
    } catch (error) {
        showPlanError("This saved trip is in an older format. Please create a new trip to see the dashboard.");
    }

    if (plan && typeof plan === "object" && !Array.isArray(plan)) {
        const validShape = typeof plan.trip_summary === "string" &&
            Array.isArray(plan.hotels) &&
            Array.isArray(plan.itinerary) &&
            Array.isArray(plan.food) &&
            Array.isArray(plan.transport) &&
            plan.budget_breakdown;

        if (!validShape) {
            showPlanError("The saved trip is incomplete. Please create a new trip.");
        } else {
            document.getElementById("tripTitle").textContent = destination;
            document.getElementById("tripDetails").textContent =
                days + " days \u00b7 Total budget " + money.format(budget);
            document.getElementById("tripSummary").textContent = plan.trip_summary;

            renderRecommendations("hotelGrid", plan.hotels, "recommendation-card", "Estimated stay");

            const itineraryGrid = document.getElementById("itineraryGrid");
            plan.itinerary.forEach(day => {
                const card = makeElement("article", "itinerary-card");
                card.appendChild(makeElement("p", "day-label", "DAY " + day.day));
                card.appendChild(makeElement("h3", "recommendation-title", day.title));
                const activities = makeElement("ul", "activity-list");
                day.activities.forEach(activity => {
                    activities.appendChild(makeElement("li", "", activity));
                });
                card.appendChild(activities);
                itineraryGrid.appendChild(card);
            });

            renderRecommendations("foodList", plan.food, "simple-card", "Estimate");
            renderRecommendations("transportList", plan.transport, "simple-card", "Estimate");

            const breakdown = plan.budget_breakdown;
            const categories = [
                ["Accommodation", breakdown.accommodation],
                ["Food", breakdown.food],
                ["Transport", breakdown.transport],
                ["Activities", breakdown.activities],
                ["Buffer", breakdown.buffer]
            ];
            document.getElementById("budgetTotal").textContent = money.format(breakdown.total);

            const budgetList = document.getElementById("budgetList");
            const meter = document.getElementById("budgetMeter");
            const colors = ["#d8b66e", "#b8904f", "#92713e", "#6e5734", "#4f422d"];

            categories.forEach(([label, amount], index) => {
                const percentage = budget > 0 ? (amount / budget) * 100 : 0;
                const row = makeElement("div", "budget-row");
                row.appendChild(makeElement("span", "budget-category", label));
                row.appendChild(makeElement("span", "budget-amount", money.format(amount)));
                row.appendChild(makeElement("span", "budget-share", percentage.toFixed(0) + "%"));
                budgetList.appendChild(row);

                const segment = document.createElement("span");
                segment.className = "budget-segment";
                segment.style.width = percentage + "%";
                segment.style.backgroundColor = colors[index];
                segment.setAttribute("aria-label", label + ": " + percentage.toFixed(0) + " percent");
                meter.appendChild(segment);
            });

            meter.setAttribute("aria-valuenow", "100");
            document.getElementById("budgetMeterCaption").textContent =
                "Your estimated category amounts add up to your full trip budget.";
        }
    } else if (plan) {
        showPlanError("The saved trip is incomplete. Please create a new trip.");
    }
}
