(function () {
  var emp = document.getElementById("empfaenger"), kat = document.getElementById("kategorie");
  if (!emp || !kat) return;
  var topics = JSON.parse(emp.dataset.topics || "{}");
  var current = kat.value;
  // Themenliste passend zum gewaehlten Empfaenger aufbauen (ohne JavaScript zeigt die Seite alle Themen gruppiert an)
  function fill() {
    var list = topics[emp.value] || [];
    kat.innerHTML = "";
    var ph = document.createElement("option");
    ph.value = ""; ph.disabled = true; ph.selected = true;
    ph.textContent = emp.value ? "Thema auswählen" : "Zuerst einen Empfänger wählen";
    kat.appendChild(ph);
    list.forEach(function (t) {
      var o = document.createElement("option");
      o.value = t; o.textContent = t;
      if (t === current) o.selected = true;
      kat.appendChild(o);
    });
  }
  emp.addEventListener("change", function () { current = ""; fill(); });
  fill();
})();
