# Crédits

Tous les sons de `library/sfx/` proviennent de [freesound.org](https://freesound.org) sous licence **CC0 1.0** (domaine public) :
aucune attribution n'est requise et ils peuvent être redistribués et utilisés commercialement.
Ils ont été recoupés, convertis en WAV 48 kHz et normalisés.

Le détail par fichier (source, licence, rôle, intensité) est dans `library/manifest.json`.

Si tu ajoutes tes propres sons : renseigne `license` (CC0 / OWN / CC-BY) puis lance
`python scripts/index_library.py --check`. Les sons CC-BY exigent auteur + URL ici ; ceux en CC-BY-NC
ne doivent pas être redistribués avec le skill.

## Moteur d'animations (`engine/`)
- **GSAP 3.14** (`engine/vendor/gsap.min.js`) : GreenSock, licence standard GSAP (gratuite, usage commercial compris) - https://gsap.com/standard-license
- **Montserrat** (`engine/fonts/montserrat-*.woff2`) : Julieta Ulanovsky et al., SIL Open Font License 1.1
- **Noto Color Emoji** (`engine/fonts/noto-color-emoji.woff2`) : Google, SIL Open Font License 1.1
- Rendu : **HyperFrames** (HeyGen, Apache 2.0), téléchargé via npx au premier rendu.

## Emojis (`library/emoji/`)
- **Fluent UI Emoji** (version 3D), Microsoft Corporation, licence **MIT** - https://github.com/microsoft/fluentui-emoji
  20 emojis copiés tels quels (renommés : `rocket`, `fire`, `idea`, `warning`, `check`, `cross`, `money`, `up`, `down`, `time`,
  `brain`, `thinking`, `mindblown`, `shock`, `wow`, `party`, `eyes`, `laptop`, `robot`, `question`).
  La notice de licence MIT est jointe : `library/emoji/LICENSE-fluentui-emoji.txt` (à garder si tu redistribues le skill).

## Logos
Les logos de marques (paramètre `logo`) sont téléchargés à la demande depuis [Simple Icons](https://simpleicons.org) (SVG sous licence CC0) et mis en cache dans `library/logos/` (non versionné). Les marques et logos restent la propriété de leurs titulaires : ils servent uniquement à désigner le produit cité dans la vidéo.
