const opening = document.getElementById("skyblink-opening");
const explore = document.getElementById("skyblink-explore");
const teamView = document.getElementById("team-view");
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

teamView.inert = true;
if (!reducedMotion.matches) {
  for (const animation of opening.querySelectorAll("animate, animateMotion")) {
    animation.beginElement?.();
  }
}

function showTeamView() {
  opening.hidden = true;
  teamView.inert = false;
  document.getElementById("q").focus({ preventScroll: true });
  window.dispatchEvent(new Event("resize"));
}

explore.addEventListener("click", () => {
  if (reducedMotion.matches) {
    showTeamView();
    return;
  }
  const transform = getComputedStyle(opening, "::before").transform;
  if (transform !== "none") {
    opening.style.setProperty("--opening-scale", new DOMMatrixReadOnly(transform).a);
  }
  opening.classList.add("departing");
  setTimeout(showTeamView, 760);
}, { once: true });
