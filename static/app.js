(function () {
  var toggle = document.querySelector("[data-nav-toggle]");
  var nav = document.querySelector("[data-nav]");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }
  document.querySelectorAll("[data-upper]").forEach(function (el) {
    el.addEventListener("input", function () {
      var pos = el.selectionStart;
      el.value = el.value.toUpperCase();
      try { el.setSelectionRange(pos, pos); } catch (e) {}
    });
  });
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.getAttribute("data-confirm"))) { e.preventDefault(); }
    });
  });
  // Country-aware forms: swap examples, help text and the list of places when the country changes.
  (function () {
    var form = document.querySelector("form[data-countries]");
    var select = document.getElementById("id_country");
    var area = document.getElementById("id_area");
    if (!form || !select || !area) { return; }
    var data;
    try { data = JSON.parse(form.getAttribute("data-countries")); } catch (e) { return; }
    var groups = Array.prototype.slice.call(area.querySelectorAll("optgroup"));
    var phoneIds = ["id_phone", "id_holder_phone"];
    function setPlaceholder(id, text) { var el = document.getElementById(id); if (el) { el.setAttribute("placeholder", text); } }
    function apply() {
      var c = data[select.value] || data.ZW;
      var keep = area.value;
      groups.forEach(function (g) { if (g.parentNode === area) { area.removeChild(g); } });
      groups.forEach(function (g) { if (g.label === c.name) { area.appendChild(g); } });
      var stillThere = Array.prototype.some.call(area.options, function (o) { return o.value === keep && o.value !== ""; });
      area.value = stillThere ? keep : "";
      setPlaceholder("id_full_name", c.name_example);
      setPlaceholder("id_last5", c.last5_example);
      setPlaceholder("id_location_detail", c.place_example);
      phoneIds.forEach(function (id) { setPlaceholder(id, c.phone_example); });
      var help = document.getElementById("id_last5_help");
      if (help) { help.textContent = c.last5_help; }
      var label = document.querySelector('label[for="id_area"]');
      if (label) { label.textContent = c.area_label.charAt(0).toUpperCase() + c.area_label.slice(1) + " *"; }
    }
    select.addEventListener("change", apply);
    apply();
  })();
})();
