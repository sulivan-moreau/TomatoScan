# Veille technique et réglementaire — TomatoScan (C6)

Support de veille du projet TomatoScan, versionné au même titre que le code. Ce
document regroupe l'organisation de la veille, les sources suivies et les synthèses
datées. Il alimente directement les décisions de conception (choix d'architecture,
conformité réglementaire, grille d'élimination du benchmark C7).

## Thématique

Deux axes complémentaires, tous deux directement mobilisés par le projet :

1. **Technique** — architectures de classification d'images légères pour l'inférence
   **CPU** (MobileNet, EfficientNet-lite, MobileViT…), transfer learning, et l'outil
   central du projet (PyTorch / torchvision).
2. **Réglementaire** — cadre de l'IA appliquée à un service en ligne traitant des
   images utilisateur : **AI Act** (règlement UE 2024/1689), **RGPD** et souveraineté
   des données (CLOUD Act, FISA 702, jurisprudence Schrems).

## Organisation de la veille

| Critère | Mise en œuvre |
|---|---|
| Récurrence | 1 h minimum par semaine, le **vendredi** — créneau fixe dédié à la lecture et à la synthèse |
| Support | `docs/veille.md`, versionné dans le dépôt Git au même titre que le code |
| Structure d'une synthèse | Date · Sujet · Sources · Points clés · Impact projet |
| Partage | Synthèses versionnées, consultables par toute partie prenante du dépôt ; points saillants repris dans la documentation du projet |
| Accessibilité | Markdown structuré : hiérarchie de titres navigable au lecteur d'écran, listes plutôt que blocs de texte, liens explicites, aucune information portée uniquement par la couleur (recommandations AcceDe Web / Valentin Haüy) |

## Outils d'agrégation et sources suivies

Dispositif aligné sur le budget du projet (0 € récurrent) : flux RSS et newsletters
gratuites, centralisés dans un agrégateur RSS gratuit (Inoreader, offre gratuite),
plus deux newsletters reçues par e-mail. Une heure hebdomadaire suffit à parcourir ce
volume.

| Source | Type | Fréquence de suivi | Fiabilité |
|---|---|---|---|
| Blog PyTorch (pytorch.org/blog) | Flux RSS | Hebdomadaire | Équipe PyTorch nommée, source officielle du framework utilisé par le projet |
| Hugging Face Blog | Flux RSS | Hebdomadaire | Équipe identifiée, contenu relié à arXiv et au code, référencé par la communauté ML |
| Newsletter CNIL | Newsletter e-mail | Mensuelle | Autorité française officielle de protection des données |
| EUR-Lex (règlement IA) | Consultation ciblée | À l'actualité | Texte officiel de l'UE, daté et opposable |
| The Batch — DeepLearning.AI | Newsletter e-mail | Hebdomadaire | Rédaction identifiée (Andrew Ng), synthèse éditorialisée de l'actualité IA |

### Critères de fiabilité appliqués

Appliqués de façon **cumulative** avant d'intégrer une source : auteur identifié et
compétent · contenu daté et récent · information confirmable par des tiers reconnus ·
document structuré et accessible. Les sources institutionnelles (EUR-Lex, CNIL,
justice.gov) sont privilégiées pour le volet réglementaire ; les sources techniques
sont adossées aux éditeurs des outils du projet.

---

## Synthèse 1 — Modèles de vision légers pour l'inférence CPU (12 juin 2026)

**Sujet :** choix d'une architecture de classification d'images adaptée à une inférence
CPU sur VPS, sans GPU, pour 10 classes spécialisées.

**Sources :** documentation `torchvision.models` (poids pré-entraînés et métriques
ImageNet officielles) · blog PyTorch · papier MobileNetV2 (Sandler et al., CVPR 2018,
arXiv:1801.04381).

**Points clés :**

- Les architectures « mobiles » (MobileNetV2/V3) utilisent des convolutions séparables
  en profondeur et des blocs à goulot d'étranglement inversé : beaucoup moins de
  paramètres et d'opérations qu'un ResNet, au prix d'une accuracy générique ImageNet
  plus faible.
- Sur un dataset spécialisé étroit (10 classes visuellement proches), l'écart d'accuracy
  générique mesuré sur les 1 000 classes ImageNet n'est pas prédictif : le transfer
  learning referme largement l'écart.
- Certaines opérations de MobileNetV3 (h-swish, blocs squeeze-and-excite) sont
  optimisées pour les processeurs ARM mobiles et ne bénéficient d'aucune accélération
  particulière sur le CPU x86 d'un VPS.

**Impact projet :** pré-sélection de MobileNetV2 comme architecture candidate principale
pour le benchmark C7, et stratégie de transfer learning (backbone pré-entraîné ImageNet
gelé, classifier final ré-entraîné) actée avant le lancement de l'entraînement du
24 juin (cf. C8).

## Synthèse 2 — AI Act européen et obligations de transparence (10 juillet 2026)

**Sujet :** entrée en application complète du règlement (UE) 2024/1689 (AI Act) le
2 août 2026, et conséquences pour un système de classification d'images en production.

**Sources :** Règlement (UE) 2024/1689 — AI Act (EUR-Lex) · CNIL — dossier Intelligence
artificielle.

**Points clés :**

- Le calendrier d'application du règlement se termine le 2 août 2026 : à cette date,
  l'ensemble des dispositions restantes devient contraignant.
- TomatoScan n'entre pas dans les systèmes à haut risque de l'Annexe III (pas de score
  social, pas de décision affectant l'accès à un droit fondamental, pas de dispositif
  médical) : qualification en **risque minimal**.
- L'article 50 impose néanmoins une obligation de transparence : informer l'utilisateur
  qu'il interagit avec un système d'IA et présenter le résultat de façon compréhensible,
  score de confiance inclus lorsque c'est pertinent.

**Impact projet :** vérification effectuée sur le frontend Streamlit — le score de
confiance est déjà affiché sur l'écran de prédiction (`predict.py`, barre de progression
+ pourcentage) et dans l'historique (`history.py`, colonne « Confiance »). Aucune action
corrective nécessaire ; point à resurveiller si de nouveaux actes d'exécution précisent
les obligations avant l'échéance.

## Synthèse 3 — CLOUD Act, FISA 702 et transferts UE–USA (17 juillet 2026)

**Sujet :** risques juridiques d'un hébergement de données ou d'un service d'IA opéré par
un fournisseur américain, à la lumière des évolutions 2026.

**Sources :** US CLOUD Act — ressources officielles (justice.gov) · CNIL — présentation de
l'arrêt Schrems II de la CJUE.

**Points clés :**

- La section 702 du FISA, qui autorise la surveillance de données détenues par des
  fournisseurs américains, a été prolongée en avril 2026 — elle s'applique y compris à
  des données stockées sur des serveurs situés en UE.
- Le CLOUD Act confirme qu'un fournisseur de droit américain reste soumis aux
  réquisitions judiciaires américaines quelle que soit la localisation géographique des
  serveurs.
- Une jurisprudence en cours en 2026, dans la continuité de Schrems I et II, fragilise à
  nouveau la solidité juridique du Data Privacy Framework, mécanisme censé encadrer les
  transferts UE → USA.

**Impact projet :** conforte le choix d'un hébergement 100 % France (VPS OVH Roubaix) :
aucune donnée du projet (images, comptes, prédictions) ne transite par un fournisseur
soumis au CLOUD Act ou à FISA 702. Ce constat structure la grille d'élimination du
benchmark C7 (voir [docs/benchmark_services_ia.md] si présent, ou le rapport E2).

---

## Gabarit pour les prochaines synthèses

```
## Synthèse N — <titre> (<date>)
**Sujet :** …
**Sources :** … (auteur identifié, date, lien)
**Points clés :**
- …
**Impact projet :** … (décision ou vérification concrète déclenchée par cette veille)
```

> À tenir à jour : ajouter une synthèse par créneau hebdomadaire tenu. Chaque entrée
> doit être datée, sourcée, et conclue par un impact projet concret — c'est ce qui
> distingue une veille d'une simple lecture.

---

*Accessibilité : document Markdown structuré par hiérarchie de titres (H1→H3), tableaux
avec en-têtes de colonnes, listes plutôt que blocs denses, liens explicites, aucune
information portée uniquement par la couleur ; lisible par un lecteur d'écran et
navigable au clavier depuis GitHub.*
