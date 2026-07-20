# Journal des rituels agiles — TomatoScan

> **⚠️ Document à compléter par le candidat.** Ce fichier fournit la **structure** du
> journal de bord des rituels agiles et **pré-remplit deux lignes d'exemple clairement
> marquées**. Le candidat DOIT remplacer ces exemples par ses **vraies dates et décisions**,
> notamment les **points hebdomadaires de suivi avec le formateur référent Simplon**.
>
> **Aucune date de rituel n'est inventée dans ce document.** Les seules dates réelles
> présentes ici sont des dates *techniques* déjà prouvées par Git (elles sont référencées
> comme telles). Les lignes du journal marquées `[EXEMPLE]` ne sont pas des preuves : elles
> montrent le format attendu et doivent être supprimées ou remplacées.

## Sommaire

1. [Pourquoi ce document](#pourquoi-ce-document)
2. [Méthode agile réellement appliquée](#méthode-agile-réellement-appliquée)
3. [Modalités des rituels](#modalités-des-rituels)
4. [Journal de bord](#journal-de-bord)
5. [Consignes de remplissage](#consignes-de-remplissage)

## Pourquoi ce document

Le référentiel (REAC / bloc gestion de projet agile) demande de **documenter les objectifs
et les modalités des rituels** de coordination. Sur un projet de certification **individuel**,
le candidat assume simultanément les rôles de Product Owner, Scrum Master et Développeur
(voir [docs/agile.md](agile.md#contexte-et-rôles)) : les rituels d'équipe classiques (daily
stand-up, sprint planning à plusieurs) perdent une partie de leur sens, mais le **suivi
régulier** et la **revue** restent pertinents et doivent être tracés.

Ce journal complète deux artefacts factuels déjà générés depuis Git :

- [docs/pr_cadence.md](pr_cadence.md) — la cadence chiffrée réelle (PR fusionnées par semaine).
- [docs/backlog.md](backlog.md) — le backlog reconstruit (user stories, tâches, correctifs).

## Méthode agile réellement appliquée

La méthode effectivement suivie, **prouvée par l'historique Git**, est un **Kanban léger**
adossé à GitHub :

- **Support de pilotage** : GitHub Issues + un tableau GitHub Projects (colonnes de suivi
  des issues) ; les issues portent des numéros référencés dans les commits (ex. #4, #5, #6,
  #25, #26, #27 — voir `git log --all --grep="#"`).
- **Cycle de travail** unitaire, répété **35 fois** sur le projet :
  `issue → branche dédiée (feature/* ou fix/*) → Pull Request → merge sur develop`.
- **Flux tiré, par petits lots** : un ticket = une branche = une PR, livré en continu
  plutôt qu'en sprints de durée fixe. Ce choix (Kanban plutôt que SCRUM strict) est cohérent
  avec un contexte individuel et documenté dans [docs/agile.md](agile.md#méthode-appliquée).

Ce cycle est **entièrement vérifiable** dans le dépôt public ; ce que Git ne prouve **pas**,
en revanche, ce sont les **temps de suivi et de revue** (points formateur, rétros
personnelles) — c'est précisément l'objet du [journal de bord](#journal-de-bord) ci-dessous.

## Modalités des rituels

| Rituel | Objectif | Fréquence cible | Format | Partage |
|---|---|---|---|---|
| **Point de suivi formateur** | Faire le point sur l'avancement, lever les blocages, valider les priorités avec le formateur référent Simplon | Hebdomadaire (à confirmer par le candidat) | Échange synchrone (visio ou présentiel) | Décisions consignées dans ce journal |
| **Revue personnelle d'avancement** | Vérifier l'état du backlog, replanifier les priorités de la semaine, déplacer les cartes du tableau Kanban | Hebdomadaire | Revue solo du GitHub Project + backlog | Tableau GitHub Projects (dépôt public) |
| **Rétrospective personnelle** | Prendre du recul sur ce qui a bien/mal fonctionné, décider d'ajustements de méthode | À une ou plusieurs étapes clés (ex. fin d'un bloc) | Note écrite | Ce journal + éventuellement `docs/agile.md` |

> La colonne « Fréquence cible » indique l'intention. Le **rythme réellement tenu** doit
> être renseigné par le candidat dans le journal ci-dessous, avec les dates réelles.

## Journal de bord

Renseigner une ligne par point de suivi / revue / rétro réellement tenu. **Les deux lignes
`[EXEMPLE]` ci-dessous sont à supprimer ou remplacer.**

| Date | Type de point | Participants | Décisions / actions |
|---|---|---|---|
| `[EXEMPLE — remplacer par une vraie date]` | Point hebdo formateur | Candidat + formateur référent Simplon | `[EXEMPLE — ex. « valider la priorité API avant frontend ; revoir la couverture de tests la semaine prochaine »]` |
| `[EXEMPLE — remplacer par une vraie date]` | Rétrospective perso | Candidat | `[EXEMPLE — ex. « les correctifs de déploiement (torch CPU, réseau Coolify) ont coûté du temps : tester le build Docker plus tôt à l'avenir »]` |
| _(à compléter)_ | | | |
| _(à compléter)_ | | | |

**Repères techniques réels** (dates prouvées par Git, à utiliser comme jalons si un point de
suivi les a accompagnés — **ne pas les présenter comme des dates de rituel sans en avoir
réellement tenu un à cette date**) :

- 2026-06-23 → amorce du projet (structure initiale, promotion `develop → main`).
- 2026-06-29 → 2026-07-02 → livraison du socle applicatif (pic de 20 PR, voir [pr_cadence.md](pr_cadence.md)).
- 2026-07-07 → incident Grafana (dashboard masqué par le volume) diagnostiqué et corrigé en local.
- 2026-07-13 → 2026-07-19 → phase de durcissement (rôles, PostgreSQL async, corrections d'audit).

## Consignes de remplissage

1. **Supprimer les deux lignes `[EXEMPLE]`** une fois de vraies entrées ajoutées.
2. **Ne jamais antidater** un rituel qui n'a pas eu lieu : mieux vaut un journal court et
   vrai qu'un journal long et fabriqué (règle de non-fabrication de preuves du projet).
3. **Prioriser les points formateur** : ce sont les rituels les plus attendus par le jury
   pour un projet individuel — ils attestent d'un vrai suivi externe.
4. Si un tableau GitHub Projects a servi de Kanban, **y joindre des captures** dans
   [docs/agile.md](agile.md#kanban) pour prouver l'usage continu dans le temps.

---

*Accessibilité : document Markdown structuré (H1→H2), journal en tableau à en-têtes de
colonnes, consignes en liste ordonnée ; aucune information portée uniquement par la couleur.
Rendu et navigation délégués à la plateforme d'hébergement (GitHub).*
