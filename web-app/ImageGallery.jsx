import { useEffect } from "react";
import { fetchCommonsImages } from "./apiClient.js";

// Sous-onglet "Image" du panneau Résultat (voir App.jsx, resultSubTab === "image") : galerie de
// suggestions Wikimedia Commons pour la taxobox, déjà filtrées côté serveur par licence
// permissive et par distinction qualité/featured (voir organon/modules/commons_images/service.py)
// — ce composant n'a plus qu'à afficher, jamais à re-filtrer.
//
// Deux actions distinctes par vignette, volontairement non conflictuelles : cliquer l'image
// sélectionne le fichier pour la taxobox (`onSelect`), le lien "Voir sur Commons" à côté ouvre la
// page du fichier dans un nouvel onglet sans rien sélectionner (stopPropagation + cible dédiée).
//
// Les suggestions sont mises en cache côté App.jsx (`cache`, indexé par taxon) plutôt que dans un
// état local : le rendu conditionnel du sous-onglet démonte ce composant à chaque fois qu'on
// bascule sur un autre onglet, un état local perdrait donc les résultats déjà récupérés et
// relancerait la recherche à chaque retour sur "Image". `onCacheChange` reçoit toujours une
// fonction de mise à jour (jamais l'objet complet) pour ne jamais écraser l'entrée d'un autre
// taxon déjà en cache pendant que celle en cours de résolution.
export default function ImageGallery({ taxon, selectedFileName, onSelect, onDeselect, cache, onCacheChange }) {
  const entry = taxon ? cache[taxon] : null;

  useEffect(() => {
    if (!taxon || entry) return; // déjà en cache (recherche précédente ou retour d'onglet)
    onCacheChange((prev) => ({ ...prev, [taxon]: { status: "loading" } }));
    fetchCommonsImages(taxon)
      .then((data) => {
        onCacheChange((prev) => ({ ...prev, [taxon]: { status: "ok", data } }));
      })
      .catch((err) => {
        onCacheChange((prev) => ({
          ...prev,
          [taxon]: { status: "error", error: err.message || "Erreur inconnue." },
        }));
      });
  }, [taxon, entry, onCacheChange]);

  if (!taxon) {
    return <div className="panel-empty">Lancez une génération pour voir les images disponibles.</div>;
  }
  if (!entry || entry.status === "loading") {
    return (
      <div className="panel-loading">
        <p>Recherche d'images sur Commons…</p>
      </div>
    );
  }
  if (entry.status === "error") {
    return <div className="panel-empty">Impossible d'interroger Commons : {entry.error}</div>;
  }

  const { suggestions, category_url: categoryUrl, search_url: searchUrl } = entry.data;
  const browseUrl = categoryUrl || searchUrl;

  if (suggestions.length === 0) {
    return (
      <div className="panel-empty image-gallery-empty">
        <p>
          Aucune image remarquable labelisée n'a été trouvée
          automatiquement pour ce taxon — c'est le cas le plus fréquent, ces distinctions restent rares sur
          Commons.
        </p>
        <a className="edit-btn" href={browseUrl} target="_blank" rel="noopener noreferrer">
          Parcourir {categoryUrl ? "la catégorie Commons" : "Commons"} pour ce taxon
        </a>
      </div>
    );
  }

  return (
    <div className="image-gallery">
      <p className="result-sub">Les images Commons suivantes sont labelisées. Incorporez-les dans l'article ou  cliquez sur la vignette pour l'utiliser directement dans la taxobox.</p>
      <div className="image-gallery-grid">
        {suggestions.map((s) => {
          const selected = s.file_name === selectedFileName;
          return (
            <div className={"image-card" + (selected ? " selected" : "")} key={s.file_name}>
              {/* Le badge "Sélectionnée" devient le bouton de désélection : même emplacement,
                  mais posé en dehors de image-card-thumb (imbriquer un bouton dans un autre
                  bouton serait invalide en HTML). */}
              <div className="image-card-thumb-wrap">
                <button
                  type="button"
                  className="image-card-thumb"
                  onClick={() => onSelect(s.file_name)}
                  aria-pressed={selected}
                  title={selected ? "Image sélectionnée pour la taxobox" : "Utiliser cette image pour la taxobox"}
                >
                  <img src={s.thumb_url} alt={s.file_name} loading="lazy" />
                  {s.is_wikidata_image && (
                    <span className="image-card-badge image-card-badge-wikidata">Déjà utilisée par Wikidata</span>
                  )}
                </button>
                {selected && (
                  <button
                    type="button"
                    className="image-card-badge image-card-badge-selected image-card-deselect"
                    onClick={onDeselect}
                    title="Retirer cette image de la taxobox"
                  >
                    ✕ Désélectionner
                  </button>
                )}
              </div>
              <div className="image-card-meta">
                <span className="image-card-license" title={s.file_name}>
                  {s.license_label}
                </span>
                <a href={s.page_url} target="_blank" rel="noopener noreferrer" className="image-card-link">
                  voir sur Commons
                </a>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
