(function () {
  var pw = document.getElementById("code");
  var toggle = document.getElementById("zeigen");
  if (pw && toggle) {
    toggle.addEventListener("change", function () { pw.type = toggle.checked ? "text" : "password"; });
  }
  // Chrome & Co.: Code ausdruecklich zum Speichern anbieten (nur auf Wunsch, beim Klick auf den Button)
  var form = document.getElementById("speichern");
  if (!form || !window.PasswordCredential || !navigator.credentials || !navigator.credentials.store) return;
  form.addEventListener("submit", function (e) {
    if (form.dataset.done) return;
    e.preventDefault();
    var go = function () { form.dataset.done = "1"; form.submit(); };
    try {
      var name = form.elements.benutzer.value;
      navigator.credentials.store(new PasswordCredential({ id: name, name: name, password: form.elements.code.value })).then(go, go);
    } catch (err) { go(); }
  });
})();
