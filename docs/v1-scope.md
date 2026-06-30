# Scope V1 - Assistant d'explication de facture operateur

## Contexte

L'application vise en priorite les utilisateurs finaux de l'operateur dans la
comprehension des ecarts de facturation telecom.

Elle doit pouvoir etre activee par telephone ou via un chat vocal sur une page
web. Le parcours Voice2Voice est obligatoire en V1 : l'utilisateur doit pouvoir
poser sa question oralement et recevoir une reponse orale. Cela n'empeche pas
de proposer aussi une sollicitation par ecrit lorsque le canal le permet.

La V1 aura acces en lecture aux donnees du BSS de l'operateur. Le BSS constitue
la source de verite pour les factures, contrats, offres, options, remises,
consommations, evenements de billing, regularisations, paiements et changements
de situation client.

## Objectif produit V1

Permettre a un utilisateur final d'interroger le bot, principalement par la
voix, pour comprendre pourquoi une facture ou une periode de facturation differe
d'une autre.

Le bot doit s'appuyer sur l'identite et le contexte client fournis par le canal
d'activation ou par le BSS, recuperer les donnees pertinentes, comparer les
factures ou periodes concernees, puis restituer une explication fiable,
detaillee et tracable des differences de prix.

Question cible :

> Pourquoi la facture de juin est-elle plus chere que celle de mai ?

Reponse attendue :

> La facture augmente de 18,40 EUR. Cette hausse vient principalement de
> l'expiration d'une remise de 10 EUR, d'un hors-forfait data de 6,90 EUR, et
> d'un prorata de 1,50 EUR lie a l'activation d'une option le 14 juin.

## Principe cle

Le LLM ne doit pas deviner les causes.

Le systeme doit d'abord calculer les ecarts de maniere deterministe a partir
des donnees BSS, puis utiliser l'IA pour formuler une explication claire,
pedagogique et contextualisee.

La base de connaissance sert a expliquer les regles metier et tarifaires. Elle
ne doit pas etre utilisee pour inventer des montants ou compenser l'absence de
donnees BSS.

## Perimetre fonctionnel V1

### Acces aux donnees BSS

L'application doit pouvoir recuperer, pour un client donne :

- les factures disponibles ;
- les lignes de facture detaillees ;
- les contrats et abonnements actifs sur les periodes comparees ;
- les offres, options et services factures ;
- les remises commerciales et leur periode de validite ;
- les consommations facturees ou hors forfait ;
- les taxes, frais ponctuels, regularisations et proratas ;
- les evenements de billing importants : changement d'offre, activation
d'option, resiliation, remise expiree, geste commercial.

### Comparaison de factures

L'application doit comparer deux factures ou deux periodes et identifier :

- les lignes apparues ;
- les lignes disparues ;
- les lignes dont le montant a change ;
- les variations de consommation ;
- les remises expirees ou modifiees ;
- les frais ponctuels ;
- les regularisations ;
- les changements d'offre ou d'option ;
- les ecarts de taxes ou proratas.

Le resultat attendu n'est pas seulement un diff technique. Il doit produire une
analyse causale orientee metier.

### Explication des ecarts

L'assistant doit transformer les ecarts detectes en explication comprehensible.

L'explication doit :

- commencer par le delta global ;
- lister les principales causes par impact decroissant ;
- distinguer les causes certaines des causes probables ;
- citer les elements BSS utilises comme preuves ;
- expliquer les regles tarifaires si necessaire ;
- eviter toute conclusion non justifiee par les donnees disponibles.

### Interaction utilisateur

En V1, l'utilisateur final doit pouvoir :

- appeler le bot par telephone ;
- utiliser un chat vocal depuis une page web ;
- poser une question oralement sur une facture ou un ecart de prix ;
- recevoir une reponse orale claire et explicable ;
- utiliser l'ecrit comme canal complementaire lorsque l'interface le permet ;
- consulter une synthese des ecarts sur la page web ;
- consulter le detail ligne par ligne lorsque l'interface web est disponible ;
- obtenir les preuves BSS associees a l'explication.

Le coeur de valeur V1 est l'explication de facture basee sur les donnees BSS,
delivree en Voice2Voice sur les canaux telephone et web vocal.

### Escalade vers un agent humain

Le bot doit pouvoir transferer la conversation vers un agent humain dans deux
cas :

- le client demande explicitement a parler a un conseiller ;
- le bot ne peut pas repondre avec un niveau de certitude suffisant, par
  exemple donnees BSS manquantes, incoherentes, ou absence de preuve permettant
  d'expliquer l'ecart.

Dans ce cas, le bot doit annoncer clairement la limite rencontree, resumer le
contexte deja collecte et transmettre les elements utiles a l'agent humain pour
eviter au client de repeter toute sa demande.

## Besoins non fonctionnels

### Fiabilite

Chaque explication doit etre rattachee a des donnees BSS precises.

Si une donnee manque, l'assistant doit le dire explicitement plutot que
produire une hypothese non verifiable.

### Tracabilite

Chaque cause d'ecart doit pouvoir etre reliee a :

- une ligne de facture ;
- un evenement BSS ;
- une regle tarifaire ;
- une consommation ;
- une remise ;
- une modification contractuelle.

### Securite

L'acces au BSS implique des donnees sensibles. La V1 doit prevoir :

- authentification forte ;
- controle d'acces par role ;
- journalisation des consultations ;
- masquage des donnees personnelles non necessaires ;
- absence de donnees personnelles sensibles dans les logs applicatifs ;
- acces BSS en lecture seule.

### Performance

La comparaison doit etre suffisamment rapide pour un usage conversationnel par
un utilisateur final.

Objectif recommande : resultat de comparaison initial en moins de quelques
secondes sur une facture standard.

La cible `first audio < 700 ms` est un critere obligatoire pour l'experience
Voice2Voice. Elle ne doit toutefois pas conduire a produire une explication non
fiable : si l'analyse metier necessite plus de temps, le bot doit pouvoir
produire un accuse de reception oral rapide, puis livrer l'explication fiable
quand les preuves BSS sont disponibles.

### Exigences techniques structurantes V1

Certains items du backlog deviennent des pre-requis directs du scope V1, car
ils conditionnent l'experience Voice2Voice, l'omnicanal et l'exploitation en
cloud prive.

La V1 doit donc prevoir :

- STT streaming reel et detection de fin de tour cote serveur pour eviter de
  dependre uniquement du VAD navigateur, notamment sur le canal telephone ;
- TTS streaming chunke et connexion TTS persistante pour demarrer la reponse
  orale sans attendre la generation audio complete ;
- etat conversationnel partage, par exemple Redis, pour permettre les parcours
  omnicanaux et le scale-out du backend ;
- memoire conversationnelle persistante pour reprendre une session et fournir
  le contexte utile en cas de transfert vers un agent humain ;
- cache semantique pour les questions frequentes et les explications tarifaires
  recurrentes, sans contourner la verification des preuves BSS ;
- observabilite par span sur tout le pipeline : STT, recuperation BSS,
  comparaison, recherche KB, LLM first-token, TTS first-audio et transfert agent
  humain ;
- co-localisation en cloud prive des composants critiques du chemin vocal
  lorsque la cible `first audio < 700 ms` doit etre tenue en production ;
- connecteurs KB supplementaires, notamment PDF, Confluence ou base de donnees,
  pour enrichir les regles tarifaires et les contenus d'explication.

Ces exigences doivent rester reliees au backlog pour le decoupage en epics et
user stories. Le scope V1 indique pourquoi elles sont necessaires ; le backlog
porte le detail d'execution et les priorites.

### Agnosticite des fournisseurs IA et voix

Le coeur produit doit rester agnostique des fournisseurs et modeles utilises
pour le LLM, le STT et le TTS.

Les services metier ne doivent pas dependre directement d'un fournisseur
particulier, ni d'un SDK specifique. Les capacites suivantes doivent etre
exposees via des ports applicatifs :

- generation ou reformulation par LLM ;
- transcription speech-to-text ;
- synthese text-to-speech ;
- embeddings et recherche vectorielle si necessaire.

Les implementations concretes peuvent varier selon l'environnement : solution
cloud, solution self-hosted en cloud prive, modele local, ou fournisseur
manage. Le changement de fournisseur ne doit pas remettre en cause le modele
metier billing, le moteur de comparaison, ni le contrat fonctionnel du bot.

Pour demarrer le POC/V1, les adapters vocaux de reference seront bases sur
Gradium pour les capacites STT/TTS et sur Pipecat pour l'orchestration temps
reel du pipeline vocal. Ces choix servent de point de depart operationnel et de
base de benchmark, sans fermer la possibilite de tester ou remplacer ces
solutions ensuite.

Cette agnosticite doit aussi permettre de tester facilement plusieurs solutions
LLM, STT ou TTS pendant les phases de POC, benchmark et industrialisation. Le
choix d'une implementation doit pouvoir se faire par configuration ou par
remplacement d'adapter, sans modifier le coeur metier ni les parcours
utilisateur.

## Hors perimetre V1

- Modifier une facture.
- Corriger automatiquement une erreur de billing.
- Declencher un geste commercial.
- Emettre une nouvelle facture.
- Faire du recouvrement.
- Remplacer le systeme BSS.
- Donner une reponse sans preuve lorsque les donnees sont absentes.

## Criteres de succes V1

La V1 sera consideree utile si elle permet de repondre correctement a ces cas :

- Appel telephone : l'utilisateur demande oralement pourquoi sa facture a
  augmente et recoit une reponse orale.
- Chat vocal web : l'utilisateur pose la meme question depuis une page web et
  recoit une reponse orale, avec un resume affiche.
- Pourquoi ma facture a augmente ce mois-ci ?
- Quelle ligne explique la difference principale ?
- Est-ce du a une remise expiree ?
- Est-ce du a du hors forfait ?
- Y a-t-il eu un changement d'offre ou d'option ?
- Peux-tu me resumer l'explication pour un client ?
- Peux-tu me montrer les preuves dans la facture ou le BSS ?
- Je veux parler a un conseiller.
- Le bot transfere vers un agent humain lorsqu'il ne peut pas expliquer l'ecart
  avec assez de certitude.

## Formulation synthetique du besoin

Construire un assistant vocal d'analyse de facturation operateur, cible
utilisateurs finaux, accessible par telephone et par chat vocal web, connecte en
lecture au BSS, capable de comparer deux factures ou periodes client,
d'identifier les causes metier des ecarts de prix, puis de produire une
explication orale claire, fiable et tracable, fondee sur les donnees BSS et
enrichie par la base de connaissance tarifaire.

## Decoupage pressenti

Une fois ce scope valide, le decoupage peut etre organise autour des epics
suivantes :

- Connecteur BSS lecture seule.
- Modele domaine billing : facture, contrat, offre, consommation.
- Moteur de comparaison de factures.
- Moteur d'explication avec preuves BSS.
- Parcours Voice2Voice telephone.
- Parcours Voice2Voice web.
- Interface web de synthese et preuves.
- Securite, audit et gouvernance des acces BSS.
- Abstractions LLM / STT / TTS et contraintes de latence.

