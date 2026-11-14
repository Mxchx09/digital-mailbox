(() => {
  function hideCode() {
    postfachCode.textContent = "•".repeat(originalCode.length);
  }

  function showCode() {
    postfachCode.textContent = originalCode;
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
    setTimeout(() => {
      popup.remove();
    }, 2000); // show for two seconds
  }

  const codeBox = document.getElementById("postfach-code");
  const postfachCode = document.getElementById("postfach-value");

  // copy on button click
  const copyButton = document.getElementById("copy-code");
  if (copyButton && postfachCode) {
    copyButton.addEventListener("click", () => {
      const code = postfachCode.textContent;
      navigator.clipboard.writeText(code).then(() => {
        feedbackOnCopy();
      }); // for visual feedback on copy
    });
  }
  
  if (!codeBox || !postfachCode) {
    return;
  }

  const originalCode = postfachCode.textContent;

  hideCode();
  codeBox.addEventListener("mouseenter", showCode);
  codeBox.addEventListener("mouseleave", hideCode);
})();