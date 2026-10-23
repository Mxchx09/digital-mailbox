(function () {
  var box = document.getElementById("text"), out = document.getElementById("count");
  if (!box || !out) return;
  var min = parseInt(box.dataset.min, 10);
  function update() {
    var n = box.value.trim() ? box.value.trim().split(/\s+/).length : 0;
    out.textContent = n >= min ? n + " Wörter, das reicht." : n + " von mindestens " + min + " Wörtern";
  }
  box.addEventListener("input", update);
  update();
})();
