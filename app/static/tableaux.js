/* Tableaux de données (recherche, tri, pagination) sans dépendance et hors ligne.
 *
 * S'applique à toutes les tables `table.table` de la page, sauf celles marquées data-tableau="non".
 * Les lignes ne sont jamais recréées : elles sont seulement masquées ou réordonnées. Les champs de
 * saisie, les formulaires reliés (attribut form=) et les libellés de la vue mobile restent intacts.
 */
(function () {
  "use strict";
  const TAILLES = [10, 25, 50, 0]; // 0 = tout

  // Valeur de tri d'une cellule : nombre (montants, quantités), date, sinon texte.
  function valeur(cellule) {
    if (!cellule) return "";
    const champ = cellule.querySelector("input:not([type=hidden]), select");
    const brut = (champ ? (champ.tagName === "SELECT" ? champ.options[champ.selectedIndex]?.text : champ.value)
                        : cellule.textContent) || "";
    const texte = brut.replace(/\s+/g, " ").trim();
    const date = texte.match(/^(\d{2})\/(\d{2})\/(\d{4})(?:\s+(\d{2}):(\d{2}))?/);
    if (date) return Number(date[3] + date[2] + date[1] + (date[4] || "00") + (date[5] || "00"));
    const nombre = texte.replace(/[\s  ]/g, "").replace(/F$|%$/, "").replace(/^[−-]/, "-").replace(",", ".");
    if (/^-?\d+(\.\d+)?$/.test(nombre)) return Number(nombre);
    return texte.toLocaleLowerCase("fr");
  }

  function comparer(a, b) {
    if (typeof a === "number" && typeof b === "number") return a - b;
    return String(a).localeCompare(String(b), "fr", { numeric: true });
  }

  function equiper(table, index) {
    const corps = table.tBodies[0];
    if (!corps) return;
    const lignes = Array.from(corps.rows).filter(l => !(l.cells.length === 1 && l.cells[0].colSpan > 1));
    if (lignes.length < 2) return; // ligne « aucun résultat » ou ligne unique : rien à trier ni à chercher
    const etat = { filtre: "", taille: 10, page: 0, colonne: -1, sens: 1 };
    lignes.forEach(l => { l.dataset.recherche = l.textContent.replace(/\s+/g, " ").toLocaleLowerCase("fr"); });

    // Barre d'outils au-dessus de la table, pied (pagination) en dessous.
    const enveloppe = table.closest(".table-responsive") || table;
    const outils = document.createElement("div");
    outils.className = "dt-outils";
    const id = "dt-recherche-" + index;
    outils.innerHTML =
      '<label class="dt-recherche" for="' + id + '"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="M20 20l-4.8-4.8"/></svg>' +
      '<input id="' + id + '" type="search" placeholder="Rechercher dans le tableau" aria-label="Rechercher dans le tableau"></label>' +
      '<label class="dt-taille">Afficher <select aria-label="Lignes par page">' +
      TAILLES.map(t => '<option value="' + t + '"' + (t === 10 ? " selected" : "") + ">" + (t || "Tout") + "</option>").join("") +
      "</select></label>";
    const pied = document.createElement("div");
    pied.className = "dt-pied";
    pied.innerHTML = '<span class="dt-info" aria-live="polite"></span><nav class="dt-pages" aria-label="Pagination"></nav>';
    const vide = document.createElement("tr");
    vide.className = "dt-vide";
    vide.innerHTML = '<td colspan="' + (table.tHead ? table.tHead.rows[0].cells.length : lignes[0].cells.length) + '">Aucun résultat pour cette recherche.</td>';
    enveloppe.before(outils);
    enveloppe.after(pied);
    if (lignes.length <= 10) outils.querySelector(".dt-taille").hidden = true;
    if (lignes.length <= 5) outils.hidden = true; // petite table : le tri suffit, la recherche encombrerait

    // En-têtes triables (colonnes vides ou de boutons exclues).
    const entetes = table.tHead ? Array.from(table.tHead.rows[0].cells) : [];
    entetes.forEach((th, i) => {
      if (!th.textContent.trim() || th.dataset.tri === "non") return;
      th.classList.add("dt-triable");
      th.tabIndex = 0;
      th.setAttribute("aria-sort", "none");
      const trier = () => {
        etat.sens = etat.colonne === i ? -etat.sens : 1;
        etat.colonne = i;
        entetes.forEach(e => e.setAttribute("aria-sort", "none"));
        th.setAttribute("aria-sort", etat.sens === 1 ? "ascending" : "descending");
        lignes.sort((a, b) => etat.sens * comparer(valeur(a.cells[i]), valeur(b.cells[i])));
        lignes.forEach(l => corps.appendChild(l));
        etat.page = 0;
        afficher();
      };
      th.addEventListener("click", trier);
      th.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); trier(); } });
    });

    function afficher() {
      const visibles = lignes.filter(l => !etat.filtre || l.dataset.recherche.includes(etat.filtre));
      const taille = etat.taille || visibles.length || 1;
      const pages = Math.max(1, Math.ceil(visibles.length / taille));
      etat.page = Math.min(etat.page, pages - 1);
      const debut = etat.page * taille, fin = debut + taille;
      lignes.forEach(l => { l.hidden = true; });
      visibles.slice(debut, fin).forEach(l => { l.hidden = false; });
      if (visibles.length) vide.remove(); else corps.appendChild(vide);
      pied.querySelector(".dt-info").textContent = visibles.length
        ? (debut + 1) + "–" + Math.min(fin, visibles.length) + " sur " + visibles.length + (etat.filtre ? " (filtré sur " + lignes.length + ")" : "")
        : "0 résultat";
      const nav = pied.querySelector(".dt-pages");
      nav.replaceChildren();
      if (pages > 1) {
        const bouton = (libelle, page, actif, inactif, aria) => {
          const b = document.createElement("button");
          b.type = "button"; b.textContent = libelle; b.disabled = inactif;
          if (actif) { b.className = "actif"; b.setAttribute("aria-current", "page"); }
          if (aria) b.setAttribute("aria-label", aria);
          b.addEventListener("click", () => { etat.page = page; afficher(); });
          nav.appendChild(b);
        };
        bouton("‹", etat.page - 1, false, etat.page === 0, "Page précédente");
        for (let p = 0; p < pages; p++) {
          if (pages > 7 && p > 1 && p < pages - 2 && Math.abs(p - etat.page) > 1) {
            if (!nav.lastChild || nav.lastChild.textContent !== "…") { const s = document.createElement("span"); s.textContent = "…"; nav.appendChild(s); }
            continue;
          }
          bouton(String(p + 1), p, p === etat.page, false, "Page " + (p + 1));
        }
        bouton("›", etat.page + 1, false, etat.page === pages - 1, "Page suivante");
      }
      pied.hidden = lignes.length <= 10 && !etat.filtre;
    }

    outils.querySelector("input").addEventListener("input", e => {
      etat.filtre = e.target.value.trim().toLocaleLowerCase("fr");
      etat.page = 0;
      afficher();
    });
    outils.querySelector("select").addEventListener("change", e => {
      etat.taille = Number(e.target.value);
      etat.page = 0;
      afficher();
    });
    table.classList.add("dt-equipee");
    afficher();
  }

  document.querySelectorAll("table.table:not([data-tableau=non])").forEach(equiper);
})();
