
const form = document.getElementById("tripForm");

document.querySelectorAll("[data-destination]").forEach(card => {
    card.addEventListener("click", () => {
        document.getElementById("destination").value = card.dataset.destination;
    });
});

form.addEventListener("submit", async function(event) {

    event.preventDefault();

    const destination =
        document.getElementById("destination").value;

    const startingLocation =
        document.getElementById("startingLocation").value;

    const budget =
        document.getElementById("budget").value;

    const days =
        document.getElementById("days").value;

    const button = form.querySelector("button");

    button.disabled = true;
    button.textContent = "Creating your getaway... ✨";

    try {

        const response = await fetch("/generate-plan", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                destination,
                startingLocation,
                budget,
                days
            })
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.error || "Something went wrong");
        }

        sessionStorage.setItem("travelPlan", JSON.stringify(data.plan));
        sessionStorage.setItem("destination", destination);
        sessionStorage.setItem("budget", budget);
        sessionStorage.setItem("days", days);

        window.location.href = "/results";

    } catch (error) {

        alert("Unable to generate your trip: " + error.message);

        button.disabled = false;
        button.textContent = "Generate My Travel Plan ✨";

    }

});
