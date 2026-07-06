# Guide de test — SpoolyTracker pour Home Assistant

Ce guide te permet de **tester l'intégration de bout en bout, sans imprimante 3D**,
en appelant les services à la main. Compte ~15 minutes.

---

## 0. Pré-requis

- Une instance SpoolyTracker joignable (Cloud `https://api.spoolytracker.com` ou la tienne).
- Un **token API** avec au minimum les scopes :
  `filaments:read`, `stock:read`, `consumption:read`, **`consumption:write`**, `analytics:read`.
  (SpoolyTracker → Paramètres → Clés API.)
- **Au moins une bobine** existante dans SpoolyTracker (note son **ID numérique**).
- Home Assistant 2024.8 ou plus récent.

> 💡 Pour ne pas polluer ta prod : crée une bobine de test dans SpoolyTracker, ou
> utilise une instance de dev. Les consommations enregistrées sont réelles.

---

## 1. Vérifier l'API directement (avant même HA)

Avant d'installer quoi que ce soit, confirme que ton token marche. Remplace l'URL
et le token.

**PowerShell :**
```powershell
$H = @{ Authorization = "Bearer TON_TOKEN" }
# Doit renvoyer { "data": { "spoolCount": ..., "totalRemaining": ... } }
Invoke-RestMethod -Uri "https://api.spoolytracker.com/public-api/v1/analytics/stock" -Headers $H
# Liste des bobines (récupère un id)
Invoke-RestMethod -Uri "https://api.spoolytracker.com/public-api/v1/filaments" -Headers $H
```

**curl (Linux/macOS) :**
```bash
curl -H "Authorization: Bearer TON_TOKEN" \
  https://api.spoolytracker.com/public-api/v1/analytics/stock
```

- ✅ Réponse `200` avec `{ "data": … }` → token OK.
- ❌ `401/403` → token invalide ou scope manquant.
- ❌ pas de réponse → URL/instance injoignable.

---

## 2. Installer l'intégration

### Option A — Machine de dev (recommandée pour tester)
Copie `custom_components/spoolytracker/` dans le dossier `config/custom_components/`
de ton Home Assistant, puis **redémarre HA**.

### Option B — HACS
Ajoute le dépôt custom `https://github.com/SpoolyTracker/spoolytracker-homeassistant`
(catégorie *Intégration*), installe, **redémarre HA**.

---

## 3. Ajouter l'instance (config flow)

1. **Paramètres → Appareils et services → Ajouter une intégration → SpoolyTracker**.
2. Choix du serveur :
   - **Cloud** → saisis seulement le **token** (+ nom optionnel).
   - **Autre** → saisis ton **URL** puis le token.
3. Validation attendue :
   - ✅ L'intégration se crée, un appareil « SpoolyTracker » apparaît.
   - ❌ `invalid_auth` → token/scope. `cannot_connect` → URL/instance. `invalid_url` → format d'URL.

**Ce que tu dois voir ensuite** (Paramètres → Appareils → SpoolyTracker) :

| Entité | Attendu |
|---|---|
| `sensor.spoolytracker_total_spools` | nombre de bobines |
| `sensor.spoolytracker_low_stock_spools` | nombre en stock faible (+ liste en attribut) |
| `sensor.spoolytracker_total_remaining_weight` | poids restant total (g) |
| `sensor.spoolytracker_last_consumption` | `unknown` au départ |
| `sensor.spoolytracker_api_status` | `ok` |
| `select.spoolytracker_active_spool` | liste : `none` + tes bobines |

> Si les capteurs restent indisponibles : active les logs debug (voir §8) et vérifie
> l'URL/token.

---

## 4. Tester `log_consumption`

Va dans **Outils de développement → Actions** (anciennement *Services*), cherche
**SpoolyTracker : Enregistrer une consommation**, bascule en mode YAML.

### 4.1 — Stratégie S1 (spool_id direct) — le cas le plus simple
Remplace `123` par un **ID réel** de bobine.

```yaml
action: spoolytracker.log_consumption
data:
  spool_id: "123"
  grams_used: 5
  printer_name: "Test HA"
  job_name: "Test manuel"
```

**Attendu :**
- Notification/résultat de succès.
- `sensor.spoolytracker_last_consumption` passe à `5` (attributs = contexte complet).
- Dans SpoolyTracker : une consommation de 5 g apparaît sur la bobine, avec une
  note du type `HA · Test HA · src=home_assistant` et `externalJobId = Test manuel`.
- Le poids restant de la bobine diminue de 5 g (après le refresh auto).

> Pour voir la **réponse** du service, coche « Réponse » dans l'UI, ou utilise
> `response_variable` dans une automatisation (voir `examples/automations.yaml`).

### 4.2 — Stratégie S4 (bobine active via select)
1. Mets `select.spoolytracker_active_spool` sur une de tes bobines.
2. Appelle **sans** `spool_id` :

```yaml
action: spoolytracker.log_consumption
data:
  grams_used: 3
  printer_name: "Test HA"
```
**Attendu :** résolu via le select (réponse `strategy: active_select`).

### 4.3 — Stratégie S3 (métadonnées)
```yaml
action: spoolytracker.log_consumption
data:
  grams_used: 2
  material: "PETG"     # adapte à une matière réellement présente
  color: "black"
  brand: "Bambu"
```
- ✅ Une seule bobine correspond → enregistré (`strategy: metadata`).
- ⚠️ Plusieurs correspondent → **erreur volontaire** « Plusieurs bobines
  correspondent… ». Rajoute `allow_ambiguous_match: true` pour forcer.

### 4.4 — Stratégie S5 (échec = pas de log silencieux)
```yaml
action: spoolytracker.log_consumption
data:
  grams_used: 1
  material: "MATIERE_QUI_NEXISTE_PAS"
```
**Attendu :** l'action **échoue** avec un message clair, **aucune** consommation
enregistrée, et un événement `spoolytracker_consumption_unresolved` est émis
(voir §6).

---

## 5. Tester le mapping de slot (S2)

1. Associe un slot à une bobine :
```yaml
action: spoolytracker.set_slot_spool
data:
  printer_name: "Bambu P1S"
  ams_unit: 1
  ams_slot: 0
  spool_id: "123"
```
**Attendu :** un nouveau select apparaît pour ce slot (après rechargement auto de
l'entrée), et un log info « Slot mappé… ».

2. Loggue en fournissant seulement le slot :
```yaml
action: spoolytracker.log_consumption
data:
  grams_used: 4
  printer_name: "Bambu P1S"
  ams_unit: 1
  ams_slot: 0
```
**Attendu :** résolu via `slot_map`.

3. Nettoie :
```yaml
action: spoolytracker.clear_slot_spool
data:
  printer_name: "Bambu P1S"
  ams_unit: 1
  ams_slot: 0
```

---

## 6. Observer les événements

**Outils de développement → Événements**, écoute `spoolytracker_consumption_logged`
puis `spoolytracker_consumption_unresolved`, puis relance les tests du §4.
Tu verras le contexte complet (bobine, grammes, stratégie, notes, statut).

---

## 7. Tester `refresh` et le rafraîchissement

```yaml
action: spoolytracker.refresh
```
**Attendu :** les capteurs se mettent à jour (utile après une modif faite
directement dans SpoolyTracker).

---

## 8. Logs de debug

Ajoute dans `configuration.yaml` puis redémarre (ou recharge la conf YAML) :

```yaml
logger:
  default: warning
  logs:
    custom_components.spoolytracker: debug
```

Filtre `spoolytracker` dans **Paramètres → Système → Journaux**. Tu verras chaque
requête HTTP, la stratégie retenue, et les warnings de non-résolution.

---

## 9. Tester la ré-authentification (optionnel)

1. Révoque/expire le token côté SpoolyTracker (ou change-le pour un faux).
2. Attends le prochain refresh (≤ intervalle configuré) ou appelle `refresh`.
3. **Attendu :** HA affiche une notification « Ré-authentification requise ».
   Clique, saisis un token valide → l'intégration repart sans être supprimée.

---

## 10. Tests unitaires (côté développeur)

La logique de résolution est testable **sans** Home Assistant :

```bash
pip install -r requirements-test.txt
pytest -q
```

**Attendu :** `18 passed`. Ces tests couvrent les 5 stratégies, l'ambiguïté, les
stratégies désactivées et la normalisation des bobines.

---

## Checklist express

- [ ] API OK en direct (§1)
- [ ] Intégration ajoutée, `api_status = ok` (§3)
- [ ] `log_consumption` S1 enregistre et décrémente le stock (§4.1)
- [ ] Select S4 fonctionne (§4.2)
- [ ] Métadonnées S3 + refus d'ambiguïté (§4.3)
- [ ] Échec S5 = pas de log + événement (§4.4, §6)
- [ ] Mapping de slot S2 (§5)
- [ ] `refresh` (§7)
- [ ] `pytest` = 18 passed (§10)
