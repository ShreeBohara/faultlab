# FaultLab architecture

![FaultLab system and feedback loop: the adapter applies recovery rules to an agent using mock shop APIs. Weave supplies execution evidence and a fixed Referee supplies verdicts to FaultLab. Explorer selects faults, Mechanic proposes repairs, and fixed code runs trials and checks promotion. Outputs include recovery rules, regression bundles, a dashboard and advisory Aria analysis. Only accepted rules return to the adapter for later runs.](assets/faultlab-architecture.png)

[Download the LinkedIn graphic](assets/faultlab-architecture.png) · [Original presentation](presentation.pdf)

The assistant upgrades one simulated order and sends a truthful confirmation. Explorer selects faults such as delayed completion or lost responses. Fresh trials reproduce and simplify a failure, then controlled experiments test its cause. Mechanic proposes finite recovery rules, which are tested around the assistant's tool calls through the policy interpreter.

The large return loop shows how accepted rules can reach the adapter for later runs. The smaller feedback loop returns challenge failures to repair development. Explorer selects fault experiments for the mock APIs; the fixed Referee checks actual effects and the original report. The model cannot assign its own passing score. Acceptance requires every declared gate to pass.

W&B Inference supplies the models. Weave records execution traces. Aria provides advisory campaign analysis; it does not alter policies or scores. The dashboard reads saved experiment records.

## Recorded status

In recorded campaign `campaign-44085f54a24144b78252d8eea211ebb8`, one candidate passed a three-pair source-validation batch, then failed a harder challenge. The same policy was inconsistent across other batches. No learned repair was accepted. See [learning results](learning-results.md) and [sponsor results](sponsor-results.md) for evidence and limitations.

## Visual production

Created with the built-in image-generation tool using the original presentation as the visual reference. The requested style is a dark background, restrained purple accents, simple icons, a highlighted FaultLab panel, and an explicit whole-system feedback loop. Component icons are illustrations, not official sponsor logos. The diagram describes the architecture, including conditional output paths; it does not claim that policy acceptance or every downstream study has been demonstrated live.
