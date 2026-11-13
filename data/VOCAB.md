# Signer vocabulary (frozen in M0.4)

24 signs plus the `REST` class. `GLOSS` is the class label used everywhere (model, events, landmark files).
`english` is the display text. `popsign_name` is PopSign ASL v1.0's exact sign name (its directory and tar name);
`-` means PopSign has no such sign and the team records it ourselves with `core/tools/record.py`.

| GLOSS | english | source (popsign/own) | popsign_name |
|---|---|---|---|
| HELLO | hello | popsign | hello |
| BYE | bye | popsign | bye |
| YES | yes | popsign | yes |
| NO | no | popsign | no |
| PLEASE | please | popsign | please |
| THANKYOU | thank you | popsign | thankyou |
| WAIT | wait | popsign | wait |
| FINISH | finished | popsign | finish |
| POTTY | bathroom | popsign | potty |
| WATER | water | popsign | water |
| WHERE | where | popsign | where |
| WHY | why | popsign | why |
| WHO | who | popsign | who |
| TIME | time | popsign | time |
| BOOK | book | popsign | book |
| LISTEN | listen | popsign | listen |
| TALK | talk | popsign | talk |
| HOME | home | popsign | home |
| SICK | sick | popsign | sick |
| HAPPY | happy | popsign | happy |
| HELP | help | own | - |
| QUESTION | question | own | - |
| UNDERSTAND | understand | own | - |
| AGAIN | again | own | - |
| REST | (rest) | own | - |

## Notes

- **Why these signs.** The target is a deaf signer talking to a hearing person in a classroom or an everyday
  exchange: greet, ask (WHERE, WHY, WHO, TIME, QUESTION), request (PLEASE, HELP, WATER, POTTY), react (YES, NO,
  UNDERSTAND, AGAIN, WAIT, FINISH, SICK, HAPPY), close (THANKYOU, BYE). BOOK, LISTEN, TALK and HOME give nouns and
  verbs for "where is the book" or "I'll listen". Together they form real short sentences, e.g. HELLO QUESTION,
  WHERE BOOK, PLEASE WAIT, HELP, THANKYOU BYE.
- **Visually distinct.** No near-duplicate pairs (PEN/PENCIL, SLEEP/SLEEPY, MAD/SAD, OPEN/CLOSE, LATER/TOMORROW
  were avoided). Pairs that still share a body area or motion (e.g. HELLO/BYE, WATER/THANKYOU near the chin) are
  the likeliest confusions; M1 reports per-class accuracy so we can see them. Visual choices are from our reading
  of the sign list, not yet checked against clips.
- **Own signs.** HELP, QUESTION, UNDERSTAND and AGAIN are not among PopSign's 250 signs. The team records them
  (`core/tools/record.py`), 5+ signers where possible. `PAPER` (used as an alternative in
  `contracts/events.example.jsonl`) is in neither set and is only mock data.
- **REST** is the "no sign" class: hands down, idle, transitions. It is recorded by the team and is never in PopSign.
- **Credit.** PopSign ASL v1.0, Georgia Tech / Deaf Professional Arts Network (Thad Starner et al.), licensed
  CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), https://signdata.cc.gatech.edu. Only landmarks derived
  from the videos are kept. The deck and README credit it.
