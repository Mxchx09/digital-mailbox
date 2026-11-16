(() => {
  const codeBox = document.getElementById("postfach-code");
  const postfachCode = document.getElementById("postfach-value");
  const copyButton = document.getElementById("copy-code");
  const toggle = document.getElementById("zeigen-postfach");

  if (!codeBox || !postfachCode) {
    return;
  }

  const originalCode = postfachCode.textContent;
  const touchQuery = window.matchMedia("(hover: none), (pointer: coarse)");
  let codeVisible = false;

  if (!touchQuery.matches && toggle) {
    toggle.closest("label").remove();
  }

  function updateToggle() {
    if (!toggle) {
      return;
    }

    toggle.checked = codeVisible;
  }

  function hideCode() {
    postfachCode.textContent = "•".repeat(originalCode.length);
    codeVisible = false;
    updateToggle();
  }

  function showCode() {
    postfachCode.textContent = originalCode;
    codeVisible = true;
    updateToggle();
  }

  function feedbackOnCopy() {
    let popup = document.createElement("p");
    popup.textContent = "Postfach code kopiert!";
    popup.classList.add("copy-feedback");
    document.body.appendChild(popup);

    popup.style.position = "fixed";
    popup.style.top = "10%";
    popup.style.left = "50%"; // centered horizontally
    popup.style.transform = "translate(-50%, -50%)";
    popup.style.backgroundColor = "#002d6a";
    popup.style.color = "#fff";
    popup.style.padding = "1rem 2rem";
    popup.style.borderRadius = "0.5rem";
    popup.style.zIndex = "1000";

    // show for two seconds
    setTimeout(() => {
      popup.remove();
    }, 2000);
  }

  function copyCode() {
    navigator.clipboard.writeText(originalCode).then(() => {
      feedbackOnCopy();
    });
  }

  if (copyButton) {
    copyButton.addEventListener("click", copyCode);
  }

  if (toggle) {
    toggle.addEventListener("change", () => {
      if (toggle.checked) {
        showCode();
      } else {
        hideCode();
      }
    });
  }

  hideCode();
  codeBox.addEventListener("mouseenter", () => {
    if (!touchQuery.matches) {
      showCode();
    }
  });
  codeBox.addEventListener("mouseleave", () => {
    if (!touchQuery.matches) {
      hideCode();
    }
  });
  codeBox.addEventListener("click", (event) => {
    if (touchQuery.matches && !event.target.closest("button, label")) {
      copyCode();
    }
  });
})();