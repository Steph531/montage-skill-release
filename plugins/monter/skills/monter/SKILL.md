---
name: monter
description: Monte une vidéo face caméra (TikTok, Shorts, Reels) - dérushage automatique (prises ratées, blancs, bégaiements), sous-titres mot par mot, illustrations qui montrent ce qui est dit au lieu de l'écrire (maquettes de site animées, code surligné mot par mot, conversations IA, vrais logos, schémas, chiffres, captures de site, timer) et SFX synchronisés. À utiliser quand l'utilisateur veut monter, dérusher, sous-titrer ou habiller une vidéo.
argument-hint: <video.mp4> [tiktok|reels|shorts|all] [auto]
allowed-tools: Bash(python3 *) Bash(python *) Read Write
---

# /monter

Les scripts font la mécanique (transcription, coupes, minutage, rendu). **Toi, tu décides** : ce qu'on garde, ce que chaque phrase veut dire, ce qu'on montre. **Montrer, pas écrire** : par défaut, tu illustres ce que dit la personne par une démonstration (maquette qui bouge, code qui s'allume, logo, conversation, avant / après), sans attendre qu'on te le demande. Une carte de texte ou un ✓ n'est qu'un dernier recours. Ça prend plus de temps : prends-le, la qualité passe avant la vitesse. Prends le temps de bien faire ; ne lis pas transcript.json, edit.json, overlay/ ni les scripts : le brief suffit.

`S` = dossier de ce fichier (`${CLAUDE_SKILL_DIR}`). Sous Windows, `python` au lieu de `python3`.

## Étapes
1. **Réseau** : si l'utilisateur ne l'a pas dit, demande-lui pour quel réseau est la vidéo (TikTok, Reels, Shorts, ou plusieurs). Mets `"platform"` dans plan.json : `tiktok`, `reels`, `shorts`, ou `all` (plusieurs ; défaut). Ça cale textes et sous-titres hors de l'interface de l'appli, et la flèche du `cta` sur le vrai bouton (pas de flèche en `all`).
2. `python3 "S/scripts/pipeline.py" prepare "<video>"` → brief : phrases gardées (id), retirées, texte du montage, suggestions.
   - **Premier lancement / outil manquant** : c'est toi qui installes, l'utilisateur n'a rien à taper. Lance `python3 "S/scripts/doctor.py" --fix` : il installe seul les dépendances Python et affiche la commande exacte pour ce qui reste (ffmpeg, Node.js 22+) selon le système. Explique en une phrase ce que tu vas installer et pourquoi, demande l'accord une seule fois pour tout, lance les commandes, puis relance `doctor.py` jusqu'à « Tout est prêt ». Pas de gestionnaire de paquets → donne le lien affiché. Si `python3` n'existe pas : `python` (Windows), sinon propose d'installer Python (`winget install -e --id Python.Python.3.12`, `brew install python`). Le 1er montage télécharge aussi le modèle de transcription et le navigateur de rendu (quelques minutes, automatique).
   - `auto` : saute les étapes 3 à 6, `render .montage/<nom> --auto`.
3. **Le script** : relis le TEXTE DU MONTAGE comme un spectateur. Il doit dire une chose clairement (accroche → explication → preuve → appel à l'action), sans faux départ ni info répétée. Corrige avec `cut` / `trim` / `restore`, relance `prepare`, relis jusqu'à ce que ce soit propre. Corrige les mots mal transcrits avec `fix`.
4. **Le hook** (les 3 premières secondes, voir « Hook ») : décide les trois couches (visuel, texte, vocal) en variant par rapport aux ACCROCHES RÉCENTES du brief, note-les dans l'entrée `"at": "-"` du storyboard, Une seule vidéo : pas de variantes, sauf si l'utilisateur en demande (`variants` + `render --all-variants`).
5. **Le storyboard** (`story`, voir « Lire le sens » et « Illustrer ») : une entrée par phrase gardée, avec `illu`. Pars de la section À MONTRER du brief (énumérations, logos disponibles, démonstrations possibles) et décris pour chaque phrase **ce qu'on voit bouger à l'écran**, pas un texte. Le rendu signale toute phrase oubliée.
6. **Les effets** (`events`), qui découlent du storyboard. Les suggestions du brief ne sont que des mots-clés repérés : une suggestion `card` sur un nom de produit devient un logo, une maquette ou une scène.
7. S'il y a des `screen` : `pipeline.py shots .montage/<nom>`, ouvre chaque image (Read) : bonne page, pas de cookies / connexion / captcha. Sinon change d'URL ou retire.
8. `pipeline.py render .montage/<nom>` (`--draft` = aperçu rapide). Corrige chaque `[!]` et relance ; « plus de texte que de démonstrations » ou « a un logo » se corrigent en remplaçant les cartes par des démonstrations, pas en les ignorant.
9. **Contrôle** : `pipeline.py sheet .montage/<nom>` puis ouvre `sheet.jpg` (Read) : une image par effet, zone libre du réseau en rouge. Vérifie : texte coupé ou qui déborde, élément au-dessus / en dessous / à droite des lignes rouges, chevauchement, effet qui contredit ce qui est dit. Corrige et refais le rendu tant que ce n'est pas propre.
   Une scène ou une maquette à étapes (`steps`) n'a qu'une image sur la planche : extrais une image à chaque étape (ffmpeg -ss) et vérifie qu'elle se lit.
10. Réponds en 3 lignes : chemin du MP4 (`output/<nom>_monte.mp4`, dans le dossier du projet ; le travail reste dans `.montage/<nom>/`, allégé à ~1 Mo après le rendu final et supprimé au bout de 30 jours ou si le rush disparaît), durée, ce que tu as coupé / ajouté.
11. Si l'utilisateur signale un mot coupé ou un passage en trop : `pipeline.py verify .montage/<nom>` (retranscrit et liste les écarts).

## Hook : les 3 premières secondes
Le spectateur décide avant d'entendre un mot : la 1re image doit accrocher, avec ou sans le son. C'est toi qui choisis, d'après le sujet (si l'utilisateur fournit un script avec des hooks prévus, pars de là) : une seule version, l'utilisateur n'a rien à choisir. Variantes (`variants`) seulement s'il en demande.

**Varie** : le brief liste les ACCROCHES RÉCENTES ; ne reprends ni la même famille visuelle ni le même style de texte que les dernières vidéos.

**Visuel (1re image)**, 7 familles, à choisir selon ce que la vidéo a de plus fort :
| famille | quand | comment |
|---|---|---|
| geste filmé | la personne a joué une accroche avant de parler. Ne la garde que si elle **a un sens** : demande-toi ce qu'elle cherchait à provoquer (surprise, réaction, montrer un objet) et si elle **s'enchaîne** avec la 1re phrase gardée : compare la dernière image du geste et la 1re image de la phrase (même position, même cadrage, la phrase démarre depuis la fin du geste). Une chute dans le fauteuil suivie de la phrase assise : oui. Un rapprochement de la caméra suivi d'une phrase d'une autre prise où la personne est de nouveau reculée : non (elle s'approche pour rien). Dans le doute, ne le garde pas. Gardé, il est **prioritaire** (variantes comprises), un élément plein écran prévu à 0 s est décalé après lui | `hook.jpg` (3 s avant le 1er mot) → `"head"` ou `"intro": [début, fin]` ; démarrer sur le moment fort du geste, vérifié image par image (ffmpeg fps=30) ; geste lent ou sans rapport : non |
| chiffre choc | un chiffre dit dans la vidéo résume tout | `number` / `percent` `"t": 0` (valeur finale affichée d'emblée) |
| scène | le sujet se montre : code fautif, conversation avec une IA, avant / après | `scene` `"t": 0, "mode": "full"` |
| flash-forward | un passage plus loin est plus fort que le début (chiffre, chute) | `"cold_open": {"at": "P13", "from": "auraient", "to": "20"}` (1 à 3 s, puis la vidéo repart : flash + whoosh auto) |
| zoom brutal | rien à montrer, la phrase d'ouverture est forte | `"hook_punch": 1.35` |
| secousse | ton d'alerte, d'urgence | `"hook_shake": 1` (impact sonore auto) |
| glitch | sujet tech, bug, « quelque chose cloche » | `"hook_glitch": true` (son glitch auto) |
Jamais d'ouverture molle (zoom lent, image fixe sans texte), ni capture barrée en plein écran ou forme liquide en ouverture (testées, pas convaincantes). Un élément posé à 0 s est complet dès la 1re image et se place sous le texte d'accroche.

**Texte** (`hook`, `"t": 0`, 5 à 10 mots), 4 styles à faire tourner :
- `block` : bloc du thème ; `bold` : grands mots en capitales sur l'image ; `tag` : étiquette (`"tag": "Étude Stanford"`, « Erreur n°1 », « Partie 1 ») + phrase ; `emoji` : emoji 3D + phrase (`"emoji": "warning"`).
- Formules (à varier aussi) : contre-pied (« Apprendre à coder ne suffit *plus* »), avertissement (« Les postes junior *disparaissent* »), résultat chiffré (« *55 %* plus vite. Zéro minute gagnée »), question (« Tu sais ce que l'IA laisse *traîner* dans ton code ? »), « Ce que personne ne te dit sur… », « Arrête de… si tu veux… », liste (« 3 réflexes avant de publier »), interpellation (« Dev junior : *écoute* ça »).
- Il renforce l'accroche orale sans la recopier, et il est vrai : pas de promesse que la vidéo ne tient pas.

**Vocal** : la 1re phrase entendue doit accrocher seule. Une meilleure phrase plus loin → `cold_open` ; une amorce molle (« Alors aujourd'hui je vais vous parler de… ») → `trim` pour démarrer au cœur ; « l'histoire en cours » → démarrer au milieu d'une phrase forte. Son d'ouverture : `"hook_sfx": "impacts/hit"` ou `transitions/fast_woosh`, sauf si l'ouverture a déjà son impact (secousse, glitch, éclaboussure d'un chiffre).

**Variantes** (seulement sur demande) : `"variants": {"B_flashforward": {"hook_text": "…", "cold_open": {…}}, "C_glitch": {"hook_glitch": true, "events": [...]}}`. Chaque variante remplace les clés indiquées (`events` complet possible, `hook_text` = texte du hook) → `<nom>_monte_<variante>.mp4`. Chaque variante change de famille visuelle ET de style de texte.

## Lire le sens
Un effet illustre **ce que la phrase veut dire à ce moment du récit**, pas un mot. Pour chaque phrase :
- `role` : accroche, problème, solution, preuve, avantage, démo, chiffre, transition, appel à l'action… ;
- `sens` : ce qu'elle affirme vraiment ; à quoi renvoient « ça », « ici », « regarde » ; positif ou négatif pour le spectateur ; affirmation, question, ironie ;
- `voir` : ce que le spectateur devrait avoir sous les yeux (souvent juste le visage) ;
- `illu` : la décision d'illustration (ci-dessous), ou `"non"`.

Principes : le visuel montre ce qui est désigné, au moment où c'est désigné, et reste tant qu'on en parle. Polarité : problème / avant → ✗ ou terne ; solution / après → ✓, produit ; « sans abonnement » reste un avantage. Dans un contraste (« ça ressemble à ça, alors que ça pourrait ressembler à ça »), chaque « ça » a son propre visuel. Relis le storyboard sans le son : chaque visuel doit se comprendre seul et ne rien contredire.

## Illustrer : pour chaque phrase, que montrer ?
**Montrer, pas écrire.** Presque chaque phrase nomme ou décrit quelque chose de concret (une techno, un outil, une action, un résultat, une interface, une erreur) : montre-le en action, comme si tu avais filmé l'écran. Pose-toi la question pour chaque phrase : *« qu'est-ce que le spectateur verrait si on filmait ce qu'il dit ? »*, puis fabrique ce plan. Prends le premier barreau qui s'applique :
1. **Elle décrit ce que fait une techno, un outil, une interface** (« le CSS habille ton site », « Flexbox place tes éléments », « ton site doit marcher sur mobile », « JavaScript ajoute des menus, des formulaires ») → **l'effet en action** : `site` (maquette qui se transforme sur ses mots : couleurs, police, flex, grille, format téléphone, menu, formulaire, clic, animation). Du code ou une commande → `scene code` / `terminal`. Une conversation avec une IA → `scene chat`. Un contraste avant / après → `scene compare`. Une chose réelle et publique citée (site, article, dépôt) → `screen`.
2. **Elle cite des éléments un par un** (« le titre, les textes et les boutons ») → chaque élément s'allume **quand il est dit** : `steps` (une ligne de code par mot, une action de maquette par mot), `list` / `diagram` (un point par mot). Jamais un bloc figé qui montre tout d'un coup.
3. **Elle nomme un produit, une marque, une techno** (React, Netflix, Figma, Notion…) → son **vrai logo** : `"logo": "react"` sur un point de `list`, une `card`, un `check` / `cross` ou un `title` (téléchargé sur Simple Icons ; le brief dit lesquels existent). « Il en existe plusieurs » → plusieurs logos dans une `list`.
4. **Une relation** (process, boucle, cause et options) → `diagram` (`flow`, `hub`, `cycle`, `tree`).
5. **Un chiffre** → `number` / `percent` / `stat` ; une comparaison chiffrée → `chart`. **Une durée annoncée** (« j'ai une minute pour… ») → `timer`.
6. **Seulement s'il n'y a rien à montrer** (opinion, conseil abstrait, chute) : `card`, `check` / `cross`, `emoji`, `highlight` dans les sous-titres, ou `illu: "non"` (émotion, transition : le visage suffit).

Interdit : une carte qui recopie le nom d'une chose qu'on pourrait montrer (« Étape 2 : CSS » → la maquette qui se colore ; « React » → le logo). Le rendu signale un montage qui contient plus de texte que de démonstrations.

Une même maquette (`site`) peut couvrir plusieurs phrases qui se suivent (CSS → responsive → JavaScript) : elle évolue au lieu de disparaître, avec une étiquette d'étape dans sa barre (`label`, court : « 2 · CSS »). Les démonstrations peuvent s'enchaîner ; ne les espace que pour rendre le visage sur une émotion, une transition ou l'appel à l'action. Jamais deux éléments du haut qui se chevauchent. Contenu : court (3 à 5 lignes de code de 30 caractères au plus ; messages d'une phrase), fidèle à ce qui est dit, sans chiffre inventé, maquette générique (pas l'interface exacte d'une marque : le logo, oui).

**Contrôle d'une démonstration** : la planche n'en montre qu'une image. Extrais une image à chaque étape (`ffmpeg -ss <t> -i <mp4> -frames:v 1`, recadrée sur le panneau) et vérifie que chaque étape se voit, se lit et tombe sur son mot. Si une étape passe trop vite (mots rapprochés), avance son mot déclencheur ou allonge `dur`.

## plan.json
```json
{"platform": "all", "cut": ["P04"], "restore": [],
 "trim": [{"at": "P15", "from": "sans", "to": "PC"}],
 "fix": [{"at": "P06", "from": "LIA", "to": "L'IA"}],
 "story": [
  {"at": "P10", "role": "problème (démo)", "sens": "« regarde ça » = une clé API en clair dans le code", "voir": "le code fautif", "illu": "scene code, ligne de la clé en rouge"},
  {"at": "P12", "role": "étape", "sens": "le CSS habille le site : couleurs, Flexbox ; puis il doit marcher sur mobile", "voir": "une page brute qui se colore, se range, passe en téléphone", "illu": "site : color, flex, mobile"},
  {"at": "P11", "role": "transition", "sens": "et c'est courant", "voir": "visage", "illu": "non"}],
 "events": [
  {"fx": "hook", "t": 0, "text": "Ce que l'IA laisse *traîner* dans ton code"},
  {"at": "P10", "word": "regarde", "fx": "scene", "kind": "code", "title": "config.js",
   "lines": ["const API_KEY = \"sk-live-…\";"], "highlight": {"line": 0, "color": "red", "note": "Clé visible par tous"}},
  {"at": "P12", "word": "CSS", "fx": "site", "label": "2 · CSS", "steps": [
    {"word": "couleurs", "do": "color"}, {"word": "Flexbox", "do": "flex"}, {"at": "P13", "word": "mobile", "do": "mobile", "label": "3 · Responsive"}]},
  {"at": "P15", "word": "framework", "fx": "list", "title": "Un framework", "items": [
    {"word": "plusieurs", "text": "Vue", "logo": "vuedotjs"}, {"word": "React", "text": "*React*", "logo": "react"}]},
  {"at": "P17", "word": "abonne", "fx": "cta", "text": "*Abonne-toi* pour la suite", "target": "follow"}]}
```
- `at` = id de phrase (stable entre deux `prepare`), `word` = mot déclencheur (début du mot ; `"n": 2` = 2e occurrence). Options d'un effet : `"dur"` (s), `"sfx": "none"` ou `"ui/ding"`, `"burst": true` (éclaboussure : card, check, cross, emoji, stat, number ; 2-3 par vidéo au plus).
- `trim` : retire du mot `from` au mot `to` inclus, à une articulation naturelle. `fix` : corrige le texte affiché (pas le son).
- Hook : `head`, `intro`, `cold_open`, `hook_punch`, `hook_shake`, `hook_glitch`, `hook_sfx`, `variants` sur demande (voir « Hook »).
- `steps` (scene code, site) : `[{at?, word, n?, …}]`, chaque étape part sur son mot ; sans `dur`, l'effet reste 2 s après la dernière.
- Globales : `platform`, `theme` (`light` défaut, `glass`), `accent`, `captions: false`, `cut_zoom: 1.0` (sans zoom alterné), `tail` (s après le dernier mot, 0.4), `mirror` (`true` ou `["P62"]`), `sfx_volume_db` (décalage, -3 = plus discret).

| fx | usage | params |
|---|---|---|
| hook | accroche dès la 1re image (= miniature), 5-10 mots, pas la 1re phrase | text (`*mots*` surlignés), t: 0, style (block / bold / tag / emoji), tag?, emoji?, dur? (3) |
| card | nom, idée clé | text, sub?, emoji? ou logo? |
| check / cross | avantage / erreur (2-4 mots) | text, emoji? ou logo? |
| stat | chiffre dit | value ("10 000 €", "87 %"), label? |
| emoji | émotion, objet | emoji : rocket, fire, idea, warning, check, cross, money, up, down, time, brain, thinking, mindblown, shock, wow, party, eyes, laptop, robot, question |
| list | énumération ; vidéo rétrécie en bas | title?, items [{at?, word, text, emoji? ou logo?}] (2-5 points) |
| scene | montrer ce qu'on ne voit pas ; vidéo rétrécie en bas | kind `code` (title, lines, steps [{word, line, note?, color? red}] = ligne surlignée quand elle est dite, ou highlight {line, color red/green, note}) · `terminal` (lines : [{cmd: true, text}, "sortie"]) · `chat` (messages [{from: user/ai, text}]) · `compare` (before / after {label, text}) ; dur? (3-4) |
| diagram | relations entre éléments ; vidéo rétrécie en bas, schéma sur plateau clair, cases qui apparaissent quand elles sont dites, liens qui se tracent, points qui voyagent | kind `flow` (A → B → C) · `hub` (1er item au centre) · `cycle` (boucle) · `tree` (1er item = racine) ; title?, items [{at?, word, text (1-3 mots), icon, tone? (pos / neg)}] (2-6) ; highlight? |
| screen | vrai site cité | url (précise, jamais inventée), mode? (split / full), focus?, scroll?, strike? (barré en rouge), dur? (4) |
| number / percent | LE chiffre clé (1 par vidéo) | value, label? |
| chart | comparaison chiffrée dite (≥ 2 valeurs) | kind (bar / line), data [{label, value}], unit?, title? |
| title | nouvelle partie, idée centrale (1-3 par vidéo) | text (2-6 mots), sub?, logo? |
| site | maquette de site qui se transforme sur la parole ; vidéo rétrécie en bas. Part du HTML brut (police par défaut, liens bleus) | steps [{at?, word, do, label?}] ; do : `color` (couleurs, le titre change de teinte), `font` (police, titre plus grand), `flex` (blocs en ligne), `grid` (grille), `mobile` / `desktop` (format téléphone), `menu` (menu qui s'ouvre), `form` (formulaire rempli puis envoyé), `click` (clic + « Merci ! »), `anim` (blocs qui bougent) ; start? (actions déjà faites, ex `["color", "font", "flex"]`), label? (étiquette d'étape dans la barre), title? (adresse), heading?, button?, dur? |
| timer | compte à rebours annoncé (« j'ai une minute ») ; reste dans le coin haut gauche jusqu'à la fin, rouge sur les 10 dernières s | from (s, 60) |
| splash | transition liquide entre deux parties (1-2 par vidéo) | text?, sub? |
| blob | mot fort sur une forme liquide | text (1-4 mots) |
| cta | abonne-toi, commente, enregistre (4-5 mots) ; flèche vers le bouton du réseau | text, target (follow / like / comment / save / share / description) |
| zoom | 2-3 vraies phrases choc par vidéo | scale? (1.15) |
| highlight | mot fort dans les sous-titres | - |

**Icônes des schémas** (`icon`, au trait, jamais d'emoji dans un schéma) : user, users, agent, code, file, gear, search, scissors, zoom, text, shield, target, link, flow, check, cross, warning, clock, bulb, rocket, lock, key, bug, chat, bell, up, down, money, eye, fire, star, heart, plus, arrow, video. `tone` : `pos` (vert) pour ce qui est positif / la bonne voie, `neg` (rouge) pour le négatif / ce qu'on évite ; sans ton, neutre.

## Règles
- **Une info = une fois** ; reprises ratées, apartés `[murmuré]` et « c'est bon », « je vais essayer » toujours coupés. La vidéo commence par l'accroche.
- **Rythme** : un effet du haut toutes les 2,5 s au plus ; un élément du haut chasse le précédent. Alterne les types (pas trois ✓ d'affilée).
- **Chiffres** : uniquement ceux dits dans la vidéo (ou donnés par l'utilisateur), jamais inventés.
- **Textes** courts, reformulés, majuscule au début ; 1 ou 2 mots surlignés (`*mot*`) au plus. `cta` : « commente » → comment, « en description » → description, « lien en bio » → follow.
- **Captures de site** : seulement si la page illustre vraiment ce qui est dit ; 1-2 par vidéo ; si tu ne connais pas l'adresse exacte, n'en mets pas.
- **Son de révélation** : `"sfx": "reveal"` sur l'effet qui présente LA solution ou la leçon à retenir (le « donc… », le secret, la règle) : une montée de cymbale qui culmine pile à cet instant. 1 ou 2 par vidéo au plus, jamais sur une simple info.
- Les sons d'impact (boom, hit) gardent toute leur résonance ; les autres sont coupés à la durée de leur animation.
- Le code gère seul : la synchro des sons (chacun tombe sur l'instant fort de son animation : trait qui finit de barrer, compteur qui s'arrête, éclaboussure ; l'attaque réelle de chaque fichier est mesurée) et leur durée (chaque son est coupé avec un fondu à la durée de son animation : `SFX_LEN` dans pipeline.py), espacement des zooms, niveau des sons (et leur durée, ex. le clavier calé sur la frappe), bruit de compteur des chiffres, zones de l'interface. Ne précise un son que pour le changer.

## Maintenance (pas pendant un montage)
- Ajouter un effet : fonction dans `engine/effects.js` + entrée dans `engine/effects.json`. Zones des réseaux : `PLATFORMS` dans `scripts/pipeline.py`.
- Suggestions auto : `triggers.json`. Sons : `library/sfx/` puis `scripts/index_library.py --check` (licences). Emojis : `library/emoji/` (Fluent UI Emoji, MIT, voir CREDITS.md).
