/* Téléphone WhatsApp flottant : ouvert sur toutes les pages, déplaçable, redimensionnable.
 * Position, taille et état ouvert ou fermé sont conservés d'une page à l'autre (localStorage). */
(function () {
  "use strict";
  const panneau = document.getElementById("tel-flottant"), lanceur = document.getElementById("tel-lanceur");
  const poignee = document.getElementById("tel-poignee"), cadre = document.getElementById("tel-cadre");
  if (!panneau || !lanceur) return;
  const CLE = "efacil-telephone";
  const lire = () => { try { return JSON.parse(localStorage.getItem(CLE)) || {}; } catch (e) { return {}; } };
  const ecrire = (maj) => { try { localStorage.setItem(CLE, JSON.stringify({ ...lire(), ...maj })); } catch (e) {} };

  function borner() {
    const r = panneau.getBoundingClientRect(), marge = 8;
    const x = Math.min(Math.max(marge, r.left), window.innerWidth - Math.min(r.width, window.innerWidth) - marge);
    const y = Math.min(Math.max(marge, r.top), window.innerHeight - 48);
    panneau.style.left = x + "px"; panneau.style.top = y + "px";
  }
  function ouvrir(enregistrer = true) {
    if (!cadre.src) cadre.src = cadre.dataset.src;
    panneau.hidden = false; lanceur.setAttribute("aria-expanded", "true"); lanceur.classList.add("ouvert");
    borner();
    if (enregistrer) ecrire({ ouvert: true });
  }
  function fermer() {
    panneau.hidden = true; lanceur.setAttribute("aria-expanded", "false"); lanceur.classList.remove("ouvert");
    ecrire({ ouvert: false }); lanceur.focus();
  }

  // État initial : dernière position et taille connues, sinon en bas à droite.
  const etat = lire();
  const largeur = etat.largeur || 330, hauteur = etat.hauteur || Math.min(680, window.innerHeight - 110);
  panneau.style.width = largeur + "px"; panneau.style.height = hauteur + "px";
  panneau.style.left = (etat.x ?? window.innerWidth - largeur - 24) + "px";
  panneau.style.top = (etat.y ?? window.innerHeight - hauteur - 90) + "px";
  if (etat.ouvert) ouvrir(false);

  lanceur.addEventListener("click", () => (panneau.hidden ? ouvrir() : fermer()));
  document.getElementById("tel-fermer").addEventListener("click", fermer);
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !panneau.hidden && panneau.contains(document.activeElement)) fermer(); });

  // Déplacement par la barre de titre (souris, doigt ou stylet). L'iframe ne capte pas le geste pendant le glissement.
  poignee.addEventListener("pointerdown", e => {
    if (e.target.closest("button, a")) return;
    e.preventDefault();
    const r = panneau.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top;
    panneau.classList.add("glisse"); poignee.setPointerCapture(e.pointerId);
    const bouger = ev => { panneau.style.left = (ev.clientX - dx) + "px"; panneau.style.top = (ev.clientY - dy) + "px"; };
    const lacher = () => {
      panneau.classList.remove("glisse"); borner();
      const p = panneau.getBoundingClientRect(); ecrire({ x: Math.round(p.left), y: Math.round(p.top) });
      poignee.removeEventListener("pointermove", bouger);
    };
    poignee.addEventListener("pointermove", bouger);
    poignee.addEventListener("pointerup", lacher, { once: true });
    poignee.addEventListener("pointercancel", lacher, { once: true });
  });
  // Clavier : flèches pour déplacer quand la barre a le focus.
  poignee.tabIndex = 0;
  poignee.addEventListener("keydown", e => {
    const pas = e.shiftKey ? 40 : 10, d = { ArrowLeft: [-pas, 0], ArrowRight: [pas, 0], ArrowUp: [0, -pas], ArrowDown: [0, pas] }[e.key];
    if (!d) return;
    e.preventDefault();
    const r = panneau.getBoundingClientRect();
    panneau.style.left = (r.left + d[0]) + "px"; panneau.style.top = (r.top + d[1]) + "px"; borner();
    ecrire({ x: Math.round(r.left + d[0]), y: Math.round(r.top + d[1]) });
  });
  // Redimensionnement par le coin (CSS resize) : on mémorise la taille.
  if (window.ResizeObserver) {
    new ResizeObserver(() => {
      if (panneau.hidden) return;
      ecrire({ largeur: Math.round(panneau.offsetWidth), hauteur: Math.round(panneau.offsetHeight) });
    }).observe(panneau);
  }
  window.addEventListener("resize", () => { if (!panneau.hidden) borner(); });
})();
