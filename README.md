# SpoolyTracker pour Home Assistant

Intégration Home Assistant **custom** qui connecte votre instance
[SpoolyTracker](https://spoolytracker.com) à Home Assistant via un token API, puis
permet d'**enregistrer automatiquement une consommation de filament** quand une
impression 3D se termine.

L'intégration est **générique et pilotable par automatisation** : elle n'a
**aucune dépendance** à Bambu Lab ni à une intégration d'imprimante particulière.
N'importe quelle automatisation, script ou intégration peut appeler ses services.

- ✅ Config flow UI + stockage sécurisé du token
- ✅ Ré-authentification automatique si le token expire
- ✅ `DataUpdateCoordinator` async, client `aiohttp` de Home Assistant
- ✅ 4 services documentés
- ✅ 5 sensors + selects de bobine active
- ✅ 5 stratégies d'identification de la bobine (du plus fiable au plus automatique)
- ✅ Compatible HACS (dépôt custom)

---

## Sommaire

- [Installation](#installation)
- [Configuration](#configuration)
- [Le vrai problème : identifier la bonne bobine](#le-vrai-problème--identifier-la-bonne-bobine)
- [Stratégies de mapping (recommandations)](#stratégies-de-mapping-recommandations)
- [Services](#services)
- [Entités](#entités)
- [Exemple d'automatisation Bambu Lab](#exemple-dautomatisation-bambu-lab)
- [Événements](#événements)
- [Correspondance avec l'API SpoolyTracker](#correspondance-avec-lapi-spoolytracker)
- [TODO côté API SpoolyTracker](#todo-côté-api-spoolytracker)
- [Feuille de route V2](#feuille-de-route-v2)
- [Dépannage](#dépannage)

---

## Installation

### Via HACS (dépôt custom — recommandé)

1. HACS → menu ⋮ → **Dépôts personnalisés**.
2. URL : `https://github.com/SpoolyTracker/spoolytracker-homeassistant`, catégorie **Intégration**.
3. Installez **SpoolyTracker**, puis **redémarrez Home Assistant**.

### Manuelle

1. Copiez le dossier `custom_components/spoolytracker/` dans le
   `custom_components/` de votre configuration Home Assistant.
2. Redémarrez Home Assistant.

---

## Configuration

**Paramètres → Appareils et services → Ajouter une intégration → SpoolyTracker.**

| Champ | Exemple | Notes |
|---|---|---|
| URL de l'instance | `https://api.spoolytracker.com` | Sans `/public-api/v1` (ajouté automatiquement). Une URL auto-hébergée fonctionne aussi. |
| Token API | `sk_...` | Généré dans SpoolyTracker (Paramètres → Clés API). |
| Nom | `Atelier` | Optionnel. |

Le token est validé à l'ajout (appel à `/analytics/stock`). Scopes requis
recommandés : `filaments:read`, `stock:read`, `consumption:read`,
**`consumption:write`** (indispensable pour loguer), et `analytics:read`.

### Options (⚙️ sur l'intégration)

- **Intervalle de rafraîchissement** (défaut 300 s)
- Activer/désactiver chaque stratégie de matching (S2 slot, S4 select, S3 métadonnées)
- Autoriser par défaut le matching ambigu

---

## Le vrai problème : identifier la bonne bobine

Quand un print se termine, Home Assistant sait *combien* de grammes ont été
consommés, mais **pas quelle bobine physique** a servi. L'intégration ne devine
donc **jamais** en silence. Elle applique des stratégies **dans l'ordre de
fiabilité** et refuse d'enregistrer si l'identification est douteuse.

```
S1 spool_id direct   ─┐  le plus fiable
S2 mapping slot AMS  ─┤
S4 select actif      ─┤
S3 métadonnées       ─┘  le moins fiable (fallback, jamais si ambigu)
S5 échec → aucun log silencieux : événement + warning + erreur claire
```

---

## Stratégies de mapping (recommandations)

Par ordre de préférence :

1. **`spool_id` direct** — le plus fiable. Votre automatisation fournit
   directement l'ID SpoolyTracker. Idéal si vous imprimez toujours la même bobine
   par imprimante, ou si vous choisissez la bobine dans un dashboard.
2. **Mapping de slot AMS** — associez une fois `(imprimante, ams_unit, ams_slot) →
   spool_id` via `spoolytracker.set_slot_spool`. L'automatisation n'a plus qu'à
   fournir l'AMS et le slot.
3. **Select « bobine active »** — choisissez la bobine dans l'UI
   (`select.spoolytracker_active_spool`). Pratique et visuel.
4. **Métadonnées uniquement en dernier recours** — matière/couleur/marque/profil.
   Si plusieurs bobines correspondent, l'intégration **refuse** de loguer sauf si
   `allow_ambiguous_match: true`.

---

## Services

### `spoolytracker.log_consumption`

Enregistre une consommation. Résout la bobine via les stratégies ci-dessus.

| Champ | Type | Requis | Description |
|---|---|---|---|
| `spool_id` | string/int | non\* | ID de bobine. Requis si aucun matching. |
| `grams_used` | number | **oui** | Grammes consommés. |
| `length_used_m` | number | non | Longueur (m) — ajoutée aux notes. |
| `printer_name` | string | non | Imprimante (pour S2/S4). |
| `job_name` | string | non | Nom du print → `externalJobId`. |
| `project_id` | string | non | Projet — ajouté aux notes. |
| `source` | string | non | Défaut `home_assistant`. |
| `metadata` | object | non | Contexte libre supplémentaire. |
| `ams_unit` | number | non | Unité AMS (S2/S4). |
| `ams_slot` | number | non | Slot AMS (S2/S4). |
| `external` | boolean | non | Bobine externe (pas dans l'AMS). |
| `material` | string | non | Matière (S3). |
| `color` | string | non | Couleur (S3). |
| `brand` | string | non | Marque (S3). |
| `filament_profile` | string | non | Profil filament (S3, matching approché). |
| `allow_ambiguous_match` | boolean | non | Défaut `false`. |

\* Optionnel si une stratégie de matching peut résoudre la bobine.

Le service **renvoie une réponse** (`spool_id`, `spool_label`, `grams_used`,
`strategy`, `api_response`) — utilisable via `response_variable`.

### `spoolytracker.set_slot_spool`

Associe une bobine à un slot. Champs : `printer_name` (req.), `ams_unit`,
`ams_slot`, `external`, `spool_id` (req.).

### `spoolytracker.clear_slot_spool`

Supprime une association. Champs : `printer_name` (req.), `ams_unit`, `ams_slot`,
`external`.

### `spoolytracker.refresh`

Force le rafraîchissement des données depuis SpoolyTracker.

---

## Entités

**Sensors :**

| Entité | Description |
|---|---|
| `sensor.spoolytracker_total_spools` | Nombre total de bobines |
| `sensor.spoolytracker_low_stock_spools` | Bobines en stock faible (+ liste en attribut) |
| `sensor.spoolytracker_total_remaining_weight` | Poids restant total (g) |
| `sensor.spoolytracker_last_consumption` | Dernière consommation loguée (g + contexte complet en attributs) |
| `sensor.spoolytracker_api_status` | État de l'API (`ok` / `unavailable`) |

**Selects :**

- `select.spoolytracker_active_spool` — bobine active globale
- un select par slot mappé (créé automatiquement après `set_slot_spool`)

> Design volontairement **minimal** : on ne crée **pas** une entité par bobine,
> pour rester lisible même avec des centaines de bobines.

---

## Exemple d'automatisation Bambu Lab

> ⚠️ **Les entity_id Bambu Lab varient** selon l'intégration installée
> (`ha-bambulab`, MQTT, etc.). **Adaptez les `entity_id` ci-dessous** à votre
> installation. L'intégration SpoolyTracker reste générique : elle ne connaît pas
> Bambu Lab.

```yaml
alias: Log SpoolyTracker après un print Bambu
description: Enregistre la consommation quand un print Bambu se termine
triggers:
  - trigger: state
    entity_id: sensor.bambu_p1s_print_status
    to: "finish" # selon l'intégration : "finish", "finished", "completed"…
conditions: []
actions:
  - action: spoolytracker.log_consumption
    data:
      printer_name: "Bambu P1S"
      job_name: "{{ states('sensor.bambu_p1s_current_stage') }}"
      grams_used: "{{ states('sensor.bambu_p1s_print_weight') | float(0) }}"
      ams_unit: 1
      ams_slot: "{{ states('sensor.bambu_p1s_active_tray') | int(0) }}"
      material: "{{ states('sensor.bambu_p1s_active_tray_type') }}"
      color: "{{ states('sensor.bambu_p1s_active_tray_color') }}"
      source: "home_assistant_bambulab"
mode: single
```

Avec cette configuration, la bobine est résolue par **le mapping de slot** (S2) si
vous avez fait :

```yaml
action: spoolytracker.set_slot_spool
data:
  printer_name: "Bambu P1S"
  ams_unit: 1
  ams_slot: 0
  spool_id: "123"
```

Sinon elle retombe sur le **select actif** (S4) puis les **métadonnées** (S3).

Voir [`examples/`](examples/) pour d'autres scénarios (spool_id direct, select,
gestion de l'échec de résolution).

---

## Événements

| Événement | Émis quand |
|---|---|
| `spoolytracker_consumption_logged` | Une consommation a été enregistrée (contient bobine, grammes, stratégie, notes). |
| `spoolytracker_consumption_unresolved` | La bobine n'a pas pu être identifiée (`status: not_found` ou `ambiguous`). |

Écoutez `spoolytracker_consumption_unresolved` pour envoyer une notification et
rejouer la consommation manuellement (voir V2).

---

## Correspondance avec l'API SpoolyTracker

L'intégration cible l'**API publique réelle** (`/public-api/v1`, doc :
<https://api.spoolytracker.com/public-api/docs>). Points importants :

- Une « bobine » = un **filament** ; `spool_id` est en réalité un **entier**
  (`filamentId`). L'intégration accepte le nom convivial `spool_id` et le convertit.
- `POST /consumption` accepte
  `{filamentId, amount, type, notes, externalJobId, date, …}`. Il **n'existe pas**
  de champs `length_used_m`, `source`, `printer_name`, `ams_*`, `material`,
  `color` ni `metadata` côté serveur. Ce contexte est donc :
  - envoyé dans **`notes`** sous forme lisible
    (`HA · Bambu P1S · AMS1/slot3 · PETG black (Bambu) · 13.2m · src=…`),
  - `job_name` → **`externalJobId`**, `type` fixé à **`PRINT`**,
  - **et** ré-émis intégralement dans l'événement `spoolytracker_consumption_logged`
    (rien n'est perdu).
- Il **n'existe pas** d'endpoint public `projects`. `project_id` est accepté mais
  seulement ajouté aux notes.

---

## TODO côté API SpoolyTracker

Améliorations qui permettraient une intégration plus riche (non bloquantes) :

1. **Champs structurés sur `POST /consumption`** : `lengthUsedM`, `source`,
   `printerName`, `metadata` (objet libre avec `amsUnit`, `amsSlot`, `material`,
   `color`, `brand`, `filamentProfile`). Aujourd'hui tout est concaténé dans `notes`.
2. **Endpoint projets public** : `GET /public-api/v1/projects` (le scope
   `projects:read` existe déjà mais aucun controller ne le sert). Débloquerait
   `project_id` et un sensor projets.
3. **Endpoint de résolution de bobine** : `POST /public-api/v1/filaments/resolve`
   prenant matière/couleur/marque/tag et renvoyant les candidats — déplacerait la
   logique de matching côté serveur (plus fiable, multi-clients).
4. **Endpoint de validation de token léger** : `GET /public-api/v1/me` renvoyant
   scopes + organisation, pour un diagnostic clair au lieu d'appeler `/analytics/stock`.
5. **Tag / référence NFC-QR exposé** dans le filament public (`tag`, `nfcId`)
   pour un matching S3 déterministe par identifiant physique.

Toutes ces URL sont centralisées dans
[`const.py`](custom_components/spoolytracker/const.py) : l'adaptation sera triviale.

---

## Feuille de route V2

- **File d'attente des consommations non résolues** + entité `pending consumption`,
  avec service `resolve_pending` pour rejouer avec un `spool_id` choisi.
- **Notification mobile actionnable** (`notify` + `mobile_app`) proposant de choisir
  la bobine quand la résolution échoue.
- **Support multi-matériaux** par job (plusieurs slots/plusieurs bobines en une fois).
- **Détection automatique de l'AMS** (lecture d'entités AMS pour pré-remplir le mapping).
- **Synchronisation des bobines actives** vers SpoolyTracker (S4 ↔ serveur).
- **Alertes de stock faible** remontées comme `binary_sensor` + notifications.
- **Entités projets** dès que l'API expose `/projects`.

---

## Dépannage

- **`invalid_auth`** : token révoqué/expiré, ou scope `consumption:write` manquant.
  Régénérez une clé API dans SpoolyTracker.
- **`cannot_connect`** : URL incorrecte ou instance injoignable. Testez
  `https://VOTRE_URL/public-api/v1/analytics/stock` avec l'en-tête
  `Authorization: Bearer <token>`.
- **« Aucune bobine identifiée »** : normal si aucune stratégie n'a abouti —
  fournissez `spool_id`, configurez un mapping de slot, ou sélectionnez une bobine
  active. Écoutez `spoolytracker_consumption_unresolved`.
- **Logs** : `Paramètres → Journaux`, filtre `spoolytracker`. Pour le mode debug :

  ```yaml
  logger:
    logs:
      custom_components.spoolytracker: debug
  ```
