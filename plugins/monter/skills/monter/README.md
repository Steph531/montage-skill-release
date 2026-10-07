# /monter : le montage de tes vidéos face caméra par Claude

Tu filmes, Claude monte. Ce skill pour [Claude Code](https://claude.com/claude-code) transforme un rush face caméra (TikTok, Reels, Shorts) en vidéo prête à publier :

- **Dérushage** : prises ratées, blancs, bégaiements et répétitions coupés ; il ne garde que la meilleure version de chaque phrase.
- **Sous-titres** mot par mot, avec le mot prononcé surligné au marqueur.
- **Montrer plutôt qu'écrire** : ce que tu décris s'anime à l'écran (maquette de site qui se transforme, code qui s'allume ligne par ligne, conversation avec une IA, vrais logos des outils cités), synchronisé sur tes mots.
- **Accroche des 3 premières secondes** : texte, visuel et voix (variantes à tester sur demande).
- **Habillage selon ce que tu dis** : chiffres animés, listes, schémas, scènes illustrées (code, terminal, conversation avec une IA), captures de sites, appels à l'action qui pointent vers le vrai bouton de l'appli.
- **Sons synchronisés** sur chaque animation, à un volume calé sous ta voix.

Tout tourne sur ton ordinateur : ta vidéo n'est envoyée nulle part.

> **Rejoins les Builders sur [stephenbuild.fr](https://stephenbuild.fr/#rejoindre)** : un mail à chaque nouvelle version du skill et à chaque nouvel outil, et l'accès à toute la bibliothèque. Il suffit de ton mail.

---

## Installation

Il te faut seulement [Claude Code](https://claude.com/claude-code). Deux façons d'installer, au choix.

### Option 1 : depuis le marketplace (recommandé)

Dans Claude Code, tape ces deux commandes :

```
/plugin marketplace add Steph531/montage-skill-release
/plugin install monter@montage-skill
```

Redémarre Claude Code : la commande `/monter` est disponible dans tous tes projets (si un autre skill porte le même nom, elle s'appelle `/monter:monter`).

**Mise à jour** : `/plugin marketplace update montage-skill`, ou active la mise à jour automatique dans `/plugin`. Tes montages ne sont pas touchés.

### Option 2 : avec le zip

1. Télécharge [monter.zip](https://github.com/Steph531/montage-skill-release/releases/latest/download/monter.zip) (par exemple dans Téléchargements).
2. Ouvre Claude Code n'importe où et colle cette phrase (adapte le chemin si le zip est ailleurs) :

   > Installe le skill monter depuis le fichier ~/Downloads/monter.zip dans mon dossier de skills personnels (~/.claude/skills/monter), puis vérifie que tout est prêt.

3. Redémarre Claude Code. La commande `/monter` est disponible dans tous tes projets : le skill ne s'installe pas dans un projet, mais une fois pour toutes sur ta machine.

**Mise à jour** : télécharge le nouveau `monter.zip` et colle « Mets à jour le skill monter avec le fichier ~/Downloads/monter.zip ». Tes montages ne sont pas touchés.

<details>
<summary>Installation à la main (optionnel)</summary>

Dézippe `monter.zip` : tu obtiens un dossier `monter`. Place-le dans `~/.claude/skills/` (macOS / Linux) ou `%USERPROFILE%\.claude\skills\` (Windows). Crée le dossier `skills` s'il n'existe pas.
</details>

Pour la suite, tu n'as aucune commande à taper : au premier `/monter`, Claude vérifie ta machine et installe lui-même ce qui manque.

| Élément | À quoi il sert | Comment il s'installe |
|---|---|---|
| Modules Python | transcription, détection du visage | automatiquement |
| ffmpeg | découpe et assemblage de la vidéo | Claude te dit ce qu'il installe et attend ton « oui » |
| Node.js 22+ | rendu des animations | idem, dans le même « oui » |
| Modèle de transcription, navigateur de rendu | — | téléchargés automatiquement, une seule fois (quelques minutes) |

- Claude utilise le gestionnaire de paquets de ta machine : `brew` sur Mac, `winget` sur Windows, `apt`, `dnf` ou `pacman` sous Linux.
- Rien ne s'installe sans ton accord : tu réponds « oui » une seule fois pour ffmpeg et Node.js.
- Si Python n'est pas installé (surtout sous Windows), Claude te propose de l'installer aussi.
- Sur un Mac sans Homebrew, ou si l'installation automatique échoue, Claude te donne le lien de téléchargement à utiliser.
- Pour revérifier plus tard, dis simplement à Claude « vérifie que tout est installé ».

---

## Utilisation

Ouvre Claude Code dans le dossier où tu veux tes montages, puis tape :

```
/monter ma_video.mp4
```

Claude te demande pour quel réseau est la vidéo, puis il fait tout le reste. Tu peux aussi le préciser directement :

```
/monter ma_video.mp4 tiktok        # ou reels, shorts, all (plusieurs réseaux)
/monter ma_video.mp4 auto          # montage rapide, sans relecture du sens (moins soigné)
/monter tout le dossier ~/Videos/a_monter, mets les vidéos finies dans un dossier output
```

**Ce que tu obtiens** : `output/<nom>_monte.mp4`, la vidéo montée, dans un dossier `output/` créé là où tu lances le montage. Les fichiers de travail (transcription, plan, planche de contrôle `sheet.jpg`) restent dans un dossier caché `.montage/<nom>/` pour les retouches : environ 1 Mo par vidéo, supprimés automatiquement au bout de 30 jours ou si tu supprimes le rush.

Compte quelques minutes par vidéo. Le rendu se fait sur ta machine.

### Demander des retouches

Parle à Claude normalement, il modifie le montage et refait le rendu :

- « Le mot "abonnement" est coupé à 0:12 »
- « Enlève la phrase sur mon accent »
- « Il y a encore une répétition sur "sans abonnement" »
- « Le son du glitch est trop long » / « Les sons sont trop forts »
- « Mets la vidéo en miroir » (si tu as oublié le mode miroir de ta caméra)
- « Ajoute la page de captionbuild.com quand je parle de mon outil »
- « Je publie seulement sur Reels » (refait les rendus avec les zones de l'interface Reels)

---

## Bien filmer pour un bon montage

- **Refais tes phrases autant que tu veux** : le skill garde automatiquement la dernière prise réussie de chaque phrase. Inutile de couper entre deux essais.
- **Une idée par phrase, des phrases complètes** : plus c'est clair à l'oral, mieux le skill choisit les illustrations.
- **Dis tes chiffres et tes sources à voix haute** (« selon Stanford, 20 % de… ») : le skill n'affiche que des chiffres réellement dits.
- **Geste d'accroche** : si tu ouvres par un geste (main sur l'objectif, entrée dans le cadre), fais-le vite. Le skill démarre la vidéo sur le moment fort du geste.
- **Laisse le haut de l'écran respirer** : c'est là que s'affichent les textes et les animations.
- Tu as un **script prévu** (accroche, plan ET / MAIS / DONC) ? Donne-le à Claude avec la vidéo : il s'en sert pour les accroches et les illustrations.

---

## Personnaliser

Dis-le simplement à Claude, par exemple :
- « Utilise ma couleur #FF5A1F à la place du jaune »
- « Cartes sombres plutôt que blanches » (thème `glass`)
- « Fais-moi 2 variantes de l'accroche » / « Pas de sous-titres »

Pour aller plus loin (nouveaux effets, sons, zones des réseaux), voir la section « Maintenance » de [SKILL.md](SKILL.md).

---

## Problèmes fréquents

| Problème | Solution |
|---|---|
| « ffmpeg introuvable » / « Node 22+ requis » | Dis à Claude « installe ce qui manque » : il relance le diagnostic et l'installation |
| Le rendu « s'est figé » | La machine est surchargée : ferme les autres rendus ou les applis gourmandes, puis relance |
| Un mot coupé, une phrase en trop | Dis-le à Claude avec le moment (« vers 0:12 ») : il retranscrit le montage et corrige |
| Un texte mal transcrit (nom propre, jargon) | « Écris "Caption Build" et pas "CaptionBuild" » |
| Une capture de site affiche un bandeau cookies ou une page de connexion | Demande une autre page, ou de retirer la capture |

---

## Crédits et licences

Sons (CC0, freesound.org), emojis 3D (Fluent UI Emoji, Microsoft, MIT), polices (SIL OFL), GSAP, HyperFrames : le détail est dans [CREDITS.md](CREDITS.md). Garde ce fichier et `library/emoji/LICENSE-fluentui-emoji.txt` si tu redistribues le skill.
